<!-- geo-misc-01 기하·수학 › 색·영상 + 회전 표현 + 카메라 모델 + 수치 (24개) 2026-09-17 -->

#### RGBA vs BGRA

**직관:** 픽셀 4바이트의 채널 순서 — Maya 프레임버퍼는 R,G,B,A 순인데 OpenCV는 B,G,R,A를 기본으로 해석한다. 그대로 띄우면 빨강과 파랑이 뒤바뀌어 얼굴이 파랗게 나오는 "스머프 현상"이 난다.

**동작:** 레거시 `image_bridge`는 `M3dView::readColorBuffer`로 뷰포트 RGBA를 읽어 공유 메모리에 넣고, 수신 쪽이 `cv::Mat(h, w, CV_8UC4, buf)`로 감싼 뒤 `cv::cvtColor(image, image, cv::COLOR_RGBA2BGRA)`로 순서를 바꿔 표시·전송했다. 4K RGBA 한 프레임은 35MB라 매 프레임 복사가 비쌌고, 이 스트리밍 트랙은 현재 빌드 밖이다.

**예시:**
```cpp
cv::Mat image(height, width, CV_8UC4, local_buffer.data());   // 바이트는 RGBA
cv::cvtColor(image, image, cv::COLOR_RGBA2BGRA);             // OpenCV가 기대하는 BGRA로
```

**관련 코드:**
- `src/image_bridge/src/image_bridge_node.cpp:80-81` — Mat 래핑과 변환(레거시)
- `src/ViewportStreamer.cpp` — 뷰포트 읽기 쪽(레거시)

**증거:**
- §4.3, §4.3.1, §4.3.5

**함정:** 채널 순서 오류는 크래시가 아니라 "색이 이상함"으로만 나타나 알고리즘 버그로 오인하기 쉽다. 빨강 물체가 파랗게 보이면 먼저 채널 순서를 의심한다.

**교훈:** 바이트 버퍼를 다른 라이브러리에 넘길 때는 "레이아웃 계약"을 먼저 맞춘다. 같은 4바이트도 해석이 다르다.

#### OpenCV `CV_8UC4`

**직관:** OpenCV의 픽셀 타입 상수 — 8비트 부호 없는 정수(8U) 4채널(C4). 바이트 순서를 정하지 않으며, OpenCV 함수들이 BGR(A)로 "가정"할 뿐이다.

**동작:** `cv::Mat(h, w, CV_8UC4, ptr)`는 외부 버퍼를 복사 없이 감싼다. 타입은 "채널 4개, 각 1바이트"만 말하고 순서는 데이터에 달려 있으므로 Maya RGBA 버퍼를 감싸면 R/B가 뒤바뀐 상태로 `imshow`·`imencode`가 돈다. 그래서 `cvtColor(RGBA2BGRA)`가 뒤따른다.

**예시:**
```cpp
cv::Mat image(height, width, CV_8UC4, local_buffer.data());   // 복사 없음, 순서 모름
```

**관련 코드:**
- `src/image_bridge/src/image_bridge_node.cpp:80` — 래핑(레거시)

**증거:**
- §4.3, §4.3.1

**함정:** 외부 버퍼를 감싼 Mat은 버퍼 수명에 의존한다. 벡터가 재할당되면 Mat이 댕글링 포인터를 쥔다 — 그래서 로컬 벡터로 복사한 뒤 감쌌다.

**교훈:** 타입 상수는 메모리 형태만 말한다. 의미(채널 순서)는 별도 계약이다.

#### `cvtColor`

**직관:** OpenCV의 색 공간·채널 순서 변환 함수. `COLOR_RGBA2BGRA`처럼 변환 코드를 주면 바이트를 재배열한다.

**동작:** 레거시 스트리밍 흐름: Winsock 연결 → `named_mutex` 안에서 `frame_index` 비교 → 로컬 벡터로 복사 → unlock(락 시간 최소화) → `cvtColor(RGBA2BGRA)` → 헤더 `int[2]{w,h}` 전송 → 청크 분할 `send`. 변환은 락 밖에서 해 공유 메모리 점유 시간을 줄였다. 현재 Maro는 뷰포트 스트리밍 대신 Arnold 합성 데이터(EXR)를 쓰므로 OpenCV 의존이 없다.

**예시:**
```cpp
// 락 안: 복사만          락 밖: 변환·전송
{ lock; std::copy(shm, shm + n, local.begin()); }
cv::cvtColor(image, image, cv::COLOR_RGBA2BGRA);
send(sock, header, sizeof(header), 0);
```

**관련 코드:**
- `src/image_bridge/src/image_bridge_node.cpp:60-103` — 흐름 전체(레거시)

**증거:**
- §4.3, §4.3.1, §4.3.6

**함정:** in-place 변환(`src == dst`)은 채널 수가 같을 때만 안전하다. RGBA→BGR(3채널)처럼 크기가 바뀌면 별도 출력 Mat이 필요하다.

**교훈:** 공유 자원 락 안에서는 복사만, 변환 같은 계산은 밖에서. 락 시간이 곧 프레임 레이트다.

#### 쿼터니언(`Quat{x,y,z,w}`)

**직관:** 단위 사원수로 3D 회전을 표현하는 4개 숫자 — 벡터부 `(x,y,z) = axis·sin(θ/2)`, 스칼라 `w = cos(θ/2)`. 오일러각과 달리 짐벌락이 없고 합성이 곱셈이다.

