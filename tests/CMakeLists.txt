find_package(GTest CONFIG REQUIRED)
# test_journal_writer.cpp parses journal lines back into JSON to assert
# field values (Finding 2). find_package's imported target is scoped to the
# directory tree it's called in, and src/maro_diag's call
# (src/maro_diag/CMakeLists.txt) doesn't reach this sibling directory, so it
# is repeated here rather than relying on that one.
find_package(nlohmann_json CONFIG REQUIRED)

include(GoogleTest)

add_executable(maro_ipc_tests
    ipc/test_message.cpp
    ipc/test_naming.cpp
    ipc/test_sentinel_record.cpp
    ipc/test_named_mutex_guard.cpp
    ipc/test_named_pipe.cpp
    ipc/test_job_escape.cpp
    ipc/test_sentinel_process.cpp
    ipc/test_console_window.cpp
)

target_link_libraries(maro_ipc_tests PRIVATE
    maro_ipc
    GTest::gtest
    GTest::gtest_main
)

# test_sentinel_process.cpp는 진짜 maro_sentinel.exe를 서브프로세스로 띄운다.
# 이 프로젝트는 멀티 컨피그 제너레이터(Visual Studio)라 두 타깃이 각자 다른
# 하위 디렉터리(tests/Release/, src/maro_sentinel/Release/)에 놓이므로
# "테스트 실행 파일 옆에 있겠지"라는 가정이 성립하지 않는다. 빌드 시스템이
# 아는 정확한 경로를 컴파일 타임에 넘긴다.
target_compile_definitions(maro_ipc_tests PRIVATE
    MARO_SENTINEL_EXE_PATH="$<TARGET_FILE:maro_sentinel>"
    # test_console_window.cpp도 같은 이유로 정확한 경로를 컴파일 타임에 받는다.
    MARO_CONSOLE_PROBE_EXE_PATH="$<TARGET_FILE:maro_console_window_probe>"
    # SentinelStuckInAJobRecordsThatItIsInAJob이 띄우는 job 격리 도우미도 마찬가지.
    MARO_SENTINEL_IN_JOB_HELPER_EXE_PATH="$<TARGET_FILE:maro_sentinel_in_job_helper>")

gtest_discover_tests(maro_ipc_tests)

add_executable(maro_job_escape_test_helper ipc/job_escape_test_helper.cpp)
target_link_libraries(maro_job_escape_test_helper PRIVATE maro_ipc)
# 아래 콘솔 프로브와 같은 이유로 명시적 의존이 필요하다: 테스트는 이 도우미를
# 경로로만 찾으므로(SpawnWithBreakawayFailsInsideARestrictiveJob이
# GetModuleFileNameA로 자기 옆 경로를 조립한다) CMake가 의존을 추론하지
# 못한다. 이것이 없으면 maro_ipc_tests 타깃만 골라 빌드했을 때 도우미가
# 빌드되지 않은 채 남아 그 테스트가 "도우미를 못 찾았다"로 실패한다.
add_dependencies(maro_ipc_tests maro_job_escape_test_helper)

# 감시자를 breakaway 불허 job 안에서 띄우는 도우미(최종 리뷰 I1). 감시자
# 실행 파일 경로는 maro_ipc_tests와 똑같은 이유로 컴파일 타임에 박아 준다 --
# 멀티 컨피그 제너레이터에서는 "내 옆에 있겠지"가 성립하지 않는다.
add_executable(maro_sentinel_in_job_helper ipc/sentinel_in_job_helper.cpp)
target_link_libraries(maro_sentinel_in_job_helper PRIVATE maro_ipc)
target_compile_definitions(maro_sentinel_in_job_helper PRIVATE
    MARO_SENTINEL_EXE_PATH="$<TARGET_FILE:maro_sentinel>")
add_dependencies(maro_sentinel_in_job_helper maro_sentinel)
add_dependencies(maro_ipc_tests maro_sentinel_in_job_helper)

