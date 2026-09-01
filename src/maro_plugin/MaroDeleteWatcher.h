#pragma once

#include <maya/MCallbackIdArray.h>
#include <maya/MDGModifier.h>
#include <maya/MObject.h>
#include <maya/MStatus.h>

namespace maro {

// 삭제 규칙은 비대칭이다.
//   오브젝트 삭제 -> 바인딩된 축도 삭제
//   축 삭제       -> 오브젝트는 생존, 능력 노드는 고아로 남음
//
// [최종 리뷰 I-4] LiDAR 쌍도 같은 규율로 다룬다. 비대칭도 같은 모양이다:
//   maroLidar 삭제      -> 짝인 maroPointCloud도 삭제
//   maroPointCloud 삭제 -> maroLidar는 생존
//
// 방향이 이쪽인 이유: maroPointCloud는 maroLidar 하나의 스캔 결과를 그리는
// **종속 시각화 노드**다. 마킹 메뉴가 만드는 배치에서 그것은 탑재 오브젝트의
// DAG 하위가 아니라 공유 프록시 그룹(maroRosProxy_grp) 아래에 산다 -- 즉
// 탑재 오브젝트를 지우면 maroLidar는 자식으로서 함께 사라지지만
// maroPointCloud는 전혀 다른 부모 밑에 있어 살아남고, 마지막 스캔 스냅샷을
// 영원히 그리는 고아가 된다. 사용자 입장에서는 "지운 LiDAR의 점이 계속
// 보이는" 상태이고, 아웃라이너에서 프록시 그룹을 펼쳐 보기 전에는 그것이
// 무엇인지조차 알 수 없다.
//
// 반대 방향으로는 지우지 않는다(능력 노드를 축 삭제 때 지우지 않는 것과 같은
// 취지다): maroPointCloud는 순수한 표시 장치라 그것 하나를 지우는 것은
// "시각화를 끈다"는 뜻이지 "센서를 없앤다"는 뜻이 아니다. 그래서
// maroPointCloud에는 삭제 콜백을 아예 걸지 않는다.
//
// addNodeAboutToDeleteCallback이 넘겨주는 MDGModifier에 작업을 실으면
// 사용자의 삭제와 같은 undo 청크로 묶인다. 직접 청킹할 필요가 없다.
class MaroDeleteWatcher {
public:
    static MStatus install();
    static MStatus uninstall();

private:
    static void onNodeAdded(MObject& node, void* clientData);
    static void onObjectAboutToDelete(MObject& node, MDGModifier& modifier,
                                      void* clientData);
    static void onAxisAboutToDelete(MObject& node, MDGModifier& modifier,
                                    void* clientData);
    static void onLidarAboutToDelete(MObject& node, MDGModifier& modifier,
                                     void* clientData);

    static MCallbackIdArray s_callbacks;
};

}  // namespace maro
