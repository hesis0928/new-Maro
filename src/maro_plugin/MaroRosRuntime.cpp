#include "MaroRosRuntime.h"

#include <chrono>

#include <rclcpp/rclcpp.hpp>

#include <geometry_msgs/msg/transform_stamped.hpp>
#include <sensor_msgs/msg/joint_state.hpp>
#include <sensor_msgs/msg/point_cloud2.hpp>
#include <tf2_msgs/msg/tf_message.hpp>

#include "maro_lidar/PointCloudPacking.h"
#include "maro_transform/Convert.h"

namespace maro {

struct MaroRosRuntime::Impl {
    std::shared_ptr<rclcpp::Node> node;
    rclcpp::Publisher<sensor_msgs::msg::JointState>::SharedPtr jointPub;
    rclcpp::Publisher<tf2_msgs::msg::TFMessage>::SharedPtr tfPub;
    rclcpp::Publisher<sensor_msgs::msg::PointCloud2>::SharedPtr lidarPub;
};

MaroRosRuntime::MaroRosRuntime() : m_impl(std::make_unique<Impl>()) {}

MaroRosRuntime::~MaroRosRuntime() {
    stop();
}

bool MaroRosRuntime::start(const std::string& robotName) {
    if (m_running.load()) return true;

    try {
        if (!rclcpp::ok()) {
            rclcpp::init(0, nullptr);
        }
        m_impl->node = rclcpp::Node::make_shared(robotName);
        // 상대 토픽 이름("joint_states")은 노드의 네임스페이스(기본 "/")
        // 아래로 풀려 "/joint_states"가 된다 -- 노드 *이름*은 토픽 해석에
        // 관여하지 않는다. MaroCommandDeviceNode.cpp(Task 10, 수신 방향)가
        // 이미 "/" + robotName + "/joint_commands"로 완전한 절대 경로를
        // 쓰고 있으므로, 발행 방향도 같은 관례를 따라야 두 방향이 같은
        // "/<robotName>/..." 네임스페이스 아래 나란히 선다.
        m_impl->jointPub =
            m_impl->node->create_publisher<sensor_msgs::msg::JointState>(
                "/" + robotName + "/joint_states", 10);
        m_impl->tfPub =
            m_impl->node->create_publisher<tf2_msgs::msg::TFMessage>("/tf", 10);
        // joint_states와 같은 절대 경로 관례 -- 위 주석 참고.
        m_impl->lidarPub =
            m_impl->node->create_publisher<sensor_msgs::msg::PointCloud2>(
                "/" + robotName + "/points", 10);
    } catch (const std::exception&) {
        // 예외가 Maya 쪽으로 새지 않게 여기서 막는다.
        m_impl->lidarPub.reset();
        m_impl->tfPub.reset();
        m_impl->jointPub.reset();
        m_impl->node.reset();
        return false;
    } catch (...) {
        m_impl->lidarPub.reset();
        m_impl->tfPub.reset();
        m_impl->jointPub.reset();
        m_impl->node.reset();
        return false;
    }

    m_stopRequested.store(false);
    m_running.store(true);
    m_thread = std::thread(&MaroRosRuntime::spinLoop, this);
    return true;
}

void MaroRosRuntime::stop() {
    if (!m_running.load()) return;

    m_stopRequested.store(true);
    if (m_thread.joinable()) {
        m_thread.join();
    }
    m_running.store(false);

    // 순서가 중요하다. 노드 내부를 참조하는 것들을 먼저 놓아야
    // DDS 참가자가 살아남아 프로세스가 안 끝나는 일이 없다. lidarPub도
    // 같은 노드를 붙들고 있으므로 여기서 함께 놓지 않으면 §12에서 실제로
    // 겪은 "퍼블리셔 누수로 프로세스가 종료되지 않는" 결함이 그대로 돌아온다.
    m_impl->lidarPub.reset();
    m_impl->tfPub.reset();
    m_impl->jointPub.reset();
    m_impl->node.reset();

    // 이 rclcpp::shutdown()은 프로세스 전역 rclcpp 컨텍스트를 끝낸다.
    // MaroCommandDeviceNode도 같은 전역 컨텍스트로 자기 노드를 만들므로,
    // 그쪽 스레드가 완전히 멈춘 뒤에만 여기까지 와야 한다. 호출자
    // (MaroCommands.cpp의 shutdownBridge())가 그 순서를 보장한다 — 여기서
    // 순서를 어기면 살아있는 스레드 밑에서 컨텍스트가 끊겨 크래시하거나
    // 프로세스가 끝나지 않는다.
    if (rclcpp::ok()) {
        rclcpp::shutdown();
    }
}

void MaroRosRuntime::spinLoop() {
    // try는 while 몸통 하나만 감싼다 -- 루프 전체를 감싸면 drainAndPublish()
    // 한 번의 예외로 루프를 완전히 빠져나가는데, m_running은 여전히
    // true라서 maroStartBridge는 "already running"이라 하고
    // maroBridgeStats 카운터는 그대로 멈춘 채 아무 로그도 안 남는다 --
    // "조용히 죽은 스레드"가 크래시보다 진단하기 어렵다는 게 이 프로젝트의
    // 설계 방침이다. MaroCommandDeviceNode::threadHandler()가 이미 같은
    // 관례를 쓴다: 그쪽도 try를 루프 안쪽에 둬서 실패한 틱 하나가 스레드
    // 전체를 끝내지 않게 한다.
    while (!m_stopRequested.load() && rclcpp::ok()) {
        try {
            // 이 노드는 퍼블리셔만 갖는다 — 구독은 MaroCommandDeviceNode
            // 쪽의 별도 노드가 처리한다 (Task 10 설계 노트). 퍼블리셔는
            // spin 없이도 publish()가 바로 나가므로 여기서
            // rclcpp::spin_some()을 부를 필요가 없다.
            //
            // Task 10에서는 개수만 셌다. 이제 실제로 발행한다.
            drainAndPublish();
        } catch (...) {
            // 이 틱은 건너뛰지만 스레드는 계속 돈다. 카운터로만 남기고
            // 다음 반복에서 다시 시도한다.
            m_publishErrors.fetch_add(1, std::memory_order_relaxed);
        }

        std::this_thread::sleep_for(std::chrono::milliseconds(5));
    }
}

void MaroRosRuntime::drainAndPublish() {
    // 축 드레인은 이르게 return 하면 안 된다 -- 아래 LiDAR 드레인이 같은
    // 함수에 있기 때문이다. 예전에는 `if (samples.empty()) return;`와
    // `if (!jointPub || !tfPub) return;`가 함수 앞머리에 있었는데, 축이
    // 하나도 없는 씬(LiDAR만 있는 씬)에서는 그 첫 return이 항상 걸려
    // LiDAR가 영영 발행되지 않는다. 조건을 return이 아니라 블록 가드로
    // 바꿔 두 드레인이 서로 독립이 되게 한다 -- 카운터 증가 시점(퍼블리셔
    // 유무와 무관하게 드레인한 만큼)은 예전 그대로다.
    const std::vector<AxisSample> samples = m_publishQueue.drain();
    if (!samples.empty()) {
        m_drainedSamples.fetch_add(samples.size(), std::memory_order_relaxed);

        if (m_impl->jointPub && m_impl->tfPub) {
            sensor_msgs::msg::JointState joints;
            joints.header.stamp = m_impl->node->now();

            tf2_msgs::msg::TFMessage tf;

            for (const AxisSample& sample : samples) {
                joints.name.push_back(sample.jointName);
                joints.position.push_back(sample.value);

                const Vec3 p = mayaToRosPosition(sample.position, sample.unit);
                const Quat q = mayaToRosRotation(sample.rotation);

                geometry_msgs::msg::TransformStamped t;
                t.header.stamp = joints.header.stamp;
                t.header.frame_id = "world";
                t.child_frame_id = sample.jointName;
                t.transform.translation.x = p.x;
                t.transform.translation.y = p.y;
                t.transform.translation.z = p.z;
                t.transform.rotation.x = q.x;
                t.transform.rotation.y = q.y;
                t.transform.rotation.z = q.z;
                t.transform.rotation.w = q.w;
                tf.transforms.push_back(t);
            }

            m_impl->jointPub->publish(joints);
            m_impl->tfPub->publish(tf);
        }
    }

    // LiDAR도 축과 같은 자리에서 좌표 변환한다 -- 메인 스레드(MaroPump)는
    // Maya 좌표계 그대로 실어 보내고, 변환은 이 백그라운드 스레드 한 곳에서만
    // 일어난다.
    const std::vector<LidarSample> lidarSamples = m_lidarQueue.drain();
    if (!lidarSamples.empty()) {
        // 축과 별개인 전용 계수기다 (Finding M1) -- 예전에는 여기서도
        // m_drainedSamples를 밀어서 두 생산자가 한 숫자에 섞였다.
        // 그리고 증가는 퍼블리셔 유무보다 위에 있다 (Finding M2): 축
        // 분기(위 141행)가 이미 "드레인한 만큼 무조건" 올리는데 LiDAR만
        // lidarPub이 있을 때만 올리면 같은 이름의 계수기가 생산자에 따라
        // 다른 뜻을 갖는다.
        m_drainedLidarScans.fetch_add(lidarSamples.size(), std::memory_order_relaxed);

        if (m_impl->lidarPub) {
            for (const LidarSample& sample : lidarSamples) {
                std::vector<Vec3> rosPoints;
                rosPoints.reserve(sample.points.size());
                for (const Vec3& p : sample.points) {
                    rosPoints.push_back(mayaToRosPosition(p, sample.unit));
                }
                const maro::lidar::PackedPointCloud packed =
                    maro::lidar::packPointCloud(rosPoints, {});

                sensor_msgs::msg::PointCloud2 cloud;
                cloud.header.stamp = m_impl->node->now();
                // sample.points는 라이다 로컬 프레임이 아니라 월드 좌표(mayaToRosPosition은
                // 기저/단위만 바꿀 뿐 원점을 옮기지 않는다)이므로, 축 경로(158행)와 같은
                // "world"를 찍는다. 노드의 frameId 어트리뷰트를 여기 쓰려면 먼저 히트를
                // 라이다 로컬 프레임으로 변환하고 world->frameId TF를 함께 발행해야 한다
                // -- 워킹 스켈레톤에서는 의도적으로 보류. 그래서 LidarSample은 아예
                // frameId를 나르지 않는다 (Finding I4, MaroBridgeQueues.h 참고).
                cloud.header.frame_id = "world";
                cloud.height = 1;
                cloud.width = packed.width;
                cloud.is_bigendian = false;
                cloud.is_dense = true;
                cloud.point_step = packed.pointStep;
                cloud.row_step = packed.pointStep * packed.width;

                sensor_msgs::msg::PointField fieldX, fieldY, fieldZ, fieldIntensity;
                fieldX.name = "x"; fieldX.offset = 0; fieldX.datatype = sensor_msgs::msg::PointField::FLOAT32; fieldX.count = 1;
                fieldY.name = "y"; fieldY.offset = 4; fieldY.datatype = sensor_msgs::msg::PointField::FLOAT32; fieldY.count = 1;
                fieldZ.name = "z"; fieldZ.offset = 8; fieldZ.datatype = sensor_msgs::msg::PointField::FLOAT32; fieldZ.count = 1;
                fieldIntensity.name = "intensity"; fieldIntensity.offset = 12; fieldIntensity.datatype = sensor_msgs::msg::PointField::FLOAT32; fieldIntensity.count = 1;
                cloud.fields = {fieldX, fieldY, fieldZ, fieldIntensity};

                cloud.data = packed.data;

                m_impl->lidarPub->publish(cloud);
            }
        }
    }
}

}  // namespace maro
