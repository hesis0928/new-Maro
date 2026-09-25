# -*- coding: utf-8 -*-
"""마스터 레퍼런스 파이프라인 공통 설정. 모든 스크립트가 여기서만 경로/오버라이드를 읽는다.

위치: `tools/masterref/`(2026-09-24에 임시 스크래치패드에서 옮겨옴 — 임시 폴더 정리로
한 번 통째로 날아간 적이 있어 저장소 안으로 들였다). `work/`·`out/`·`reports/`는 생성물이다."""
import os, sys, pathlib

HERE = pathlib.Path(__file__).resolve().parent     # tools/masterref
REPO = HERE.parent.parent                          # 저장소 루트
SCRATCH = HERE                                     # build_taxonomy.py가 스크립트와 같은 폴더에 있다
sys.path.insert(0, str(SCRATCH))          # build_taxonomy 재사용

# 마스터는 이 저장소 안이므로 상대 경로로 유도한다(체크아웃 위치가 바뀌어도 따라온다).
MASTER_SRC = REPO / "docs" / "maro-master-reference.md"
VAULT_ROOT = pathlib.Path(r"C:\Users\ckd30\OneDrive\Documents\Maro Project")
LIVE_DIR = VAULT_ROOT / "Master Reference"
EXISTING_DIR = VAULT_ROOT / "Maya Ver-2026.1"
WORK = HERE / "work"; EDIT = HERE / "edit"; OUT = HERE / "out" / "Master Reference"; REPORTS = HERE / "reports"

LAYER_REF, LAYER_NOTE, LAYER_FAIL = "Maro Reference", "Maro Note", "Maro Failure"
ROOT_HUB = "Intro Master Reference"

# 장 폴더 표시명 (## N. 헤딩은 파일명으로 못 씀)
CHAPTER_TITLES = {
    0: "00 이 문서에 대하여", 1: "01 프로젝트 개요와 아키텍처", 2: "02 저장소 지도",
    3: "03 빌드 시스템과 개발 환경", 4: "04 역사와 레거시", 5: "05 기반 라이브러리",
    6: "06 Maya 플러그인", 7: "07 파이썬 계층", 8: "08 테스트 체계",
    9: "09 설계 문서 연대기", 10: "10 횡단 기법", 11: "11 키워드·용어 사전", 12: "12 계약 색인",
}
# 절 파일명 오버라이드 (자동 유도가 어색한 것만)
SECTION_TITLE_OVERRIDES = {
    "6.6": "6.6 브리지 런타임", "6.7": "6.7 진단·센티널·삭제 규칙", "6.8": "6.8 LiDAR·포인트클라우드·충돌",
    "6.9": "6.9 UI 브리지", "7.15": "7.15 합성 데이터",
}
# §14 분류 폴더
FAIL_CLASSES = [
    ("BLD", "빌드·링크·툴체인"), ("CRA", "런타임 크래시·UB·메모리"), ("UNIT", "논리 — 단위·좌표·프레임"),
    ("DG", "논리 — Maya DG·API 함정"), ("BRG", "브리지·스레드·수명"), ("IPC", "프로세스·IPC·Windows"),
    ("DIAG", "진단 서브시스템"), ("UI", "UI·Qt·Python"), ("TST", "테스트 결함"), ("PLT", "플랫폼 한계"),
    ("SEC", "보안·권한"), ("HYP", "반증된 가설·문서 정정"), ("DROP", "계획 단계 폐기 기술"), ("OPEN", "미해결·이월"),
]
CAT_TAGS = {
    "컴퓨터과학 일반": "cat/cs", "C++ 언어·라이브러리": "cat/cpp", "빌드·툴체인": "cat/build", "Maya": "cat/maya",
    "Python·Qt": "cat/python-qt", "ROS 2": "cat/ros2", "기하·수학": "cat/geometry", "Windows": "cat/windows",
    "파일 포맷·인코딩": "cat/fileformat", "Maro 고유": "cat/maro", "개발 프로세스": "cat/process",
}
# 가지 폴더 이름 오버라이드(금지 문자)
BRANCH_FOLDER_OVERRIDES = {"명명된 파이프·I/O": "명명된 파이프·I-O"}
TERM_FILENAME_OVERRIDES = {}   # 원문 용어 문자열 → 파일 basename (70자 초과 등)
MERGES = {"행렬식 +1": "행렬식(det) +1", "퇴화축": "퇴화 축",
          "켤레 불변(conjugation invariance) vs 벡터 재배치": "켤레(conjugation) 불변 vs 벡터 재배치"}  # term_key → 생존 term_key (같은 최상위 카테고리일 때만)
EXTRA_ALIASES = {}             # term_key → [추가 표면형]
PREFER = {"CP949": "cp949", "MARO_PLUGIN_PY_MODULES": "maro_plugin_py_modules", "skinCluster": "skincluster"}  # 표면형 → term_key (모호 해소)
STOPWORDS = {"text", "time", "string", "bool", "int", "double", "float", "value", "name", "path", "file", "node", "data"}
HUB_STOPLIST = {"Maya", "ROS 2", "C++", "Python", "CMake", "Windows", "프로세스", "플러그인", "스레드", "노드", "커맨드",
                "테스트", "빌드", "DLL", "Qt", "PySide6", "Embree", "vcpkg", "gtest", "mayapy", "URDF", "DDS", "rclcpp"}
SUBKNOW_MAP = {}               # (§13 item, 하위지식 제목) → term_key
CROSS_VAULT_LINKS = {}         # term_key → 기존 vault 노트 basename (예: "노드": "Intro Node")

LINK_MODE = "all"              # "all" | "first-per-note"
CODE_ALIAS_STYLE = "plain"     # "backtick" | "plain" — P0 미확인이라 보수적으로 plain
PAD_MINOR = False              # True면 절 번호를 10.02 식으로
TERM_NAME_MAX = 70
SECTION_NAME_MAX = 60
FAIL_NAME_MAX = 50

# ---- 노트 보강(2026-09-16 계획): 집필 필드와 발췌 상한
ORIG_F_LABELS = ("증상", "근본 원인", "발견 경위", "해결/결정", "재발 방지", "출처", "근거", "대체", "시점", "상태")  # §14 원본 필드(한 줄)
AUTHORED_F = ("발단", "원인 해설", "증거", "해결책", "교훈")          # §14 집필 필드(다중 행) — 이 순서로 렌더
AUTHORED_T = ("직관", "동작", "예시", "관련 코드", "증거", "함정", "교훈")  # §16 집필 필드(다중 행) — 이 순서로 렌더
EXCERPT_CAPS = {"term_body": 12, "term_body_other": 8, "term_body_primary_min": 6, "term_ctx": 6, "row10": 4, "row11": 2, "term_fail_inline": 6,
                "fail_body": 10, "fail_ctx": 6, "fail_row10": 4, "fail_row9": 4, "fail_mentions": 8, "hub_stop": 5}
SEC16_FILE = None              # None이면 §16은 마스터 안. 파일 경로를 주면 그 파일이 §16 원천(마스터 비대화 대비)
EDIT14 = HERE / "edit14"; EDIT16 = HERE / "edit16"
LAYER_EXCERPT = "Maro Excerpt"   # 기계 발췌 층(용어·실패 노트의 `## 발췌 → 상세` 링크로 진입)
EXCERPT_SUFFIX = " 발췌"
