# -*- coding: utf-8 -*-
"""terms-collected.md (용어|분류|절|깊이) → §15 용어 분류 체계 마크다운.
용어 셀은 ' / ' 로 분리(복수 용어), 백틱/공백 정규화 키로 중복 통합(첫 등장 절 우선)."""
import sys, re, collections

SRC, DST = sys.argv[1], sys.argv[2]

# ---------- 최상위 카테고리와 중간 사슬/필요 하위 개념 ----------
TOP_ORDER = ["컴퓨터과학 일반", "C++ 언어·라이브러리", "빌드·툴체인", "Maya", "Python·Qt", "ROS 2",
             "기하·수학", "Windows", "파일 포맷·인코딩", "Maro 고유", "개발 프로세스"]

# sub: (사슬 중간 개념들, 필요 하위 개념)
SUBS = {
 ("컴퓨터과학 일반","동시성"): ("운영체제 > 프로세스·스레드 > 동시성", "스레드·뮤텍스/락·원자 연산·메모리 순서·교착·경쟁 조건(TOCTOU)·재진입"),
 ("컴퓨터과학 일반","운영체제·프로세스"): ("운영체제", "프로세스·핸들·환경변수·페이지 캐시·시계(벽시계/단조)·종료 코드"),
 ("컴퓨터과학 일반","IPC"): ("운영체제 > 프로세스 간 통신", "파이프·공유 메모리·메시지 경계·타임아웃·직렬화"),
 ("컴퓨터과학 일반","자료구조·알고리즘"): ("알고리즘·자료구조", "복잡도(O 표기)·큐/덱·해시 함수·그래프 순회(BFS/DFS)·순환 방어"),
 ("컴퓨터과학 일반","소프트웨어 설계 원칙"): ("소프트웨어 공학 > 설계 원칙", "단일 진실 원천·불변식·계약·소유권·멱등성·YAGNI·명시적 실패"),
 ("컴퓨터과학 일반","네트워크"): ("네트워크", "TCP/UDP·포트·멀티캐스트·도메인"),
 ("컴퓨터과학 일반","보안"): ("보안 원칙", "최소 권한·이름 선점·사칭·상대 경로"),
 ("C++ 언어·라이브러리","언어 핵심(RAII·수명·예외)"): ("언어 핵심", "소멸자 순서·스택 되감기·noexcept·정적 저장 기간·소유권(unique_ptr)·이동 의미론"),
 ("C++ 언어·라이브러리","표준 라이브러리"): ("표준 라이브러리(STL)", "std::atomic·std::thread·chrono·optional·locale·mutex·deque"),
 ("C++ 언어·라이브러리","서드파티 라이브러리"): ("서드파티 라이브러리(Boost·nlohmann·Embree·gtest)", "헤더 온리 vs 링크·ABI·DLL 의존·예외 계열"),
 ("C++ 언어·라이브러리","관용구·패턴"): ("관용구·패턴", "RAII 가드·pImpl·thread_local·정적 초기화"),
 ("빌드·툴체인","CMake"): ("CMake", "타깃·프로퍼티·제너레이터 표현식·커스텀 커맨드·find_package·컨피그"),
 ("빌드·툴체인","CTest"): ("CMake > CTest", "add_test·ENVIRONMENT(_MODIFICATION)·fixture·RUN_SERIAL·TIMEOUT"),
 ("빌드·툴체인","MSVC·MSBuild"): ("MSVC 툴체인", "컴파일 옵션(/utf-8,/EHsc,/Zi)·CRT 종류·링커 오류 코드(LNKxxxx)·PDB·멀티 컨피그"),
 ("빌드·툴체인","패키지 관리(vcpkg)"): ("패키지 관리", "classic/manifest 모드·포트·트리플릿·DLL 스테이징"),
 ("빌드·툴체인","개발 환경"): ("개발 환경", "VS Dev Shell·vswhere·환경변수 주입·PATH"),
 ("빌드·툴체인","배포·스테이징"): ("배포·스테이징", "스테이징 디렉터리·모듈 파일(.mod)·DLL 검색·POST_BUILD vs OUTPUT"),
 ("Maya","플러그인 아키텍처"): ("플러그인 아키텍처", "initialize/uninitializePlugin·MFnPlugin·.mll 로드/언로드·등록 레지스트리·devkit"),
 ("Maya","DG(의존성 그래프)"): ("DG(의존성 그래프)", "노드·어트리뷰트·플러그·dirty 전파(attributeAffects)·compute·데이터블록·논리/물리 인덱스"),
 ("Maya","DAG"): ("DAG", "트랜스폼/셰이프·MDagPath·인스턴싱·월드 행렬·부모/자식"),
 ("Maya","C++ API(함수 집합·메시지)"): ("C++ API", "MObject·MFn* 함수 집합·MStatus·MMessage 콜백·MString"),
 ("Maya","커맨드·undo"): ("커맨드·undo", "MPxCommand doIt/redoIt/undoIt·MSyntax·MDGModifier·undo 큐·undoInfo 청크"),
 ("Maya","Python 층(cmds·API 2.0)"): ("Python 층", "maya.cmds(UI 단위, undoable)·maya.api.OpenMaya(내부 단위)·이름 해석·플래그"),
 ("Maya","MEL"): ("MEL", "프로시저·전역 변수·source·whatIs·파싱 규칙"),
 ("Maya","단위 체계"): ("단위 체계", "내부 단위(cm/rad)·UI 단위·kAngle/kDistance·unitConversion·currentUnit"),
 ("Maya","UI 컨트롤"): ("UI 컨트롤", "workspaceControl·formLayout/paneLayout·modelPanel·menu·scriptJob·evalDeferred"),
 ("Maya","Qt 통합"): ("Qt 통합", "MQtUtil·포인터↔UI 이름·QApplication 팔레트"),
 ("Maya","Viewport 2.0"): ("Viewport 2.0", "MPxDrawOverride 단계(prepareForDraw/addUIDrawables)·MUserData·MUIDrawManager·classification·setGeometryDrawDirty"),
 ("Maya","평가·스레딩(PEM)"): ("평가 관리자(PEM)", "스케줄링 타입·워커 스레드·메인 스레드 전용 API·MPxThreadedDeviceNode"),
 ("Maya","배치 모드(mayapy)"): ("배치 모드", "maya.standalone·유휴 큐 부재·QGuiApplication·ogsRender"),
 ("Maya","리깅"): ("리깅", "joint·skinCluster·인플루언스·가중치"),
 ("Maya","카메라·렌더링(Arnold)"): ("렌더링", "카메라 파라미터·Film Fit·defaultResolution·AOV(MtoA)·oiiotool"),
 ("Maya","설정·prefs"): ("설정", "optionVar·userPrefs·internalVar"),
 ("Maya","배포(모듈 파일)"): ("배포", ".mod 규격·MAYA_MODULE_PATH·MAYA_PLUG_IN_PATH·requiredPlugin"),
 ("Python·Qt","Python 언어·표준 라이브러리"): ("Python", "예외 시맨틱(finally)·클로저·subprocess·os/struct·sys.path·문자열 리터럴"),
 ("Python·Qt","PySide6/Qt"): ("Qt(PySide6)", "QObject 수명(shiboken)·이벤트/포커스·앱 객체·플랫폼 플러그인·위젯/레이아웃"),
 ("ROS 2","rclcpp·클라이언트 계층"): ("클라이언트 라이브러리(rclcpp)", "Context·Node·Publisher/Subscription·Executor·spin·InitOptions"),
 ("ROS 2","메시지·토픽·QoS"): ("메시지·토픽", ".msg 정의·네임스페이스·QoS·DDS·typesupport"),
 ("ROS 2","TF·좌표 규약(REP)"): ("TF·좌표 규약", "프레임 트리·REP-103/105·child_frame_id·robot_state_publisher"),
 ("ROS 2","URDF"): ("URDF", "link/joint/origin/axis/limit/mimic·rpy 고정축·package:// URI·check_urdf"),
 ("ROS 2","Windows 통합·빌드"): ("Windows 통합", "install/include·DLL 154개·vendor bin·typesupport 링크"),
 ("ROS 2","생태계·도구"): ("생태계·도구", "RViz·ros2 CLI·rclpy·ros2_control·Gazebo"),
 ("기하·수학","좌표계·변환"): ("선형대수 > 좌표계·변환", "회전 행렬·행/열벡터 관례·행렬식·켤레(conjugation)·상대 변환"),
 ("기하·수학","회전 표현"): ("선형대수 > 회전 표현", "쿼터니언·오일러(순서/intrinsic·extrinsic)·반각·짐벌 특이점"),
 ("기하·수학","계산기하"): ("계산기하", "볼록성·분리축(SAT)·AABB·볼록 껍질(QuickHull)·레이 교차·eps"),
 ("기하·수학","카메라 모델"): ("카메라 모델", "핀홀·내부 행렬(fx,fy,cx,cy)·투영/역투영·planar/radial depth"),
 ("기하·수학","수치"): ("수치 해석", "부동소수·상대/절대 오차·NaN·클램프·보간·외삽"),
 ("기하·수학","색·영상"): ("색·영상", "휘도(BT.601)·sRGB·래스터"),
 ("Windows","커널 객체·동기화"): ("커널 객체", "핸들·시그널 상태·대기 함수·명명(Global\\)·뮤텍스/이벤트"),
 ("Windows","프로세스·job object"): ("프로세스 관리", "CreateProcess 플래그·상속·콘솔·job object·breakaway"),
 ("Windows","명명된 파이프·I/O"): ("I/O", "overlapped·메시지 모드·CancelIoEx·ERROR_* 코드"),
 ("Windows","COM·WMI"): ("COM·WMI", "아파트먼트·프록시 보안·Win32_Process·ReturnValue"),
 ("Windows","로더·DLL"): ("로더", "DLL 검색 순서·LoadLibraryEx·모듈 핸들·GetModuleFileName"),
 ("Windows","디버깅"): ("디버깅", "미니덤프·예외 코드·dbghelp·ASan·힙 손상"),
 ("Windows","파일 시스템·시간"): ("파일 시스템·시간", "공유 모드·mtime·GetTickCount64·last-error"),
 ("Windows","보안"): ("보안", "SQOS·FILE_FLAG_FIRST_PIPE_INSTANCE·상대 경로 실행"),
 ("파일 포맷·인코딩","JSON·JSON Lines"): ("텍스트 직렬화", "줄 단위 독립·strict UTF-8·파서 예외 계열"),
 ("파일 포맷·인코딩","3D·영상 포맷"): ("바이너리 포맷", "STL·PLY·PFM·EXR·엔디안·정렬·struct 팩"),
 ("파일 포맷·인코딩","문자 인코딩"): ("문자 인코딩", "UTF-8·CP949·코드페이지·로케일·이스케이프"),
 ("Maro 고유","노드·어트리뷰트 계약"): ("노드·어트리뷰트 계약", "축·능력 노드 7종·capType·1차 구동·controlMode·바인딩·단위 정책"),
 ("Maro 고유","브리지 런타임"): ("브리지 런타임", "펌프·유계 큐·Maro 소유 Context·발행 스레드·디바이스 노드·델타체크"),
 ("Maro 고유","진단 생태계"): ("진단 생태계", "boad·book(정본/스필)·onfix·저널·감시자·remedy·패널 프레젠터"),
 ("Maro 고유","LiDAR·포인트클라우드·충돌"): ("LiDAR·포인트클라우드", "ScanEngine·kMaxRaysPerScan·decimation·CollisionEngine·프리뷰"),
 ("Maro 고유","UI(MaroUI·SONE·ONE·패널)"): ("UI", "MaroUI·SONE·ONE/GSON·마킹 메뉴·설정/LiDAR/능력 패널·Tech Diag"),
 ("Maro 고유","URDF·합성 데이터"): ("내보내기·합성 데이터", "축 트리·링크 프레임·스킨 분할·볼록 껍질·AOV·역투영"),
 ("Maro 고유","계약·상수·이름"): ("계약·상수", "필드 수 상수·이름 계약·환경변수·optionVar·TypeId"),
 ("Maro 고유","역사·폐기·미해결"): ("역사", "레거시 세대·폐기 결정·이월 항목"),
 ("Maro 고유","테스트 인프라"): ("테스트 인프라", "maroQtBatch·피어·오케스트레이션·book 격리·트레이스"),
 ("개발 프로세스","SDD·리뷰 흐름"): ("SDD", "브레인스토밍→스펙→플랜→구현자/리뷰어→최종 리뷰→체크리스트"),
 ("개발 프로세스","테스트 설계·변이 검증"): ("테스트 설계", "변이 검증·픽스처 함정·값 단언·연산 횟수 성능"),
 ("개발 프로세스","문서 관례"): ("문서 관례", "정정 박스·실측/추론·Global Constraints·자기 검토"),
 ("개발 프로세스","디버깅 절차"): ("디버깅 절차", "덤프→심볼화→프로세스 안 스택→ASan"),
}

