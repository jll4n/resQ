from main import ip_robot
import mysql.connector
from pyniryo import NiryoRobot
import datetime

DB_CONFIG = {
    "host":     "127.0.0.1",
    "user":     "root",
    "password": "root123",
    "database": "niryo_data"
}

db     = mysql.connector.connect(**DB_CONFIG)
cursor = db.cursor()

robot = NiryoRobot(ip_robot)

def log_mouvement(label, statut="ok", erreur=None):
    joints = robot.get_joints()
    pose   = robot.get_pose()
    cursor.execute("""
        INSERT INTO robot_logs
            (timestamp, label, statut, j1, j2, j3, j4, j5, j6, x, y, z, erreur)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (
        datetime.datetime.now(), label, statut,
        *joints,
        pose.x, pose.y, pose.z,
        erreur
    ))
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

