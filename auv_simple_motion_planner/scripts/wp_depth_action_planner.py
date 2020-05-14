#!/usr/bin/python

# Copyright 2018 Nils Bore, Sriharsha Bhat (nbore@kth.se, svbhat@kth.se)
#
# Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the documentation and/or other materials provided with the distribution.
#
# 3. Neither the name of the copyright holder nor the names of its contributors may be used to endorse or promote products derived from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

from __future__ import division, print_function

import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
from nav_msgs.msg import Path
from geometry_msgs.msg import PoseStamped, PointStamped
from move_base_msgs.msg import MoveBaseFeedback, MoveBaseResult, MoveBaseAction
import actionlib
import rospy
import tf
from sam_msgs.msg import ThrusterRPMs, ThrusterAngles
from std_msgs.msg import Float64, Header, Bool
import math

class WPDepthPlanner(object):

    # create messages that are used to publish feedback/result
    _feedback = MoveBaseFeedback()
    _result = MoveBaseResult()


    def yaw_feedback_cb(self,yaw_feedback):
        self.yaw_feedback= yaw_feedback.data

    def turbo_turn(self,angle):
        rpm = self.turbo_turn_rpm
        rudder_angle = self.rudder_angle
        flip_rate = self.flip_rate

        left_turn = True
        if angle < 0:
            left_turn = False

        rospy.loginfo('Turbo Turning!')
        if left_turn:
            rudder_angle = -rudder_angle

        thrust_rate = 11.
        rate = rospy.Rate(thrust_rate)

        self.vec_pub.publish(0., rudder_angle, Header())
        loop_time = 0.

        while not rospy.is_shutdown() and loop_time < .5/flip_rate:
            self.rpm_pub.publish(rpm, rpm, Header())
            loop_time += 1./thrust_rate
            rate.sleep()

        self.vec_pub.publish(0., -rudder_angle, Header())

        loop_time = 0.
        while not rospy.is_shutdown() and loop_time < .5/flip_rate:
            self.rpm_pub.publish(-rpm, -rpm, Header())
            loop_time += 1./thrust_rate
            rate.sleep()

    def execute_cb(self, goal):

        rospy.loginfo("Goal received")

        success = True
        self.nav_goal = goal.target_pose.pose
        self.nav_goal_frame = goal.target_pose.header.frame_id
        if self.nav_goal_frame is None or self.nav_goal_frame == '':
            rospy.logwarn("Goal has no frame id! Using /world_utm by default")
            self.nav_goal_frame = '/world_utm'

        goal_point = PointStamped()
        goal_point.header.frame_id = self.nav_goal_frame
        goal_point.header.stamp = rospy.Time(0)
        goal_point.point.x = self.nav_goal.position.x
        goal_point.point.y = self.nav_goal.position.y
        goal_point.point.z = self.nav_goal.position.z
        try:
            goal_point_local = self.listener.transformPoint(self.nav_goal_frame, goal_point)
            self.nav_goal.position.x = goal_point_local.point.x
            self.nav_goal.position.y = goal_point_local.point.y
            self.nav_goal.position.z = goal_point_local.point.z
        except (tf.LookupException, tf.ConnectivityException, tf.ExtrapolationException):
            print ("Not transforming point to world local")
            pass

        rospy.loginfo('Nav goal in local %s ' % self.nav_goal.position.x)

        r = rospy.Rate(11.) # 10hz
        counter = 0
        while not rospy.is_shutdown() and self.nav_goal is not None:

            self.yaw_pid_enable.publish(True)
            self.depth_pid_enable.publish(True)
            # Preempted
            if self._as.is_preempt_requested():
                rospy.loginfo('%s: Preempted' % self._action_name)
                success = False
                self.nav_goal = None

                # Stop thrusters
                rpm = ThrusterRPMs()
                rpm.thruster_1_rpm = 0.
                rpm.thruster_2_rpm = 0.
                self.rpm_pub.publish(rpm)
                self.yaw_pid_enable.publish(False)
                self.depth_pid_enable.publish(False)
		self.vel_pid_enable.publish(False)

                print('wp depth action planner: stopped thrusters')
                self._as.set_preempted(self._result, "Preempted WP action")
                return

            # Publish feedback
            if counter % 10 == 0:
                try:
                    (trans, rot) = self.listener.lookupTransform(self.nav_goal_frame, self.base_frame, rospy.Time(0))
                except (tf.LookupException, tf.ConnectivityException, tf.ExtrapolationException):
                    rospy.loginfo("Error with tf:"+str(self.nav_goal_frame) + " to "+str(self.base_frame))
                    continue

                pose_fb = PoseStamped()
                pose_fb.header.frame_id = self.nav_goal_frame
                pose_fb.pose.position.x = trans[0]
                pose_fb.pose.position.y = trans[1]
                pose_fb.pose.position.z = trans[2]
                self._feedback.base_position = pose_fb
                self._feedback.base_position.header.stamp = rospy.get_rostime()
                self._as.publish_feedback(self._feedback)
                #rospy.loginfo("Sending feedback")

                #Compute yaw setpoint.
                xdiff = self.nav_goal.position.x - pose_fb.pose.position.x
                ydiff = self.nav_goal.position.y - pose_fb.pose.position.y
                yaw_setpoint = math.atan2(ydiff,xdiff)

		#compute yaw_error (e.g. for turbo_turn)
                yaw_error= (self.yaw_feedback - yaw_setpoint)
                if(yaw_error>3.141516):
                    yaw_error= -(2*3.141516 - abs(yaw_error))

                depth_setpoint = self.nav_goal.position.z

            self.depth_pub.publish(depth_setpoint)
            #  self.vbs_pub.publish(depth_setpoint)

            if self.vel_ctrl_flag:
		rospy.loginfo_throttle_identical(5, "vel ctrl, no turbo turn")
                #with Velocity control
                self.yaw_pid_enable.publish(True)
                self.yaw_pub.publish(yaw_setpoint)

                # Publish to velocity controller
                self.vel_pid_enable.publish(True)
                self.vel_pub.publish(self.vel_setpoint)
		self.roll_pub.publish(self.roll_setpoint)
                #rospy.loginfo("Velocity published")

            else:
		if self.turbo_turn_flag:
                    #if turbo turn is included
                    rospy.loginfo("Yaw error: %f", yaw_error)
                    if abs(yaw_error) > self.turbo_angle_min:
                        #turbo turn with large deviations
                        self.yaw_pid_enable.publish(False)
                        self.turbo_turn(yaw_error)
                    else:
                        rospy.loginfo_throttle_identical(5,"Normal WP following")
                        #normal turning if the deviation is small
                        self.yaw_pid_enable.publish(True)
                        self.yaw_pub.publish(yaw_setpoint)

                        # Thruster forward
                        rpm = ThrusterRPMs()
                        rpm.thruster_1_rpm = self.forward_rpm
                        rpm.thruster_2_rpm = self.forward_rpm
                        self.rpm_pub.publish(rpm)
                        #rospy.loginfo("Thrusters forward")

                else:
                    #turbo turn not included, no velocity control
                    rospy.loginfo_throttle_identical(5, "Normal WP following, no turbo turn")
                    self.yaw_pid_enable.publish(True)
                    self.yaw_pub.publish(yaw_setpoint)

                    # Thruster forward
                    rpm = ThrusterRPMs()
                    rpm.thruster_1_rpm = self.forward_rpm
                    rpm.thruster_2_rpm = self.forward_rpm
                    self.rpm_pub.publish(rpm)
                    #rospy.loginfo("Thrusters forward")

            counter += 1
            r.sleep()

        # Stop thruster
	self.vel_pid_enable.publish(False)
	rpm = ThrusterRPMs()
        rpm.thruster_1_rpm = 0.0
        rpm.thruster_2_rpm = 0.0
        self.rpm_pub.publish(rpm)

        #Stop controllers
        self.yaw_pid_enable.publish(False)
        self.depth_pid_enable.publish(False)
        self.vel_pid_enable.publish(False)
        rospy.loginfo('%s: Succeeded' % self._action_name)
        self._as.set_succeeded(self._result)


    def timer_callback(self, event):
        if self.nav_goal is None:
            #rospy.loginfo_throttle(30, "Nav goal is None!")
            return

        try:
            (trans, rot) = self.listener.lookupTransform(self.nav_goal_frame, self.base_frame, rospy.Time(0))
        except (tf.LookupException, tf.ConnectivityException, tf.ExtrapolationException):
            return

        # TODO: we could use this code for the other check also
        goal_point = PointStamped()
        goal_point.header.frame_id = self.nav_goal_frame
        goal_point.header.stamp = rospy.Time(0)
        goal_point.point.x = self.nav_goal.position.x
        goal_point.point.y = self.nav_goal.position.y
        goal_point.point.z = self.nav_goal.position.z

        #print("Checking if nav goal is reached!")

        start_pos = np.array(trans)
        end_pos = np.array([self.nav_goal.position.x, self.nav_goal.position.y, self.nav_goal.position.z])

        # We check for success out of the main control loop in case the main control loop is
        # running at 300Hz or sth. like that. We dont need to check succes that frequently.
        xydiff = start_pos[:2] - end_pos[:2]
        zdiff = np.abs(np.abs(start_pos[2]) - np.abs(end_pos[2]))
        xydiff_norm = np.linalg.norm(xydiff)
        rospy.logdebug("diff xy:"+ str(xydiff_norm)+' z:' + str(zdiff))
        if xydiff_norm < self.wp_tolerance and zdiff < self.depth_tolerance:
            rospy.loginfo("Reached goal!")
            self.nav_goal = None

    def __init__(self, name):

        """Publish yaw and depth setpoints based on waypoints"""
        self._action_name = name

        #self.heading_offset = rospy.get_param('~heading_offsets', 5.)
        self.wp_tolerance = rospy.get_param('~wp_tolerance', 5.)
        self.depth_tolerance = rospy.get_param('~depth_tolerance', 0.5)

        self.base_frame = rospy.get_param('~base_frame', "sam/base_link")

        rpm_cmd_topic = rospy.get_param('~rpm_cmd_topic', '/sam/core/rpm_cmd')
        heading_setpoint_topic = rospy.get_param('~heading_setpoint_topic', '/sam/ctrl/dynamic_heading/setpoint')
        yaw_pid_enable_topic = rospy.get_param('~yaw_pid_enable_topic', '/sam/ctrl/dynamic_heading/pid_enable')
        depth_setpoint_topic = rospy.get_param('~depth_setpoint_topic', '/sam/ctrl/dynamic_depth/setpoint')
        depth_pid_enable_topic = rospy.get_param('~depth_pid_enable_topic', '/sam/ctrl/dynamic_depth/pid_enable')

        self.forward_rpm = int(rospy.get_param('~forward_rpm', 1000))


        #related to turbo turn
	self.turbo_turn_flag = rospy.get_param('~turbo_turn_flag', True)
	thrust_vector_cmd_topic = rospy.get_param('~thrust_vector_cmd_topic', '/sam/core/thrust_vector_cmd')
	yaw_feedback_topic = rospy.get_param('~yaw_feedback_topic', '/sam/ctrl/yaw_feedback')
        self.turbo_angle_min_deg = rospy.get_param('~turbo_angle_min', 90)
        self.turbo_angle_min= np.radians(self.turbo_angle_min_deg)
        self.flip_rate = rospy.get_param('~flip_rate', 0.5)
        self.rudder_angle = rospy.get_param('~rudder_angle', 0.08)
        self.turbo_turn_rpm = rospy.get_param('~turbo_turn_rpm', 1000)


	#related to velocity regulation instead of rpm
	self.vel_ctrl_flag = rospy.get_param('~vel_ctrl_flag', False)
	self.vel_setpoint = rospy.get_param('~vel_setpoint', 2) #velocity setpoint in m/s
	self.roll_setpoint = rospy.get_param('~roll_setpoint', 0)
	vel_setpoint_topic = rospy.get_param('~vel_setpoint_topic', '/sam/ctrl/dynamic_velocity/u_setpoint')
	roll_setpoint_topic = rospy.get_param('~roll_setpoint_topic', '/sam/ctrl/dynamic_velocity/roll_setpoint')
	vel_pid_enable_topic = rospy.get_param('~vel_pid_enable_topic', '/sam/ctrl/dynamic_velocity/pid_enable')

        self.nav_goal = None

        self.listener = tf.TransformListener()
        rospy.Timer(rospy.Duration(0.5), self.timer_callback)

	self.yaw_feedback=0
	rospy.Subscriber('/sam1/ctrl/yaw_feedback',Float64, self.yaw_feedback_cb)

        self.rpm_pub = rospy.Publisher(rpm_cmd_topic, ThrusterRPMs, queue_size=10)
        self.yaw_pub = rospy.Publisher(heading_setpoint_topic, Float64, queue_size=10)
        self.depth_pub = rospy.Publisher(depth_setpoint_topic, Float64, queue_size=10)
        self.vel_pub = rospy.Publisher(vel_setpoint_topic, Float64, queue_size=10)
        self.roll_pub = rospy.Publisher(roll_setpoint_topic, Float64, queue_size=10)

        #TODO make proper if it works.
        #  self.vbs_pub = rospy.Publisher('/sam/ctrl/vbs/setpoint', Float64, queue_size=10)
        self.yaw_pid_enable = rospy.Publisher(yaw_pid_enable_topic, Bool, queue_size=10)
        self.depth_pid_enable = rospy.Publisher(depth_pid_enable_topic, Bool, queue_size=10)
	self.vel_pid_enable = rospy.Publisher(vel_pid_enable_topic, Bool, queue_size=10)
        self.vec_pub = rospy.Publisher(thrust_vector_cmd_topic, ThrusterAngles, queue_size=10)

        self._as = actionlib.SimpleActionServer(self._action_name, MoveBaseAction, execute_cb=self.execute_cb, auto_start = False)
        self._as.start()
        rospy.loginfo("Announced action server with name: %s", self._action_name)

        rospy.spin()

if __name__ == '__main__':

    rospy.init_node('wp_depth_action_planner')
    planner = WPDepthPlanner(rospy.get_name())