**동작:** `maro_transform`의 `Quat{x,y,z,w}`는 ROS `geometry_msgs/Quaternion`과 같은 (x,y,z,w) 순서다. Maya `MQuaternion`도 같은 순서지만 Maya 헤더를 라이브러리에 끌어들이지 않으려 별도 타입으로 뒀다. 단위 노름 `x²+y²+z²+w²=1`, `q`와 `−q`는 같은 회전(이중 덮개), 곱셈은 비가환. Maya→ROS 변환은 벡터부에 위치와 같은 재배치 `(x,−z,y)`, `w` 불변. `jointToMayaRotation`이 축-각→쿼터니언, `mayaRotationToJoint`가 사영으로 역변환한다.

**예시:**
```cpp
struct Quat { double x, y, z, w; };            // (x,y,z,w) — ROS와 같은 순서
Quat mayaToRosRotation(const Quat& q) { return Quat{q.x, -q.z, q.y, q.w}; }
```

**관련 코드:**
- `src/maro_transform/include/maro_transform/Types.h` — `Quat` 정의
- `src/maro_transform/src/Convert.cpp:18-52` — 변환·축-각·사영
- `src/maro_plugin/MaroPump.cpp:225-240` — `MFnTransform::rotation(kWorld)`을 Quat로

**증거:**
- §5.1, §5.1.1, §5.1.2, §10.6

**함정:** 라이브러리마다 (w,x,y,z) 순서도 있다(Eigen 생성자). 순서를 틀리면 회전이 엉뚱해지는데 단위 노름은 여전히 1이라 검증으로 안 잡힌다.

**교훈:** 쿼터니언 타입은 순서를 이름(필드)으로 고정하고, 다른 라이브러리와 넘길 때 필드 단위로 옮긴다.

#### 축-각(axis-angle) → 쿼터니언

**직관:** 회전축 단위 벡터 `a`와 각 θ에서 쿼터니언 `(a·sin(θ/2), cos(θ/2))`를 만드는 공식. 관절 하나의 회전은 축-각이 자연스러운 표현이라 이 변환이 발행 경로의 마지막 단계다.

**동작:** `jointToMayaRotation(angleRad, conv)`는 `AxisConvention{axis, invert}`에서 로컬 축 벡터를 얻고(`invert`면 부호 반전) `half = angle/2`, `Quat{axis·sin(half), cos(half)}`를 돌려준다. `AxisConvention`은 "어느 로컬 축(X/Y/Z)이 관절 축인가 + 부호"를 표현하는 사용자 기준 축 보정이다(스펙 §7.1 데이터 모델).

**예시:**
```cpp
Quat jointToMayaRotation(double angleRad, const AxisConvention& conv) {
    const Vec3 axis = axisVectorOf(conv);          // 단위 벡터, invert 반영
    const double half = angleRad * 0.5, sn = std::sin(half);
    return Quat{axis.x * sn, axis.y * sn, axis.z * sn, std::cos(half)};
}
```

**관련 코드:**
- `src/maro_transform/src/Convert.cpp:36-41` — 공식
- `src/maro_transform/include/maro_transform/Types.h:21-30` — `LocalAxis`·`AxisConvention`

**증거:**
- §5.1, §5.1.1, §5.1.2

**함정:** θ 대신 θ/2를 잊으면 회전이 두 배가 된다. 단위 테스트는 90°를 넣어 결과가 90°인지(180°가 아닌지) 본다.

**교훈:** 반각 공식은 외우기보다 테스트로 고정한다. "90° 넣으면 90°"가 가장 싼 검증이다.

#### `atan2` vs `acos`

**직관:** 각도를 복원할 때 `acos(w)`는 (0, π]만 돌려줘 회전 방향(부호)을 잃지만, `atan2(sinHalf, cosHalf)`는 두 인자의 부호로 (−π, π] 전체를 복원한다.

**동작:** `mayaRotationToJoint`는 `sinHalf = q_v·axis`(부호 있음), `cosHalf = clamp(w, −1, 1)`, `θ = 2·atan2(sinHalf, cosHalf)`. `acos(w)`였다면 −30°와 +30°가 같은 값이 돼 관절이 한쪽으로만 움직인다. `asin(sinHalf)`였다면 ±90° 너머를 잃는다. 테스트는 `|angle| > π/2`인 케이스로 `asin` 구현을, 음의 각으로 `acos` 구현을 배제한다(플랜 Task 3/4 변이 검증).

**예시:**
```
θ = −60°: q = (a·sin(−30°), cos(−30°))
acos(w)  = acos(0.866) = 30°  → 2·30 = +60°   (부호 소실)
atan2(−0.5, 0.866) = −30°     → 2·(−30) = −60° (정확)
```

**관련 코드:**
- `src/maro_transform/src/Convert.cpp:43-52` — atan2 사용과 이유 주석
- `tests/transform/test_convert.cpp:160-241` — asin/acos 배제 케이스

**증거:**
- §5.1, §5.1.2

**함정:** `w`를 clamp하지 않으면 부동소수점 오차로 1.0000001이 들어와 `acos`는 NaN을 준다. `atan2`는 NaN을 내지 않지만 습관적으로 clamp한다.

**교훈:** 역삼각함수는 `atan2` 하나로 통일한다. 사분면을 잃는 함수는 각도 복원에 쓰지 않는다.

#### `axisBasisEulerXYZ(dir)`

**직관:** 방향 벡터 `dir`을 로컬 Z로 갖는 정규직교 기저를 만들어 XYZ 오일러(도)로 돌려주는 함수. 리밋 보정 헬퍼 로케이터를 사용자가 고른 축 방향에 맞춰 놓는 데 쓴다.

