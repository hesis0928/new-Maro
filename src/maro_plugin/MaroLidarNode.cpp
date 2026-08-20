#include "MaroLidarNode.h"

#include <maya/MFnMessageAttribute.h>
#include <maya/MFnNumericAttribute.h>
#include <maya/MFnStringData.h>
#include <maya/MFnTypedAttribute.h>
#include <maya/MFnUnitAttribute.h>

namespace maro {

MTypeId MaroLidarNode::id(0x00135106);

MObject MaroLidarNode::aVerticalSamples;
MObject MaroLidarNode::aVerticalMinAngle;
MObject MaroLidarNode::aVerticalMaxAngle;
MObject MaroLidarNode::aHorizontalSamples;
MObject MaroLidarNode::aHorizontalMinAngle;
MObject MaroLidarNode::aHorizontalMaxAngle;
MObject MaroLidarNode::aRangeMin;
MObject MaroLidarNode::aRangeMax;
MObject MaroLidarNode::aUpdateRate;
MObject MaroLidarNode::aFrameId;
MObject MaroLidarNode::aTargetMeshes;
MObject MaroLidarNode::aEnabled;

void* MaroLidarNode::creator() { return new MaroLidarNode(); }

MStatus MaroLidarNode::initialize() {
    MFnNumericAttribute numFn;
    MFnUnitAttribute angFn;
    MFnTypedAttribute typedFn;
    MFnMessageAttribute msgFn;
    MFnStringData stringDataFn;

    aVerticalSamples = numFn.create("verticalSamples", "vts", MFnNumericData::kInt, 4);
    numFn.setKeyable(true);
    addAttribute(aVerticalSamples);

    aVerticalMinAngle = angFn.create("verticalMinAngle", "vmn", MFnUnitAttribute::kAngle, -0.1);
    angFn.setKeyable(true);
    addAttribute(aVerticalMinAngle);

    aVerticalMaxAngle = angFn.create("verticalMaxAngle", "vmx", MFnUnitAttribute::kAngle, 0.1);
    angFn.setKeyable(true);
    addAttribute(aVerticalMaxAngle);

    aHorizontalSamples = numFn.create("horizontalSamples", "hts", MFnNumericData::kInt, 36);
    numFn.setKeyable(true);
    addAttribute(aHorizontalSamples);

    aHorizontalMinAngle =
        angFn.create("horizontalMinAngle", "hmn", MFnUnitAttribute::kAngle, -3.14159265358979);
    angFn.setKeyable(true);
    addAttribute(aHorizontalMinAngle);

    aHorizontalMaxAngle =
        angFn.create("horizontalMaxAngle", "hmx", MFnUnitAttribute::kAngle, 3.14159265358979);
    angFn.setKeyable(true);
    addAttribute(aHorizontalMaxAngle);

    aRangeMin = numFn.create("rangeMin", "rmn", MFnNumericData::kDouble, 0.1);
    numFn.setKeyable(true);
    addAttribute(aRangeMin);

    aRangeMax = numFn.create("rangeMax", "rmx", MFnNumericData::kDouble, 30.0);
    numFn.setKeyable(true);
    addAttribute(aRangeMax);

    aUpdateRate = numFn.create("updateRate", "upr", MFnNumericData::kDouble, 10.0);
    numFn.setKeyable(true);
    addAttribute(aUpdateRate);

    MObject defaultFrameId = stringDataFn.create("lidar_link");
    aFrameId = typedFn.create("frameId", "fri", MFnData::kString, defaultFrameId);
    typedFn.setKeyable(false);
    addAttribute(aFrameId);

    aTargetMeshes = msgFn.create("targetMeshes", "tgm");
    msgFn.setArray(true);
    msgFn.setIndexMatters(true);
    addAttribute(aTargetMeshes);

    aEnabled = numFn.create("enabled", "enb", MFnNumericData::kBoolean, true);
    numFn.setKeyable(true);
    addAttribute(aEnabled);

    return MS::kSuccess;
}

}  // namespace maro
