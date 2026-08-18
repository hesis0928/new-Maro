#include "maro_diag/RemedyAction.h"

#include <cmath>

namespace maro {

std::string describeRemedyAction(const RemedyAction& action) {
    switch (action.kind) {
        case RemedyActionKind::None:
            return "";
        case RemedyActionKind::SelectNode:
            return "'" + action.nodeName + "' 노드를 선택합니다.";
        case RemedyActionKind::SetAttribute: {
            const long long rounded = std::llround(action.value);
            return "'" + action.nodeName + "'." + action.attributeName +
                   " 값을 " + std::to_string(rounded) + "(으)로 설정합니다.";
        }
        case RemedyActionKind::Disconnect:
            return "'" + action.sourcePlug + "' -> '" + action.destPlug +
                   "' 연결을 끊습니다.";
    }
    return "";
}

}  // namespace maro
