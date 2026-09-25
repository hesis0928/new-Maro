# -*- coding: utf-8 -*-
"""§10 은 표 위주라 원문 블록을 그대로 두고 장 도입·절마다 `**한 줄 요약:**` 만 삽입해 edit/c10.md 를 만든다."""
import io, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import config as C
from assemble_master import blocks_of

INTRO = """## 10. 횡단 기법 모음 — 서브시스템을 가로지르는 규율과 그 근거

**한 줄 요약:** 앞 절들에 흩어진 "같은 모양의 결정"을 열한 갈래(스레드·이벤트 루프·언로드·Undo·DG·단위·예외·IPC·UI·테스트·빌드)로 모은
체크리스트로, 각 항목은 **규칙 → 왜 → 어디서 → 어기면 무슨 일이 일어났는가(실측)** 순서입니다.

**쓰는 법:** 새 코드를 쓸 때 체크리스트로 씁니다. 표의 "어디서" 열은 그 규칙이 실제로 지켜지는 절과 파일이고, 규칙이 깨졌던 실측 사례는
§14 실패 카탈로그와 짝을 이룹니다.
"""

SUMMARY = {
    "10.1": "ROS 스레드·PEM 워커·메인 스레드의 경계를 어디에 두는가 — Maya API는 메인 스레드 전용이므로 두 큐만이 접점이고, 샘플에 컨텍스트를 실어 보내며, 메인 스레드 판정은 `initializePlugin`에서 붙잡은 스레드 id로 합니다.",
    "10.2": "콜백·타이머·scriptJob은 설치한 곳이 반드시 해제하고 정리는 `maroMainWindow.teardown()` 한 곳으로 모으며, 상시 큐(0.1s)와 발행 펌프(30Hz)를 분리하고 미루는 것은 커맨드 안이 아니라 호출 시점입니다.",
    "10.3": "언로드는 등록의 역순으로 브리지·감시자·큐를 먼저 내리고 드로우 오버라이드를 노드보다 먼저 해제하며, 보조 계층은 로드·언로드를 막지 않고, 프로세스가 끝나지 않으면 그 자체가 teardown 결함입니다.",
    "10.4": "사용자 구성 변경은 `MPxCommand` + `MDGModifier`(또는 `undoInfo` 청크)로, 매 프레임 런타임 데이터는 raw write로 — 두 쓰기 경로를 섞으면 undo 큐가 도배되거나 고아 노드가 남습니다.",
    "10.5": "`compute()`는 순수 계산, NaN 차단, 배열 플러그는 물리 인덱스 순회, 값이 흘러야 하면 복합 데이터·식별만이면 message, 사용자 값은 unit 타입·내부 전송은 plain double, `array()` 대신 `copyTo()` — DG를 다루는 열 가지 규칙입니다.",
    "10.6": "Maya→ROS 변환 수식은 한 곳에만 두고, 켤레 불변(origin·각도)과 벡터 재배치(`conventionAxis`)를 구분하며, `cmds`(UI 단위)와 `om2`(내부 단위)의 차이·`File>New`의 단위 되돌림·강체 링크 프레임·`kXYZ` rpy를 실측으로 못박은 규칙들입니다.",
    "10.7": "모든 콜백 최상위에 catch-all, 조용한 실패 금지, 검사 실패와 문제 없음을 구분, 부분 실패는 그 항목만 빼되 프로토콜 드리프트는 전파, 강등은 기본 모드, 이름은 Apply 시점에도 하나를 가리켜야 — 실패를 다루는 규칙들입니다.",
    "10.8": "모든 대기에 타임아웃, 이름은 PID 키로 한 곳에서, 메시지 모드 오버랩 파이프, 서버는 답장 직후 닫지 않기, job 탈출 3단계, `GetLastError()` 즉시 읽기, 프로세스별 저널 파일, 벽시계 금지 — Windows IPC·프로세스 규칙입니다.",
    "10.9": "컨테이너는 네이티브·Qt 위젯만 임베드, `setStyleSheet()` 금지, 싱글톤 재오픈, 순환 import 회피, C++↔Python 필드 수 상수 양쪽 핀, 클릭 자리를 스냅샷에 대고 풀지 않기 — UI 계층의 규칙들입니다.",
    "10.10": "Maya 없이 맞아야 하는 로직은 gtest로, 순수 함수와 씬 조회를 분리, 변이 검증과 픽스처 함정 점검, 값을 단언, 성능은 연산 횟수로, \"배치라서 불가능\"은 재검증, 전체 `ctest`, book 격리 — 테스트 규율입니다.",
    "10.11": "CMake ≥3.22·`/utf-8`·C++17, OUTPUT 기반 스테이징, TBB-free Embree 가드, vendor DLL 스테이징, `maro.mod` 이름 로드, `VsDevCmd.bat` 환경 파싱, 좀비 mayapy 대책 — 빌드·배포 규칙입니다.",
}


def main():
    text = io.open(C.WORK / "master.v0.md", encoding="utf-8").read()
    lines, idx = blocks_of(text)
    out = [INTRO]
    for num, summ in SUMMARY.items():
        s, e = idx[f"###:{num}"]
        body = lines[s:e]
        assert body[1].startswith("> 보강 참조"), body[:2]
        block = [body[0], body[1], "", f"**한 줄 요약:** {summ}", ""] + body[2:]
        # 블록 끝의 빈 줄 정리
        while block and block[-1].strip() == "": block.pop()
        out.append("\n".join(block) + "\n")
    io.open(C.EDIT / "c10.md", "w", encoding="utf-8", newline="\n").write("\n".join(out))
    print("wrote edit/c10.md")


if __name__ == "__main__":
    main()
