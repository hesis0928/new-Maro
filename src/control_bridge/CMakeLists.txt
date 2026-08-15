cmake_minimum_required(VERSION 3.8)
project(control_bridge)

# C++ 표준 설정
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Boost 찾기 (공유 메모리용)
# 참고: 윈도우 환경(vcpkg)에 맞게 경로가 잡혀있다고 가정합니다.
find_package(Boost REQUIRED)

# 윈도우 네트워크 통신을 위한 라이브러리(ws2_32)
set(NETWORK_LIBS ws2_32)

# 실행 파일 만들기
add_executable(control_bridge_node src/control_bridge_node.cpp)

# Boost 헤더 및 네트워크 라이브러리 연결 (ROS 2 흔적 0%)
target_include_directories(control_bridge_node PRIVATE ${Boost_INCLUDE_DIRS})
target_link_libraries(control_bridge_node PRIVATE ${NETWORK_LIBS})

# 설치 경로 설정 (기존 C++ 빌드 방식 유지)
install(TARGETS control_bridge_node DESTINATION bin)