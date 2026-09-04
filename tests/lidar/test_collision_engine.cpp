#include <cmath>
#include <cstdint>
#include <vector>

#include <gtest/gtest.h>

#include "maro_lidar/CollisionEngine.h"

// CollisionEngine::hasCollision()의 실제 알고리즘(CollisionEngine.cpp의
// 익명 네임스페이스 trianglesIntersect(), 대략 116~163행)은 rtcCollide가
// 넘겨준 AABB 후보쌍마다 SAT(분리축 정리)로 정확한 삼각형-삼각형 교차를
// 검사한다. 이 파일은 그 SAT 구현 자체를 Maya 없이 직접 검증한다 --
// tests/maya/test_mesh_collision.py는 큐브 2개로만 간접 검증하므로 SAT의
// 축 종류별 분기(면 법선 2개, 변x변 외적 9개, 동일 평면 2D 대체 경로)를
// 거의 못 건드린다.
//
// CollisionEngine.cpp에서 읽어낸, 이 테스트들이 근거로 삼는 실제 허용오차
// 규칙(코드를 그대로 옮긴 것, 여기서 새로 지어낸 것이 아니다):
//   scale = sqrt(max(양쪽 삼각형 6개 변의 길이^2))  (최소 1e-12로 클램프)
//   eps   = scale * 1e-6
//   axisSeparates(axis)는 axis 길이^2 < eps^2 이면(=퇴화축) 항상 false.
//   축이 유효하면 aMax < bMin - eps 또는 bMax < aMin - eps 일 때만 "분리".
//     -> 간격이 정확히 0이거나 eps 이하이면 "분리 아님"(= 접촉도 충돌로 침).
//   coplanar 판정: 양쪽 법선 길이가 둘 다 eps보다 크고, 두 법선 사잇각의
//   sin이 1e-6 미만이며, 평면 간 거리가 eps 미만이면 coplanar=true로 보고
//   2D 변-법선 축(cross(normal, edge))으로 대체한다. 법선이 하나라도
//   퇴화(길이<=eps)면 coplanar 분기 자체에 들어가지 않는다.
namespace {

using maro::lidar::CollisionEngine;

std::vector<std::uint32_t> oneTriangleIndices() { return {0, 1, 2}; }

// 정점 9개(삼각형 하나)를 CollisionEngine::setMeshes()가 기대하는
// std::vector<float> 레이아웃(x0,y0,z0,x1,y1,z1,x2,y2,z2)으로 만든다.
std::vector<float> triangleVertices(double x0, double y0, double z0, double x1, double y1, double z1, double x2,
                                     double y2, double z2) {
    return {
        static_cast<float>(x0), static_cast<float>(y0), static_cast<float>(z0),
        static_cast<float>(x1), static_cast<float>(y1), static_cast<float>(z1),
        static_cast<float>(x2), static_cast<float>(y2), static_cast<float>(z2),
    };
}

}  // namespace

// ---------------------------------------------------------------------
// 1) 명백히 겹치는 두 삼각형 (동일 평면, sanity 양성 케이스)
// ---------------------------------------------------------------------
//
// A = (0,0,0),(4,0,0),(0,4,0) -- z=0 평면의 직각삼각형(x,y>=0, x+y<=4).
// B = (1,1,0),(2,1,0),(1,2,0) -- A와 완전히 같은 평면 위에 있고, B의 세
// 꼭짓점 모두 x,y>=1, x+y<=3<4를 만족하므로 B는 A 안에 통째로 들어있다
// (B ⊂ A). 즉 좌표를 눈대중으로 겹쳐 보이게 그린 게 아니라, B의 각
// 꼭짓점이 A의 반평면 부등식 3개(x>=0, y>=0, x+y<=4)를 모두 만족함을
// 직접 확인해 겹침을 보장했다.
TEST(CollisionEngine, CoplanarTrianglesWithGenuineOverlapCollide) {
    CollisionEngine engine;
    ASSERT_TRUE(engine.setMeshes(triangleVertices(0, 0, 0, 4, 0, 0, 0, 4, 0), oneTriangleIndices(),
                                  triangleVertices(1, 1, 0, 2, 1, 0, 1, 2, 0), oneTriangleIndices()));
    EXPECT_TRUE(engine.hasCollision());
}

