#include "MaroPointCloudNode.h"

#include <algorithm>

#include <maya/MColor.h>
#include <maya/MDagPath.h>
#include <maya/MFnData.h>
#include <maya/MFnMessageAttribute.h>
#include <maya/MFnNumericAttribute.h>
#include <maya/MFnNumericData.h>
#include <maya/MFnPointArrayData.h>
#include <maya/MFnTypedAttribute.h>
#include <maya/MGlobal.h>
#include <maya/MPlug.h>
#include <maya/MPoint.h>
#include <maya/MPointArray.h>

// Viewport 2.0
#include <maya/MDrawContext.h>
#include <maya/MDrawRegistry.h>
#include <maya/MFnDependencyNode.h>
#include <maya/MHWGeometryUtilities.h>
#include <maya/MPxDrawOverride.h>
#include <maya/MUIDrawManager.h>
#include <maya/MUserData.h>
#include <maya/MViewport2Renderer.h>

namespace {

// 뷰포트 콜백 경계에서 예외를 삼킬 때 쓰는 한 번만 찍는 로거. 이 경로들은
// 프레임마다 불리므로 그냥 로그하면 스크립트 에디터가 초당 수십 줄로 넘친다.
void reportOnce(bool& reported, const char* what) {
    if (reported) return;
    reported = true;
    MGlobal::displayWarning(MString("Maro: maroPointCloud ") + what +
                            " swallowed an exception (reported once per session).");
}

}  // namespace

