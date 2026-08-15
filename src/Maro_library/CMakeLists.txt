cmake_minimum_required(VERSION 3.8)
project(maro_library)

# C++ 표준 설정
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# 콜콘 빌드 시스템 유지용
find_package(ament_cmake REQUIRED)

# 헤더 파일(IpcData.h)만 제공하는 가벼운 '인터페이스 라이브러리'로 생성합니다.
add_library(${PROJECT_NAME} INTERFACE)

target_include_directories(${PROJECT_NAME} INTERFACE
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>
)

# ★ 바로 이 부분! 헤더 파일들을 install 폴더로 실제 복사해 주는 핵심 명령어입니다.
install(DIRECTORY include/ DESTINATION include)

# 다른 윈도우 패키지들이 이 뼈대를 가져다 쓸 수 있도록 내보내기
ament_export_include_directories(include)
ament_package()