**동작:** 보정 세션 `start()`는 undo 청크 안에서 (1) 세 채널의 원래 커넥션/값 캡처, (2) 커넥션 끊기, (3) `spaceLocator("maroCalibHelper#")`를 `axisBasisEulerXYZ`로 정렬해 pivot에, (4) 대상을 헬퍼 밑으로 재부모(월드 포즈 보존). 사용자는 네이티브 Rotate/Move 툴로 헬퍼의 로컬 Z만 조작하고 `currentValue()`는 `rotateZ/translateZ`를 그대로 읽는다 — 별도 축-각 투영이 필요 없다. X/Y는 월드 업 참조로 결정하고 평행하면 월드 X를 쓴다.

**예시:**
```python
euler = axisBasisEulerXYZ(axisDirectionFromPoints(a, b))   # (rx, ry, rz) 도
helper = cmds.spaceLocator(name="maroCalibHelper#")[0]
cmds.xform(helper, ws=True, t=pivot, ro=euler)
cmds.parent(target, helper)                                 # 월드 포즈 보존
```

**관련 코드:**
- `python/maroLimitCalibration.py:27-60` — 기저와 오일러 변환
- `python/maroLimitCalibration.py:69-114` — `start()`의 헬퍼 배치
- `tests/maya/test_limit_calibration_pure.py` — 로컬 Z 회전 대조

**증거:**
- §7.10, §8.3.6

**함정:** 오일러 순서를 `xform ro`의 기본(XYZ)과 다르게 만들면 헬퍼가 엉뚱한 방향을 본다. 함수 이름에 순서를 넣은 이유다.

**교훈:** "사용자가 Z만 만지면 된다"는 UX는 기저를 미리 정렬해 두는 수학에서 나온다. 계산을 앞당겨 조작을 단순하게 한다.

#### 짐벌 특이점

**직관:** 방향이 참조 벡터(월드 업)와 평행해지면 외적이 0벡터가 돼 기저를 만들 수 없는 상황. 오일러각의 짐벌락과 같은 부류의 특이점이다.

**동작:** `axisBasisEulerXYZ`는 `|dir·up|`이 임계를 넘으면 참조를 월드 X로 바꾼다. 그러면 외적이 다시 유의미해지고 기저가 정해진다. 1자유도 계라 X/Y 선택은 결과 값(rotateZ/translateZ)에 영향이 없고 표시 안정성만 좌우한다. 순수 함수 테스트가 수직 축 입력을 검증한다.

**예시:**
```python
if abs(z * MVector(0, 1, 0)) > 0.999:      # 거의 수직 → 특이점
    reference = MVector(1, 0, 0)            # 월드 X로 대체
```

**관련 코드:**
- `python/maroLimitCalibration.py:27-60` — 참조 대체
- `tests/maya/test_limit_calibration_pure.py` — 수직 축 케이스

**증거:**
- §7.10

**함정:** 특이점 "근처"에서는 외적이 0은 아니지만 매우 작아 정규화가 노이즈를 증폭한다. 정확히 평행할 때만이 아니라 임계 이내면 대체한다.

**교훈:** 특이점 처리는 "0일 때"가 아니라 "0에 가까울 때"다. 임계값과 대체 전략을 주석으로 남긴다.

#### `Rz·Ry·Rx`

**직관:** URDF `<origin rpy="r p y">`의 정의 — 고정축 X→Y→Z 순으로 회전한 것이며 열벡터 관례로 행렬 곱 Rz(y)·Ry(p)·Rx(r)이다.

**동작:** `computeRelativeOrigin(pPos, pQuat, cPos, cQuat)`는 `relative = child · parent⁻¹`(Maya 행벡터 관례)로 상대 변환을 만들고 오일러로 바꿔 `(xyz, rpy)`를 돌려준다. rpy 순서는 실측 1차 원리 비교로 확정했다 — `MEulerRotation(r,p,y,kXYZ).asMatrix()`의 전치가 URDF 공식 `Rz·Ry·Rx`와 수치 일치. 브리프의 `kZYX` 가설은 최대 오차 ~0.33으로 반증됐다. 테스트는 독립 회전행렬 `_rotX/_rotY/_rotZ`·`_matmul`로 오라클을 만들어 대조한다.

**예시:**
```python
# test_urdf_export.py — 독립 오라클
expectedColumnVectorMatrix = _matmul(_matmul(_rotZ(yaw), _rotY(pitch)), _rotX(roll))
# om2.MEulerRotation(roll, pitch, yaw, kXYZ).asMatrix() 의 전치와 비교
```

**관련 코드:**
- `python/maroUrdfExport.py:158-195` — `computeRelativeOrigin`과 kXYZ 결정 주석
- `tests/maya/test_urdf_export.py:165-215` — 독립 회전행렬 오라클

**증거:**
- §7.14, §10.6

**함정:** "URDF는 ZYX"라는 말이 흔한데 이는 intrinsic 표현이고, extrinsic(고정축) XYZ와 같은 행렬이다. 이름이 아니라 행렬로 확인한다.

**교훈:** 회전 순서는 문서의 단어가 아니라 수치 비교로 확정한다. 독립 오라클(직접 쓴 회전행렬)이 가장 확실하다.

#### 쿼터니언 벡터부 규칙·`w` 불변

