find_package(nlohmann_json CONFIG REQUIRED)

add_library(maro_diag STATIC
    src/ErrorHash.cpp
    src/BookStore.cpp
)

target_include_directories(maro_diag PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/include
)

# BookStore.cpp 내부에서만 쓴다. 헤더가 nlohmann/json.hpp를 노출하지 않으므로
# PRIVATE로 충분하고, maro_plugin이 이 의존성을 몰라도 된다.
target_link_libraries(maro_diag PRIVATE nlohmann_json::nlohmann_json)

# Maya devkit이 플러그인 타깃을 C++17로 강제한다(devkit.cmake). 이 라이브러리는
# 플러그인에 링크되므로 표준을 맞춘다 -- maro_transform과 같은 이유
# (src/maro_transform/CMakeLists.txt 참고).
target_compile_features(maro_diag PUBLIC cxx_std_17)
