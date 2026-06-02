#!/usr/bin/env python3
from flask import Flask, render_template, jsonify, request, Response
import mysql.connector
import datetime
import threading
import time
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

DB_CONFIG = {
    "host":     os.getenv("DB_HOST",     "127.0.0.1"),
    "user":     os.getenv("DB_USER",     "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME",     "niryo_data"),
}

robot_state = {
    "connected":       False,
    "running":         False,
    "stop_requested":  False,
    "conveyor_active": False,
    "last_action":     "—",
    "mode":            "wifi",   # "wifi" ou "ethernet"
    "joints": {"j1": 0, "j2": 0, "j3": 0, "j4": 0, "j5": 0, "j6": 0},
    "count": {"BLUE": 0, "RED": 0, "GREEN": 0},
    "cycle_target":    1,
    "cycles_done":     0,
}

robot_lock = threading.Lock()
robot_obj  = None   # instance NiryoRobot active


def get_db():
    return mysql.connector.connect(**DB_CONFIG)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/state")
def api_state():
    return jsonify(robot_state)

@app.route("/api/logs")
def api_logs():
    statut = request.args.get("statut", None)
    try:
        db     = get_db()
        cursor = db.cursor(dictionary=True)
        if statut:
            cursor.execute(
                "SELECT * FROM robot_logs WHERE statut=%s ORDER BY timestamp DESC LIMIT 100",
                (statut,)
            )
        else:
            cursor.execute(
                "SELECT * FROM robot_logs ORDER BY timestamp DESC LIMIT 100"
            )
        logs = cursor.fetchall()
        for row in logs:
            if isinstance(row.get("timestamp"), datetime.datetime):
                row["timestamp"] = row["timestamp"].strftime("%Y-%m-%d %H:%M:%S")
        cursor.close()
        db.close()
        return jsonify(logs)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/count")
def api_count():
    try:
        db     = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute("""
            SELECT color, COUNT(*) AS total
            FROM robot_logs
            WHERE color IS NOT NULL
            GROUP BY color
        """)
        rows   = cursor.fetchall()
        counts = {"BLUE": 0, "RED": 0, "GREEN": 0}
        for r in rows:
            c = (r["color"] or "").upper()
            if c in counts:
                counts[c] = r["total"]
        cursor.close()
        db.close()
        return jsonify(counts)
    except Exception as e:
        return jsonify(robot_state["count"])


@app.route("/api/mode", methods=["POST"])
def api_mode():
    data = request.get_json(silent=True) or {}
    mode = data.get("mode", "wifi")
    if mode not in ("wifi", "ethernet"):
        return jsonify({"error": "mode invalide"}), 400
    robot_state["mode"] = mode
    return jsonify({"mode": mode})