// ---------------------------------------------------------------------
// 2) 명백히 분리된 두 삼각형 (sanity 음성 케이스)
// ---------------------------------------------------------------------
TEST(CollisionEngine, FarApartTrianglesDoNotCollide) {
    CollisionEngine engine;
    ASSERT_TRUE(engine.setMeshes(triangleVertices(0, 0, 0, 1, 0, 0, 0, 1, 0), oneTriangleIndices(),
                                  triangleVertices(1000, 1000, 1000, 1001, 1000, 1000, 1000, 1001, 1000),
                                  oneTriangleIndices()));
    EXPECT_FALSE(engine.hasCollision());
}

// ---------------------------------------------------------------------
// 3) 비동일 평면(일반 분기) 삼각형이 실제로 3D에서 관통하는 양성 케이스
// ---------------------------------------------------------------------
//
// A = (0,0,0),(4,0,0),(0,4,0)  -- z=0 평면.
//   edgesA = [(4,0,0), (-4,4,0), ...], normalA = cross((4,0,0),(-4,4,0))
//          = (0*0-0*4, 0*(-4)-4*0, 4*4-0*(-4)) = (0,0,16).
// B = (1,1,-1),(1,1,1),(2,1,0) -- 세 꼭짓점 모두 y=1이므로 평면 y=1 위.
//   edgesB0 = (0,0,2), edgesB1 = (1,0,-1),
//   normalB = cross((0,0,2),(1,0,-1)) = (0*-1-2*0, 2*1-0*-1, 0*0-0*1) = (0,2,0).
// normalA=(0,0,16)와 normalB=(0,2,0)은 평행이 아니므로(sinAngle~1)
// coplanar 판정에 걸리지 않고 일반 3D SAT 분기를 탄다.
//
// B가 A의 평면(z=0)과 실제로 만나는 지점: B의 밑변 (1,1,-1)-(1,1,1)은
// z=0에서 중점 (1,1,0)을 지나고, 꼭짓점 (2,1,0)은 이미 z=0에 있다. 즉
// B와 평면 z=0의 교선은 정확히 (1,1,0)-(2,1,0) 선분이다. 이 선분은
// y=1, x in [1,2] 이고, A의 부등식(x>=0,y>=0,x+y<=4)을 만족(x+y in
// [2,3])하므로 A 내부를 통과한다 -- 따라서 B는 A를 실제로 3D에서 꿰뚫는다.
TEST(CollisionEngine, NonCoplanarTrianglesThatGenuinelyInterpenetrateCollide) {
    CollisionEngine engine;
    ASSERT_TRUE(engine.setMeshes(triangleVertices(0, 0, 0, 4, 0, 0, 0, 4, 0), oneTriangleIndices(),
                                  triangleVertices(1, 1, -1, 1, 1, 1, 2, 1, 0), oneTriangleIndices()));
    EXPECT_TRUE(engine.hasCollision());
}

// ---------------------------------------------------------------------
// 4) 변x변 외적 축(edge-cross axis)이 아니면 분리를 증명할 수 없는 케이스
// ---------------------------------------------------------------------
//
// A0=(-1,-1,0), A1=(1,1,0), A2=(-1,-1,1)
//   edgesA = [A1-A0=(2,2,0), A2-A1=(-2,-2,1), A0-A2=(0,0,-1)]
//   normalA = cross((2,2,0),(-2,-2,1)) = (2*1-0*-2, 0*-2-2*1, 2*-2-2*-2) = (2,-2,0).
// B0=(-1,1,2), B1=(1,-1,2), B2=(-1,1,3)
//   edgesB = [B1-B0=(2,-2,0), B2-B1=(-2,2,1), B0-B2=(0,0,-1)]
//   normalB = cross((2,-2,0),(-2,2,1)) = (-2*1-0*2, 0*-2-2*1, 2*2-(-2)*-2) = (-2,-2,0).
//
// normalA·normalB = -4+4+0 = 0 (수직) -> sinAngle~1, coplanar 아님(일반
// 3D 분기 확정).
//
// 두 면 법선 축 모두 분리 실패를 직접 계산으로 확인:
//   normalA=(2,-2,0) 축에 A를 투영하면 세 꼭짓점 모두 정확히 0으로
//   찍힌다(자기 자신의 법선이므로 당연히 폭 0). B를 투영하면
//   {-4,4,-4} -> [-4,4]. 0이 [-4,4] 안에 있으므로 분리 아님.
//   normalB=(-2,-2,0) 축에 B를 투영하면 역시 폭 0인 점 {0,0,0}. A를
//   투영하면 {4,-4,4} -> [-4,4]. 0이 그 안에 있으므로 분리 아님.
//
// 반면 edgesA[0]=(2,2,0)과 edgesB[0]=(2,-2,0)의 외적(코드 루프에서 가장
// 먼저 검사되는 변x변 축):
//   cross((2,2,0),(2,-2,0)) = (2*0-0*-2, 0*2-2*0, 2*-2-2*2) = (0,0,-8).
// 이 축(사실상 z축)에 A를 투영: A0,A1의 z=0 -> 0, A2의 z=1 -> -8*1=-8.
//   범위 [-8,0]. B를 투영: B0,B1의 z=2 -> -16, B2의 z=3 -> -24.
//   범위 [-24,-16]. -16 < -8 - eps 이므로(간격 8 >> eps) 이 축에서
//   "분리"로 판정된다.
// 즉 두 면 법선 축은 모두 겹침을 보고하지만, edgesA[0]x edgesB[0] 축
// 하나만 실제 간격(8)을 드러낸다 -- SAT에 변x변 축이 필요한 교과서적
// 사례를 그대로 구성한 것이다.
TEST(CollisionEngine, SeparationOnlyProvableByEdgeCrossAxisReportsNoCollision) {
    CollisionEngine engine;
    ASSERT_TRUE(engine.setMeshes(triangleVertices(-1, -1, 0, 1, 1, 0, -1, -1, 1), oneTriangleIndices(),
                                  triangleVertices(-1, 1, 2, 1, -1, 2, -1, 1, 3), oneTriangleIndices()));
    EXPECT_FALSE(engine.hasCollision());
}

