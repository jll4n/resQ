# !/usr/bin/env python3
from pyniryo import *
import time
from db import executer_tache, log_mouvement

ip_robot = "169.254.200.200"
robot = NiryoRobot(ip_robot)
robot.calibrate_auto()
workspace_name = "Workspace python"
robot.update_tool()
conveyor_id = robot.set_conveyor()

base_pose = JointsPosition(0.19, -0.012, 0.281, -1.491, 1.384, -2.77)
carre_pose = JointsPosition(0.157, 0.19, 0.113, 2.941, 0.957, -3.122)
lowbase_pose = JointsPosition(0.244, 0.005, 0.131, -2.61, 1.451, -2.893)
rond_pose = JointsPosition(0.138, -0.184, 0.135, -1.901, 1.083, 2.961)
eject_pose = JointsPosition(0.296, 0.004, 0.114, -2.7, 1.456, 3.111)
baseeject_pose = JointsPosition(0.19, -0.002, 0.115, -2.72, 1.3011, -3.094)

count_dict = {
    ObjectColor.BLUE: 0,
    ObjectColor.RED: 0,
    ObjectColor.GREEN: 0,
}


def pickcarre():
    robot.move_pose(carre_pose)
    robot.pull_air_vacuum_pump()
    robot.move_pose(base_pose)
    robot.move_pose(lowbase_pose)
    robot.push_air_vacuum_pump()
    executer_tache("Pick carre")


def pickrond():
    robot.move_pose(rond_pose)
    robot.pull_air_vacuum_pump()
    robot.move_pose(base_pose)
    robot.move_pose(lowbase_pose)
    robot.push_air_vacuum_pump()
    robot.move_pose(base_pose)
    executer_tache("Pick rond")


def checkcolor():
    robot.move_pose(base_pose)
    obj_found, shape_ret, color_ret = robot.vision_pick(workspace_name)
    if color_ret == ObjectColor.RED and shape_ret == ObjectShape.CIRCLE:
        robot.run_conveyor(conveyor_id)
        time.sleep(2)
        robot.stop_conveyor(conveyor_id)
    elif color_ret == ObjectColor.BLUE:
        robot.move_pose(baseeject_pose)
        robot.move_pose(eject_pose)
    executer_tache("Check color")


robot.move_pose(base_pose)
time.sleep(1)
pickcarre()
time.sleep(1)
robot.move_pose(base_pose)
pickrond()
checkcolor()

robot.close_connection()