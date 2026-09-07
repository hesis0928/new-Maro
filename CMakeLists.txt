# tests/CMakeLists.txt uses set_tests_properties(... ENVIRONMENT_MODIFICATION ...)
# (path_list_prepend, to build PATH without shredding it on embedded
# semicolons) -- that property was only added in CMake 3.22, so the floor
# below must track that, not the older baseline this project started from.
cmake_minimum_required(VERSION 3.22)
project(maro LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# 소스에 한국어 주석이 있다. MSVC 기본 코드페이지(949)로 읽으면 C4819가 뜨고
# 주석이 깨진다. 소스와 실행 문자셋을 모두 UTF-8로 고정한다.
if(MSVC)
    add_compile_options(/utf-8)

    # 이 프로젝트는 모든 Maya/ROS 2 콜백 경계에서 예외를 잡아 막는 것을
    # 전제로 한다. 해제(unwind) 시맨틱이 꺼져 있으면 스택 되감기 중 소멸자가
    # 실행되지 않아 그 방어가 무의미해진다.
    add_compile_options(/EHsc)
endif()

# 외부 위치. 캐시 변수로 주입해 하드코딩을 피한다.
set(DEVKIT_LOCATION "C:/Users/ckd30/Projects/devkitBase" CACHE PATH "Maya devkit root")
set(ROS2_INSTALL    "C:/dev/ros2_jazzy/install"          CACHE PATH "ROS 2 install prefix")

# devkit의 pluginEntry.cmake는 환경 변수로 읽으므로 여기서 채워준다.
set(ENV{DEVKIT_LOCATION} "${DEVKIT_LOCATION}")

option(MARO_BUILD_PLUGIN "Build the Maya plugin (needs devkit + ROS 2)" ON)
option(MARO_BUILD_TESTS  "Build tests" ON)

# AddressSanitizer 빌드. 기본은 OFF -- 켜는 것은 진단 전용이고, 별도
# 빌드 트리(out/build-asan 등)에서만 쓴다.
#
# 왜 있는가: maroPointCloud 드로우 오버라이드의 use-after-free를 쫓다가
# 만들었다(경위는 docs/maro-main-ui-manual-checklist.md의 §6-1). 그 버그
# 자체는 결국 ASan이 아니라 콜백 카운터 계측이 잡았지만, 힙 손상류가 또
# 의심될 때 시스템 전역 설정을 바꾸는 gflags/PageHeap 대신 쓸 수 있는
# 자족적인 수단으로 남겨 둔다.
#
# **Maya에서 쓰는 법**: ASan 런타임을 Maya 초기화 *전에* 프로세스에 넣어야
# 한다 -- mayapy라면 maya.standalone.initialize()보다 먼저
# ctypes.CDLL("...clang_rt.asan_dynamic-x86_64.dll"). 늦게 로드하면 리포트
# 없이 프로세스가 그냥 죽는다(실측). tools/crashtriage/run-asan-tests.ps1 참고.
option(MARO_ASAN "Build with AddressSanitizer (diagnostic builds only)" OFF)

if(MARO_ASAN)
    if(NOT MSVC)
        message(FATAL_ERROR "MARO_ASAN currently only wired up for MSVC")
    endif()
    # ASan은 편집 계속하기(/ZI)와 증분 링크를 못 쓴다. 멀티 컨피그
    # 제너레이터라 Debug 기본값에 /ZI가 들어 있으므로 /Zi로 낮춘다.
    # /DEBUG가 없으면 ASan 리포트의 스택 트레이스에 함수명이 안 나온다
    # (링커가 LNK4302로 직접 경고한다) -- 이 빌드 트리의 존재 이유가
    # 그 스택 트레이스이므로 반드시 켠다.
    add_compile_options(/fsanitize=address /Zi)
    add_link_options(/INCREMENTAL:NO /DEBUG)
    string(REPLACE "/ZI" "/Zi" CMAKE_CXX_FLAGS_DEBUG "${CMAKE_CXX_FLAGS_DEBUG}")
    message(STATUS "Maro: AddressSanitizer ENABLED for this build tree")
endif()

add_subdirectory(src/maro_transform)
add_subdirectory(src/maro_lidar)
add_subdirectory(src/maro_diag)
add_subdirectory(src/maro_ipc)
add_subdirectory(src/maro_sentinel)

if(MARO_BUILD_TESTS)
    enable_testing()
    add_subdirectory(tests)
endif()

if(MARO_BUILD_PLUGIN)
    add_subdirectory(src/maro_plugin)
endif()