def classify(cat, term):
    """분류 문자열(+용어 힌트) → (top, sub)"""
    c = cat; t = term.lower()
    has = lambda *ks: any(k in c for k in ks)
    th = lambda *ks: any(k in t for k in ks)
    # ---- Maro
    if has("Maro") or has("문서 구조"):
        if has("진단","해시","JSON","IPC"): return ("Maro 고유","진단 생태계")
        if has("URDF","Arnold","카메라"): return ("Maro 고유","URDF·합성 데이터")
        if has("UI","Qt"): return ("Maro 고유","UI(MaroUI·SONE·ONE·패널)")
        if has("테스트"): return ("Maro 고유","테스트 인프라")
        if has("레거시","폐기","미해결","실측"): return ("Maro 고유","역사·폐기·미해결")
        if has("상수","배포","빌드","OS"): return ("Maro 고유","계약·상수·이름")
        if th("boad","book","journal","저널","sentinel","감시자","워치독","remedy","해법","diag","sitetag","crash","패널","panel","presenter","spill","스필","hash","해시","onfix","activecommand","scopedcommand","prioranalysis","knownbefore","loadmerged","pathforprocess","processidfrompath","예산","억제","suppress","budget","sweep","한 세션","레코드","문턱","접기","hidden","applyunavailable","메모이제이션","markabnormal","빠른 실패","fast fail","kdidnot","연속 카운터","백오프","관측","행(hang","ghost","offix","osbridge","servedfrombook","errorhash","m:<sev","notcaptured","notapplicable","분석"): return ("Maro 고유","진단 생태계")
        if th("lidar","라이다","scan","스캔","point","포인트","충돌","collision","ray","레이","프리뷰","decimat","setmin","setmax","rangemin","rangemax","mayapermeter","visualize","offsettranslate","offsetrotate","effectiveworld","directionbias","placeholder","targetmesh","verticalsamples","horizontalsamples","kmaxrays","preview"): return ("Maro 고유","LiDAR·포인트클라우드·충돌")
        if has("동시성","ROS 2","C++") or th("펌프","pump","큐","queue","context","컨텍스트","스레드","thread","runtime","브리지","bridge","spin","executor","pool","delta","델타","normalize","정규화","skip","sample","drain","collect","device","디바이스","seed","시딩","setdouble","updaterate","frameid","스로틀","throttle","내리고","2초","isthreadalive","publish","발행","commandout","commandrecord","rosrun","roscontext","mainthreadqueue","enqueue","ontimer","dropped","poolexhausted","ticks"): return ("Maro 고유","브리지 런타임")
        if th("urdf","<link","링크 이름","joint","조인트","convex","hull","껍질","stl","aov","depth","pfm","intrinsic","역투영","skin","스킨","influence","mesh","buildaxistree","루트","axisvector","켤레","ns:cube","_resolve","_axisparent","consumedshapes","cluster","-0.0","camera","addattr","마커","xcam","ycam","−z","writeply","dominant","assigntriangle","jointtype","computerelative","buildurdfxml","sanitize","axisalignedbox","mayatriangles","binarystl","_linkframe","_linkmesh","_split","_write","_buildrobot","export","oiiotool","calibration json","해상도 불일치"): return ("Maro 고유","URDF·합성 데이터")
        if th("sone","gson","maroui","마킹","메뉴","tech diag","패널","창","calibration","캘리브","hud","dagmenu","proxy","프록시","격리","_wrapper","복원","_open_","peel","_deleteaxis","유일 자식","cancel","씬 손상","_cleanup","_cleaned","_isunderhelper","expandrange","present-then","stop()","start()","refreshifopen","_onclosing","_onidle","_syncproxy","_refresh","_attrs","_panel_classes","opencapabilitypanel","openlidarpanel","teardown","buildui","closecommand","_embedded","rowsholder","selectionholder","_check","remedyfill","remedyrename","suggestdis","adjacentmesh","checklimit","checkjoint","checkmesh","checklidar","refinemesh","_readcurrent","_collect","limitproximity","proximity","emptyjointname","duplicatejointname","nodriveractive","aabb 겹침","unknown"): return ("Maro 고유","UI(MaroUI·SONE·ONE·패널)")
        if th("maroqtbatch","peer","피어","session","오케스트","trace","fixture","book_dir","book 루트","_pump","pump_idle","pid_marker","commandthreadticks","미끼","decoy","write_live"): return ("Maro 고유","테스트 인프라")
        if th("폐기","레거시","이연","미착수","미확인","미해결","v1","phase","layer","slice","슬라이스","s1","s2","s4","s5","pillars","기둥","core kernel","b-1","b-2","c-1","c-2","yagni","모션캡처","미사용","드리프트","교훈","횡단","연결점","함정","랩 미정규","two-track","투 트랙","track","viewportstreamer","image_bridge","control_bridge","debugutility","management","wsl","go/no-go","pass","fail"): return ("Maro 고유","역사·폐기·미해결")
        if th("fields","필드","상수","kmax","threshold","이름 계약","optionvar","환경","typeid","계약","contract","_name","maro_","maroset","domainid","등록 순서","사전(","runpluginpython","robotname","maro.mod","maro_plugin_py_modules","0x001351","kunchanged","row_fields","detail_fields","axis_fields","capability_fields","lidar_query","min_collision"): return ("Maro 고유","계약·상수·이름")
        if th("axis","축","capabilit","능력","captype","controlmode","바인딩","bind","limit","coupling","rotation","translation","sensor","conventio","jointname","displayname","broadcast","primary","1차","family","계열","orphan","고아","연쇄","클램프","ratio","offset","islinear","occupied","kcapability","mismatch","conflict","alreadyconnected","indexoccupied","negativeindex","notconnected","iscapabilitynode","디포머","undo 정합","양방향","실시간"): return ("Maro 고유","노드·어트리뷰트 계약")
        if has("설계","수학","수치","단위","알고리즘","DG"): return ("Maro 고유","노드·어트리뷰트 계약")
        return ("Maro 고유","노드·어트리뷰트 계약")
    # ---- Maya
    if has("Maya","Arnold","MtoA","devkit"):
        if has("Viewport"): return ("Maya","Viewport 2.0")
        if has("단위"): return ("Maya","단위 체계")
        if has("MEL"): return ("Maya","MEL")
        if has("cmds","Python","API 2.0"): return ("Maya","Python 층(cmds·API 2.0)")
        if has("커맨드","undo"): return ("Maya","커맨드·undo")
        if has("DAG"): return ("Maya","DAG")
        if has("DG"): return ("Maya","DG(의존성 그래프)")
        if has("Qt"): return ("Maya","Qt 통합")
        if has("UI","설정","환경") and not has("설정·prefs"):
            if has("설정") or th("optionvar","prefs","internalvar"): return ("Maya","설정·prefs")
            return ("Maya","UI 컨트롤")
        if has("배치","플랫폼"): return ("Maya","배치 모드(mayapy)")
        if has("리깅"): return ("Maya","리깅")
        if has("Arnold","MtoA","렌더","카메라"): return ("Maya","카메라·렌더링(Arnold)")
        if has("배포"): return ("Maya","배포(모듈 파일)")
        if has("동시성","성능") or th("pem","parallel","schedul","thread","스레드","워커"): return ("Maya","평가·스레딩(PEM)")
        if has("플러그인","빌드","devkit") or th("plugin","mfnplugin","initialize","register","deregister",".mll","mnoplugin","freelibrary","dll_process"): return ("Maya","플러그인 아키텍처")
        if has("디버깅","수학","설계","테스트","폐기","인코딩","Maro"):
            if th("mfn","mobject","mplug","mdag","mstring","mselection","mtransformation","meuler","mquaternion","mmatrix","mbounding"): return ("Maya","C++ API(함수 집합·메시지)")
            if th("attribute","어트리뷰트","compute","plug","플러그","dirty","message"): return ("Maya","DG(의존성 그래프)")
            if th("cmds","listconnections","getattr","setattr","parent(","ls(","file(","refresh","currentunit","filterexpand","xform"): return ("Maya","Python 층(cmds·API 2.0)")
            if th("viewport","draw","render","ogs"): return ("Maya","Viewport 2.0")
            if th("workspacecontrol","modelpanel","menu","scriptjob","panel","layout","dialog"): return ("Maya","UI 컨트롤")
            return ("Maya","C++ API(함수 집합·메시지)")
        # plain "Maya·API" / "Maya"
        if th("mpxthreadeddevice","threadhandler","memorypool","pushthreaddata","popthreaddata","beginthreadloop","live","framerate","schedulingtype","postevaluation","pem"): return ("Maya","평가·스레딩(PEM)")
        if th("mpxdrawoverride","muidrawmanager","muserdata","preparefordraw","adduidrawables","setgeometrydrawdirty","classification","mdrawregistry","mrenderer","hasuidrawables","supporteddrawapis"): return ("Maya","Viewport 2.0")
        if th("mpxcommand","msyntax","margdatabase","mdgmodifier","doit","undoit","redoit","setresult","isundoable","commandtoexecute","executecommand"): return ("Maya","커맨드·undo")
        if th("attribute","어트리뷰트","compute","mdatablock","mdatahandle","marraydatahandle","setstorable","setwritable","setkeyable","elementby","evaluatenumelements","logicalindex","mplug","message","typeid","mtypeid","unitconversion","kunknownparameter","setclean","attributeaffects","setdonotwrite","mfnnumeric","mfnenum","mfntyped","mfnunit","mfncompound","mfnmessage","mfnmatrix","mfnpointarray","mfndata","mobjecthandle","dg "): return ("Maya","DG(의존성 그래프)")
        if th("mdagpath","mfndagnode","mfntransform","inclusivematrix","extendtoshape","numberofshapes","intermediate","instanc","mfnmesh","getpoints","gettriangles","pop()","hasfn","kmesh","ktransform","childcount","parentcount","fullpathname","partialname","partialpathname","getapathto","mfnset","objectset"): return ("Maya","DAG")
        if th("mtimermessage","mnodemessage","mdgmessage","mscenemessage","addcallback","removecallback","kafterimport","mglobal","mayastate","mfnplugin","loadpath","findplugin","mstring","asutf8","setutf8","aschar","mselectionlist","mfncamera","mfnskincluster","getweights","mtransformationmatrix","meuler","mquaternion","mmatrix","mangle","mdistance","mboundingbox","mpoint","mvector","mstatus","mfn::"): return ("Maya","C++ API(함수 집합·메시지)")
        if th("workspacecontrol","modelpanel","paneLayout".lower(),"formlayout","menu","scriptjob","evaldeferred","isolateselect","textscrolllist","promptdialog","coloreditor","filedialog","undoinfo","optionvar","mqtutil","addwidgettomayalayout","findlayout","getcpppointer","internalvar"): return ("Maya","UI 컨트롤")
        if th("mel","whatis","dagmenuproc","uires","source","global proc","proc "): return ("Maya","MEL")
        if th("mayapy","standalone","batch","배치","ogsrender","qguiapplication"): return ("Maya","배치 모드(mayapy)")
        if th("skincluster","joint","influence","리깅"): return ("Maya","리깅")
        if th("film","aperture","focal","aov","arnold","mtoa","defaultresolution","pixelaspect","overscan","render","camera"): return ("Maya","카메라·렌더링(Arnold)")
        if th(".mod","module","requiredplugin","maya_plug_in_path","maya_module_path"): return ("Maya","배포(모듈 파일)")
        if th("cmds","listrelatives","listconnections","getattr","setattr","xform","exactworldboundingbox","filterexpand","pointposition","polylistcomponent","currentunit","refresh","file(new","createnode","cmds."): return ("Maya","Python 층(cmds·API 2.0)")
        return ("Maya","C++ API(함수 집합·메시지)")
    # ---- ROS 2
    if has("ROS 2","ROS2","로보틱스","URDF","DDS","TF"):
        if has("URDF") or th("urdf","<link","<joint","<axis","<limit","<mimic","<origin","revolute","prismatic","check_urdf","package://","rpy","xsd"): return ("ROS 2","URDF")
        if has("TF") or th("rep-1","tf","frame_id","z-up","right-hand","robot_state"): return ("ROS 2","TF·좌표 규약(REP)")
        if has("빌드","Windows") or th("idl","typesupport","rosidl","statistics","install/","dll"): return ("ROS 2","Windows 통합·빌드")
        if has("메시지","DDS","QoS") or th("msg","jointstate","pointcloud2","pointfield","laserscan","topic","토픽","qos","domain","도메인","namespace","네임스페이스","ring"): return ("ROS 2","메시지·토픽·QoS")
        if has("생태계","테스트","Maya","수치","수명","Python") and not th("context","executor","spin","node"):
            if th("rviz","cli","rclpy","rsp","gazebo","isaac","ros2_control","urdf_sensor","ray"): return ("ROS 2","생태계·도구")
        if th("rclcpp","context","executor","spin","node","publisher","subscription","init","shutdown","rcl_","rcutils","initoptions","reset"): return ("ROS 2","rclcpp·클라이언트 계층")
        if th("rviz","cli","rclpy","gazebo","isaac","ros2_control","urdf_sensor","sensor.h","계층","스택","rmw"): return ("ROS 2","생태계·도구")
        return ("ROS 2","메시지·토픽·QoS")
    # ---- Windows
    if has("Windows","Win32","COM","WMI","PE","job","로더","커널","DLL") and not has("Python") or has("MSVC·도구") and th("dumpbin"):
        if has("디버깅") or th("minidump","미니덤프","dbghelp","asan","sanitizer","dump","덤프","exception","0xc","gflags","pageheap","symbol","심볼","rva","pdb","stacktrace","dbgeng"): return ("Windows","디버깅")
        if has("보안") or th("sqos","identification","impersonat","first_pipe_instance","선점","사칭"): return ("Windows","보안")
        if has("COM","WMI") or th("wmi","win32_process","cosetproxyblanket","coinitialize","iwbem","com ","_bstr_t","comptr","returnvalue","execmethod"): return ("Windows","COM·WMI")
        if has("IPC") or th("pipe","파이프","overlapped","cancelioex","getoverlappedresult","readfile","writefile","connectnamedpipe","disconnectnamedpipe","error_io_pending","error_broken","error_no_data","flushfilebuffers","readmode","setnamedpipe"): return ("Windows","명명된 파이프·I/O")
        if has("프로세스","job") or th("createprocess","detached","create_no_window","breakaway","job object","job ","kill_on_job","assignprocess","isprocessinjob","console","콘솔","getconsolewindow","sw_hide","terminateprocess","openprocess","exit code","종료 코드","spawn"): return ("Windows","프로세스·job object")
        if has("로더","DLL","PE") or th("loadlibrary","altered_search","dll 검색","getmodulehandle","getmodulefilename","dumpbin","freelibrary","dll_process","모듈"): return ("Windows","로더·DLL")
        if has("파일","시간") or th("mtime","ofstream","remove()","gettickcount","steady_clock","system_clock","filesystem","공유 모드","lasterror","last-error","getlasterror"): return ("Windows","파일 시스템·시간")
        return ("Windows","커널 객체·동기화")
    # ---- Python / Qt
    if has("Python","Qt","PySide","UI"):
        if has("Qt","PySide","UI") and not has("Python·테스트","Python·설계","Python·인코딩"):
            if th("closure","클로저","finally","subprocess","os.","dup2","struct","sys.path","import","__main__","repr","리터럴","valueerror","runtimeerror"): return ("Python·Qt","Python 언어·표준 라이브러리")
            return ("Python·Qt","PySide6/Qt")
        if has("인코딩"): return ("파일 포맷·인코딩","문자 인코딩")
        return ("Python·Qt","Python 언어·표준 라이브러리")
    # ---- 빌드
    if has("빌드","CMake","MSVC","MSBuild","vcpkg","CTest","IDE","도구","배포","환경") and not has("설계·") :
        if has("CTest") or th("ctest","add_test","environment","fixture","run_serial","timeout","gtest_discover"): return ("빌드·툴체인","CTest")
        if has("vcpkg") or th("vcpkg","manifest","classic","port"): return ("빌드·툴체인","패키지 관리(vcpkg)")
        if has("MSVC","MSBuild") or th("lnk","cl ","/utf-8","/ehsc","/zi","/fsanitize","_iterator_debug","runtimelibrary","crt","postbuildevent","msbuild","pdb","dumpbin","c4819","codecvt"): return ("빌드·툴체인","MSVC·MSBuild")
        if has("IDE","환경") or th("vsdevcmd","vswhere","launch-vsdevshell","dev shell","환경 변수","path"): return ("빌드·툴체인","개발 환경")
        if has("배포") or th("스테이징","staging",".mod","module","copy_","post_build","output","install/bin","opt/"): return ("빌드·툴체인","배포·스테이징")
        if has("도구") or th("oiiotool","taskkill","invoke-cimmethod","wmi terminate","pdf"): return ("빌드·툴체인","개발 환경")
        return ("빌드·툴체인","CMake")
    # ---- C++
    if has("C++","라이브러리","Embree","nlohmann","gtest","Boost"):
        if has("동시성","시간") or th("atomic","thread","mutex","memory_order","chrono","steady","relaxed","acquire","release","lock","조인","join","terminate"):
            if th("atomic","chrono","steady","memory_order","optional","locale","imbue","deque","unique_ptr","std::"): return ("C++ 언어·라이브러리","표준 라이브러리")
            return ("C++ 언어·라이브러리","언어 핵심(RAII·수명·예외)")
        if has("패턴","설계") or th("raii","가드","guard","pimpl","thread_local","관용구","idiom","scoped"): return ("C++ 언어·라이브러리","관용구·패턴")
        if has("라이브러리","Embree","nlohmann","gtest","Boost","포맷","수치","I/O") or th("boost","nlohmann","embree","rtc","gtest","tbb","json","stacktrace","interprocess","dbgeng","type_error","parse_error","dump()","expect_","assert_","test_f"): return ("C++ 언어·라이브러리","서드파티 라이브러리")
        if th("std::","optional","locale","imbue","deque","unique_ptr","release()","numeric_limits","max_digits10","ostringstream","string_view","vector","atomic","thread","chrono"): return ("C++ 언어·라이브러리","표준 라이브러리")
        return ("C++ 언어·라이브러리","언어 핵심(RAII·수명·예외)")
    # ---- 파일 포맷/인코딩
    if has("포맷","인코딩","JSON","PDF"):
        if has("인코딩") or th("utf","cp949","코드페이지","로케일","locale","이스케이프","모지바케","bom"): return ("파일 포맷·인코딩","문자 인코딩")
        if has("JSON") or th("json","jsonl","lines"): return ("파일 포맷·인코딩","JSON·JSON Lines")
        return ("파일 포맷·인코딩","3D·영상 포맷")
    # ---- 기하/수학
    if has("기하","수학","회전","카메라","수치","선형대수","영상","색","알고리즘"):
        if has("알고리즘","그래프") and not has("기하"):
            if th("hull","껍질","sat","aabb","ray","레이","삼각형","triangle","horizon","conflict","가시","visib","극단","tetra","사면체","교차","intersect","볼록","convex"): return ("기하·수학","계산기하")
            return ("컴퓨터과학 일반","자료구조·알고리즘")
        if has("색","영상") or th("휘도","luma","bt.601","srgb","highlight","색"): return ("기하·수학","색·영상")
        if has("카메라") or th("핀홀","pinhole","fx","intrinsic","역투영","unproject","film","aperture","planar","radial","depth"): return ("기하·수학","카메라 모델")
        if has("회전") or th("쿼터니언","quaternion","오일러","euler","kxyz","kzyx","rpy","extrinsic","intrinsic","반각","짐벌","gimbal","atan2","asin","rotation order"): return ("기하·수학","회전 표현")
        if has("수치") or th("eps","epsilon","nan","isfinite","클램프","clamp","보간","interpol","외삽","extrapol","부동소수","float","오차","max_digits","1e-"): return ("기하·수학","수치")
        if th("hull","껍질","sat","aabb","separating","분리축","레이","ray","삼각형","triangle","horizon","conflict","가시","극단","사면체","교차","볼록","convex","tnear","tfar","기저","basis","정규직교","cross","외적","법선","normal","와인딩","winding"): return ("기하·수학","계산기하")
        return ("기하·수학","좌표계·변환")
    # ---- CS 일반
    if has("CS","동시성","OS","IPC","네트워크","아키텍처","자료구조"):
        if has("동시성") or th("mutex","락","lock","atomic","교착","deadlock","toctou","경쟁","race","재진입","스레드","thread","memory_order","release","acquire"): return ("컴퓨터과학 일반","동시성")
        if has("IPC") or th("파이프","pipe","shm","공유 메모리","메시지 경계","ipc"): return ("컴퓨터과학 일반","IPC")
        if has("네트워크") or th("tcp","udp","포트","multicast","멀티캐스트"): return ("컴퓨터과학 일반","네트워크")
        if has("자료구조","알고리즘") or th("큐","queue","deque","hash","해시","fnv","graph","그래프","bfs","dfs","o(","복잡도"): return ("컴퓨터과학 일반","자료구조·알고리즘")
        if has("아키텍처"): return ("컴퓨터과학 일반","소프트웨어 설계 원칙")
        return ("컴퓨터과학 일반","운영체제·프로세스")
    # ---- 설계 / 테스트 / 개발 프로세스 / 디버깅
    if has("보안"): return ("컴퓨터과학 일반","보안")
    if has("설계"):
        if th("변이","mutation","픽스처","fixture","단언","assert","테스트"): return ("개발 프로세스","테스트 설계·변이 검증")
        return ("컴퓨터과학 일반","소프트웨어 설계 원칙")
    if has("테스트"):
        if th("ctest","gtest","fixture","run_serial","environment") and not th("픽스처 함정"): return ("빌드·툴체인","CTest")
        return ("개발 프로세스","테스트 설계·변이 검증")
    if has("디버깅"): return ("개발 프로세스","디버깅 절차")
    if has("문서"): return ("개발 프로세스","문서 관례")
    if has("개발") or has("프로세스"):
        if th("변이","픽스처","단언","테스트","커버"): return ("개발 프로세스","테스트 설계·변이 검증")
        if th("정정","실측","추론","constraints","자기 검토","as-built","독스트링","체크리스트","go/no-go","blocked","관찰","정보성"): return ("개발 프로세스","문서 관례")
        if th("덤프","심볼","asan","디버깅"): return ("개발 프로세스","디버깅 절차")
        return ("개발 프로세스","SDD·리뷰 흐름")
    if has("생태계","로보틱스"): return ("ROS 2","생태계·도구")
    return ("컴퓨터과학 일반","소프트웨어 설계 원칙")

