# devkit 공식 진입점. .mll 접미사, NT_PLUGIN 정의, devkit include/lib를 처리한다.
include($ENV{DEVKIT_LOCATION}/cmake/pluginEntry.cmake)

set(PROJECT_NAME maro)

set(SOURCE_FILES
    MaroPluginMain.cpp
    MaroAxisNode.cpp
    MaroCapabilityNodes.cpp
    MaroCommands.cpp
    MaroDeleteWatcher.cpp
    MaroRosRuntime.cpp
    MaroPump.cpp
    MaroCommandDeviceNode.cpp
    MaroDiag.cpp
    MaroDiagCommands.cpp
    MaroPanelCommands.cpp
    MaroMainThreadQueue.cpp
    MaroRemedyCommands.cpp
    MaroSentinelClient.cpp
)

set(LIBRARIES
    OpenMaya
    OpenMayaUI
    OpenMayaRender
    OpenMayaAnim
    Foundation
)

# ROS 2 헤더. install/include 아래 패키지별 하위 디렉터리를 모두 넣는다.
# idl/idlc는 string.h 등 표준 헤더와 이름이 충돌하므로 제외한다.
file(GLOB ROS2_PACKAGE_INCLUDES LIST_DIRECTORIES true "${ROS2_INSTALL}/include/*")
set(INCLUDE_DIRS ${ROS2_INSTALL}/include)
foreach(dir ${ROS2_PACKAGE_INCLUDES})
    if(IS_DIRECTORY ${dir})
        get_filename_component(name ${dir} NAME)
        if(NOT name STREQUAL "idl" AND NOT name STREQUAL "idlc")
            list(APPEND INCLUDE_DIRS ${dir})
        endif()
    endif()
endforeach()

set(LIBRARY_DIRS ${ROS2_INSTALL}/Lib)

build_plugin()

# build_plugin()이 만든 타깃에 나머지를 얹는다. devkit의 pluginEntry.cmake가
# build_plugin() 안에서 이미 target_link_libraries(${PROJECT_NAME} ${MAYA_LIBRARIES})를
# 키워드 없는(plain) 형태로 호출해 놓았다. CMake는 같은 타깃에 plain과
# keyword(PRIVATE/PUBLIC) 시그니처를 섞어 쓰는 것을 금지하므로, 여기서도
# PRIVATE 없이 plain 형태로 이어 붙인다.
target_link_libraries(${PROJECT_NAME} maro_transform)
target_link_libraries(${PROJECT_NAME} maro_diag)
target_link_libraries(${PROJECT_NAME} maro_ipc)

foreach(ros_lib rclcpp rcl rcutils rcpputils rmw rosidl_runtime_c
                rosidl_typesupport_cpp
                sensor_msgs__rosidl_typesupport_cpp
                geometry_msgs__rosidl_typesupport_cpp
                tf2_msgs__rosidl_typesupport_cpp
                builtin_interfaces__rosidl_typesupport_cpp
                # rclcpp의 토픽 통계 기능(SubscriptionTopicStatistics)이
                # 이 둘을 끌어온다. 브리프의 링크 목록에는 없었지만 링크
                # 단계에서 libstatistics_collector 미해결 심볼로 드러났다.
                libstatistics_collector
                statistics_msgs__rosidl_typesupport_cpp)
    target_link_libraries(${PROJECT_NAME} "${ROS2_INSTALL}/Lib/${ros_lib}.lib")
endforeach()

# windows.h의 min/max 매크로가 rclcpp의 numeric_limits 사용과 충돌한다.
target_compile_definitions(${PROJECT_NAME} PRIVATE
    NOMINMAX
    _SILENCE_CXX17_CODECVT_HEADER_DEPRECATION_WARNING
)