namespace maro {

// 브리프는 0x00135108을 지정했지만 그 ID는 이미 MaroTranslationLimitNode가
// 쓰고 있다(MaroCapabilityNodes.cpp:422 -- Phase 4에서 병합됨). 이 플랜이
// 작성될 당시의 등록 목록을 기준으로 번호를 골랐다가, 그 사이 병합된 Phase 4의
// 0x00135107~0x00135109와 겹친 것이다(Phase 4 계획서 자체가 "구현 시점에 다시
// grep해서 충돌을 확인하라"고 남겨 둔 바로 그 함정). 현재 사용 중인 구간은
// 0x00135100~0x00135109이므로 다음 미사용 번호인 0x0013510A를 쓴다.
MTypeId MaroPointCloudNode::id(0x0013510A);
MString MaroPointCloudNode::kDrawDbClassification("drawdb/geometry/maro/pointCloud");
MString MaroPointCloudNode::kDrawRegistrantId("MaroPointCloudPlugin");

MObject MaroPointCloudNode::aPoints;
MObject MaroPointCloudNode::aPointSize;
MObject MaroPointCloudNode::aColor;
MObject MaroPointCloudNode::aEnabled;
MObject MaroPointCloudNode::aSourceLidar;

void* MaroPointCloudNode::creator() { return new MaroPointCloudNode(); }

MStatus MaroPointCloudNode::initialize() {
    MFnTypedAttribute typedFn;
    MFnNumericAttribute numFn;
    MFnMessageAttribute msgFn;
    MFnPointArrayData pointArrayDataFn;

    MObject defaultPoints = pointArrayDataFn.create(MPointArray());
    aPoints = typedFn.create("points", "pts", MFnData::kPointArray, defaultPoints);
    // 세션 내 스캔 스냅샷일 뿐 씬 파일에 저장하지 않는다(전역 제약 참고).
    typedFn.setStorable(false);
    typedFn.setKeyable(false);
    addAttribute(aPoints);

    aPointSize = numFn.create("pointSize", "psz", MFnNumericData::kDouble, 2.0);
    numFn.setKeyable(true);
    numFn.setMin(0.1);
    addAttribute(aPointSize);

    aColor = numFn.createColor("color", "clr");
    numFn.setDefault(0.2f, 0.8f, 1.0f);
    numFn.setKeyable(true);
    addAttribute(aColor);

    aEnabled = numFn.create("enabled", "enb", MFnNumericData::kBoolean, true);
    numFn.setKeyable(true);
    addAttribute(aEnabled);

    aSourceLidar = msgFn.create("sourceLidar", "srl");
    addAttribute(aSourceLidar);

    return MS::kSuccess;
}

MBoundingBox MaroPointCloudNode::boundingBox() const {
    // 이 함수도 Maya가 직접 부르는 콜백 경계다 -- 예외를 넘기지 않는다
    // (전역 제약: Maya 콜백에서 예외가 새면 안 된다).
    try {
        MObject thisNode = thisMObject();
        MPlug pointsPlug(thisNode, aPoints);
        MObject pointsData;
        pointsPlug.getValue(pointsData);

        MStatus status;
        MFnPointArrayData pointArrayDataFn(pointsData, &status);
        MPointArray points;
        if (status) {
            points = pointArrayDataFn.array();
        }

        // 빈 배열이면 오비트 컬링을 피할 수 있는 작은 기본 박스를 준다 --
        // MBoundingBox()의 기본 생성자는 "무효" 상태라 일부 뷰포트 코드가
        // 놀랄 수 있다.
        if (points.length() == 0) {
            return MBoundingBox(MPoint(-1, -1, -1), MPoint(1, 1, 1));
        }

        MPoint minP = points[0];
        MPoint maxP = points[0];
        for (unsigned int i = 1; i < points.length(); ++i) {
            const MPoint& p = points[i];
            minP.x = std::min(minP.x, p.x);
            minP.y = std::min(minP.y, p.y);
            minP.z = std::min(minP.z, p.z);
            maxP.x = std::max(maxP.x, p.x);
            maxP.y = std::max(maxP.y, p.y);
            maxP.z = std::max(maxP.z, p.z);
        }
        return MBoundingBox(minP, maxP);
    } catch (...) {
        static bool reported = false;
        reportOnce(reported, "boundingBox()");
        return MBoundingBox(MPoint(-1, -1, -1), MPoint(1, 1, 1));
    }
}

MStatus MaroPointCloudNode::preEvaluation(const MDGContext& context,
                                          const MEvaluationNode& evaluationNode) {
    try {
        if (context.isNormal()) {
            MStatus status;
            if (evaluationNode.dirtyPlugExists(aPoints, &status) && status) {
                MHWRender::MRenderer::setGeometryDrawDirty(thisMObject());
            }
        }
    } catch (...) {
        static bool reported = false;
        reportOnce(reported, "preEvaluation()");
    }
    return MS::kSuccess;
}

}  // namespace maro

namespace {

class MaroPointCloudUserData : public MUserData {
public:
    MaroPointCloudUserData() = default;
    MPointArray points;
    MColor color{0.2f, 0.8f, 1.0f, 1.0f};
    double pointSize = 2.0;
    bool enabled = true;
};

}  // namespace

class MaroPointCloudDrawOverride : public MHWRender::MPxDrawOverride {
public:
    static MHWRender::MPxDrawOverride* creator(const MObject& obj) {
        return new MaroPointCloudDrawOverride(obj);
    }

    ~MaroPointCloudDrawOverride() override = default;

    MHWRender::DrawAPI supportedDrawAPIs() const override {
        return (MHWRender::kOpenGL | MHWRender::kDirectX11 | MHWRender::kOpenGLCoreProfile);
    }

    bool isBounded(const MDagPath& /*objPath*/, const MDagPath& /*cameraPath*/) const override {
        return true;
    }

    MBoundingBox boundingBox(const MDagPath& objPath, const MDagPath& /*cameraPath*/) const override {
        MStatus status;
        MFnDependencyNode nodeFn(objPath.node(&status));
        if (!status) return MBoundingBox();
        auto* node = dynamic_cast<maro::MaroPointCloudNode*>(nodeFn.userNode());
        // MaroPointCloudNode::boundingBox()가 자기 예외를 이미 삼킨다.
        return node ? node->boundingBox() : MBoundingBox();
    }