# 콘솔 창 검증용 프로브. maro_sentinel.exe와 같은 조건을 만들어야 하므로
# 반드시 *콘솔 서브시스템*으로 둔다 -- WIN32_EXECUTABLE을 붙이면 GUI
# 서브시스템이 되어 애초에 콘솔이 할당되지 않고, 그러면 이 테스트가 무엇을
# 하든 통과하는 무의미한 테스트가 된다.
add_executable(maro_console_window_probe ipc/console_window_probe.cpp)
target_link_libraries(maro_console_window_probe PRIVATE maro_ipc)
# 테스트가 실행될 때 프로브가 이미 빌드돼 있어야 한다(경로만 넘겨받으므로
# CMake가 의존을 자동으로 추론하지 못한다).
add_dependencies(maro_ipc_tests maro_console_window_probe)

add_executable(maro_transform_tests
    transform/test_convert.cpp
)

target_link_libraries(maro_transform_tests PRIVATE
    maro_transform
    GTest::gtest
    GTest::gtest_main
)

gtest_discover_tests(maro_transform_tests)

add_executable(maro_lidar_tests
    lidar/test_ray_pattern.cpp
    lidar/test_scan_engine.cpp
    lidar/test_point_cloud_packing.cpp
)

target_link_libraries(maro_lidar_tests PRIVATE
    maro_lidar
    GTest::gtest
    GTest::gtest_main
)

gtest_discover_tests(maro_lidar_tests)

add_executable(maro_diag_tests
    diag/test_error_hash.cpp
    diag/test_book_store.cpp
    diag/test_panel_presenter.cpp
    diag/test_journal_writer.cpp
    diag/test_journal_reader.cpp
    diag/test_remedy_action.cpp
)

target_link_libraries(maro_diag_tests PRIVATE
    maro_diag
    GTest::gtest
    GTest::gtest_main
    # test_journal_writer.cpp parses emitted lines back into JSON to assert
    # field values. maro_diag keeps nlohmann PRIVATE (its header isn't part
    # of the library's public interface), so the test target links it
    # directly rather than making it public on the library.
    nlohmann_json::nlohmann_json
)

gtest_discover_tests(maro_diag_tests)

add_executable(maro_plugin_logic_tests
    plugin/test_command_delta_check.cpp
)

target_include_directories(maro_plugin_logic_tests PRIVATE
    ${CMAKE_SOURCE_DIR}/src/maro_plugin
)

target_link_libraries(maro_plugin_logic_tests PRIVATE
    GTest::gtest
    GTest::gtest_main
)

gtest_discover_tests(maro_plugin_logic_tests)

