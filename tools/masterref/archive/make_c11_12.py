# -*- coding: utf-8 -*-
"""§11·§12 는 표/목록 위주라 원문 블록을 그대로 두고 장 도입·절마다 `**한 줄 요약:**` 만 삽입해 edit/c11-12.md 를 만든다."""
import io, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import config as C
from assemble_master import blocks_of

INTRO_11 = """## 11. 키워드·용어 사전

**한 줄 요약:** 문서 전체에 등장하는 이름과 기법을 Maro 고유 용어·Maya API·ROS 2·Windows·C++/빌드의 다섯 갈래로 한 줄씩 정리한 사전입니다 —
코드 심볼은 `등폭`, 개념은 굵게, 상세는 괄호의 절 참조이며 §15의 분류 체계가 이 사전을 용어 단위로 확장합니다.
"""

INTRO_12 = """## 12. 부록 — 계약 색인

**한 줄 요약:** 커맨드 35개·노드 11개·ROS 2 토픽·환경 변수·optionVar·UI 이름·파일 경로·상수처럼 C++/Python/테스트/사용자가 공유하는
"이름과 값의 계약"을 한 자리에 모은 색인입니다 — 여기 적힌 값이 바뀌면 양쪽을 함께 고쳐야 합니다.
"""

SUMMARY = {
    "11.1": "축·능력 노드·capType·controlMode·바인딩·링크·SONE/ONE/MaroUI·Tech Diag·5 Pillars·siteTag/errorHash·스필·저널·감시자·강등처럼 Maro가 스스로 만든 이름들의 뜻입니다.",
    "11.2": "`MPxLocatorNode`·`MPxThreadedDeviceNode`·`MPxDrawOverride`·`MDGModifier`·단위 어트리뷰트·message 어트리뷰트·배열 플러그 순회·`MQtUtil`·`workspaceControl`·`dagMenuProc`·PEM처럼 이 프로젝트가 기대는 Maya API와 개념의 쓰임입니다.",
    "11.3": "rclcpp 컨텍스트·`JointState`·`/tf`·`PointCloud2`·REP-103·DDS 도메인·URDF 요소와 관절 타입·`urdf_sensor`·`check_urdf`처럼 ROS 2와 로보틱스 쪽 용어입니다.",
    "11.4": "명명된 파이프·job object·WMI·콘솔 창 억제·명명된 뮤텍스·리브니스·단조 시계·DLL 검색·미니덤프/ASan·링커 에러·인코딩처럼 Windows와 시스템 쪽 용어입니다.",
    "11.5": "RAII 가드·원자 카운터·`BoundedQueue`·`std::optional`·FNV-1a·JSON Lines·Embree·SAT·QuickHull·파일 포맷·핀홀 역투영·gtest/CTest/CMake·devkit 매크로·SDD처럼 C++·빌드·기법 쪽 용어입니다.",
    "12.1": "등록 순 커맨드 35개의 인자/플래그·undo 가능 여부·용도입니다 — \"테스트 전용\"은 프로덕션 경로에 등장하지 않습니다.",
    "12.2": "노드 11개의 `MTypeId`(`0x001351xx` 대역)·베이스 클래스·어트리뷰트 long name입니다.",
    "12.3": "`/<robotName>/joint_states`·`/tf`·`/<robotName>/points`(Maya → ROS)와 `/<robotName>/joint_commands`(ROS → Maya)의 타입·방향·조건입니다.",
    "12.4": "book 디렉터리·스택 트레이스 킬 스위치·드로우 트레이스·테스트 경로·모듈 경로·DDS 도메인·ASan·PATH — 환경 변수와 그것을 읽는 자리입니다.",
    "12.5": "ROS 프록시 고정 대상과 설정 창의 네 항목을 저장하는 optionVar 다섯 개의 이름과 타입입니다.",
    "12.6": "C++ 언로드 MEL 정리와 Python이 같은 문자열을 써야 하는 workspaceControl·뷰포트·메뉴·프록시 그룹·MEL 전역 이름입니다.",
    "12.7": "스테이징된 플러그인·모듈 파일·감시자·book·저널·기록·테스트 book 루트·크래시 덤프·URDF/합성 데이터 출력·외부 의존 경로입니다.",
    "12.8": "펌프/큐 주기·델타 epsilon·레이 상한·프리뷰 상한·저널 예산·crashAdjacency 문턱·패널 최대 행·감시자 시간·필드 수·충돌 eps·기본 해상도처럼 코드에 박힌 상수와 위치입니다.",
}


def render(chapter, intro, lines, idx):
    out = [intro]
    for num, summ in SUMMARY.items():
        if not num.startswith(f"{chapter}."): continue
        s, e = idx[f"###:{num}"]
        body = lines[s:e]
        assert body[1].startswith("> 보강 참조"), body[:2]
        block = [body[0], body[1], "", f"**한 줄 요약:** {summ}", ""] + body[2:]
        while block and block[-1].strip() == "": block.pop()
        out.append("\n".join(block) + "\n")
    return out


def main():
    text = io.open(C.WORK / "master.v0.md", encoding="utf-8").read()
    lines, idx = blocks_of(text)
    out = render(11, INTRO_11, lines, idx) + render(12, INTRO_12, lines, idx)
    io.open(C.EDIT / "c11-12.md", "w", encoding="utf-8", newline="\n").write("\n".join(out))
    print("wrote edit/c11-12.md")


if __name__ == "__main__":
    main()
