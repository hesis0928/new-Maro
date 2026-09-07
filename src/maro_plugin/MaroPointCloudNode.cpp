#include "MaroPointCloudNode.h"

#include <algorithm>
#include <atomic>
#include <cstdio>
#include <cstdlib>

#include <maya/MColor.h>
#include <maya/MDagPath.h>
#include <maya/MFnData.h>
#include <maya/MFnMessageAttribute.h>
#include <maya/MFnNumericAttribute.h>
#include <maya/MFnNumericData.h>
#include <maya/MFnPointArrayData.h>
#include <maya/MFnTypedAttribute.h>
#include <maya/MPlug.h>
#include <maya/MPoint.h>
#include <maya/MPointArray.h>

// Viewport 2.0
#include <maya/MDrawRegistry.h>
#include <maya/MFnDependencyNode.h>
#include <maya/MPxDrawOverride.h>
#include <maya/MUIDrawManager.h>
#include <maya/MUserData.h>
#include <maya/MViewport2Renderer.h>

#include "MaroDiag.h"

namespace {

// 뷰포트 콜백 경계에서 예외를 삼킬 때 쓰는 한 번만 찍는 로거. 이 경로들은
// 프레임마다 불리므로 그냥 로그하면 스크립트 에디터가 초당 수십 줄로 넘친다.
// 리뷰 Finding I1: 예전에는 여기서 MGlobal::displayWarning을 직접 불렀는데,
// 이 파일 가족의 다른 노드들(MaroAxisNode.cpp, MaroCapabilityNodes.cpp,
// MaroCommandDeviceNode.cpp)은 전부 maro::BoadMaro::error를 거친다. 그
// 관례를 깨면 두 가지가 깨진다: (1) BoadMaro::warn/error가 MGlobal::display*
// 에코를 isMainThread() 뒤로 가두는 가드(MaroDiag.h 참고 -- Evaluation
// Manager 워커 스레드는 MGlobal::display*를 직접 부르면 안 된다)를 이
// 콜백들만 우회하게 되고, (2) 실패가 진단 저널/Tech Diag 패널에 전혀 남지
// 않아 나중에 찾을 수 없다. 그래서 이 헬퍼는 BoadMaro::error로 위임만 하고,
// 세션당 1회 dedup만 스스로 담당한다.
void reportOnce(bool& reported, const std::string& siteTag, const MString& message,
                const maro::DgContext& context) {
    if (reported) return;
    reported = true;
    maro::BoadMaro::error(siteTag, message, context);
}

// MaroPointCloudNode 자신의 콜백(boundingBox/preEvaluation)용 DgContext
// 조립기. Viewport 2.0이 이 콜백들을 부르는 스레드는 compute()와 같은 처지다
// -- MaroAxisNode.cpp의 computeContext()와 정확히 같은 정책을 따른다: 노드
// "이름"은 MFnDependencyNode 조회가 필요한 진짜 Maya API 호출이므로
// isMainThread()가 안전을 보장할 때만 채우고, 워커면 빈 문자열로 둔다.
maro::DgContext pointCloudNodeContext(const MPxNode& node) {
    maro::DgContext ctx;
    ctx.nodeType = "maroPointCloud";
    ctx.activeCommand = maro::onfix::activeCommand();
    if (maro::isMainThread()) {
        // catch 블록 안에서(이미 예외가 한 번 난 상태에서) 부르므로, 이
        // 조회 자체가 또 실패해도 Maya 콜백 경계를 못 넘게 한 번 더 감싼다.
        try {
            MFnDependencyNode fn(node.thisMObject());
            ctx.axisOrTarget = fn.name().asChar();
        } catch (...) {
            ctx.nameUnavailable = true;
        }
    } else {
        ctx.nameUnavailable = true;
    }
    return ctx;
}

// MaroPointCloudDrawOverride::prepareForDraw()용 DgContext 조립기. 이쪽은
// MPxNode가 아니라 MDagPath만 갖고 있어 pointCloudNodeContext와 조회 경로가
// 다르다 -- 정책은 동일하다(isMainThread()가 안전을 보장할 때만 이름을 채움).
maro::DgContext pointCloudDrawContext(const MDagPath& objPath) {
    maro::DgContext ctx;
    ctx.nodeType = "maroPointCloud";
    ctx.activeCommand = maro::onfix::activeCommand();
    if (maro::isMainThread()) {
        try {
            MStatus status;
            MFnDependencyNode fn(objPath.node(&status));
            if (status) {
                ctx.axisOrTarget = fn.name().asChar();
            } else {
                ctx.nameUnavailable = true;
            }
        } catch (...) {
            ctx.nameUnavailable = true;
        }
    } else {
        ctx.nameUnavailable = true;
    }
    return ctx;
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
            // array()가 아니라 copyTo(). 여기는 지역 변수 pointsData가 아직
            // 살아 있는 같은 스코프라 array()로도 "우연히" 동작하지만,
            // prepareForDraw()에서 정확히 그 차이가 use-after-free를 냈다
            // (아래 주석 참고). 같은 파일 안에서 위험한 관용구와 안전한
            // 관용구를 섞어 두지 않는다.
            pointArrayDataFn.copyTo(points);
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
        reportOnce(reported, "MaroPointCloudNode.boundingBox.UnknownException",
                  "Maro: maroPointCloud boundingBox() swallowed an exception (reported once per session).",
                  pointCloudNodeContext(*this));
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
        reportOnce(reported, "MaroPointCloudNode.preEvaluation.UnknownException",
                  "Maro: maroPointCloud preEvaluation() swallowed an exception (reported once per session).",
                  pointCloudNodeContext(*this));
    }
    return MS::kSuccess;
}

}  // namespace maro