// ---------------------------------------------------------------------
// 5) 퇴화(공선/면적 0) 삼각형이 크래시 없이 정의된 결과를 낸다
// ---------------------------------------------------------------------
//
// A = (0,0,0),(1,0,0),(2,0,0) -- 셋 다 x축 위(y=0,z=0)의 공선점, 면적 0.
//   edgesA = [(1,0,0),(1,0,0),(-2,0,0)] (전부 x축과 평행), normalA =
//   cross((1,0,0),(1,0,0)) = (0,0,0) -> 코드의 axisLenEps 검사(length2(axis)
//   < eps^2)에 걸려 "분리축으로 못 씀"으로 처리된다(coplanar 판정도
//   normalALen<=eps라 건너뛴다).
// B = (0,10,0),(1,10,0),(0,10,1) -- 평면 y=10 위의 정상 삼각형.
//   edgesB0=(1,0,0), edgesB1=(-1,0,1), normalB=cross((1,0,0),(-1,0,1))
//   = (0*1-0*0, 0*-1-1*1, 1*0-0*-1) = (0,-1,0).
// A의 법선축은 퇴화라 분리 판정에 기여하지 못하지만(코드가 명시적으로
// "퇴화 축은 분리 아님"으로 처리), B의 법선축(0,-1,0)은 정상이다: A를
// 투영하면 세 점 모두 y=0 -> dot=0. B를 투영하면 세 점 모두 y=10 ->
// dot=-10. 0과 -10 사이 간격 10 >> eps 이므로 이 축에서 분리가
// 성립한다 -- 코드 자신의 퇴화축 처리 규칙(퇴화축은 조용히 스킵되고,
// 다른 유효한 축이 있으면 그걸로 정상 판정한다)이 예측하는 그대로
// "충돌 없음"이 나와야 하고, 크래시나 UB 없이 그 값이 실제로 나오는지만
// 확인한다.
TEST(CollisionEngine, DegenerateCollinearTriangleAgainstFarTriangleDoesNotCrashAndReportsNoCollision) {
    CollisionEngine engine;
    ASSERT_TRUE(engine.setMeshes(triangleVertices(0, 0, 0, 1, 0, 0, 2, 0, 0), oneTriangleIndices(),
                                  triangleVertices(0, 10, 0, 1, 10, 0, 0, 10, 1), oneTriangleIndices()));
    EXPECT_FALSE(engine.hasCollision());
}

