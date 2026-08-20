// 감시자(maro_sentinel.exe)를 띄울 때 사용자 화면에 콘솔 창이 뜨지 않는지
// 검증한다. 배경과 재현 조건은 ipc/console_window_probe.cpp 머리주석 참고 --
// 요점은 "콘솔이 없는 부모(= GUI 서브시스템인 Maya.exe)가 콘솔 프로그램을
// 자식으로 만들면 Windows가 새 콘솔 창을 띄운다"이고, gtest/mayapy는 둘 다
// 콘솔 프로그램이라 그 조건을 그냥은 재현하지 못한다는 것이다.
//
// 그래서 여기서는 프로브를 DETACHED_PROCESS로 띄워 "콘솔 없는 부모"를
// 인위적으로 만든 뒤, 그 안에서 maro_ipc의 진짜 spawn 함수를 호출하게 한다.
#include <gtest/gtest.h>

#include <windows.h>

#include <cstdio>
#include <cstdlib>
#include <string>

namespace {

std::string tempFilePath(const char* stem) {
    char tempDir[MAX_PATH] = {};
    const DWORD length = ::GetTempPathA(MAX_PATH, tempDir);
    EXPECT_GT(length, 0u);
    return std::string(tempDir) + "maro_" + stem + "_" +
           std::to_string(::GetCurrentProcessId()) + ".txt";
}

std::string readFileIfPresent(const std::string& path) {
    std::FILE* file = nullptr;
    if (::fopen_s(&file, path.c_str(), "rb") != 0 || file == nullptr) return {};
    char buffer[256] = {};
    const size_t read = std::fread(buffer, 1, sizeof(buffer) - 1, file);
    std::fclose(file);
    return std::string(buffer, read);
}

// 프로브가 남긴 한 줄에서 key=<정수>를 뽑는다. 값이 없거나 파싱이 안 되면 -1.
long long fieldValue(const std::string& report, const char* key) {
    const std::string needle = std::string(key) + "=";
    const auto position = report.find(needle);
    if (position == std::string::npos) return -1;
    return std::strtoll(report.c_str() + position + needle.size(), nullptr, 10);
}

// 프로브를 "spawn" 모드로, 콘솔이 전혀 없는 상태(DETACHED_PROCESS)로 띄운다.
// 이것이 Maya.exe를 흉내 내는 부분이다.
struct ProbeResult {
    bool launched = false;
    DWORD exitCode = 0;
    std::string childReport;
    std::string parentReport;
};

ProbeResult runProbe(const char* tier, const char* stem) {
    ProbeResult result;
    const std::string outPath = tempFilePath(stem);
    const std::string parentPath = outPath + ".parent";
    ::DeleteFileA(outPath.c_str());
    ::DeleteFileA(parentPath.c_str());

    std::string commandLine = "\"" + std::string(MARO_CONSOLE_PROBE_EXE_PATH) + "\" spawn " +
                              tier + " \"" + outPath + "\"";

    STARTUPINFOA startupInfo{};
    startupInfo.cb = sizeof(startupInfo);
    PROCESS_INFORMATION processInfo{};
    // DETACHED_PROCESS: 이 gtest 프로세스의 콘솔을 물려주지 않는다. 프로브는
    // 콘솔 프로그램이지만 이 플래그로 뜨면 콘솔이 아예 없는 상태가 되어,
    // GUI 서브시스템 프로세스(Maya.exe)와 같은 조건이 된다.
    const BOOL created = ::CreateProcessA(MARO_CONSOLE_PROBE_EXE_PATH, commandLine.data(),
                                          nullptr, nullptr, FALSE, DETACHED_PROCESS,
                                          nullptr, nullptr, &startupInfo, &processInfo);
    if (!created) return result;
    result.launched = true;

    ::WaitForSingleObject(processInfo.hProcess, 20000);
    ::GetExitCodeProcess(processInfo.hProcess, &result.exitCode);
    ::CloseHandle(processInfo.hProcess);
    ::CloseHandle(processInfo.hThread);

    // tier 2(WMI)는 자식이 WMI 서비스 밑에서 비동기로 생기므로, 프로브가
    // 끝난 뒤에도 결과 파일이 잠깐 늦게 나타날 수 있다 -- 폴링한다.
    for (int attempt = 0; attempt < 100 && result.childReport.empty(); ++attempt) {
        result.childReport = readFileIfPresent(outPath);
        if (result.childReport.empty()) ::Sleep(50);
    }
    result.parentReport = readFileIfPresent(parentPath);

    ::DeleteFileA(outPath.c_str());
    ::DeleteFileA(parentPath.c_str());
    return result;
}

TEST(ConsoleWindow, SpawnWithBreakawayGivesTheChildNoConsoleWindow) {
    const ProbeResult probe = runProbe("1", "tier1");
    ASSERT_TRUE(probe.launched) << "could not launch the console-window probe";
    ASSERT_EQ(probe.exitCode, 0u) << "probe could not spawn its child (tier 1)";

    // 전제 검증: 부모가 정말 콘솔 없는 상태였는가. 이게 깨지면 아래 단언은
    // 아무것도 증명하지 못한다(부모 콘솔을 물려받아 새 창이 안 뜬 것뿐).
    ASSERT_FALSE(probe.parentReport.empty()) << "probe did not report its own console state";
    EXPECT_EQ(fieldValue(probe.parentReport, "console"), 0)
        << "precondition broken: the spawning process had a console of its own, so this "
           "test cannot distinguish 'no new window' from 'inherited the parent's window' -- "
           "report was: " << probe.parentReport;

    ASSERT_FALSE(probe.childReport.empty()) << "child never reported back";
    // 핵심 단언. CREATE_NO_WINDOW가 빠지면 콘솔 없는 부모 밑의 콘솔 자식은
    // 새 콘솔을 할당받아 console!=0이 된다(실측 확인).
    EXPECT_EQ(fieldValue(probe.childReport, "console"), 0)
        << "the spawned process has a console window -- a real Maya user would see it pop "
           "up and stay for the sentinel's whole lifetime; report was: " << probe.childReport;
    EXPECT_EQ(fieldValue(probe.childReport, "visible"), 0) << probe.childReport;
}

TEST(ConsoleWindow, SpawnViaWmiGivesTheChildNoConsoleWindow) {
    const ProbeResult probe = runProbe("2", "tier2");
    ASSERT_TRUE(probe.launched) << "could not launch the console-window probe";
    if (probe.exitCode != 0) {
        GTEST_SKIP() << "probe could not spawn via WMI on this machine (exit code "
                     << probe.exitCode << ") -- same environment caveat the other WMI "
                        "tests carry, not a maro_ipc bug";
    }

    ASSERT_FALSE(probe.childReport.empty()) << "child never reported back";
    EXPECT_EQ(fieldValue(probe.childReport, "console"), 0)
        << "the WMI-spawned process has a console window; report was: " << probe.childReport;
    EXPECT_EQ(fieldValue(probe.childReport, "visible"), 0) << probe.childReport;
}

}  // namespace