@app.route("/api/lancer", methods=["POST"])
def api_lancer():
    data = request.get_json(silent=True) or {}
    cycles = int(data.get("cycles", 1))

    with robot_lock:
        if robot_state["running"]:
            return jsonify({"error": "Cycle déjà en cours"}), 409
        robot_state["running"]        = True
        robot_state["stop_requested"] = False
        robot_state["cycles_done"]    = 0
        robot_state["cycle_target"]   = max(0, cycles)

    def run_cycle():
        global robot_obj
        import os
        if os.environ.get("USE_MOCK"):
            from mock_niryo import NiryoRobot, ObjectColor, ObjectShape, PoseObject
        else:
            from pyniryo import NiryoRobot, ObjectColor, ObjectShape, PoseObject

        ip = "169.254.200.200" if robot_state["mode"] == "ethernet" else "10.10.10.10"

        target = robot_state["cycle_target"]  # 0 = infini

        try:
            robot_obj = NiryoRobot(ip)
            # pyniryo n'expose pas d'API publique pour le timeout d'opération ;
            # accès à l'attribut privé pour éviter un timeout pendant calibrate_auto() (60 s+)
            try:
                robot_obj._TcpClient__client_socket.settimeout(120)
            except Exception:
                pass  # si l'attribut change dans une future version, on continue avec le timeout par défaut
            robot_obj.calibrate_auto()
            robot_obj.set_learning_mode(False)
            robot_state["connected"] = True

            workspace_name = "Workspace python"

            try:
                robot_obj.update_tool()
                print("[ROBOT] update_tool OK")
            except Exception as e:
                print(f"[ROBOT] update_tool ignoré : {e}")

            conveyor_id = None
            try:
                conveyor_id = robot_obj.set_conveyor()
                print(f"[ROBOT] set_conveyor OK → {conveyor_id}")
            except Exception as e:
                print(f"[ROBOT] set_conveyor ignoré : {e}")

            # Poses
            base_pose     = [ 0.19,  -0.012,  0.281, -1.491,  1.384, -2.77]
            carre_pose    = [ 0.157,  0.19,   0.113,  2.941,  0.957, -3.122]
            lowbase_pose  = [ 0.244,  0.005,  0.131, -2.61,   1.451, -2.893]
            rond_pose     = [ 0.138, -0.184,  0.135, -1.901,  1.083,  2.961]
            eject_pose    = [ 0.296,  0.004,  0.114, -2.7,    1.456,  3.111]
            baseeject_pose= [ 0.19,  -0.002,  0.115, -2.72,   1.3011,-3.094]

            def update_joints():
                j = robot_obj.get_joints()
                robot_state["joints"] = {
                    "j1": round(j[0], 3), "j2": round(j[1], 3),
                    "j3": round(j[2], 3), "j4": round(j[3], 3),
                    "j5": round(j[4], 3), "j6": round(j[5], 3),
                }

            def log_bdd(label, statut="ok", erreur=None, color=None):
                try:
                    db     = get_db()
                    cur    = db.cursor()
                    joints = robot_obj.get_joints()
                    pose   = robot_obj.get_pose()
                    cur.execute("""
                        INSERT INTO robot_logs
                            (timestamp, label, statut, j1, j2, j3, j4, j5, j6, x, y, z, erreur, color)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """, (datetime.datetime.now(), label, statut,
                          *joints, pose.x, pose.y, pose.z, erreur, color))
                    db.commit()
                    cur.close()
                    db.close()
                except Exception:
                    pass

            while not robot_state["stop_requested"]:
                if target > 0 and robot_state["cycles_done"] >= target:
                    break

                robot_state["last_action"] = "Mouvement base"
                print(f"[ROBOT] move base_pose {base_pose}")
                robot_obj.move(PoseObject(*base_pose))
                print("[ROBOT] move base_pose OK")
                update_joints()
                time.sleep(1)

                if robot_state["stop_requested"]: break

                robot_state["last_action"] = "Pick rond"
                robot_obj.move(PoseObject(*rond_pose))
                robot_obj.pull_air_vacuum_pump()
                robot_obj.move(PoseObject(*base_pose))
                robot_obj.move(PoseObject(*lowbase_pose))
                robot_obj.push_air_vacuum_pump()
                robot_obj.move(PoseObject(*base_pose))
                update_joints()
                log_bdd("Pick rond")

                if robot_state["stop_requested"]: break

                robot_state["last_action"] = "Détection couleur"
                robot_obj.move(PoseObject(*base_pose))
                try:
                    obj_found, shape_ret, color_ret = robot_obj.vision_pick(workspace_name)
                except UnicodeDecodeError:
                    raise RuntimeError(
                        "vision_pick : erreur de décodage — mismatch pyniryo/firmware. "
                        "Vérifie la version NiryOS sur http://10.10.10.10 et adapte pyniryo."
                    )

                if not obj_found:
                    robot_state["last_action"] = "Aucun objet détecté"
                elif color_ret == ObjectColor.RED and shape_ret == ObjectShape.CIRCLE:
                    robot_state["last_action"] = "Pick carré + Convoyeur — cercle rouge"
                    robot_obj.move(PoseObject(*carre_pose))
                    robot_obj.pull_air_vacuum_pump()
                    robot_obj.move(PoseObject(*base_pose))
                    robot_obj.move(PoseObject(*lowbase_pose))
                    robot_obj.push_air_vacuum_pump()
                    log_bdd("Pick carre")
                    if conveyor_id:
                        robot_state["conveyor_active"] = True
                        robot_obj.run_conveyor(conveyor_id)
                        time.sleep(2)
                        robot_obj.stop_conveyor(conveyor_id)
                        robot_state["conveyor_active"] = False
                    robot_state["count"]["RED"] += 1
                elif color_ret == ObjectColor.BLUE:
                    robot_state["last_action"] = "Éjection — objet bleu"
                    robot_obj.move(PoseObject(*baseeject_pose))
                    robot_obj.move(PoseObject(*eject_pose))
                    robot_obj.push_air_vacuum_pump()
                    robot_state["count"]["BLUE"] += 1
                elif color_ret == ObjectColor.GREEN:
                    robot_state["last_action"] = "Objet vert détecté"
                    robot_obj.push_air_vacuum_pump()
                    robot_state["count"]["GREEN"] += 1

                update_joints()
                color_str = color_ret.name if obj_found and color_ret else None
                log_bdd("Check color", color=color_str)

                robot_state["cycles_done"] += 1
                suffix = f"{robot_state['cycles_done']}/{target}" if target > 0 else str(robot_state["cycles_done"])
                robot_state["last_action"] = f"Cycle {suffix} terminé ✓"

            if not robot_state["stop_requested"]:
                robot_state["last_action"] = f"Terminé — {robot_state['cycles_done']} cycle(s)"

        except Exception as e:
            robot_state["last_action"] = f"Erreur : {e}"
        finally:
            if robot_obj:
                try:
                    robot_obj.close_connection()
                except Exception:
                    pass
            robot_state["running"]   = False
            robot_state["connected"] = False

    threading.Thread(target=run_cycle, daemon=True).start()
    return jsonify({"statut": "cycle lancé"})

@app.route("/api/camera")
def api_camera():
    # Caméra désactivée temporairement
    return Response(status=204)


@app.route("/api/stop", methods=["POST"])
def api_stop():
    with robot_lock:
        robot_state["stop_requested"] = True
        robot_state["last_action"]    = "⛔ Stop d'urgence"
        obj = robot_obj
    if obj:
        try:
            obj.stop_move()
        except Exception:
            pass
    return jsonify({"statut": "stop envoyé"})


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)