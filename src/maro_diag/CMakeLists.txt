add_library(maro_diag STATIC
    src/ErrorHash.cpp
)

target_include_directories(maro_diag PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/include
)

# Maya devkit이 플러그인 타깃을 C++17로 강제한다(devkit.cmake). 이 라이브러리는
# 플러그인에 링크되므로 표준을 맞춘다 -- maro_transform과 같은 이유
# (src/maro_transform/CMakeLists.txt 참고).
target_compile_features(maro_diag PUBLIC cxx_std_17)
