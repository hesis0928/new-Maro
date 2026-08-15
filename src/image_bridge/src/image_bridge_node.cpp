#include <iostream>
#include <vector>
#include <winsock2.h>
#pragma comment(lib, "ws2_32.lib")

#include <boost/interprocess/windows_shared_memory.hpp>
#include <boost/interprocess/mapped_region.hpp>
#include <boost/interprocess/sync/named_mutex.hpp>
#include <boost/interprocess/sync/scoped_lock.hpp>
#include <opencv2/opencv.hpp>

// 공유 메모리 구조체가 정의된 뼈대 헤더
#include "maro_library/IpcData.h"

using namespace boost::interprocess;

int main() {
    std::cout << "=========================================" << std::endl;
    std::cout << " [Maro Image Bridge] Windows TCP Sender" << std::endl;
    std::cout << "=========================================" << std::endl;

    // 터미널 출력 인코딩을 강제로 UTF-8로 고정
    SetConsoleOutputCP(CP_UTF8);

    std::cout << "=========================================" << std::endl;

    // 1. 윈도우 네트워크(Winsock) 초기화
    WSADATA wsaData;
    if (WSAStartup(MAKEWORD(2, 2), &wsaData) != 0) return 1;

    // 2. TCP 소켓 생성 (대용량 영상 전송에는 TCP가 필수)
    SOCKET sock = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    sockaddr_in serverAddr;
    serverAddr.sin_family = AF_INET;
    serverAddr.sin_port = htons(9091); // 이미지 전용 포트 9091
    serverAddr.sin_addr.s_addr = inet_addr("127.0.0.1"); // 리눅스(WSL2) 주소

    // 3. 우분투 수신기가 켜질 때까지 무한 접속 시도
    std::cout << "우분투 Image Receiver(Port:9091) 연결 대기 중..." << std::endl;
    while (connect(sock, (SOCKADDR*)&serverAddr, sizeof(serverAddr)) == SOCKET_ERROR) {
        Sleep(1000);
    }
    std::cout << "🚀 우분투와 이미지 통신망 연결 성공!" << std::endl;

    try {
        // 4. 공유 메모리 오픈
        named_mutex mutex(open_only, MaroPlugin::MUTEX_NAME);
        windows_shared_memory shm(open_only, MaroPlugin::SHM_NAME, read_only);
        mapped_region region(shm, read_only);

        MaroPlugin::SharedImageHeader* header = static_cast<MaroPlugin::SharedImageHeader*>(region.get_address());
        uint8_t* pPixels = static_cast<uint8_t*>(region.get_address()) + sizeof(MaroPlugin::SharedImageHeader);

        uint64_t last_frame = 0;

        // 5. 초고속 영상 전송 무한 루프
        while (true) {
            mutex.lock();

            // ★ 수정된 부분: frame_index 오타 수정 및 atomic 안전 로드
            uint64_t current_frame = header->frame_index.load();

            // 새 프레임이 없거나 데이터가 비어있으면 스킵
            if (current_frame == last_frame || header->width == 0) {
                mutex.unlock();
                Sleep(1);
                continue;
            }

            int width = header->width;
            int height = header->height;
            int data_size = width * height * 4; // RGBA 4채널

            // 뮤텍스 잠금 시간을 최소화하기 위해 데이터를 로컬로 쏙 빼옵니다.
            std::vector<uint8_t> local_buffer(pPixels, pPixels + data_size);
            last_frame = current_frame;
            mutex.unlock();

            // OpenCV를 이용해 마야의 RGBA를 ROS 2 표준인 BGRA로 색상 변환
            cv::Mat image(height, width, CV_8UC4, local_buffer.data());
            cv::cvtColor(image, image, cv::COLOR_RGBA2BGRA);

            // [전송 1] 해상도 정보(헤더) 먼저 쏘기
            int header_info[2] = { width, height };
            if (send(sock, (char*)header_info, sizeof(header_info), 0) <= 0) break;

            // [전송 2] 변환된 픽셀 데이터 쏘기 (청크 분할 안전 전송)
            int total_sent = 0;
            char* data_ptr = (char*)image.data;
            while (total_sent < data_size) {
                int sent = send(sock, data_ptr + total_sent, data_size - total_sent, 0);
                if (sent <= 0) break;
                total_sent += sent;
            }
        }
    }
    catch (const interprocess_exception& ex) {
        std::cerr << "공유 메모리 에러: " << ex.what() << "\n(Maya에서 ViewportStreamer가 켜져 있는지 확인하세요.)" << std::endl;
    }

    closesocket(sock);
    WSACleanup();
    return 0;
}