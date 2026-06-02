# !/usr/bin/env python3
import os
if os.environ.get("USE_MOCK"):
    from mock_niryo import *
else:
    from pyniryo import *
import time
import argparse
import mysql.connector
import datetime
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "host":     os.getenv("DB_HOST",     "127.0.0.1"),
    "user":     os.getenv("DB_USER",     "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME",     "niryo_data"),
}

# ── Poses ─────────────────────────────────────────────────────────────────────
base_pose       = JointsPosition( 0.19,  -0.012,  0.281, -1.491,  1.384, -2.77)
carre_pose      = JointsPosition( 0.157,  0.19,   0.113,  2.941,  0.957, -3.122)
lowbase_pose    = JointsPosition( 0.244,  0.005,  0.131, -2.61,   1.451, -2.893)
rond_pose       = JointsPosition( 0.138, -0.184,  0.135, -1.901,  1.083,  2.961)
eject_pose      = JointsPosition( 0.296,  0.004,  0.114, -2.7,    1.456,  3.111)
baseeject_pose  = JointsPosition( 0.19,  -0.002,  0.115, -2.72,   1.3011,-3.094)
base_pose_carre = JointsPosition( 0,      0,       0,     0,       0,     0)  # a ajouter

count_dict = {ObjectColor.BLUE: 0, ObjectColor.RED: 0, ObjectColor.GREEN: 0}


# ── Logging BDD ───────────────────────────────────────────────────────────────
def log_mouvement(label, statut="ok", erreur=None):
    joints = robot.get_joints()
    pose   = robot.get_pose()
    cursor.execute("""
        INSERT INTO robot_logs
            (timestamp, label, statut, j1, j2, j3, j4, j5, j6, x, y, z, erreur)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (datetime.datetime.now(), label, statut,
          *joints, pose.x, pose.y, pose.z, erreur))
    db.commit()


def executer_tache(nom_tache):
    cursor.execute("""
        SELECT j1,j2,j3,j4,j5,j6 FROM tasks
        WHERE name=%s ORDER BY step_order
    """, (nom_tache,))
    steps = cursor.fetchall()
    for i, joints in enumerate(steps):
        try:
            robot.move_joints(*joints)
            log_mouvement(label=f"{nom_tache}_step{i}", statut="ok")
        except Exception as e:
            log_mouvement(label=f"{nom_tache}_step{i}", statut="erreur", erreur=str(e))
            raise


# ── Séquences robot ───────────────────────────────────────────────────────────
def pickcarre():
    robot.move_pose(carre_pose)
    robot.pull_air_vacuum_pump()
    robot.move_pose(base_pose)
    robot.move_pose(lowbase_pose)  # a ajouter
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
        pickcarre()
        robot.run_conveyor(conveyor_id)
        time.sleep(2)
        robot.stop_conveyor(conveyor_id)
    elif color_ret == ObjectColor.BLUE:
        robot.move_pose(baseeject_pose)
        robot.move_pose(eject_pose)
    executer_tache("Check color")
    if color_ret:
        count_dict[color_ret] += 1


# ── Point d'entrée ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Niryo Ned 2 — cycle de tri")
    parser.add_argument(
        "--cycles", type=int, default=1,
        metavar="N",
        help="Nombre de cycles (0 = infini, défaut : 1)"
    )
    parser.add_argument(
        "--mode", choices=["wifi", "ethernet"], default="wifi",
        help="Mode réseau (défaut : wifi)"
    )
    args = parser.parse_args()

    # Connexion BDD
    db     = mysql.connector.connect(**DB_CONFIG)
    cursor = db.cursor()

    # Connexion robot
    ip_robot = "169.254.200.200" if args.mode == "ethernet" else "10.10.10.10"
    robot          = NiryoRobot(ip_robot)
    robot.calibrate_auto()
    workspace_name = "Workspace python"
    robot.update_tool()
    conveyor_id    = robot.set_conveyor()

    target = args.cycles
    cycle  = 0

    try:
        robot.move_pose(base_pose)
        time.sleep(1)

        while True:
            if target > 0 and cycle >= target:
                break

            label = f"{cycle + 1}/{target}" if target > 0 else f"{cycle + 1} (∞)"
            print(f"\n{'─'*40}\nCycle {label}\n{'─'*40}")

            pickrond()
            checkcolor()
            cycle += 1

            b = count_dict[ObjectColor.BLUE]
            r = count_dict[ObjectColor.RED]
            g = count_dict[ObjectColor.GREEN]
            print(f"→ Terminé | BLEU:{b}  ROUGE:{r}  VERT:{g}")

            if target > 0 and cycle >= target:
                break

            robot.move_pose(base_pose)
            time.sleep(1)

    except KeyboardInterrupt:
        print("\nArrêt demandé (Ctrl+C)")
    except Exception as e:
        print(f"\nErreur : {e}")
        log_mouvement("ERREUR CRITIQUE", statut="erreur", erreur=str(e))
    finally:
        print(f"\nFin — {cycle} cycle(s) effectué(s)")
        try:
            robot.move_pose(base_pose)
        except Exception:
            pass
        robot.close_connection()
        cursor.close()
        db.close()
