find_package(nlohmann_json CONFIG REQUIRED)

add_library(maro_ipc STATIC
    src/Message.cpp
)

target_include_directories(maro_ipc PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/include
)

# Message.cpp 내부에서만 쓴다 -- maro_diag/CMakeLists.txt와 같은 이유로 PRIVATE.
target_link_libraries(maro_ipc PRIVATE nlohmann_json::nlohmann_json)

# maro_plugin에 링크되므로 그 타깃이 강제하는 표준을 맞춘다
# (maro_diag/CMakeLists.txt와 같은 이유).
target_compile_features(maro_ipc PUBLIC cxx_std_17)

# 이 라이브러리 전체가 Windows 전용이다(다음 태스크들이 명명된 파이프/뮤텍스/
# job object를 쓴다). 지금 당장은 이 파일에 Windows API 호출이 없지만, 이후
# 태스크들이 여기 소스를 추가하므로 정의를 미리 걸어 둔다.
target_compile_definitions(maro_ipc PUBLIC NOMINMAX WIN32_LEAN_AND_MEAN)
