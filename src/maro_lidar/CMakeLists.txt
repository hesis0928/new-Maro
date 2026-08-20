# Embree 4.4.0(vcpkg 포트 이름은 `embree`, `embree3`가 아니다). 설치된
# `share/embree/embree-config-version.cmake`는 요청 버전의 major가 4이고
# 4.4.0보다 낮으면 호환으로 표시하므로 `4`를 그대로 쓸 수 있다.
find_package(embree 4 CONFIG REQUIRED)

# find_package()가 만든 IMPORTED 타깃은 기본적으로 이 디렉터리(와 그 하위)
# 스코프에만 보인다. src/maro_plugin은 형제 디렉터리라 거기서
# `$<TARGET_FILE:embree>`를 쓰면 generate 단계에서 "No target embree"로
# 죽는다 -- 그 제네레이터 식을 써야 embree4.dll을 플러그인 옆에 스테이징할
# 수 있으므로(아래 I1) 여기서 전역으로 승격시킨다.
set_target_properties(embree PROPERTIES IMPORTED_GLOBAL TRUE)

# --------------------------------------------------------------------------
# I1: 설정(configure) 시점 TBB 부재 가드
#
# Maya 2026은 자기 tbb12.dll을 시작 시점에 이미 로드해 둔다. Windows
# 로더는 같은 베이스 이름의 모듈이 이미 로드돼 있으면 그것을 재사용하므로,
# vcpkg 기본 피처(`tasking-tbb`)로 빌드된 embree4.dll이 들어오면
# `tbb::detail::r1::get_thread_reference_vertex`를 못 찾아 loadPlugin이
# ERROR_PROC_NOT_FOUND("지정된 프로시저를 찾을 수 없습니다")로 실패한다.
# PATH 순서로도, 옆에 복사하기로도 이길 수 없다(src/maro_plugin/CMakeLists.txt의
# 긴 주석 참고).
#
# 그 실패는 빌드가 전부 성공한 뒤 Maya 안에서, 원인을 전혀 알려주지 않는
# 메시지로 터진다. 여기서 미리 임포트 테이블을 들여다보고 시끄럽게 죽는
# 편이 낫다. IMPORTED_LOCATION_*는 실제 경로(제네레이터 식이 아님)라
# execute_process에 그대로 넘길 수 있다.
get_target_property(MARO_EMBREE_DLL embree IMPORTED_LOCATION_RELEASE)
if(NOT MARO_EMBREE_DLL)
    get_target_property(MARO_EMBREE_DLL embree IMPORTED_LOCATION)
endif()
if(NOT MARO_EMBREE_DLL)
    get_target_property(MARO_EMBREE_DLL embree IMPORTED_LOCATION_DEBUG)
endif()

find_program(MARO_DUMPBIN_EXECUTABLE NAMES dumpbin)
if(NOT MARO_EMBREE_DLL OR NOT EXISTS "${MARO_EMBREE_DLL}")
    message(WARNING
        "Maro: could not locate the imported Embree DLL, so the tbb12.dll "
        "conflict check was skipped. If loadPlugin later fails with "
        "ERROR_PROC_NOT_FOUND, reinstall embree without the 'tasking-tbb' "
        "feature (see vcpkg.json).")
elseif(NOT MARO_DUMPBIN_EXECUTABLE)
    message(WARNING
        "Maro: dumpbin was not found on PATH, so the tbb12.dll conflict check "
        "on '${MARO_EMBREE_DLL}' was skipped. Configure from a Visual Studio "
        "developer shell to enable it.")
else()
    execute_process(
        COMMAND "${MARO_DUMPBIN_EXECUTABLE}" /dependents "${MARO_EMBREE_DLL}"
        OUTPUT_VARIABLE MARO_EMBREE_DEPENDENTS
        ERROR_VARIABLE  MARO_EMBREE_DEPENDENTS_ERR
        RESULT_VARIABLE MARO_EMBREE_DEPENDENTS_RESULT
        OUTPUT_STRIP_TRAILING_WHITESPACE)
    if(NOT MARO_EMBREE_DEPENDENTS_RESULT EQUAL 0)
        message(WARNING
            "Maro: 'dumpbin /dependents ${MARO_EMBREE_DLL}' failed "
            "(${MARO_EMBREE_DEPENDENTS_RESULT}): ${MARO_EMBREE_DEPENDENTS_ERR}. "
            "The tbb12.dll conflict check was skipped.")
    else()
        string(TOLOWER "${MARO_EMBREE_DEPENDENTS}" MARO_EMBREE_DEPENDENTS_LOWER)
        if(MARO_EMBREE_DEPENDENTS_LOWER MATCHES "tbb[0-9]*\\.dll")
            message(FATAL_ERROR
                "Maro: the resolved Embree (${MARO_EMBREE_DLL}) imports TBB. "
                "That build cannot be loaded into Maya: Maya already has its "
                "own tbb12.dll in the process, the Windows loader reuses a "
                "module by base name, and Maya's copy does not export the "
                "symbols this Embree needs -- loadPlugin would fail with a "
                "bare ERROR_PROC_NOT_FOUND and no hint at the cause. Rebuild "
                "or reinstall Embree with EMBREE_TASKING_SYSTEM=INTERNAL, i.e. "
                "without vcpkg's default 'tasking-tbb' feature (the feature "
                "list this project needs is pinned in vcpkg.json; note that "
                "the build tree resolves packages classic-mode out of the "
                "global vcpkg installed tree, not from that manifest).")
        endif()
        message(STATUS
            "Maro: Embree at '${MARO_EMBREE_DLL}' imports no TBB -- safe to "
            "load inside Maya.")
    endif()
endif()
# --------------------------------------------------------------------------

add_library(maro_lidar STATIC
    src/RayPattern.cpp
    src/ScanEngine.cpp
    src/PointCloudPacking.cpp
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
