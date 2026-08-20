# Embree 4.4.0(vcpkg 포트 이름은 `embree`, `embree3`가 아니다). 설치된
# `share/embree/embree-config-version.cmake`는 요청 버전의 major가 4이고
# 4.4.0보다 낮으면 호환으로 표시하므로 `4`를 그대로 쓸 수 있다.
find_package(embree 4 CONFIG REQUIRED)

add_library(maro_lidar STATIC
    src/RayPattern.cpp
    src/ScanEngine.cpp
)

target_include_directories(maro_lidar PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/include
)

target_link_libraries(maro_lidar PUBLIC
    maro_transform
)

# 실제 설치된 `share/embree/embree-targets.cmake`가 `add_library(embree SHARED
# IMPORTED)`로 노출하는 타깃 이름이 그대로 `embree`다(같은 config가
# `unofficial::embree::embree` 인터페이스 별칭도 만들지만, 포트의 usage 파일이
# 안내하는 이름은 `embree`다). PRIVATE인 이유: Embree 타입은 ScanEngine.h의
# 공개 인터페이스에 노출되지 않는다(불투명 핸들 전방 선언만 쓴다).
target_link_libraries(maro_lidar PRIVATE
    embree
)

# Maya 2026 devkit이 플러그인 타깃을 C++17로 강제한다(devkit.cmake). 이 라이브러리는
# 플러그인에 링크되므로 표준을 맞춘다.
target_compile_features(maro_lidar PUBLIC cxx_std_17)
