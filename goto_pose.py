#!/usr/bin/env python3
"""
Utilitaire — déplace le robot vers une position cartésienne donnée.
Usage : python goto_pose.py x y z roll pitch yaw [--mode ethernet]

Exemple :
    python goto_pose.py 0.2341 -0.0123 0.3012 0.012 1.384 -2.77
"""
import os, argparse
if os.environ.get("USE_MOCK"):
    from mock_niryo import *
else:
    from pyniryo import *

parser = argparse.ArgumentParser(description="Déplacer le robot vers une pose cartésienne")
parser.add_argument("x",     type=float, help="Position X en mètres")
parser.add_argument("y",     type=float, help="Position Y en mètres")
parser.add_argument("z",     type=float, help="Position Z en mètres")
parser.add_argument("roll",  type=float, help="Roll en radians")
parser.add_argument("pitch", type=float, help="Pitch en radians")
parser.add_argument("yaw",   type=float, help="Yaw en radians")
parser.add_argument("--mode", choices=["wifi", "ethernet"], default="wifi")
args = parser.parse_args()

ip = "169.254.200.200" if args.mode == "ethernet" else "10.10.10.10"

print(f"Connexion à {ip}...")
robot = NiryoRobot(ip)
robot.calibrate_auto()
robot.set_learning_mode(False)

target = PoseObject(args.x, args.y, args.z, args.roll, args.pitch, args.yaw)

print(f"\nDéplacement vers :")
print(f"  x={args.x}  y={args.y}  z={args.z}")
print(f"  roll={args.roll}  pitch={args.pitch}  yaw={args.yaw}")

robot.move_pose(target)
print("✓ Position atteinte")

joints = robot.get_joints()
j = [round(v, 4) for v in joints]
print(f"\nJointsPosition résultante :")
print(f"JointsPosition({j[0]}, {j[1]}, {j[2]}, {j[3]}, {j[4]}, {j[5]})")

robot.set_learning_mode(True)
robot.close_connection()