// 위 케이스의 짝: 퇴화 삼각형이 완전히 한 점으로 뭉개져도(변이 전부 길이
// 0) 그 점이 실제로 다른 삼각형 내부에 있으면 여전히 크래시 없이 "충돌"로
// 나와야 한다(모든 변이 0벡터이므로 변x변 외적도 전부 0=퇴화축이 되어
// edgesA 쪽에서는 어떤 축도 분리를 증명할 수 없고, 유일하게 남는 축은
// normalB인데 아래처럼 그 축에서도 겹친다).
//
// A = (1,1,0)이 3번 반복된 "삼각형"(면적 0, 사실상 점 하나).
// B = (0,0,0),(4,0,0),(0,4,0) -- z=0 평면의 직각삼각형이고 (1,1,0)은
//   x>=0,y>=0,x+y=2<=4를 만족하므로 B 내부(경계 포함)의 점이다.
// normalB = cross((4,0,0),(-4,4,0)) = (0,0,16). A를 이 축에 투영하면 세
//   점 모두 (1,1,0)이므로 dot=0. B를 투영하면 세 꼭짓점 모두 z=0이므로
//   dot도 항상 0(평면 위 삼각형은 자기 법선 방향으로 폭이 0). 두 범위가
//   똑같이 {0}이라 분리가 아니다. 다른 모든 축(A의 변이 전부 0벡터라
//   edgesA x edgesB는 전부 0, normalA도 0)은 퇴화라 스킵되므로, 분리
//   축을 하나도 못 찾고 "충돌"로 떨어진다 -- 실제로 점이 삼각형 내부에
//   있다는 기하와도 일치한다.
TEST(CollisionEngine, DegeneratePointTriangleInsideNormalTriangleCollides) {
    CollisionEngine engine;
    ASSERT_TRUE(engine.setMeshes(triangleVertices(1, 1, 0, 1, 1, 0, 1, 1, 0), oneTriangleIndices(),
                                  triangleVertices(0, 0, 0, 4, 0, 0, 0, 4, 0), oneTriangleIndices()));
    EXPECT_TRUE(engine.hasCollision());
}

// ---------------------------------------------------------------------
// 6) 변 하나를 정확히 공유하는 두 삼각형 (닿아 있을 뿐 내부는 안 겹침)
// ---------------------------------------------------------------------
//
// A = (0,0,0),(1,0,0),(0,1,0) -- z=0 평면, y>=0 쪽에 있는 삼각형.
// B = (0,0,0),(1,0,0),(0,-1,0) -- 같은 변 (0,0,0)-(1,0,0)을 공유하지만
//   세 번째 꼭짓점이 y=-1로 반대쪽에 있다. A는 y>=0 반평면, B는 y<=0
//   반평면에 있으므로 내부(interior)는 절대 겹치지 않고 딱 그 변에서만
//   맞닿는다.
//
// 일반 원칙: 두 삼각형이 공통점을 하나라도 가지면(여기서는 변 전체,
// 즉 (0,0,0)과 (1,0,0) 둘 다 공유) 어떤 축에 투영해도 그 공통점의
// 투영값이 A의 [min,max]와 B의 [min,max] 양쪽에 동시에 속하므로
// "aMax < bMin" 이나 "bMax < aMin"이 (엄격한 부등호로는) 성립할 수
// 없다 -- 즉 분리축이 원천적으로 존재하지 않는다. 코드의 gapEps는
// 이 결론을 더 강하게 만들 뿐(정확히 0인 간격도 "분리 아님"으로 처리)
// 바꾸지 않는다. 따라서 hasCollision()은 true여야 한다 -- 이는 "닿기만
// 해도 충돌로 센다"는 코드의 실제(반드시 직관적이진 않은) 경계 시맨틱을
// 그대로 반영한 기대값이다.
TEST(CollisionEngine, TrianglesSharingExactlyOneEdgeCollide) {
    CollisionEngine engine;
    ASSERT_TRUE(engine.setMeshes(triangleVertices(0, 0, 0, 1, 0, 0, 0, 1, 0), oneTriangleIndices(),
                                  triangleVertices(0, 0, 0, 1, 0, 0, 0, -1, 0), oneTriangleIndices()));
    EXPECT_TRUE(engine.hasCollision());
}

// ---------------------------------------------------------------------
// 7) 꼭짓점 하나만 정확히 공유하는 두 삼각형
// ---------------------------------------------------------------------
//
// A = (0,0,0),(1,0,0),(0,1,0) -- 제1사분면(x>=0,y>=0) 삼각형.
// B = (0,0,0),(-1,0,0),(0,-1,0) -- 제3사분면(x<=0,y<=0) 삼각형. 공통
//   꼭짓점은 원점 (0,0,0) 하나뿐이고, 그 외에는 서로 다른 사분면이라
//   내부가 겹치지 않는다.
// 위 6번과 같은 "공통점 존재 -> 분리축 없음" 원칙이 그대로 적용된다
//   (공유하는 게 변 전체가 아니라 점 하나뿐이어도 그 점 하나의 투영값이
//   여전히 양쪽 [min,max]에 동시에 속하므로 결론은 동일하다). 따라서
//   hasCollision()은 true여야 한다.
TEST(CollisionEngine, TrianglesSharingExactlyOneVertexCollide) {
    CollisionEngine engine;
    ASSERT_TRUE(engine.setMeshes(triangleVertices(0, 0, 0, 1, 0, 0, 0, 1, 0), oneTriangleIndices(),
                                  triangleVertices(0, 0, 0, -1, 0, 0, 0, -1, 0), oneTriangleIndices()));
    EXPECT_TRUE(engine.hasCollision());
}

