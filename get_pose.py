#!/usr/bin/env python3
"""
Utilitaire — affiche la position articulaire et cartésienne actuelle du robot.
Usage : python get_pose.py [--mode ethernet]
"""
import os, argparse
if os.environ.get("USE_MOCK"):
    from mock_niryo import *
else:
    from pyniryo import *

parser = argparse.ArgumentParser(description="Lire la position du robot Niryo Ned 2")
parser.add_argument("--mode", choices=["wifi", "ethernet"], default="wifi")
args = parser.parse_args()

ip = "169.254.200.200" if args.mode == "ethernet" else "10.10.10.10"

print(f"Connexion à {ip}...")
robot = NiryoRobot(ip)
robot.calibrate_auto()

joints = robot.get_joints()
pose   = robot.get_pose()

j = [round(v, 4) for v in joints]

print("\n── JOINTS (radians) ────────────────────────────────")
print(f"  J1={j[0]}  J2={j[1]}  J3={j[2]}")
print(f"  J4={j[3]}  J5={j[4]}  J6={j[5]}")

print("\n── POSE CARTÉSIENNE ────────────────────────────────")
print(f"  x={round(pose.x,4)}  y={round(pose.y,4)}  z={round(pose.z,4)}")
print(f"  roll={round(pose.roll,4)}  pitch={round(pose.pitch,4)}  yaw={round(pose.yaw,4)}")

px = round(pose.x, 4)
py = round(pose.y, 4)
pz = round(pose.z, 4)
pr = round(pose.roll, 4)
pp = round(pose.pitch, 4)
pw = round(pose.yaw, 4)

print("\n── COPIER-COLLER prêt ──────────────────────────────")
print(f"JointsPosition({j[0]}, {j[1]}, {j[2]}, {j[3]}, {j[4]}, {j[5]})")
print(f"PoseObject({px}, {py}, {pz}, {pr}, {pp}, {pw})")

robot.close_connection()