# ---------- 파싱 ----------
rows = []
for l in open(SRC, encoding="utf-8"):
    l = l.rstrip("\n")
    if not l or l.startswith("#"): continue
    p = l.split("|")
    if len(p) < 4: continue
    term_cell, cat, sec, depth = p[0].strip(), p[1].strip(), p[2].strip(), p[3].strip()
    depth_key = "심화" if depth.startswith("심화") else "개념"
    # split on ' / ' only
    parts = [x.strip() for x in re.split(r"\s+/\s+", term_cell) if x.strip()]
    for t in parts:
        rows.append((t, cat, sec, depth_key))

def norm(t):
    s = t.replace("`", "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"\(.*?\)$", "", s).strip()  # drop trailing parenthetical for key
    return s

entries = collections.OrderedDict()
for t, cat, sec, depth in rows:
    k = norm(t)
    if not k: continue
    if k in entries:
        e = entries[k]
        if sec not in e["secs"]: e["secs"].append(sec)
        if depth == "심화": e["depth"] = "심화"
    else:
        top, sub = classify(cat, t)
        entries[k] = {"term": t, "cat": cat, "top": top, "sub": sub, "secs": [sec], "depth": depth}

# ---------- 출력 ----------
by_top = collections.OrderedDict((t, collections.OrderedDict()) for t in TOP_ORDER)
for k, e in entries.items():
    by_top[e["top"]].setdefault(e["sub"], []).append(e)

def sec_ref(s): return "§" + s
def secs_str(e): return ", ".join(sec_ref(s) for s in e["secs"][:3]) + (" 외" if len(e["secs"]) > 3 else "")

out = []
out.append("\n---\n\n## 15. 용어 분류 체계 — 카테고리 트리와 종속 사슬\n")
out.append(f"§13의 모든 용어 표에서 추출한 **{len(entries)}개 용어**(복합 셀은 ` / `로 분리, 백틱·괄호 표기를 정규화해 중복 통합)를 "
           f"11개 최상위 카테고리 → 중간 종속 개념 → 용어의 사슬로 정리한다. §11 사전은 한 줄 정의, §13은 문맥·하위지식, §15는 "
           "\"이 용어를 이해하려면 어떤 상위 개념과 하위 개념이 필요한가\"를 답한다.\n")
out.append("### 15.0 읽는 법\n")
out.append("- **15.1 카테고리 트리**: 최상위 → 중간 종속 개념(사슬) → 용어. 각 중간 노드에 `필요 하위 개념`(그 가지의 용어를 이해하는 데 전제되는 개념)을 적는다. "
           "들여쓰기 목록이라 어떤 마크다운 뷰어에서도 읽힌다.\n"
           "- **15.2 용어별 사슬 표**: `용어 | 사슬(최상위 > 중간 > 용어) | 필요 하위 개념 | 깊이 | 해설 위치(→ §13.x.y)`. 깊이 `심화`인 용어는 해설 위치의 "
           "**하위지식** 블록에 수반 개념이 전부 나열돼 있다. 용어가 여러 절에 나오면 처음 완전 해설된 절을 먼저 적는다.\n"
           "- 카테고리 판정은 §13 용어 표의 `분류` 열에서 기계적으로 유도했으며(예: `Maya·DG` → Maya > DG), 경계 사례는 §13의 문맥을 기준으로 삼는다.\n")
# 15.1 trees
out.append("### 15.1 카테고리 트리\n")
for top in TOP_ORDER:
    subs = by_top[top]
    total = sum(len(v) for v in subs.values())
    out.append(f"\n#### 15.1.{TOP_ORDER.index(top)+1} {top} ({total}개)\n")
    out.append(f"- **{top}**")
    for sub, items in subs.items():
        chain, prereq = SUBS.get((top, sub), (sub, ""))
        out.append(f"  - **{sub}** — 사슬: {top} > {chain} · 필요 하위 개념: {prereq}")
        for e in items:
            d = "★" if e["depth"] == "심화" else "·"
            out.append(f"    - {d} {e['term']} (→ {sec_ref(e['secs'][0])})")
out.append("\n★ = 심화(해당 §13 항목의 하위지식 블록 참조), · = 개념(단발 설명으로 충분)\n")
# 15.2 table
out.append("### 15.2 용어별 종속 사슬 표\n")
out.append("| 용어 | 사슬 | 필요 하위 개념 | 깊이 | 해설 |")
out.append("|---|---|---|---|---|")
for top in TOP_ORDER:
    for sub, items in by_top[top].items():
        chain, prereq = SUBS.get((top, sub), (sub, ""))
        for e in items:
            pre = prereq + (f" · **{sec_ref(e['secs'][0])} 하위지식**" if e["depth"] == "심화" else "")
            term = e["term"].replace("|", "\\|")
            out.append(f"| {term} | {top} > {chain} > 용어 | {pre} | {e['depth']} | {secs_str(e)} |")
out.append("")
# stats
out.append("### 15.3 통계\n")
out.append("| 최상위 카테고리 | 중간 가지 수 | 용어 수 | 심화 용어 수 |")
out.append("|---|---|---|---|")
for top in TOP_ORDER:
    subs = by_top[top]
    n = sum(len(v) for v in subs.values()); d = sum(1 for v in subs.values() for e in v if e["depth"] == "심화")
    out.append(f"| {top} | {len(subs)} | {n} | {d} |")
out.append(f"| **합계** | {sum(len(v) for v in by_top.values())} | {len(entries)} | {sum(1 for e in entries.values() if e['depth']=='심화')} |")
out.append("")
open(DST, "w", encoding="utf-8").write("\n".join(out))
print("entries", len(entries))
for top in TOP_ORDER:
    print(top, {s: len(v) for s, v in by_top[top].items()})