# 런타임 DLL을 플러그인 옆에 둔다. 벤더 DLL은 install/bin이 아니라
# install/opt/<vendor>/bin에 있으므로 반드시 함께 복사해야 로드된다.
#
# I8: 이 스테이징만으로는 부족하다. Maya의 플러그인 로더는 .mll을
# LoadLibraryEx(LOAD_WITH_ALTERED_SEARCH_PATH)로 열지 않는다 -- 그래서
# Windows는 .mll이 있는 이 디렉터리를 DLL 검색 경로에 자동으로 넣어주지
# 않는다. 여기서 옆에 복사해 둔 151개 ROS 2 런타임 DLL이 실제로 로드되려면
# 이 디렉터리($<TARGET_FILE_DIR:${PROJECT_NAME}>, 예:
# out/build/src/maro_plugin/<config>)가 Maya(또는 mayapy)를 띄우는
# 프로세스의 PATH 환경변수에 들어 있어야 한다. 안 넣으면 loadPlugin이
# "종속 DLL을 찾을 수 없다"류의 오류로 조용히 실패한다 -- CMake만으로는
# 고칠 수 없는 실행 시점 요구사항이라 여기 남겨 둔다.
add_custom_command(TARGET ${PROJECT_NAME} POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy_directory
            "${ROS2_INSTALL}/bin" "$<TARGET_FILE_DIR:${PROJECT_NAME}>"
    COMMAND ${CMAKE_COMMAND} -E copy_directory
            "${ROS2_INSTALL}/opt/libyaml_vendor/bin" "$<TARGET_FILE_DIR:${PROJECT_NAME}>"
    COMMAND ${CMAKE_COMMAND} -E copy_directory
            "${ROS2_INSTALL}/opt/spdlog_vendor/bin" "$<TARGET_FILE_DIR:${PROJECT_NAME}>"
    COMMAND ${CMAKE_COMMAND} -E copy_directory
            "${ROS2_INSTALL}/opt/console_bridge_vendor/bin" "$<TARGET_FILE_DIR:${PROJECT_NAME}>"
    COMMENT "Maro: staging ROS 2 runtime DLLs next to the plugin"
)

# 패널 UI 모듈은 플러그인 .mll 옆에 둔다. maroDiagPanel 커맨드가 그
# 디렉터리를 sys.path에 넣으므로 사용자가 MAYA_SCRIPT_PATH를 손댈 필요가 없다.
#
# I9: POST_BUILD는 ${PROJECT_NAME}의 relink 엣지에 묶여 있다 -- .py만 고쳐서
# 빌드하면 C++ 쪽에 변경이 없어 relink가 안 일어나고, 그러면 이 COMMAND도
# 조용히 스킵되어 스테일 모듈이 그대로 배포된 채 테스트가 통과해 버린다.
# 대신 OUTPUT 기반 add_custom_command로 python/maroDiagPanel.py 자체를
# 빌드 입력으로 만든다: DEPENDS가 소스 파일을 직접 가리키므로 Ninja가 그
# mtime을 보고 재실행 여부를 판단하고, .py만 바뀌어도 다시 복사된다.
# $<TARGET_FILE_DIR:...> in OUTPUT would be the tidier spelling, but it fails
# here at generate time ("No target maro") even though the target plainly
# exists at configure time -- build_plugin() (devkit's pluginEntry.cmake)
# creates it via add_library() from inside a function(), and CMake's
# generate-time target lookup for OUTPUT-position genexes doesn't resolve it
# in this setup. This project is single-config (Ninja, not Ninja Multi-Config),
# so the target's runtime output directory is just CMAKE_CURRENT_BINARY_DIR
# with no per-config subfolder -- confirmed on disk (maro.mll sits directly
# in out/build/src/maro_plugin). Using that plain variable for OUTPUT sidesteps
# the genex-resolution issue entirely; TARGET_FILE_DIR genex still works fine
# inside COMMAND (as used elsewhere in this file) since that path is resolved
# per-build-rule, not at OUTPUT-parsing time.
set(MARO_DIAG_PANEL_PY_SRC "${CMAKE_SOURCE_DIR}/python/maroDiagPanel.py")
set(MARO_DIAG_PANEL_PY_OUT "${CMAKE_CURRENT_BINARY_DIR}/maroDiagPanel.py")
add_custom_command(
    OUTPUT "${MARO_DIAG_PANEL_PY_OUT}"
    COMMAND ${CMAKE_COMMAND} -E make_directory "$<TARGET_FILE_DIR:${PROJECT_NAME}>"
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
            "${MARO_DIAG_PANEL_PY_SRC}" "${MARO_DIAG_PANEL_PY_OUT}"
    DEPENDS "${MARO_DIAG_PANEL_PY_SRC}"
    COMMENT "Copying maroDiagPanel.py next to the plug-in")
add_custom_target(maro_diag_panel_py ALL DEPENDS "${MARO_DIAG_PANEL_PY_OUT}")
add_dependencies(${PROJECT_NAME} maro_diag_panel_py)

