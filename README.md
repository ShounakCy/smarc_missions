# smarc_missions
![CI](https://github.com/smarc-project/smarc_missions/workflows/CI/badge.svg?branch=noetic-devel) [![license](https://img.shields.io/badge/License-BSD%203--Clause-blue.svg)](https://opensource.org/licenses/BSD-3-Clause)

Behavior trees and such for different missions

### SAM detect line and fit line

Go to package `sss_object_detection`

`sim_lines.py` - if you want to draw fake lines and get the slope and intercept values between the corner buoys.

`sim_detect_lines.py`(outdated) - tried to detect line w.r.t to the heading and find the position of the robot. Followed the same theory used to detect the buoy in the `sim_sss_detection_publisher.py` script.

`sim_tf_lines.py` -  The script performs multiple transformations.
1. The marker positions are subscibed.
2. The marker positions are transformed from map frame to robot frame, to calculate the intercepts between the buoy1 and 3. 
3. For the behaviour tree, the marker positions are also tranformed from map frame to utm frame.
4. Using least square method the slope and intercepts are calculated and conditions are written for slopes, to detect the line.
5. The intercepts are then transformed from the robot frame to the map frame.
6. A point cloud of intercepts are published.
7. Same set of intercepts is published as Point Stamped. The intercepts publised here are transformed to utm frame from map frame for the behaviour tree.

To execute, (terminal) /catkin_ws$ roslaunch sss_object_detection sim_lines.launch

`sim_lines_wf.py` - A line is fitted using RANSAC, from the point cloud formed from the subscribed intercept points.

1. Subscibe to intercept point cloud in map frame.
2. store in a list and convert it to array.
3. Publish the latest intercetps in Point Stamped for future reference.
4. Usinf RANSACRegressor to fit a line for a given number of points in the point cloud.
5. In the map-frame, and condition is checked whether the robot has reached y=6 and atleast we have 20 samples to fit the line.
6. A counter is initialised which upon incrementing and fulfilling the condition publishes the predicted intercepts in utm frame.

### SAM follow waypoint

Go to package `sam_action_servers`

In the `smarc_bt.py` file, three topics are read in the "const_data_ingestion_tree" as read_marker1, read_marker3 anbd read_intercepts. In the "const_execute_mission_tree" a sample_action "A_FollowWaypoint" is called, which performs a custom action.

In the `bt_actions.py` file, a separate action client is created called as "A_FollowWaypoint".
1. The initial goal point is set to marker1.
2. In the "update" funtion, if there is no detected line point(intercept) it continues to go the subscribed marker1 goal.
3. If "predicted intercept is not None, then the goal changes to predicted intercept coordinates, else.
4. If intercept is not None and is not equal to marker1, the goal changes to the intercept. As the robot moves forward, it keeps on detecing the intercepts and the goal changes simultaneously.

The goal is further sent to the action server `wp_depth_action_planner.py`, where the control action is performed. As a practice(rough check), the a static goal point was set in the "execute_cb" function to see if SAM is going to the respective wp.

### How to run

1. catkin_ws/$ catkin build sam_action_servers

2. (terminal 1)  catkin_ws/$ rosrun sam_stonefish_sim bringup.sh 
(start all the nodes, try to pull the robot back manually a bit otherwise it hits the buoy/rope with time and SAM goes to error state in neptus)

3. (terminal 2)  catkin_ws/src/neptus$ ./neptus 
(choose sample goto waypoint)

4. (terminal 3) catkin_ws/$ roslaunch sss_object_detection sim_lines.launch
(this will subscribe to the published markers in map frame and publish them in utm. Also this will publish the intercepts in utm frame.)

5. (terminal 4) catkin_ws/$ roslaunch sss_object_detection sim_lines_wf.launch
(this will fit a line on the point cloud and calculate a slope and intercept. After for a future x-unit it will calculate the corresponding y-unit and publish the predicted intercepts in utm frame.)

6. ( terminal 5) catkin_ws/$ rviz
(to vizualize, choose marker.rviz)




