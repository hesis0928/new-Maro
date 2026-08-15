cmake_minimum_required(VERSION 3.8)
project(image_bridge)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# ament_cmake와 뼈대(maro_library) 불러오기
find_package(ament_cmake REQUIRED)
find_package(maro_library REQUIRED)

find_package(Boost REQUIRED COMPONENTS interprocess)
find_package(OpenCV REQUIRED)

set(NETWORK_LIBS ws2_32)

add_executable(image_bridge_node src/image_bridge_node.cpp)

target_include_directories(image_bridge_node PRIVATE ${Boost_INCLUDE_DIRS} ${OpenCV_INCLUDE_DIRS})
target_link_libraries(image_bridge_node PRIVATE Boost::interprocess ${OpenCV_LIBRARIES} ${NETWORK_LIBS})

# ROS 2 시스템(rclcpp) 없이 순수 헤더(IpcData.h)만 안전하게 연결!
ament_target_dependencies(image_bridge_node maro_library)

install(TARGETS image_bridge_node DESTINATION lib/${PROJECT_NAME})

ament_package()