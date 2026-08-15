#include <iostream>
#include <thread>
#include <chrono>

// 윈도우 네트워크 통신(소켓) 헤더
#include <winsock2.h>
#pragma comment(lib, "ws2_32.lib")

// Maya 플러그인(Maro)과 연결할 공유 메모리 헤더
#include <boost/interprocess/windows_shared_memory.hpp>
#include <boost/interprocess/mapped_region.hpp>
#include "maro_library/IpcData.h"

using namespace boost::interprocess;

// 우분투에서 날아오는 네트워크 패킷 규격 (IpcData.h의 데이터와 동일한 크기)
// 네트워크 수신용이므로 std::atomic은 제외하고 원시 타입(uint64_t)으로 받습니다.
#pragma pack(push, 1)
struct UdpControlPacket {
    uint64_t command_index;
    bool has_transform;
    float position[3];
    float orientation[4];
};
#pragma pack(pop)

int main(int argc, char** argv) {
    std::cout << "=========================================" << std::endl;
    std::cout << " [Maro Control Bridge] Windows UDP Receiver" << std::endl;
    std::cout << "=========================================" << std::endl;

    // 1. 윈도우 네트워크(Winsock) 초기화
    WSADATA wsaData;
    if (WSAStartup(MAKEWORD(2, 2), &wsaData) != 0) {
        std::cerr << "Winsock 초기화 실패!" << std::endl;
        return 1;
    }

    // 2. UDP 소켓 생성
    SOCKET recvSocket = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    if (recvSocket == INVALID_SOCKET) {
        std::cerr << "소켓 생성 실패!" << std::endl;
        WSACleanup();
        return 1;
    }

    // 3. 포트 9090 바인딩
    sockaddr_in serverAddr;
    serverAddr.sin_family = AF_INET;
    serverAddr.sin_port = htons(9090);
    serverAddr.sin_addr.s_addr = INADDR_ANY;

    if (bind(recvSocket, (SOCKADDR*)&serverAddr, sizeof(serverAddr)) == SOCKET_ERROR) {
        std::cerr << "포트 9090 바인딩 실패!" << std::endl;
        closesocket(recvSocket);
        WSACleanup();
        return 1;
    }

    // 4. Maya가 생성해둔 공유 메모리 열기 (Maya 플러그인이 켜져 있어야 함)
    MaroPlugin::RobotControlData* shm_data = nullptr;
    try {
        windows_shared_memory shm(open_only, MaroPlugin::CTRL_SHM_NAME, read_write);
        mapped_region region(shm, read_write);
        shm_data = static_cast<MaroPlugin::RobotControlData*>(region.get_address());
        std::cout << "🚀 Maya 공유 메모리 연결 성공!" << std::endl;
    }
    catch (const interprocess_exception& e) {
        std::cerr << "공유 메모리 에러: " << e.what() << "\n(Maya에서 ViewportStreamer를 먼저 실행하세요.)" << std::endl;
        closesocket(recvSocket);
        WSACleanup();
        return 1;
    }

    std::cout << "통신 대기 중... (UDP Port: 9090)" << std::endl;

    // 5. 무한 루프 돌면서 데이터 수신 및 SHM 업데이트
    char buffer[sizeof(UdpControlPacket)];
    sockaddr_in clientAddr;
    int clientAddrLen = sizeof(clientAddr);

    while (true) {
        int bytesReceived = recvfrom(recvSocket, buffer, sizeof(UdpControlPacket), 0, (SOCKADDR*)&clientAddr, &clientAddrLen);

        if (bytesReceived == sizeof(UdpControlPacket)) {
            // 바이트 배열을 네트워크 패킷 구조체로 캐스팅
            UdpControlPacket* received_data = reinterpret_cast<UdpControlPacket*>(buffer);

            // 공유 메모리(SHM) 구조체에 데이터 밀어넣기
            shm_data->command_index.store(received_data->command_index);
            shm_data->has_transform = received_data->has_transform;

            for (int i = 0; i < 3; i++) shm_data->position[i] = received_data->position[i];
            for (int i = 0; i < 4; i++) shm_data->orientation[i] = received_data->orientation[i];

            std::cout << "[제어 수신] Index: " << received_data->command_index
                << " | X: " << received_data->position[0]
                << " | Y: " << received_data->position[1]
                << " | Z: " << received_data->position[2] << std::endl;
        }
        else if (bytesReceived == SOCKET_ERROR) {
            std::cerr << "수신 에러 발생!" << std::endl;
            break;
        }
    }

    closesocket(recvSocket);
    WSACleanup();
    return 0;
}