# 감시자 실행 파일을 플러그인 옆에 둔다. MaroSentinelClient.cpp가 자기
# 모듈(.mll) 경로 기준으로 그 디렉터리에서 maro_sentinel.exe를 찾는다.
#
# [최종 리뷰 3i] 예전에는 이것이 ${PROJECT_NAME}의 POST_BUILD였고, 위 I9
# 주석과 같은 함정("maro_sentinel 소스만 바뀌면 플러그인이 relink되지 않아
# 복사가 스킵되고 스테일한 exe가 배포된 채 테스트만 통과한다")을 알려진
# 위험으로 안고 있었다. 위 maroDiagPanel.py와 같은 OUTPUT 기반 규칙으로
# 바꿔 그 의존을 없앤다.
#
# 실측으로 확인한 사실 하나를 남겨 둔다(고친 이유가 바뀌므로): **지금 이
# 빌드 트리(Visual Studio 멀티 컨피그 제너레이터)에서는 그 함정이 실제로
# 발현하지 않았다.** CMake의 VS 제너레이터는 POST_BUILD를 MSBuild의
# <PostBuildEvent>로 내보내고, RunPostBuildEvent를 지정하지 않으면 기본값이
# OnBuildSuccess라 링크가 스킵돼도 이벤트는 매 빌드 실행된다(생성된
# maro.vcxproj에 RunPostBuildEvent 항목이 없음을 확인했고, main.cpp만 고친
# 빌드에서 maro.mll의 mtime은 그대로인데 복사는 실행됐다). 함정이 진짜인
# 것은 POST_BUILD가 링크 규칙에 직접 묶이는 Ninja/Makefile 제너레이터이며,
# I9 주석은 이 저장소가 Ninja를 쓰던 시절에 쓰였다. 즉 지금의 정확성은
# "MSBuild의 기본값이 마침 우리에게 유리하다"에 기대고 있었다 --
# RunPostBuildEvent를 OnOutputUpdated로 바꾸거나 제너레이터를 되돌리면 조용히
# 사라지는 종류의 정확성이다. 아래 규칙은 제너레이터와 무관하게 성립한다.
#
# DEPENDS에 타깃 이름(maro_sentinel)을 주는 것이 핵심이다: CMake는 그것이
# 실행 파일/라이브러리 타깃이면 타깃 수준 의존(순서)과 **파일 수준
# 의존(재실행)** 을 둘 다 만든다. 그래서 maro_sentinel이 다시 링크되면
# 이 복사도 반드시 다시 돈다 -- 플러그인이 relink되는지와 무관하게.
#
# OUTPUT 경로에 $<TARGET_FILE_DIR:...> 대신 CMAKE_CURRENT_BINARY_DIR/$<CONFIG>를
# 쓰는 이유는 위 maroDiagPanel.py 블록의 주석과 같다(build_plugin()이 함수
# 안에서 타깃을 만들어 OUTPUT 자리의 타깃 조회가 해소되지 않는다). 다만 이쪽은
# 멀티 컨피그 제너레이터라 컨피그별 하위 디렉터리가 붙으므로 $<CONFIG>를
# 반드시 함께 넣어야 한다 -- 그것이 곧 $<TARGET_FILE_DIR:${PROJECT_NAME}>과
# 같은 경로다(maro.mll이 out/build/src/maro_plugin/<config>/에 놓이는 것을
# 디스크에서 확인). COMMAND 안에서는 TARGET_FILE_DIR 젠엑스가 정상 동작하므로
# 디렉터리 생성에는 그것을 그대로 쓴다.
set(MARO_SENTINEL_EXE_OUT "${CMAKE_CURRENT_BINARY_DIR}/$<CONFIG>/maro_sentinel.exe")
add_custom_command(
    OUTPUT "${MARO_SENTINEL_EXE_OUT}"
    COMMAND ${CMAKE_COMMAND} -E make_directory "$<TARGET_FILE_DIR:${PROJECT_NAME}>"
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
            "$<TARGET_FILE:maro_sentinel>" "${MARO_SENTINEL_EXE_OUT}"
    DEPENDS maro_sentinel
    COMMENT "Copying maro_sentinel.exe next to the plug-in")
add_custom_target(maro_sentinel_exe ALL DEPENDS "${MARO_SENTINEL_EXE_OUT}")
add_dependencies(${PROJECT_NAME} maro_sentinel_exe)