**직관:** Maya→ROS 기저 변환에서 쿼터니언은 벡터부 `(x,y,z)`에 위치와 같은 재배치 `(x,−z,y)`를 하고 스칼라 `w`는 그대로 둔다. 진짜 회전(det=+1) 아래에서 성립하는 규칙이다.

**동작:** `mayaToRosRotation(q) = {q.x, −q.z, q.y, q.w}`. 공액 `R·q·R⁻¹`이 벡터부에 R을 적용하는 것과 동치이고 스칼라부는 회전 각(θ)만 담아 불변이다. §9.2.1이 이 수식을 확정으로 기록하고, 플랜 Task 3/4가 부호 뒤집기·`asin` 치환 변이로 테스트의 방어력을 증명했다. 반사(det=−1)였다면 이 규칙이 성립하지 않는다.

**예시:**
```cpp
Quat mayaToRosRotation(const Quat& maya) { return Quat{maya.x, -maya.z, maya.y, maya.w}; }
Quat rosToMayaRotation(const Quat& ros)  { return Quat{ros.x, ros.z, -ros.y, ros.w}; }
```

**관련 코드:**
- `src/maro_transform/src/Convert.cpp:18-24` — 구현
- `src/maro_transform/include/maro_transform/Convert.h:20-23` — "벡터부는 위치와 같은 규칙, w 불변" 주석
- `tests/transform/test_convert.cpp:90-160` — 요·롤 부호 케이스

**증거:**
- §5.1, §5.1.2, §9.2.1

**함정:** 위치 변환에 스케일 `s`를 곱하듯 쿼터니언에도 곱하면 단위 노름이 깨진다. 스케일은 위치에만.

**교훈:** 같은 재배치를 두 종류의 값에 적용할 때, "무엇이 같고 무엇이 다른가"(스케일 유무)를 나란히 적는다.

#### 오일러 순서 `kXYZ`(정정)

**직관:** Maya 행벡터 관례의 `kXYZ`가 열벡터 관례의 `Rz·Ry·Rx`이자 URDF 고정축 XYZ와 같다는 정정. 플랜은 `kZYX`로 가정했지만 실측이 뒤집었다.

**동작:** `computeRelativeOrigin`은 상대 회전을 `euler.reorder(om2.MEulerRotation.kXYZ)`로 바꿔 rpy를 얻는다. 근거는 `MEulerRotation(r,p,y,kXYZ).asMatrix()`의 전치(행벡터→열벡터)가 `Rz·Ry·Rx`와 수치 일치한다는 것. `kZYX`는 최대 오차 0.33. 테스트 주석은 "당연해 보이는 것을 실측으로 뒤집은" 같은 종류의 발견으로 `<axis>` 재배치를 함께 든다. §10.6 규칙 표에 "rpy는 extrinsic XYZ = 열벡터 Rz·Ry·Rx; Maya 행벡터에서는 kXYZ"로 실렸다.

**예시:**
```python
euler = relativeQuat.asEulerRotation()
euler = euler.reorder(om2.MEulerRotation.kXYZ)     # kZYX 가설은 반증됨
rpy = (euler.x, euler.y, euler.z)
```

**관련 코드:**
- `python/maroUrdfExport.py:185-192` — reorder와 근거 주석
- `tests/maya/test_urdf_export.py:165-215` — 오라클 비교

**증거:**
- §7.14, §10.6

**함정:** Maya의 회전 순서 enum 이름(`kXYZ`)은 "적용 순서"이고 행벡터 관례라 열벡터 문서와 이름이 반대로 보인다. 이름 매칭으로 판단하면 틀린다.

**교훈:** 두 시스템의 관례(행/열벡터, intrinsic/extrinsic)가 겹치면 이름은 신뢰할 수 없다. 행렬 하나를 만들어 비교한다.

#### 동일 평면(coplanar) 2D SAT

**직관:** 두 삼각형이 같은 평면에 있으면 3D SAT의 11개 축이 전부 법선과 평행해져 평면 안의 분리를 구분하지 못한다. 그래서 평면 안에서 2D 볼록다각형 SAT로 전환한다.

**동작:** 공면 판정은 법선 사이 `sinAngle < 1e-6`이고 평면 거리 `< eps`. 공면이면 각 삼각형의 세 변에 대해 평면 내 법선 `cross(normal, edge)`를 축으로 삼아(6개) 투영 구간을 비교한다. 3D 축들은 법선 방향 투영이 폭 0인 같은 점이 돼 "겹침"으로만 나오므로, 2D 축 없이는 나란히 놓인 두 공면 삼각형이 항상 충돌로 오판된다. 테스트 `CoplanarTrianglesWithGenuineOverlapCollide`가 이 경로를 검증한다.

**예시:**
```cpp
if (coplanar) {
    // 표준 2D 볼록다각형 SAT: 각 변의 평면 내 법선
    for (edge : edgesA) axes.push_back(cross(normalA, edge));
    for (edge : edgesB) axes.push_back(cross(normalA, edge));
}
```

**관련 코드:**
- `src/maro_lidar/src/CollisionEngine.cpp:133-160` — 공면 판정과 2D 축
- `tests/lidar/test_collision_engine.cpp:57-66` — 공면 겹침 케이스

**증거:**
- §5.2, §5.2.4

**함정:** 공면 판정 없이 3D 축만 쓰면 "분리"가 절대 나오지 않아 테이블 위에 놓인 파트끼리 전부 충돌로 나온다. 공면은 예외가 아니라 흔한 경우다.

