add_library(maro_lidar STATIC
    src/RayPattern.cpp
)

target_include_directories(maro_lidar PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/include
)

target_link_libraries(maro_lidar PUBLIC
    maro_transform
)

# Maya 2026 devkit이 플러그인 타깃을 C++17로 강제한다(devkit.cmake). 이 라이브러리는
# 플러그인에 링크되므로 표준을 맞춘다.
target_compile_features(maro_lidar PUBLIC cxx_std_17)