    // DG 조회는 여기서만 한다 -- addUIDrawables()는 절대 하지 않는다(전역 제약).
    MUserData* prepareForDraw(const MDagPath& objPath, const MDagPath& /*cameraPath*/,
                              const MHWRender::MFrameContext& /*frameContext*/,
                              MUserData* oldData) override {
        auto* data = dynamic_cast<MaroPointCloudUserData*>(oldData);
        if (!data) data = new MaroPointCloudUserData();

        // Maya가 직접 부르는 경계 -- 예외를 넘기지 않는다(전역 제약). 도중에
        // 던져도 data 자체는 유효하므로 그대로 돌려주면 그 프레임은 직전
        // 스냅샷으로 그려진다.
        try {
            MStatus status;
            MFnDependencyNode nodeFn(objPath.node(&status));
            if (!status) return data;

            data->enabled = nodeFn.findPlug(maro::MaroPointCloudNode::aEnabled, false).asBool();

            MPlug pointsPlug = nodeFn.findPlug(maro::MaroPointCloudNode::aPoints, false);
            MObject pointsData;
            pointsPlug.getValue(pointsData);
            MStatus pointsStatus;
            MFnPointArrayData pointArrayDataFn(pointsData, &pointsStatus);
            if (pointsStatus) {
                data->points = pointArrayDataFn.array();
            } else {
                data->points.clear();
            }

            data->pointSize = nodeFn.findPlug(maro::MaroPointCloudNode::aPointSize, false).asDouble();

            MPlug colorPlug = nodeFn.findPlug(maro::MaroPointCloudNode::aColor, false);
            float r = 0.2f, g = 0.8f, b = 1.0f;
            colorPlug.child(0).getValue(r);
            colorPlug.child(1).getValue(g);
            colorPlug.child(2).getValue(b);
            data->color = MColor(r, g, b, 1.0f);
        } catch (...) {
            static bool reported = false;
            reportOnce(reported, "prepareForDraw()");
        }

        return data;
    }

    bool hasUIDrawables() const override { return true; }

    void addUIDrawables(const MDagPath& /*objPath*/, MHWRender::MUIDrawManager& drawManager,
                        const MHWRender::MFrameContext& /*frameContext*/,
                        const MUserData* data) override {
        // 여기서는 DG를 절대 건드리지 않는다 -- 필요한 값은 전부
        // prepareForDraw()가 MaroPointCloudUserData에 캐시해 뒀다(전역 제약).
        try {
            const auto* pointCloudData = dynamic_cast<const MaroPointCloudUserData*>(data);
            if (!pointCloudData || !pointCloudData->enabled || pointCloudData->points.length() == 0) {
                return;
            }
            drawManager.beginDrawable();
            drawManager.setColor(pointCloudData->color);
            drawManager.setPointSize(static_cast<float>(pointCloudData->pointSize));
            drawManager.mesh(MHWRender::MUIDrawManager::kPoints, pointCloudData->points);
            drawManager.endDrawable();
        } catch (...) {
            static bool reported = false;
            reportOnce(reported, "addUIDrawables()");
        }
    }

private:
    explicit MaroPointCloudDrawOverride(const MObject& obj)
        : MHWRender::MPxDrawOverride(obj, nullptr, false) {}
};

namespace maro {

MStatus registerPointCloudDrawOverride() {
    return MHWRender::MDrawRegistry::registerDrawOverrideCreator(
        MaroPointCloudNode::kDrawDbClassification, MaroPointCloudNode::kDrawRegistrantId,
        MaroPointCloudDrawOverride::creator);
}

MStatus deregisterPointCloudDrawOverride() {
    return MHWRender::MDrawRegistry::deregisterDrawOverrideCreator(
        MaroPointCloudNode::kDrawDbClassification, MaroPointCloudNode::kDrawRegistrantId);
}

}  // namespace maro