**교훈:** 차원이 낮아지는 퇴화 입력은 별도 알고리즘 분기를 갖는다. "일반 경우"만 구현하면 흔한 입력에서 틀린다.

#### extrinsic(고정축) XYZ vs intrinsic ZYX

**직관:** 같은 회전을 두 방식으로 읽을 수 있다 — 고정된 월드 축으로 X→Y→Z 순(extrinsic XYZ), 또는 매번 새로 도는 물체 축으로 Z→Y→X 순(intrinsic ZYX). 두 표현은 같은 행렬 `Rz·Ry·Rx`다.

**동작:** URDF rpy는 extrinsic XYZ로 정의된다. 문서에 따라 "ZYX"라고 적힌 것은 intrinsic 읽기다. Maya `MEulerRotation.kXYZ`는 행벡터 관례에서 X→Y→Z를 적용하는 것이고, 전치하면 열벡터 `Rz·Ry·Rx`가 된다. 그래서 `kXYZ`가 맞고 `kZYX`(플랜 가설)는 틀렸다. 테스트는 `_rotZ·_rotY·_rotX` 오라클로 이 동치를 수치로 확인한다.

**예시:**
```
extrinsic XYZ (고정축):  월드 X로 r, 월드 Y로 p, 월드 Z로 y  →  Rz(y)·Ry(p)·Rx(r)
intrinsic ZYX (물체축):  물체 Z로 y, 새 Y로 p, 새 X로 r      →  Rz(y)·Ry(p)·Rx(r)   (같은 행렬)
```

**관련 코드:**
- `python/maroUrdfExport.py:185-192` — kXYZ 선택
- `tests/maya/test_urdf_export.py:165-215` — 오라클로 동치 확인

**증거:**
- §7.14, §10.6

**함정:** "XYZ"라는 문자열이 extrinsic인지 intrinsic인지 문서마다 다르다. 순서 이름만 보고 코드에 옮기면 반반 확률로 틀린다.

**교훈:** 오일러 순서는 "어느 축(고정/물체)"과 "어느 관례(행/열)"를 함께 적어야 하나의 의미가 된다. 셋 중 하나라도 빠지면 모호하다.

#### `computeCameraIntrinsics` → `{fx, fy, cx, cy}`

**직관:** Maya 카메라 설정(초점거리, 필름 조리개, 해상도, Film Fit)에서 핀홀 내부 행렬의 네 수 — 초점거리 픽셀 `fx, fy`와 주점 `cx, cy` — 를 계산하는 함수. 깊이 이미지를 3D로 역투영하려면 이것이 필요하다.

**동작:** `computeCameraIntrinsics(focal, hAp, vAp, w, h, filmFit, pixelAspect, overscan)`. `filmAspect = hAp/vAp`, `deviceAspect = (w/h)·pixelAspect`. Film Fit이 Fill이면 두 후보 중 화각이 좁아지는 쪽 조리개를 유효값으로, Overscan 모드는 정반대(넓어지는 쪽). `fx = focal/(hEff·25.4)·w`(인치→mm), `cx = w/2`. `overscan` 인자는 무시한다 — 뷰포트 표시 전용이며 Arnold depth AOV가 overscan 1.0과 2.0에서 픽셀 단위로 동일함을 실측했다. `MFnCamera.getViewParameters()`를 독립 오라클로 교차 검증했다.

**예시:**
```python
K = computeCameraIntrinsics(35.0, 1.417, 0.945, 1920, 1080, "fill", 1.0, 1.0)
# {'fx': 1865.4, 'fy': 1865.4, 'cx': 960.0, 'cy': 540.0}
```

**관련 코드:**
- `python/maroSyntheticDataPointCloud.py:89-162` — 계산과 Film Fit 정정 주석
- `tests/maya/test_synthetic_data_point_cloud.py` — `getViewParameters` 오라클 대조

**증거:**
- §7.15, §10.6

**함정:** `pixelAspectRatio`는 카메라가 아니라 `defaultResolution`에 있고, Arnold는 `deviceAspectRatio`로 유효 조리개를 정하며 w/h를 바꿔도 자동 재계산되지 않는다. 카메라만 읽으면 틀린다.

**교훈:** 렌더러의 내부 행렬은 문서가 아니라 실제 렌더로 확정한다. 독립 오라클 API가 있으면 반드시 대조한다.

#### `fx = focal/(hEff·25.4)·w`

**직관:** 초점거리를 픽셀 단위로 바꾸는 식 — 초점거리(mm)를 유효 필름 폭(인치×25.4 = mm)으로 나눠 "필름 폭 대비 비율"을 얻고 이미지 폭(픽셀)을 곱한다.

**동작:** `hEff`는 Film Fit이 결정한 유효 수평 조리개(인치). Maya 필름 조리개는 인치 단위라 25.4를 곱해 mm로 맞춘다. `fy`도 `vEff`로 같은 식. `fx = fy`가 되려면 `hEff/vEff = w/h`여야 하는데 Fill/Overscan이 그렇게 조정한다. 역투영에서는 `xCam = (col+0.5−cx)·d/fx`로 쓰인다.

**예시:**
```python
fx = (focalLengthMm / (hEff * 25.4)) * widthPx
fy = (focalLengthMm / (vEff * 25.4)) * heightPx
```

**관련 코드:**
- `python/maroSyntheticDataPointCloud.py:160-161` — 식
- `python/maroSyntheticDataPointCloud.py:236-240` — 역투영에서의 사용

**증거:**
- §7.15

