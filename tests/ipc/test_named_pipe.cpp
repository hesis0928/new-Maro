#include <gtest/gtest.h>

#include <atomic>
#include <chrono>
#include <thread>

#include "maro_ipc/NamedPipe.h"

namespace {

std::string uniquePipeName(const char* suffix) {
    return "\\\\.\\pipe\\maro_ipc_test_" + std::string(suffix) + "_" +
           std::to_string(::GetCurrentProcessId());
}

// gtest의 ASSERT_*는 실패하면 그 함수에서 즉시 return한다 -- 그 자리에서
// serverThread.join()을 건너뛰면 joinable한 std::thread가 그대로 소멸하면서
// std::terminate가 돌아 프로세스 전체가 죽는다(실패 하나가 나머지 테스트를
// 통째로 날린다). 실측: 200회 반복 중 아래 hello 테스트가 한 번 실패했을 때
// 스위트가 그 자리에서 exit code 3으로 끝났다. 조인을 스코프 종료에 묶어
// 실패해도 "그 테스트만" 실패하게 만든다.
struct ThreadJoiner {
    std::thread& thread;
    ~ThreadJoiner() {
        if (thread.joinable()) thread.join();
    }
};

// 서버를 별도 스레드에서 띄우고 메인 스레드가 클라이언트로 접속한다 --
// 명명된 파이프는 스레드 경계와 무관하게 동작하므로 별도 프로세스 없이도
// 실제 파이프 I/O를 검증할 수 있다.
TEST(NamedPipe, ClientAndServerExchangeHello) {
    const std::string name = uniquePipeName("hello");
    std::atomic<bool> serverGotHello{false};
    std::atomic<bool> serverSentBack{false};

    std::thread serverThread([&]() {
        maro::ipc::NamedPipeServer server(name);
        ASSERT_TRUE(server.waitForConnection(2000));

        maro::ipc::Message received;
        ASSERT_TRUE(server.receiveMessage(received, 2000));
        serverGotHello = (received.type == maro::ipc::MessageType::Hello);

        maro::ipc::Message reply;
        reply.type = maro::ipc::MessageType::Hello;
        serverSentBack = server.sendMessage(reply);

        // 답장을 보내자마자 close()를 부르면 안 된다: close()의
        // DisconnectNamedPipe는 상대가 아직 안 읽은 데이터를 버린다(MSDN).
        // 실측으로 브리프 원본은 200회 반복 중 86회째에 클라이언트의
        // receiveMessage가 false로 떨어졌다 -- 답장이 읽히기 전에 서버가
        // 문을 닫은 것이다. 그래서 서버는 상대가 파이프를 닫을 때까지
        // (=답장을 다 읽고 나갈 때까지) 기다린 뒤 닫는다. 이 대기는 감시자가
        // 실제로 하는 일과 같다: 다음 메시지를 기다리다가 끊김을 본다.
        maro::ipc::Message afterReply;
        server.receiveMessage(afterReply, 2000);
        server.close();
    });
    ThreadJoiner joiner{serverThread};

    // 서버가 CreateNamedPipeA를 부를 시간을 준다 -- 클라이언트의 connect가
    // 그 전에 오면 ERROR_FILE_NOT_FOUND로 실패한다. connect() 자체가
    // 짧은 재시도 루프를 갖는 이유가 이것이다(Step 3 구현 참고).
    maro::ipc::NamedPipeClient client;
    ASSERT_TRUE(client.connect(name, 2000));

    maro::ipc::Message hello;
    hello.type = maro::ipc::MessageType::Hello;
    ASSERT_TRUE(client.sendMessage(hello));

    maro::ipc::Message reply;
    ASSERT_TRUE(client.receiveMessage(reply, 2000));
    EXPECT_EQ(reply.type, maro::ipc::MessageType::Hello);

    client.close();
    serverThread.join();
    EXPECT_TRUE(serverGotHello);
    EXPECT_TRUE(serverSentBack);
}

// 크래시 신호의 핵심: 메시지 없이 클라이언트가 그냥 닫히면 서버의
// receiveMessage는 "메시지가 옴"이 아니라 "연결이 끊김"을 구분해서
// 돌려줘야 한다. 이 구분이 없으면 감시자가 정상/비정상을 가릴 수 없다.
TEST(NamedPipe, ServerDetectsDisconnectWithoutMessage) {
    const std::string name = uniquePipeName("disconnect");
    std::atomic<bool> disconnectDetected{false};
    std::atomic<long long> detectMs{-1};

    std::thread serverThread([&]() {
        maro::ipc::NamedPipeServer server(name);
        ASSERT_TRUE(server.waitForConnection(2000));

        maro::ipc::Message received;
        // 클라이언트가 아무 메시지도 안 보내고 닫으므로 이건 실패해야
        // 하고, 그 실패가 "메시지 없이 끊김"이어야 한다.
        const auto start = std::chrono::steady_clock::now();
        const bool got = server.receiveMessage(received, 2000);
        detectMs = std::chrono::duration_cast<std::chrono::milliseconds>(
                       std::chrono::steady_clock::now() - start)
                       .count();
        disconnectDetected = !got;
        server.close();
    });
    ThreadJoiner joiner{serverThread};

    {
        maro::ipc::NamedPipeClient client;
        ASSERT_TRUE(client.connect(name, 2000));
        client.close();  // 메시지 없이 바로 닫는다 -- SESSION_END_CLEAN이 아니다.
    }

    serverThread.join();
    EXPECT_TRUE(disconnectDetected);
    // "끊김"과 "아직 메시지가 안 옴"을 진짜로 구분하는지 보는 것은 이
    // 시간 조건이다. 끊김을 못 알아채고 그냥 기다리기만 하는 구현도
    // 결국 타임아웃으로 false를 돌려주므로 위의 EXPECT만으로는 통과해
    // 버린다 -- 그런 구현은 감시자가 크래시를 2초씩 늦게 아는 것이고,
    // 대기가 무한이면 영원히 모르는 것이다. 끊김은 즉시 보여야 한다.
    EXPECT_GE(detectMs.load(), 0);
    EXPECT_LT(detectMs.load(), 1000) << "끊김을 즉시 감지하지 못하고 타임아웃까지 기다렸다";
}

// 정상 종료 신호의 대칭 경로: 플러그인은 SessionEndClean을 보내고 곧바로
// 파이프를 닫는다(Task 8). 그 마지막 메시지가 닫힘과 함께 사라지면 감시자는
// 정상 종료를 크래시로 오판한다 -- 이 프로젝트가 존재하는 이유 자체가
// 뒤집힌다. 클라이언트 쪽 close()는 CloseHandle뿐이라(서버의
// DisconnectNamedPipe와 달리) 이미 파이프에 들어간 데이터를 버리지 않는다는
// 것을 고정해 둔다.
TEST(NamedPipe, ServerStillReadsFinalMessageSentJustBeforeClientCloses) {
    const std::string name = uniquePipeName("last_word");
    std::atomic<bool> gotSessionEnd{false};

    std::thread serverThread([&]() {
        maro::ipc::NamedPipeServer server(name);
        ASSERT_TRUE(server.waitForConnection(2000));

        maro::ipc::Message received;
        if (server.receiveMessage(received, 2000)) {
            gotSessionEnd = (received.type == maro::ipc::MessageType::SessionEndClean);
        }
        server.close();
    });
    ThreadJoiner joiner{serverThread};

    {
        maro::ipc::NamedPipeClient client;
        ASSERT_TRUE(client.connect(name, 2000));

        maro::ipc::Message bye;
        bye.type = maro::ipc::MessageType::SessionEndClean;
        ASSERT_TRUE(client.sendMessage(bye));
    }  // 보내자마자 닫는다 -- 서버가 읽기를 걸기 전일 수 있다.

    serverThread.join();
    EXPECT_TRUE(gotSessionEnd);
}

TEST(NamedPipe, ConnectFailsCleanlyWhenNoServerListening) {
    maro::ipc::NamedPipeClient client;
    EXPECT_FALSE(client.connect(uniquePipeName("nobody_home"), 200));
}

}  // namespace
