#include "MaroRosProxyCommands.h"

#include <exception>

#include <maya/MArgDatabase.h>
#include <maya/MDistance.h>
#include <maya/MDoubleArray.h>
#include <maya/MGlobal.h>
#include <maya/MSelectionList.h>
#include <maya/MStringArray.h>

#include "MaroDiag.h"
#include "maro_transform/Convert.h"
#include "maro_transform/Types.h"

namespace maro {
namespace {

// 짧은/긴 플래그 이름을 따로 둔다 -- MaroPanelCommands.cpp의
// kSeverityFlag/kSeverityFlagLong과 같은 이 코드베이스의 기존 관례
// (짧은 이름과 긴 이름에 같은 문자열을 재사용하는 전례가 없다).
constexpr char kPx[] = "-px", kPxLong[] = "-positionX";
constexpr char kPy[] = "-py", kPyLong[] = "-positionY";
constexpr char kPz[] = "-pz", kPzLong[] = "-positionZ";
constexpr char kQx[] = "-qx", kQxLong[] = "-rotationX";
constexpr char kQy[] = "-qy", kQyLong[] = "-rotationY";
constexpr char kQz[] = "-qz", kQzLong[] = "-rotationZ";
constexpr char kQw[] = "-qw", kQwLong[] = "-rotationW";
constexpr char kClearFlag[] = "-c", kClearFlagLong[] = "-clear";
constexpr char kPinnedTargetOptionVar[] = "maroRosProxyPinnedTarget";

// 필수 double 플래그 하나를 읽는다. 없으면 BoadMaro::error를 남기고
// kFailure를 돌려준다 -- 예외가 아니라 정상적인 커맨드 실패 경로다.
MStatus requireDoubleFlag(const MArgDatabase& argData, const char* flag, double& out) {
    if (!argData.isFlagSet(flag)) {
        BoadMaro::error(
            "MaroMayaToRosCommand.MissingFlag",
            MString("Maro: maroMayaToRos is missing required flag ") + flag,
            onfix::capture("", "", ""));
        return MS::kFailure;
    }
    MStatus status;
    out = argData.flagArgumentDouble(flag, 0, &status);
    return status;
}

}  // namespace

void* MaroMayaToRosCommand::creator() { return new MaroMayaToRosCommand(); }

MSyntax MaroMayaToRosCommand::newSyntax() {
    MSyntax syntax;
    syntax.addFlag(kPx, kPxLong, MSyntax::kDouble);
    syntax.addFlag(kPy, kPyLong, MSyntax::kDouble);
    syntax.addFlag(kPz, kPzLong, MSyntax::kDouble);
    syntax.addFlag(kQx, kQxLong, MSyntax::kDouble);
    syntax.addFlag(kQy, kQyLong, MSyntax::kDouble);
    syntax.addFlag(kQz, kQzLong, MSyntax::kDouble);
    syntax.addFlag(kQw, kQwLong, MSyntax::kDouble);
    return syntax;
}

MStatus MaroMayaToRosCommand::doIt(const MArgList& args) {
    try {
        MStatus status;
        MArgDatabase argData(newSyntax(), args, &status);
        if (!status) return status;

        Vec3 mayaPos;
        Quat mayaRot;
        if (!(status = requireDoubleFlag(argData, kPx, mayaPos.x))) return status;
        if (!(status = requireDoubleFlag(argData, kPy, mayaPos.y))) return status;
        if (!(status = requireDoubleFlag(argData, kPz, mayaPos.z))) return status;
        if (!(status = requireDoubleFlag(argData, kQx, mayaRot.x))) return status;
        if (!(status = requireDoubleFlag(argData, kQy, mayaRot.y))) return status;
        if (!(status = requireDoubleFlag(argData, kQz, mayaRot.z))) return status;
        if (!(status = requireDoubleFlag(argData, kQw, mayaRot.w))) return status;

        // MaroPump.cpp의 currentSceneUnit()과 같은 방식 -- 호출부가
        // 씬 단위를 몰라도 되게 커맨드 내부에서 직접 구한다.
        SceneUnit unit;
        unit.metersPerMayaUnit =
            MDistance(1.0, MDistance::internalUnit()).asMeters();

        const Vec3 rosPos = mayaToRosPosition(mayaPos, unit);
        const Quat rosRot = mayaToRosRotation(mayaRot);

        MDoubleArray result;
        result.append(rosPos.x);
        result.append(rosPos.y);
        result.append(rosPos.z);
        result.append(rosRot.x);
        result.append(rosRot.y);
        result.append(rosRot.z);
        result.append(rosRot.w);
        setResult(result);
        return MS::kSuccess;
    } catch (const std::exception& e) {
        MGlobal::displayError(MString("Maro: maroMayaToRos failed: ") + e.what());
        return MS::kFailure;
    } catch (...) {
        MGlobal::displayError("Maro: maroMayaToRos failed with unknown error.");
        return MS::kFailure;
    }
}

void* MaroSetRosProxyTargetCommand::creator() { return new MaroSetRosProxyTargetCommand(); }

MSyntax MaroSetRosProxyTargetCommand::newSyntax() {
    MSyntax syntax;
    syntax.addFlag(kClearFlag, kClearFlagLong, MSyntax::kNoArg);
    syntax.setObjectType(MSyntax::kStringObjects, 0, 1);
    return syntax;
}

MStatus MaroSetRosProxyTargetCommand::doIt(const MArgList& args) {
    try {
        MStatus status;
        MArgDatabase argData(newSyntax(), args, &status);
        if (!status) return status;

        const bool clearRequested = argData.isFlagSet(kClearFlagLong);
        MStringArray objects;
        argData.getObjects(objects);

        if (clearRequested) {
            if (objects.length() > 0) {
                BoadMaro::error(
                    "MaroSetRosProxyTargetCommand.ClearWithObject",
                    "Maro: maroSetRosProxyTarget -clear does not take an object name.",
                    onfix::capture("", "", ""));
                return MS::kFailure;
            }
            MGlobal::executeCommand(
                MString("optionVar -remove ") + kPinnedTargetOptionVar + ";");
            return MS::kSuccess;
        }

        if (objects.length() != 1) {
            BoadMaro::error(
                "MaroSetRosProxyTargetCommand.WrongArgCount",
                "Maro: maroSetRosProxyTarget needs exactly one object name, or -clear.",
                onfix::capture("", "", ""));
            return MS::kFailure;
        }

        MSelectionList sel;
        if (!sel.add(objects[0])) {
            BoadMaro::error(
                "MaroSetRosProxyTargetCommand.ObjectNotFound",
                MString("Maro: maroSetRosProxyTarget could not find object ") + objects[0],
                onfix::capture("", "", ""));
            return MS::kFailure;
        }

        MGlobal::executeCommand(
            MString("optionVar -sv ") + kPinnedTargetOptionVar + " \"" + objects[0] + "\";");
        return MS::kSuccess;
    } catch (const std::exception& e) {
        MGlobal::displayError(
            MString("Maro: maroSetRosProxyTarget failed: ") + e.what());
        return MS::kFailure;
    } catch (...) {
        MGlobal::displayError(
            "Maro: maroSetRosProxyTarget failed with unknown error.");
        return MS::kFailure;
    }
}

}  // namespace maro
