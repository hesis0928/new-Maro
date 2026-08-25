#pragma once

#include <maya/MPxCommand.h>
#include <maya/MSyntax.h>
#include <maya/MPlug.h>
#include <maya/MDGModifier.h>
#include <maya/MString.h>

namespace maro {

// 씬의 maroAxis 전체 또는 한 축의 capability 스택을 나열한다. 쿼리
// 전용이라 undoable이 아니다.
class MaroListAxisNodesCommand : public MPxCommand {
public:
    static void* creator();
    static MSyntax newSyntax();
    MStatus doIt(const MArgList& args) override;
    bool isUndoable() const override { return false; }
};

// -type <rotation|translation|limit|translationLimit|sensorDirection|
// sensorRange|coupling> <axis>: capability 노드를 새로 만들어 축의
// capabilityIn 빈 슬롯에 연결한다(undoable). setResult로 새 노드 이름을
// 돌려준다.
class MaroAddCapabilityCommand : public MPxCommand {
public:
    static void* creator();
    static MSyntax newSyntax();
    MStatus doIt(const MArgList& args) override;
    MStatus redoIt() override;
    MStatus undoIt() override;
    bool isUndoable() const override { return m_stagedChange; }

private:
    MDGModifier m_modifier;
    bool m_stagedChange = false;
    MString m_capNodeName;
};

// <capabilityNode> <axis> [-index <int>]: 이미 존재하는 capability 노드를
// 축의 capabilityIn 슬롯에 연결한다(undoable).
class MaroConnectCapabilityCommand : public MPxCommand {
public:
    static void* creator();
    static MSyntax newSyntax();
    MStatus doIt(const MArgList& args) override;
    MStatus redoIt() override;
    MStatus undoIt() override;
    bool isUndoable() const override { return m_stagedChange; }

private:
    MDGModifier m_modifier;
    bool m_stagedChange = false;
};

// <axis> -index <int>: capabilityIn[index]의 연결만 끊는다(배열 원소
// 자체는 지우지 않는다). undoable.
class MaroDisconnectCapabilityCommand : public MPxCommand {
public:
    static void* creator();
    static MSyntax newSyntax();
    MStatus doIt(const MArgList& args) override;
    MStatus redoIt() override;
    MStatus undoIt() override;
    bool isUndoable() const override { return m_stagedChange; }

private:
    MDGModifier m_modifier;
    bool m_stagedChange = false;
};

// <axis>: 축의 targetObject 바인딩을 해제한다(undoable).
class MaroUnbindAxisCommand : public MPxCommand {
public:
    static void* creator();
    static MSyntax newSyntax();
    MStatus doIt(const MArgList& args) override;
    MStatus redoIt() override;
    MStatus undoIt() override;
    bool isUndoable() const override { return m_stagedChange; }

private:
    MDGModifier m_modifier;
    bool m_stagedChange = false;
};

// Task 6(쓰기 커맨드)이 재사용하는 헬퍼.
unsigned int nextFreeCapabilitySlot(MPlug capabilityInPlug);
bool hasPrimaryDriver(MPlug capabilityInPlug);

}  // namespace maro