**함정:** 25.4를 빼먹으면 fx가 25배 커져 포인트클라우드가 카메라 앞 한 점으로 뭉친다. 단위 변환 상수는 이름 있는 상수로 둔다.

**교훈:** 단위가 섞이는 식(mm, 인치, 픽셀)은 각 항의 단위를 주석에 적어 차원 분석이 되게 한다.

#### `_normalizeFilmFit`(int만, 음수 wraparound)

**직관:** Film Fit 입력을 정규화하는 검증 함수 — 문자열 또는 진짜 `int`(0–3)만 받는다. `float`를 `int()`로 자르거나 음수를 그대로 인덱싱하면 잘못된 입력이 조용히 다른 모드가 되기 때문이다.

**동작:** `isinstance(filmFit, int)`(bool 제외)이고 0–3 범위면 `_FILM_FIT_MODES[filmFit]`, 문자열이면 소문자로 매칭, 그 외는 `ValueError`. `float` 1.9를 `int()`로 자르면 1(horizontal)이 되어 계획의 Global Constraints가 명시한 오류가 안 들키고, `-1`은 Python 음수 인덱스 wraparound로 `_FILM_FIT_MODES[-1]` = `"overscan"`(Fill의 정반대)으로 풀린다(F-057).

**예시:**
```python
_normalizeFilmFit("Fill")   # → "fill"
_normalizeFilmFit(1)        # → "horizontal"
_normalizeFilmFit(1.9)      # ValueError (자르지 않는다)
_normalizeFilmFit(-1)       # ValueError (wraparound로 "overscan"이 되지 않게)
```

**관련 코드:**
- `python/maroSyntheticDataPointCloud.py:65-88` — 검증과 이유 주석
- `tests/maya/test_synthetic_data_point_cloud.py` — float·음수 거부 케이스

**증거:**
- §7.15
- F-057

**함정:** Python의 관용성(음수 인덱스, `int(float)`)이 입력 검증에서는 적이다. "동작하는" 잘못된 입력이 가장 늦게 발견된다.

**교훈:** enum 같은 입력은 정확한 타입과 범위를 검사하고 나머지는 예외로 알린다. 언어의 편의 기능이 검증을 우회하지 않게.

#### coplanar 재분류

**직관:** 두 삼각형이 `eps`보다 가까우면 "거의 공면"으로 재분류해 2D SAT로 보내는 것. 하나의 `eps` 상수가 "공면인가"와 "분리됐는가" 두 문턱을 동시에 통제한다.

**동작:** 테스트 케이스 8(eps 경계 회귀 그물)은 같은 삼각형을 법선 방향으로 `d = eps/2` 평행이동하면 coplanar로 재분류 → 2D SAT에서 완전 일치 → 충돌, `d = 2·eps`면 3D 분기에서 법선 축 분리 → 비충돌임을 단언한다. 기댓값은 코드 정의(`scale = sqrt(max 변 길이²)`, `eps = scale·1e-6`)에서 역산해 고정했지 임의 값을 못박은 것이 아니다.

**예시:**
```cpp
// d = eps/2 → coplanar → 2D SAT → 충돌
EXPECT_TRUE(trianglesIntersect(a, translate(a, normal * (eps / 2))));
// d = 2*eps → 3D 분기, 법선 축 분리 → 비충돌
EXPECT_FALSE(trianglesIntersect(a, translate(a, normal * (2 * eps))));
```

**관련 코드:**
- `tests/lidar/test_collision_engine.cpp:233-285` — eps 경계 그물
- `src/maro_lidar/src/CollisionEngine.cpp:122-140` — eps 정의와 coplanar 판정

**증거:**
- §8.2, §8.2.2

**함정:** eps를 바꾸면 두 문턱이 함께 움직인다. 한쪽만 조정하려다 다른 쪽 테스트가 깨지는 것은 설계대로다.

**교훈:** 허용오차 상수의 "경계 양쪽" 케이스를 테스트에 두면 상수 변경의 영향이 즉시 드러난다.

#### planar depth vs radial depth

**직관:** 깊이 이미지의 픽셀 값이 "카메라 평면까지의 수직 거리"(planar, Z)인지 "카메라 원점까지의 광선 거리"(radial)인지. 역투영 식이 달라지므로 렌더러가 어느 쪽인지 확정해야 한다.

**동작:** `unprojectDepthToPoints`는 `xCam = (col+0.5−cx)·d/fx`, `yCam = (cy−(row+0.5))·d/fy`, `planarDepth=True`면 `zLocal = −d`(Maya 카메라는 로컬 −Z를 본다), radial이면 방향 벡터를 정규화해 `d`를 곱한다. Arnold Z AOV는 실측으로 planar였다 — 500 유닛 평면의 중심·코너 픽셀이 모두 499.999. 픽셀 부호 규약도 실제 렌더(Y=+100 큐브)로 확정했다. 기본값은 표준 핀홀에서 유도한 가정이었고 실측이 이를 확인했다.

**예시:**
```python
xCam = (col + 0.5 - cx) * depth / fx
yCam = (cy - (row + 0.5)) * depth / fy
if planarDepth:  xLocal, yLocal, zLocal = xCam, yCam, -depth          # Arnold Z AOV
else:            ray = normalize(xCam, yCam, -1); xLocal, yLocal, zLocal = ray * depth
```

**관련 코드:**
- `python/maroSyntheticDataPointCloud.py:219-250` — 역투영과 planar 분기
- `python/maroSyntheticDataPointCloud.py:1-12` — "planarDepth 기본값은 가정" 주석
- `tests/maya/test_synthetic_data_point_cloud.py` — 평면 렌더 실측 케이스

