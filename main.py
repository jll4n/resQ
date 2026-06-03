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
base_pose       = [ 0.1886, -0.007, 0.3259, 3.08, 1.2298, -3.0854]
carre_pose      = [ 0.1577, 0.1956, 0.1204, 2.6986, 1.1696, -2.7449]
lowbase_pose    = [ 0.2271, -0.0209, 0.1155, -3.0273, 1.5398, -2.9527]
rond_pose       = [ 0.129, -0.1637, 0.1258, -2.7663, 1.1528, -3.0698]
eject_pose      = [ 0.2966, -0.0268, 0.112, -1.6157, 1.533, -1.4918]
baseeject_pose  = [ 0.1667, -0.014, 0.1024, -3.0793, 1.4499, -2.8848]
base_pose_carre = [ 0,      0,       0,     0,       0,     0]  # a ajouter

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
            robot.move_pose(JointsPosition(*joints))
            log_mouvement(label=f"{nom_tache}_step{i}", statut="ok")
        except Exception as e:
            log_mouvement(label=f"{nom_tache}_step{i}", statut="erreur", erreur=str(e))
            raise


# ── Séquences robot ───────────────────────────────────────────────────────────
def pickcarre():
    robot.move_pose(JointsPosition(*carre_pose))
    robot.pull_air_vacuum_pump()
    robot.move_pose(JointsPosition(*base_pose))
    robot.push_air_vacuum_pump()
    executer_tache("Pick carre")


def pickrond():
    robot.move_pose(JointsPosition(*rond_pose))
    robot.pull_air_vacuum_pump()
    robot.move_pose(JointsPosition(*base_pose))
    robot.move_pose(JointsPosition(*lowbase_pose))
    robot.push_air_vacuum_pump()
    robot.move_pose(JointsPosition(*base_pose))
    executer_tache("Pick rond")


def checkcolor():
    robot.move_pose(JointsPosition(*base_pose))
    _, shape_ret, color_ret = robot.vision_pick(workspace_name)
    print(f"[ROBOT] vision_pick → shape={shape_ret} color={color_ret}")
    if color_ret == ObjectColor.RED:
        # Rouge → convoyeur puis relâche
        if conveyor_id:
            robot.run_conveyor(conveyor_id)
            time.sleep(2)
            robot.stop_conveyor(conveyor_id)
        robot.push_air_vacuum_pump()
    elif color_ret == ObjectColor.BLUE:
        # Bleu → éjection puis relâche
        robot.move_pose(JointsPosition(*baseeject_pose))
        robot.move_pose(JointsPosition(*eject_pose))
        robot.push_air_vacuum_pump()
    elif color_ret == ObjectColor.GREEN:
        # Vert → relâche en base
        robot.move_pose(JointsPosition(*base_pose))
        robot.push_air_vacuum_pump()
    else:
        # Couleur non reconnue — relâche en base
        print(f"[ROBOT] couleur non gérée : {color_ret}, relâche en base")
        robot.move_pose(JointsPosition(*base_pose))
        robot.push_air_vacuum_pump()
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
    robot = NiryoRobot(ip_robot)
    try:
        robot._TcpClient__client_socket.settimeout(120)
    except AttributeError:
        pass
    robot.calibrate_auto()
    robot.set_learning_mode(False)
    workspace_name = "OM"
    robot.update_tool()
    try:
        conveyor_id = robot.set_conveyor()
    except Exception as e:
        conveyor_id = None
        print(f"[ROBOT] set_conveyor ignoré : {e}")

    target = args.cycles
    cycle  = 0

    try:
        robot.move_pose(JointsPosition(*base_pose))
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

            robot.move_pose(JointsPosition(*base_pose))
            time.sleep(1)

    except KeyboardInterrupt:
        print("\nArrêt demandé (Ctrl+C)")
    except Exception as e:
        print(f"\nErreur : {e}")
        log_mouvement("ERREUR CRITIQUE", statut="erreur", erreur=str(e))
    finally:
        print(f"\nFin — {cycle} cycle(s) effectué(s)")
        try:
            robot.move_pose(JointsPosition(*base_pose))
        except Exception:
            pass
        robot.close_connection()
        cursor.close()
        db.close()