if(MARO_BUILD_PLUGIN)
    set(MAYAPY "C:/Program Files/Autodesk/Maya2026/bin/mayapy.exe")

    file(GLOB ROS2_PACKAGE_INCLUDES LIST_DIRECTORIES true "${ROS2_INSTALL}/include/*")
    set(PEER_INCLUDES ${ROS2_INSTALL}/include)
    foreach(dir ${ROS2_PACKAGE_INCLUDES})
        if(IS_DIRECTORY ${dir})
            get_filename_component(name ${dir} NAME)
            if(NOT name STREQUAL "idl" AND NOT name STREQUAL "idlc")
                list(APPEND PEER_INCLUDES ${dir})
            endif()
        endif()
    endforeach()

    add_executable(maro_test_peer peer/maro_test_peer.cpp)
    target_include_directories(maro_test_peer PRIVATE ${PEER_INCLUDES})
    target_compile_definitions(maro_test_peer PRIVATE
        NOMINMAX _SILENCE_CXX17_CODECVT_HEADER_DEPRECATION_WARNING)

    foreach(ros_lib rclcpp rcl rcutils rcpputils rmw rosidl_runtime_c
                    rosidl_typesupport_cpp
                    sensor_msgs__rosidl_typesupport_cpp
                    # /tf 모드가 구독하는 tf2_msgs/msg/TFMessage는
                    # geometry_msgs/msg/TransformStamped를 담는다. 플러그인
                    # 쪽(src/maro_plugin/CMakeLists.txt)이 이미 이 둘을 같은
                    # 이유로 링크하고 있다.
                    geometry_msgs__rosidl_typesupport_cpp
                    tf2_msgs__rosidl_typesupport_cpp
                    builtin_interfaces__rosidl_typesupport_cpp
                    # rclcpp의 토픽 통계 기능(SubscriptionTopicStatistics)이
                    # 이 둘을 끌어온다. 브리프의 링크 목록에는 없었지만 링크
                    # 단계에서 libstatistics_collector 미해결 심볼로 드러났다
                    # (src/maro_plugin/CMakeLists.txt에서 이미 겪은 것과 같은 문제).
                    libstatistics_collector
                    statistics_msgs__rosidl_typesupport_cpp)
        target_link_libraries(maro_test_peer PRIVATE "${ROS2_INSTALL}/Lib/${ros_lib}.lib")
    endforeach()

    add_custom_command(TARGET maro_test_peer POST_BUILD
        COMMAND ${CMAKE_COMMAND} -E copy_directory
                "${ROS2_INSTALL}/bin" "$<TARGET_FILE_DIR:maro_test_peer>"
        COMMAND ${CMAKE_COMMAND} -E copy_directory
                "${ROS2_INSTALL}/opt/libyaml_vendor/bin" "$<TARGET_FILE_DIR:maro_test_peer>"
        COMMAND ${CMAKE_COMMAND} -E copy_directory
                "${ROS2_INSTALL}/opt/spdlog_vendor/bin" "$<TARGET_FILE_DIR:maro_test_peer>"
        COMMAND ${CMAKE_COMMAND} -E copy_directory
                "${ROS2_INSTALL}/opt/console_bridge_vendor/bin" "$<TARGET_FILE_DIR:maro_test_peer>"
    )

    # Maya의 플러그인 로더는 .mll을 LOAD_WITH_ALTERED_SEARCH_PATH로 열지
    # 않는다 (src/maro_plugin/CMakeLists.txt의 I8 주석, task-10-report.md
    # 참고) -- 그래서 옆에 스테이징해 둔 ROS 2 런타임 DLL이 로드되려면 그
    # 디렉터리가 mayapy.exe를 띄우는 프로세스의 PATH에 있어야 한다. ctest가
    # 띄우는 테스트 프로세스는 ctest 자신의 PATH를 물려받을 뿐 이 디렉터리를
    # 자동으로 넣어주지 않으므로, ENVIRONMENT_MODIFICATION의
    # path_list_prepend로 앞에 붙인다 -- 일반 ENVIRONMENT 프로퍼티로
    # "PATH=...;$ENV{PATH}"를 직접 쓰면 안 된다: ENVIRONMENT는 전체를 세미콜론
    # 구분 리스트로 저장하는데 $ENV{PATH} 자체가 세미콜론투성이라 리스트가
    # 조각나 PATH의 앞부분만 남고 나머지는 깨진 "VAR=value" 항목으로
    # 흩어진다. path_list_prepend는 값 하나(경로 하나)만 다루므로 이 문제가
    # 없고, 기존 PATH를 지우지 않고 앞에 이어 붙인다.
    #
    # ROS 2 피어가 필요한 테스트는 피어 실행 파일 자신의 디렉터리도 이미
    # 안고 있어(자기 자신의 POST_BUILD로 같은 DLL들을 복사) 별도로 PATH에
    # 넣을 필요는 없다 -- Windows는 실행 파일 자신의 디렉터리를 그 파일의
    # 의존 DLL 검색 경로에 항상 포함하므로, LoadLibrary가 아니라 직접 실행
    # (subprocess)되는 피어는 이 문제 자체를 겪지 않는다.

    # 모든 Maya 테스트는 자기만의 book 디렉터리를 빌드 트리 안에 갖는다.
    #
    # 왜 필요한가: BoadMaro::error()는 book(지식 저장소)을 읽고 스필에 덧붙이는데,
    # MARO_DIAG_BOOK_DIR이 없으면 기본 위치가 `internalVar -userAppDir` --
    # 사용자의 진짜 Maya 환경설정 디렉터리다. Task 7이 MaroCommands.cpp의
    # 검증 실패 ~45곳을 error()로 옮기면서, 거부 경로를 지나는 모든 기존
    # 테스트(test_binding.py, test_robustness.py, test_delete_rules.py 등)가
    # ctest를 돌릴 때마다 거기에 스필 항목을 쌓게 된다 -- 테스트 스위트가
    # 건드릴 이유가 전혀 없는 디렉터리다. (실측: Task 4 시점에 이미
    # test_binding.py가 남긴 항목이 사용자 prefs에 있었다.)
    #
    # ENVIRONMENT가 아니라 ENVIRONMENT_MODIFICATION을 쓰는 이유는 위 PATH와
    # 같다: ENVIRONMENT는 세미콜론 구분 리스트라 Windows 경로가 섞이면
    # 조각난다. set은 값 하나만 다루므로 안전하다. 또 ENVIRONMENT_MODIFICATION은
    # 프로세스 환경을 세팅할 뿐이므로, 파이썬에서 os.environ으로 직접 덮어쓰는
    # 테스트는 그대로 자기 값을 쓴다. 지금 그렇게 하는 것은 강등 시나리오
    # 둘(diag_degraded/diag_degraded_remedy)뿐이다 -- 그 둘은 "쓸 수 없는
    # 경로"를 일부러 만들어야 해서 여기서 주는 정상 디렉터리를 쓸 수 없다.
    # 나머지는 전부 이 값을 그대로 받아 쓴다(아래 초기화 픽스처가 걸리도록).
    set(MARO_TEST_BOOK_ROOT "${CMAKE_CURRENT_BINARY_DIR}/diag_book")

    # 리뷰 Finding 3: 위 book 디렉터리들은 빌드 트리 밑이라 사용자 진짜 prefs는
    # 더 이상 안 건드리지만, 그 자체가 ctest 재실행 사이에 남는다. 두 번째
    # 실행부터는 이 스위트의 모든 거부가 book 캐시 히트가 되어(스필에 새로
    # 기록하는 대신 저장된 분석 + "book에서 즉답" 딱지로 메시지가 바뀌고
    # appendToSpill이 전혀 안 돈다) fresh-analysis 경로가 첫 실행 이후로는
    # 커버되지 않는다. Maya 테스트가 시작하기 전에 book 루트를 통째로 지우는
    # CTest fixture 하나로 해결한다 -- 16개 파이썬 파일 각각에 정리 코드를
    # 넣지 않는다. FIXTURES_SETUP/FIXTURES_REQUIRED는 실행 순서를 보장한다:
    # 이 리셋 테스트가 먼저 통과해야 그것을 요구하는 테스트들이 돈다(CTest가
    # add_test 순서와 무관하게 이 의존을 스케줄링한다).
    add_test(NAME maya_diag_book_root_reset
             COMMAND ${CMAKE_COMMAND} -E rm -rf "${MARO_TEST_BOOK_ROOT}")
    set_tests_properties(maya_diag_book_root_reset PROPERTIES
        FIXTURES_SETUP MaroDiagBookRoot)

    # 플러그인만 있으면 되는 테스트. robustness는 순수 DG 조작/평가만 하고
    # 브리지(rclcpp)를 켜지 않으므로 이 그룹에 속한다.
    # main 병합(sentinel, PR #1)과 이 브랜치(lidar_node)가 같은 목록 끝에
    # 각자 새 항목을 붙여서 생긴 충돌 -- 둘 다 유지한다.
    foreach(maya_test load axis_node binding capability_stack delete_rules
                      robustness diag_boad diag_onfix diag_book
                      diag_book_cross_session diag_remedy
                      diag_degraded diag_degraded_remedy diag_thread
                      panel_commands journal remedy_capture
                      remedy_availability remedy_ambiguous_names
                      main_thread_queue remedy_apply sentinel lidar_node)
        add_test(NAME maya_${maya_test}
                 COMMAND "${MAYAPY}"
                         "${CMAKE_CURRENT_SOURCE_DIR}/maya/test_${maya_test}.py")
        set_tests_properties(maya_${maya_test} PROPERTIES
            ENVIRONMENT "MARO_PLUGIN_PATH=$<TARGET_FILE:maro>"
            ENVIRONMENT_MODIFICATION
                "PATH=path_list_prepend:$<TARGET_FILE_DIR:maro>;MARO_DIAG_BOOK_DIR=set:${MARO_TEST_BOOK_ROOT}/maya_${maya_test}"
            FIXTURES_REQUIRED MaroDiagBookRoot
            TIMEOUT 240)
    endforeach()

    # bridge_pump는 피어를 쓰지 않지만 maroStartBridge()로 실제 rclcpp
    # 컨텍스트(DDS 도메인)를 띄운다. publish/contract와 같은 도메인을
    # 공유하므로 그것들과 동시에 돌면 서로 간섭한다 -- RUN_SERIAL이 필요하다.
    add_test(NAME maya_bridge_pump
             COMMAND "${MAYAPY}"
                     "${CMAKE_CURRENT_SOURCE_DIR}/maya/test_bridge_pump.py")
    set_tests_properties(maya_bridge_pump PROPERTIES
        ENVIRONMENT "MARO_PLUGIN_PATH=$<TARGET_FILE:maro>"
        ENVIRONMENT_MODIFICATION
            "PATH=path_list_prepend:$<TARGET_FILE_DIR:maro>;MARO_DIAG_BOOK_DIR=set:${MARO_TEST_BOOK_ROOT}/maya_bridge_pump"
        FIXTURES_REQUIRED MaroDiagBookRoot
        TIMEOUT 240
        RUN_SERIAL TRUE)

    # lidar_publish도 bridge_pump와 같은 이유로 이 그룹에 못 들어간다:
    # maroStartBridge()로 실제 rclcpp 컨텍스트(DDS 도메인)를 띄우므로
    # publish/contract/bridge_pump와 동시에 돌면 서로 간섭한다. 브리프는 위
    # foreach 목록("플러그인만 있으면 되는 테스트")에 넣으라고 했지만 그
    # 목록에는 RUN_SERIAL이 없다 -- 그 그룹의 전제를 깨는 대신 bridge_pump와
    # 같은 모양으로 따로 등록한다.
    add_test(NAME maya_lidar_publish
             COMMAND "${MAYAPY}"
                     "${CMAKE_CURRENT_SOURCE_DIR}/maya/test_lidar_publish.py")
    set_tests_properties(maya_lidar_publish PROPERTIES
        ENVIRONMENT "MARO_PLUGIN_PATH=$<TARGET_FILE:maro>"
        ENVIRONMENT_MODIFICATION
            "PATH=path_list_prepend:$<TARGET_FILE_DIR:maro>;MARO_DIAG_BOOK_DIR=set:${MARO_TEST_BOOK_ROOT}/maya_lidar_publish"
        FIXTURES_REQUIRED MaroDiagBookRoot
        TIMEOUT 240
        RUN_SERIAL TRUE)

    # ROS 2 상대역이 필요한 테스트는 피어 경로도 받는다.
    foreach(maya_test publish contract)
        add_test(NAME maya_${maya_test}
                 COMMAND "${MAYAPY}"
                         "${CMAKE_CURRENT_SOURCE_DIR}/maya/test_${maya_test}.py")
        set_tests_properties(maya_${maya_test} PROPERTIES
            ENVIRONMENT "MARO_PLUGIN_PATH=$<TARGET_FILE:maro>;MARO_PEER_PATH=$<TARGET_FILE:maro_test_peer>"
            ENVIRONMENT_MODIFICATION
                "PATH=path_list_prepend:$<TARGET_FILE_DIR:maro>;MARO_DIAG_BOOK_DIR=set:${MARO_TEST_BOOK_ROOT}/maya_${maya_test}"
            FIXTURES_REQUIRED MaroDiagBookRoot
            TIMEOUT 360)
        # 같은 DDS 도메인을 쓰므로 병렬 실행 시 서로 간섭한다.
        set_tests_properties(maya_${maya_test} PROPERTIES RUN_SERIAL TRUE)
    endforeach()
endif()