**증거:**
- §7.15, §9.2.5, §10.6

**함정:** radial 깊이를 planar로 역투영하면 화면 가장자리 점들이 카메라 쪽으로 휘어 평면이 접시처럼 보인다. 중심만 보면 맞아 보인다 — 코너 픽셀을 검사한다.

**교훈:** 렌더러의 깊이 정의는 "평면을 렌더해 코너를 본다"로 확정한다. 문서보다 실측이 빠르고 확실하다.

#### scale-aware eps

**직관:** 허용오차를 절대 상수(예: 1e-6)가 아니라 입력 크기에 비례(최대 변 길이 × 1e-6)시키는 것. Maya 씬 단위가 cm~m로 다양하므로 절대 상수는 어떤 씬에서는 너무 크고 다른 씬에서는 너무 작다.

**동작:** `trianglesIntersect`는 `scale = sqrt(max 변 길이²)`를 두 삼각형에서 구해 `eps = scale·1e-6`으로 쓴다. 퇴화 축 판정(`길이² < eps²`), 공면 판정(평면 거리 `< eps`), 분리 판정(간격 `≥ eps`)이 모두 이 값을 쓴다. QuickHull의 `eps = span·1e-9`도 같은 원리다(점 집합 span 기준).

**예시:**
```cpp
const double scale = std::sqrt(std::max(maxEdgeLen2(a), maxEdgeLen2(b)));
const double eps = scale * 1e-6;     // 씬 단위(cm~m)와 무관하게 상대 오차
```

**관련 코드:**
- `src/maro_lidar/src/CollisionEngine.cpp:122-129` — scale과 eps
- `python/maroUrdfExport.py:1051` — QuickHull의 상대 eps

**증거:**
- §5.2, §5.2.4

**함정:** 두 삼각형의 크기가 극단적으로 다르면(1mm 나사와 1m 판) 큰 쪽 기준 eps가 작은 쪽을 통째로 퇴화로 본다. 실용 범위에서는 문제없지만 한계는 적어 둔다.

**교훈:** 부동소수점 비교의 허용오차는 "값의 크기"에 상대적이어야 한다. 단위가 바뀌는 시스템에서 절대 상수는 버그다.

#### piecewise-linear 보간

**직관:** 점 여러 개를 직선으로 이어 구간별로 선형 보간하는 것. 커플링 곡선(`curveInput → curveOutput`)이 2점 이상이면 이 방식으로 따라가는 값을 계산한다.

**동작:** `interpolateCoupling(source, sortedPoints, ratio, offset)`는 곡선 점이 2개 미만이면 `source·ratio + offset`, 아니면 `curveInput` 오름차순 정렬된 점에서 `source`가 속한 구간 `[lo, hi]`를 찾아 `lo.second + t·(hi.second − lo.second)`, `t = (source − lo.first)/span`. 중복 `curveInput`(span ≤ 0)은 `lo.second`로 방어한다. 정의역 밖은 끝점 값으로 고정한다.

**예시:**
```cpp
if (sortedPoints.size() < 2) return sourceValue * ratio + offset;
if (sourceValue <= sortedPoints.front().first) return sortedPoints.front().second;
if (sourceValue >= sortedPoints.back().first)  return sortedPoints.back().second;
// 구간 찾기 → lo.second + t * (hi.second - lo.second)
```

**관련 코드:**
- `src/maro_plugin/MaroCapabilityNodes.cpp:58-80` — 보간
- `src/maro_plugin/MaroCapabilityNodes.cpp:575-585` — compute에서의 호출
- `tests/maya/test_capability_stack.py` — 곡선 보간 케이스

**증거:**
- §6.3

**함정:** 정렬되지 않은 점을 넘기면 구간 탐색이 틀린 값을 준다. 정렬은 호출자가 아니라 함수가 보장하거나 이름(`sortedPoints`)으로 계약을 못 박는다.

**교훈:** 보간 함수는 "정렬됨, 중복 없음, 정의역 밖 정책"을 계약으로 적고 각각을 방어 코드로 갖는다.

#### 외삽(extrapolation) 금지

**직관:** 정의역(곡선의 첫 점~마지막 점) 밖에서는 직선을 연장해 추정하지 않는다. 관절값이 발산하면 로봇이 안전 범위를 벗어나므로 끝점 값으로 고정한다.

**동작:** `source ≤ first.input`이면 `first.output`, `source ≥ last.input`이면 `last.output`. 외삽했다면 마지막 구간의 기울기로 값이 무한히 커질 수 있다 — 예를 들어 기어 커플링이 90°까지 정의됐는데 입력이 180°면 출력이 두 배로 튄다. 고정하면 출력이 마지막 정의값에서 멈춘다.

**예시:**
```
곡선: (0,0), (90, 45)
입력 180 → 외삽하면 90 (위험)  /  끝점 고정하면 45 (안전)
```

**관련 코드:**
- `src/maro_plugin/MaroCapabilityNodes.cpp:64-69` — 끝점 반환
- `tests/maya/test_capability_stack.py` — 정의역 밖 케이스

**증거:**
- §6.3

**함정:** 애니메이션 도구는 보통 외삽(선형·순환)을 기본으로 제공한다. 로봇 제어에서는 그 기본값이 위험하다.

**교훈:** "정의역 밖" 정책은 안전 관점에서 정한다. 발산 가능성이 있으면 고정이 기본이다.

