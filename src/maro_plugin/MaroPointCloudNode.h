#pragma once

#include <maya/MBoundingBox.h>
#include <maya/MDGContext.h>
#include <maya/MEvaluationNode.h>
#include <maya/MObject.h>
#include <maya/MPxLocatorNode.h>
#include <maya/MStatus.h>
#include <maya/MString.h>
#include <maya/MTypeId.h>

namespace maro {

// 스캔 결과 포인트를 Viewport 2.0에 그리는 로케이터. maroAxis/maroLidar와 같은
// MPxLocatorNode 패턴이지만, 그리기 자체는 이 노드가 아니라 짝을 이루는
// MaroPointCloudDrawOverride(같은 .cpp)가 한다 -- registerNode에
// kDrawDbClassification을 함께 주는 것이 그 연결이다.
//
// 이 태스크는 LiDAR와 완전히 무관하다: points를 손으로 채운 값으로 채워도
// 그려지고, 창을 띄운 채 언로드해도 죽지 않는다는 것만 증명한다.
class MaroPointCloudNode : public MPxLocatorNode {
public:
    MaroPointCloudNode() = default;
    ~MaroPointCloudNode() override = default;

    static void* creator();
    static MStatus initialize();

    bool isBounded() const override { return true; }
    MBoundingBox boundingBox() const override;

    // points가 dirty해지면 Viewport 2.0에 다시 그리라고 명시적으로 알린다.
    // MPxDrawOverride(..., isAlwaysDirty=false)는 이 신호 없이는 언제 다시
    // 그려야 하는지 스스로 알지 못한다(devkit footPrintNode.cpp의
    // preEvaluation()과 같은 이유, 같은 패턴).
    MStatus preEvaluation(const MDGContext& context,
                          const MEvaluationNode& evaluationNode) override;

    static MTypeId id;
    static MObject aPoints;
    static MObject aPointSize;
    static MObject aColor;
    static MObject aEnabled;
    // 이 포인트클라우드를 만든 maroLidar를 가리키는 메시지 커넥션(단일,
    // 배열 아님). Task 4가 생성 시점에 연결하고, LiDAR 설정 팝업이
    // "이 lidar에 연결된 포인트클라우드"를 역참조로 찾을 때 쓴다.
    static MObject aSourceLidar;

    // Viewport 2.0 드로우 오버라이드 등록에 쓰는 classification 문자열.
    // registerNode()와 MDrawRegistry::registerDrawOverrideCreator() 양쪽이
    // 정확히 같은 문자열 인스턴스를 참조해야 서로 연결된다.
    static MString kDrawDbClassification;
    static MString kDrawRegistrantId;
};

// Viewport 2.0 드로우 오버라이드 등록/해제. 브리프 Step 4는 MaroPluginMain.cpp가
// MHWRender::MDrawRegistry::registerDrawOverrideCreator(...,
// MaroPointCloudDrawOverride::creator)를 직접 부르게 했지만, 그 클래스는
// MaroPointCloudNode.cpp 안에만 정의돼 있어(devkit footPrintNode.cpp의 배치를
// 그대로 따른 결과) 다른 번역 단위인 MaroPluginMain.cpp에서는 이름이 보이지
// 않는다 -- 그대로 쓰면 컴파일되지 않는다. 클래스 정의를 헤더로 끌어올려
// MPxDrawOverride/MUIDrawManager 헤더를 플러그인 전체에 퍼뜨리는 대신, 등록
// 자체를 이 두 함수로 감싼다. 뷰포트 2.0 세부사항은 .cpp 안에 머물고,
// MaroPluginMain.cpp는 여전히 "드로우 오버라이드 해제가 노드 해제보다 먼저"라는
// 순서 규율을 눈에 보이게 지킬 수 있다(전역 제약).
MStatus registerPointCloudDrawOverride();
MStatus deregisterPointCloudDrawOverride();

}  // namespace maro