namespace {

// [진단, 2026-09-07] 드로우 오버라이드가 실제로 불리는지 세는 카운터.
// GUI에서 "점이 전혀 안 그려진다"는 증상이 (a) 콜백이 아예 안 불리는
// 것인지 (b) 불리는데 그리지 못하는 것인지 구분하려면 이게 필요하다.
// Maya API를 부르지 않고 원자적 증가만 하므로 워커 스레드에서도 안전하다
// (이 파일의 다른 주석이 경고하는 MGlobal::display* 금지 규칙과 무관).
std::atomic<long> gPrepareForDrawCalls{0};
std::atomic<long> gAddUIDrawablesCalls{0};
std::atomic<long> gDrawOverridesCreated{0};
std::atomic<long> gPointsDrawn{0};
std::atomic<long> gBailCastFailed{0};
std::atomic<long> gBailDisabled{0};
std::atomic<long> gBailEmpty{0};
std::atomic<long> gPrepNodeFnFailed{0};
std::atomic<long> gPrepPointsFailed{0};
std::atomic<long> gPrepPointsRead{0};

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
        ++gDrawOverridesCreated;
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
        // [최종 리뷰 Minor-3] 실패 경로도 기본 생성 MBoundingBox("무효" 상태)가
        // 아니라 노드 자신의 빈 배열 폴백과 **같은** -1..1 박스를 준다.
        // MaroPointCloudNode::boundingBox()의 주석이 이미 "무효 박스는 일부
        // 뷰포트 코드를 놀라게 할 수 있어서 피한다"고 적어 두었는데, 여기
        // 실패 경로들만 정확히 그 반대를 하고 있었다 -- 같은 노드의 두 경로가
        // 서로 모순되는 상태였다.
        static const MBoundingBox kFallback(MPoint(-1, -1, -1), MPoint(1, 1, 1));
        MStatus status;
        MFnDependencyNode nodeFn(objPath.node(&status));
        if (!status) return kFallback;
        auto* node = dynamic_cast<maro::MaroPointCloudNode*>(nodeFn.userNode());
        // MaroPointCloudNode::boundingBox()가 자기 예외를 이미 삼킨다.
        return node ? node->boundingBox() : kFallback;
    }

    // DG 조회는 여기서만 한다 -- addUIDrawables()는 절대 하지 않는다(전역 제약).
    MUserData* prepareForDraw(const MDagPath& objPath, const MDagPath& /*cameraPath*/,
                              const MHWRender::MFrameContext& /*frameContext*/,
                              MUserData* oldData) override {
        ++gPrepareForDrawCalls;
        auto* data = dynamic_cast<MaroPointCloudUserData*>(oldData);
        if (!data) data = new MaroPointCloudUserData();

        // Maya가 직접 부르는 경계 -- 예외를 넘기지 않는다(전역 제약). 도중에
        // 던져도 data 자체는 유효하므로 그대로 돌려주면 그 프레임은 직전
        // 스냅샷으로 그려진다.
        try {
            MStatus status;
            MFnDependencyNode nodeFn(objPath.node(&status));
            if (!status) {
                ++gPrepNodeFnFailed;
                return data;
            }

            data->enabled = nodeFn.findPlug(maro::MaroPointCloudNode::aEnabled, false).asBool();

            MPlug pointsPlug = nodeFn.findPlug(maro::MaroPointCloudNode::aPoints, false);
            MObject pointsData;
            pointsPlug.getValue(pointsData);
            MStatus pointsStatus;
            MFnPointArrayData pointArrayDataFn(pointsData, &pointsStatus);
            if (pointsStatus) {
                // [실측으로 잡은 버그, 2026-09-07] 여기서 array()를 쓰면 안 된다.
                // MFnPointArrayData::array()는 Maya 내부 데이터를 가리키는
                // *참조*를 돌려주지, 복사본을 주지 않는다 -- 위의 지역 변수
                // pointsData(MObject)와 pointArrayDataFn이 이 함수 끝에서
                // 사라지면 그 참조는 무효가 된다. 그래서 prepareForDraw는
                // 점 5개를 "읽었는데" 바로 다음에 불리는 addUIDrawables에서는
                // points.length()가 0이었다(카운터로 실측 확인). 즉 이 노드가
                // 뷰포트에 아무것도 안 그려지던 원인이고, 동시에 해제된
                // Maya 버퍼를 계속 붙들고 있는 use-after-free라서 나중에
                // 엉뚱한 곳에서 힙 손상 크래시로 터지던 원인이기도 하다
                // (크래시 덤프의 폴트가 ntdll 힙 관리자 안이었던 이유).
                // copyTo()가 실제 복사를 하는 접근자다.
                pointArrayDataFn.copyTo(data->points);
                gPrepPointsRead += static_cast<long>(data->points.length());
            } else {
                ++gPrepPointsFailed;
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
            reportOnce(reported, "MaroPointCloudDrawOverride.prepareForDraw.UnknownException",
                      "Maro: maroPointCloud prepareForDraw() swallowed an exception (reported once per session).",
                      pointCloudDrawContext(objPath));
        }

        return data;
    }

    bool hasUIDrawables() const override { return true; }

    void addUIDrawables(const MDagPath& /*objPath*/, MHWRender::MUIDrawManager& drawManager,
                        const MHWRender::MFrameContext& /*frameContext*/,
                        const MUserData* data) override {
        // 여기서는 DG를 절대 건드리지 않는다 -- 필요한 값은 전부
        // prepareForDraw()가 MaroPointCloudUserData에 캐시해 뒀다(전역 제약).
        ++gAddUIDrawablesCalls;
        try {
            const auto* pointCloudData = dynamic_cast<const MaroPointCloudUserData*>(data);
            if (!pointCloudData) {
                ++gBailCastFailed;
                return;
            }
            if (!pointCloudData->enabled) {
                ++gBailDisabled;
                return;
            }
            if (pointCloudData->points.length() == 0) {
                ++gBailEmpty;
                return;
            }
            gPointsDrawn += static_cast<long>(pointCloudData->points.length());
            drawManager.beginDrawable();
            drawManager.setColor(pointCloudData->color);
            drawManager.setPointSize(static_cast<float>(pointCloudData->pointSize));
            drawManager.mesh(MHWRender::MUIDrawManager::kPoints, pointCloudData->points);
            drawManager.endDrawable();
        } catch (...) {
            // objPath는 일부러 쓰지 않는다 -- 이 함수는 절대 DG를 건드리지
            // 않는다는 위 규칙이 예외 경로에서도 그대로 적용된다. 그래서
            // 노드 이름은 채우지 못한다("못 채움"이 아니라 "여기서는 원래
            // 안 채운다"에 가깝다); nodeType만 컴파일타임 상수로 채운다.
            static bool reported = false;
            reportOnce(reported, "MaroPointCloudDrawOverride.addUIDrawables.UnknownException",
                      "Maro: maroPointCloud addUIDrawables() swallowed an exception (reported once per session).",
                      maro::onfix::capture("maroPointCloud", "", ""));
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
    // [진단, 2026-09-07] MARO_TRACE_DRAW가 설정돼 있으면 이 세션에서
    // 드로우 오버라이드가 몇 번 불렸는지 stderr로 남긴다. "안 그려진다"가
    // 콜백 미호출인지 그리기 실패인지 구분하는 유일한 수단이다.
    // Maya API가 아니라 fprintf만 쓰므로 언로드 경로에서 안전하다.
    if (std::getenv("MARO_TRACE_DRAW") != nullptr) {
        std::fprintf(stderr,
                     "[maro-trace] pointCloud draw override: created=%ld "
                     "prepareForDraw=%ld addUIDrawables=%ld pointsDrawn=%ld\n"
                     "[maro-trace]   prepare: nodeFnFailed=%ld pointsFailed=%ld pointsRead=%ld\n"
                     "[maro-trace]   bail: castFailed=%ld disabled=%ld empty=%ld\n",
                     gDrawOverridesCreated.load(), gPrepareForDrawCalls.load(),
                     gAddUIDrawablesCalls.load(), gPointsDrawn.load(),
                     gPrepNodeFnFailed.load(), gPrepPointsFailed.load(),
                     gPrepPointsRead.load(),
                     gBailCastFailed.load(), gBailDisabled.load(), gBailEmpty.load());
        std::fflush(stderr);
    }
    return MHWRender::MDrawRegistry::deregisterDrawOverrideCreator(
        MaroPointCloudNode::kDrawDbClassification, MaroPointCloudNode::kDrawRegistrantId);
}

}  // namespace maro