// ---------------------------------------------------------------------
// 8) 코드 자신의 eps 경계에 걸치는 근접 케이스 (회귀 그물)
// ---------------------------------------------------------------------
//
// A = (0,0,0),(1,0,0),(0,1,0), z=0 평면.
//   edgesA = [(1,0,0), (-1,1,0), (0,-1,0)], 변 길이^2 = {1, 2, 1}.
// B = A를 그대로 z 방향으로 d만큼 평행이동한 복사본:
//   (0,0,d),(1,0,d),(0,1,d).
//   B의 변 길이^2도 A와 완전히 같은 {1,2,1} (평행이동은 길이를 안 바꾼다).
// 코드의 scale = sqrt(max(양쪽 6개 변 길이^2)) = sqrt(2), eps = sqrt(2)*1e-6.
//
// normalA = cross((1,0,0),(-1,1,0)) = (0,0,1) -- 정확히 z축. normalB도
//   B가 A의 평행이동이라 동일하게 (0,0,1)이 나온다(같은 x,y 형태).
//   normalA와 normalB가 정확히 같은 방향이므로 sinAngle=0 < 1e-6이고,
//   평면 간 거리 planeDist = |dot(normalA, B0-A0)| / |normalA|
//                          = |dot((0,0,1),(0,0,d))| / 1 = d.
//
//   * d_below = eps/2 인 경우: planeDist(=d_below) < eps 이므로
//     coplanar=true로 분류되어 2D(변-법선) SAT로 대체된다. 그런데 B는
//     A를 z로만 평행이동한 것이라 x,y 좌표(즉 2D 투영 좌표)가 A와
//     정확히 동일하다 -- 그러므로 2D SAT의 어떤 축에 투영해도 A와 B의
//     [min,max] 구간이 완전히 일치해 분리가 아예 불가능하다(간격 0,
//     eps보다 작은 정도가 아니라 수학적으로 정확히 0). 따라서 반드시
//     true(충돌)가 나와야 한다.
//   * d_above = eps*2 인 경우: planeDist(=d_above) >= eps 이므로
//     coplanar=false로 남아 일반 3D 분기를 타고, normalA=(0,0,1) 축을
//     그대로 쓴다. A를 투영하면 전부 z=0 -> {0}. B를 투영하면 전부
//     z=d_above -> {d_above}. aMax(0) < bMin(d_above) - eps
//     = 2*eps - eps = eps 인지 확인: 0 < eps는 참이므로 이 축에서
//     "분리"가 성립해 즉시 false(충돌 없음)가 나와야 한다.
//
// 즉 이 한 쌍의 테스트는 코드가 실제로 쓰는 단 하나의 eps 상수가
// (a) coplanar 재분류 문턱과 (b) 일반 분기의 간격 문턱 두 곳 모두를
// 통제한다는 사실을 그대로 이용해, "약간 작으면 충돌, 약간 크면 충돌
// 아님"의 경계를 코드 자신의 정의로부터 역산해 고정한 것이다(임의로
// "eps는 이래야 한다"고 못박은 게 아니다).
TEST(CollisionEngine, GapSlightlySmallerThanEpsilonStillCollides) {
    const double eps = std::sqrt(2.0) * 1e-6;
    const double dBelow = eps * 0.5;
    CollisionEngine engine;
    ASSERT_TRUE(engine.setMeshes(triangleVertices(0, 0, 0, 1, 0, 0, 0, 1, 0), oneTriangleIndices(),
                                  triangleVertices(0, 0, dBelow, 1, 0, dBelow, 0, 1, dBelow), oneTriangleIndices()));
    EXPECT_TRUE(engine.hasCollision());
}

TEST(CollisionEngine, GapSlightlyLargerThanEpsilonDoesNotCollide) {
    const double eps = std::sqrt(2.0) * 1e-6;
    const double dAbove = eps * 2.0;
    CollisionEngine engine;
    ASSERT_TRUE(engine.setMeshes(triangleVertices(0, 0, 0, 1, 0, 0, 0, 1, 0), oneTriangleIndices(),
                                  triangleVertices(0, 0, dAbove, 1, 0, dAbove, 0, 1, dAbove), oneTriangleIndices()));
    EXPECT_FALSE(engine.hasCollision());
}