#### 끝점 고정(clamp)

**직관:** 값을 `[min, max]` 안으로 자르는 것. 커플링 보간의 정의역 밖 처리, 쿼터니언 `w`의 `[−1, 1]` 보정, 리밋 적용 등 여러 곳에서 같은 연산이 쓰인다.

**동작:** 커플링은 입력을 곡선 정의역으로 clamp한 효과(끝점 값 반환). `mayaRotationToJoint`는 `w`를 `std::clamp(w, −1, 1)`해 부동소수점 오차로 1을 넘는 값이 역삼각함수에 들어가지 않게 한다. 축 리밋은 `std::min/max`로 뒤집힌 리밋을 관용하고 값을 범위 안에 둔다. 모두 "범위 밖은 오류가 아니라 경계값"이라는 같은 정책이다.

**예시:**
```cpp
const double cosHalf = std::clamp(maya.w, -1.0, 1.0);          // 수치 보정
if (sourceValue >= sortedPoints.back().first) return sortedPoints.back().second;   // 정의역 clamp
```

**관련 코드:**
- `src/maro_transform/src/Convert.cpp:49` — `w` clamp
- `src/maro_plugin/MaroCapabilityNodes.cpp:64-69` — 정의역 끝점
- `src/maro_plugin/MaroAxisNode.cpp:250-330` — 리밋 적용

**증거:**
- §6.3

**함정:** clamp는 오류를 숨긴다 — 입력이 항상 범위 밖이면 출력이 상수가 되어 "움직이지 않는" 증상으로만 나타난다. 진단 카운터나 로그로 clamp 빈도를 남기는 것이 좋다.

**교훈:** clamp는 안전장치이지 정상 경로가 아니다. 자주 걸리면 상류(입력 범위)를 본다.

#### `eps=span·1e-9`

**직관:** QuickHull의 가시성·퇴화 판정 허용오차. 점 집합의 전체 크기(span)에 비례시켜, 미터 단위 파이프라인에서 밀리미터 파트도 퇴화로 오판하지 않게 한다.

**동작:** `span = max(bbox 대각 성분)`, `eps = span·1e-9`. "면 평면 위쪽 `> eps`"가 가시성, 초기 사면체 각 단계의 거리 `≤ eps`가 퇴화 판정이다. 고정 절대값(예: 1e-6 m)이면 1mm 파트의 두께가 eps 이하로 보여 사면체를 못 만들고 `<box>` 폴백으로 빠진다. 1e-9라는 계수는 double 정밀도(~1e-16)와 실제 메쉬 정점 오차 사이에서 잡았다.

**예시:**
```python
span = max(maxs[i] - mins[i] for i in range(3))
eps = span * 1e-9                       # 상대 — 미터 파이프라인에서 작은 파트 보호
```

**관련 코드:**
- `python/maroUrdfExport.py:1045-1055` — span과 eps
- `python/maroUrdfExport.py:1108-1112` — 가시성 판정에서의 사용

**증거:**
- §7.14

**함정:** span이 0이면(모든 점이 같음) eps도 0이라 모든 판정이 `> 0`이 되어 부동소수점 노이즈가 가시성으로 잡힌다. 초기 사면체 단계가 먼저 퇴화를 걸러 이 경우에 도달하지 않는다.

**교훈:** 상대 eps는 기준 크기가 0인 경우를 따로 다룬다. "비례"는 0에서 무너진다.

#### `eps = scale·1e-6`

**직관:** 삼각형 SAT의 허용오차 — 두 삼각형의 최대 변 길이에 1e-6을 곱한 값. 테스트 파일 머리주석이 이 정의를 코드에서 읽어 옮겨 적고 모든 기댓값을 여기서 유도한다.

**동작:** `scale = sqrt(max 변 길이²)`, `eps = scale·1e-6`. 세 판정에 쓰인다 — 퇴화 축(`길이² < eps²` → 스킵), 공면(평면 거리 `< eps`), 분리(투영 간격 `≥ eps`). 테스트는 `d = eps/2`와 `d = 2·eps` 같은 경계 케이스를 이 정의에서 손으로 계산해 단언하므로, eps 정의가 바뀌면 테스트도 같이 바뀌어야 한다는 것이 드러난다. QuickHull의 1e-9와 계수가 다른 이유는 메쉬 정점 오차(1e-6 상대)와 껍질 판정(더 엄격) 요구가 다르기 때문이다.

**예시:**
```cpp
// test_collision_engine.cpp 머리주석에서 옮긴 규칙
//   scale = sqrt(max edge length²), eps = scale * 1e-6
//   퇴화 축(길이² < eps²)은 항상 "분리 아님"
//   coplanar: sinAngle < 1e-6 && planeDist < eps
```

**관련 코드:**
- `src/maro_lidar/src/CollisionEngine.cpp:122-129` — 정의
- `tests/lidar/test_collision_engine.cpp:9-27` — 옮겨 적은 규칙
- `tests/lidar/test_collision_engine.cpp:233-285` — 경계 케이스

**증거:**
- §8.2, §8.2.2

**함정:** 테스트가 코드의 eps를 import하지 않고 값을 옮겨 적은 것은 의도다 — 코드가 바뀌면 테스트가 깨져 "누가 바꿨나"를 묻게 하려는 것. 편의로 import하면 그 방어가 사라진다.

**교훈:** 허용오차 정의는 코드와 테스트 양쪽에 독립적으로 적어 한쪽 변경이 다른 쪽에서 드러나게 한다.
