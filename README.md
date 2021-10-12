# smarc_missions
![CI](https://github.com/smarc-project/smarc_missions/workflows/CI/badge.svg?branch=noetic-devel) [![license](https://img.shields.io/badge/License-BSD%203--Clause-blue.svg)](https://opensource.org/licenses/BSD-3-Clause)

Behavior trees and such for different missions



# sam follow line 

In the "smarc_bt.py" file, three topics are read in the "const_data_ingestion_tree" as read_marker1, read_marker3 anbd read_intercepts.
In the "const_execute_mission_tree" a sample_action "A_FollowWaypoint" is called, which performs a custom action.

In the "bt_actions.py" file, a separate action client is created called as "A_FollowWaypoint". The initial goal point is set to marker1. In the "update" funtion, if there is no detected line point(intercept) it continues to go the subscribed marker1 goal. 
If intercept is not None and is not equal to marker1, the goal changes to the intercept. As the robot moves forward, it keeps on detecing the intercepts and the goal changes simultaneously.

The goal is further sent to the action server "wp_depth_action_planner.py".

# How to run

1. catkin_ws/$ catkin build sam_action_servers

2. (terminal 1)  catkin_ws/$ rosrun sam_stonefish_sim bringup.sh 
(start all the nodes, try to pull the robot back manually a bit otherwise it hits the buoy/rope with time and SAM goes to error state in neptus)

3. (terminal 2)  catkin_ws/src/neptus$ ./neptus 
(choose sample goto waypoint)

4. (terminal 3) catkin_ws/$ roslaunch sss_object_detection sim_lines.launch
(this will subscribe to the published markers in map frame and publish them in utm. Also this will publish the intercepts in utm frame.)

5.( terminal 4) catkin_ws/$ rviz
(to vizualize, choose marker.rviz)

