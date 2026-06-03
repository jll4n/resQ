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

robot_lock      = threading.Lock()
robot_obj       = None   # instance NiryoRobot active
camera_frame    = None   # dernier snapshot JPEG mis en cache
vision_history  = []     # dernières détections (max 20)


def get_db():
    return mysql.connector.connect(**DB_CONFIG)


def _snap_camera():
    """Prend un snapshot caméra et le met en cache (appelé entre les moves)."""
    global camera_frame
    if robot_obj is None or not robot_state["connected"]:
        return
    try:
        import cv2, numpy as np
        from pyniryo import uncompress_image
        compressed = robot_obj.get_img_compressed()
        img = uncompress_image(compressed)
        _, buf = cv2.imencode(".jpg", img)
        camera_frame = buf.tobytes()
    except Exception:
        pass


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


@app.route("/api/vision")
def api_vision():
    return jsonify(vision_history)


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
            from mock_niryo import NiryoRobot, ObjectColor, ObjectShape, JointsPosition
        else:
            from pyniryo import NiryoRobot, ObjectColor, ObjectShape, JointsPosition

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

            workspace_name = "OM"

            try:
                robot_obj.update_tool()
                print("[ROBOT] update_tool OK")
            except Exception as e:
                print(f"[ROBOT] update_tool ignoré : {e}")

            conveyor_id = None
            try:
                robot_obj._TcpClient__client_socket.settimeout(5)
                conveyor_id = robot_obj.set_conveyor()
                print(f"[ROBOT] set_conveyor OK → {conveyor_id}")
            except Exception as e:
                print(f"[ROBOT] set_conveyor ignoré : {e}")
            finally:
                try:
                    robot_obj._TcpClient__client_socket.settimeout(120)
                except Exception:
                    pass

            # Poses
            base_pose     = [ 0.1886, -0.007, 0.3259, 3.08, 1.2298, -3.0854]
            carre_pose    = [ 0.1577, 0.1956, 0.1204, 2.6986, 1.1696, -2.7449]
            lowbase_pose  = [ 0.2271, -0.0209, 0.1155, -3.0273, 1.5398, -2.9527]
            rond_pose     = [ 0.129, -0.1637, 0.1258, -2.7663, 1.1528, -3.0698]
            eject_pose    = [ 0.2966, -0.0268, 0.112, -1.6157, 1.533, -1.4918]
            baseeject_pose= [ 0.1667, -0.014, 0.1024, -3.0793, 1.4499, -2.8848]

            def update_joints():
                try:
                    j = robot_obj.get_joints()
                    robot_state["joints"] = {
                        "j1": round(j[0], 3), "j2": round(j[1], 3),
                        "j3": round(j[2], 3), "j4": round(j[3], 3),
                        "j5": round(j[4], 3), "j6": round(j[5], 3),
                    }
                except Exception:
                    pass  # lecture joints non bloquante

            def log_bdd(label, statut="ok", erreur=None, color=None):
                try:
                    db  = get_db()
                    cur = db.cursor()
                    try:
                        joints = robot_obj.get_joints()
                        pose   = robot_obj.get_pose()
                        j1, j2, j3, j4, j5, j6 = [float(v) for v in joints]
                        px, py, pz = float(pose.x), float(pose.y), float(pose.z)
                    except Exception:
                        j1=j2=j3=j4=j5=j6=px=py=pz=None
                    cur.execute("""
                        INSERT INTO robot_logs
                            (timestamp, label, statut, j1, j2, j3, j4, j5, j6, x, y, z, erreur, color)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """, (datetime.datetime.now(), label, statut,
                          j1, j2, j3, j4, j5, j6, px, py, pz, erreur, color))
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
                robot_obj.move_pose(JointsPosition(*base_pose))
                print("[ROBOT] move base_pose OK")
                update_joints()
                _snap_camera()
                time.sleep(1)

                if robot_state["stop_requested"]: break

                robot_state["last_action"] = "Pick rond"
                robot_obj.move_pose(JointsPosition(*rond_pose))
                robot_obj.pull_air_vacuum_pump()
                robot_obj.move_pose(JointsPosition(*base_pose))
                robot_obj.move_pose(JointsPosition(*lowbase_pose))
                robot_obj.push_air_vacuum_pump()
                robot_obj.move_pose(JointsPosition(*base_pose))
                update_joints()
                log_bdd("Pick rond")

                if robot_state["stop_requested"]: break

                # ── Détection couleur (sans saisie) ──────────────────────────
                robot_state["last_action"] = "Détection couleur"
                robot_obj.move_pose(JointsPosition(*base_pose))
                _snap_camera()

                obj_found = False
                shape_ret = None
                color_ret = None
                try:
                    obj_found, _, shape_ret, color_ret = robot_obj.detect_object(workspace_name)
                except Exception as vision_err:
                    print(f"[ROBOT] detect_object erreur : {vision_err}")
                    robot_state["last_action"] = f"detect_object ignoré : {vision_err}"

                print(f"[ROBOT] detect_object → obj_found={obj_found} shape={shape_ret} color={color_ret}")
                entry = {
                    "ts":        datetime.datetime.now().strftime("%H:%M:%S"),
                    "obj_found": obj_found,
                    "shape":     shape_ret.name if shape_ret else "—",
                    "color":     color_ret.name if color_ret else "—",
                }
                vision_history.insert(0, entry)
                if len(vision_history) > 20:
                    vision_history.pop()

                if not obj_found or color_ret in (None, ObjectColor.ANY):
                    robot_state["last_action"] = "Aucun objet détecté / couleur inconnue"

                elif color_ret == ObjectColor.RED:
                    # Rouge → saisit le rond depuis lowbase_pose et éjecte
                    robot_state["last_action"] = "Éjection — objet rouge"
                    #robot_obj.move_pose(JointsPosition(*lowbase_pose))
                    #robot_obj.pull_air_vacuum_pump()
                    #robot_obj.move_pose(JointsPosition(*base_pose))
                    robot_obj.move_pose(JointsPosition(*baseeject_pose))
                    robot_obj.move_pose(JointsPosition(*eject_pose))
                    robot_obj.push_air_vacuum_pump()
                    robot_state["count"]["RED"] += 1

                else:
                    # Pas rouge → pose un carré sur le rond
                    robot_state["last_action"] = f"Pose carré sur {color_ret.name if color_ret else '?'}"
                    robot_obj.move_pose(JointsPosition(*carre_pose))
                    robot_obj.pull_air_vacuum_pump()
                    robot_obj.move_pose(JointsPosition(*base_pose))
                    robot_obj.move_pose(JointsPosition(*lowbase_pose))
                    robot_obj.push_air_vacuum_pump()
                    robot_obj.move_pose(JointsPosition(*base_pose))
                    conveyor_id = robot_obj.set_conveyor()
                    robot_obj.run_conveyor(conveyor_id)
                    time.sleep(3)
                    robot_obj.stop_conveyor(conveyor_id)
                    if color_ret and color_ret != ObjectColor.ANY:
                        robot_state["count"][color_ret.name] += 1

                update_joints()
                color_str = color_ret.name if color_ret and color_ret != ObjectColor.ANY else None
                log_bdd("detect_object", color=color_str)

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
    def generate():
        last_sent = None
        while True:
            frame = camera_frame
            if frame is None:
                time.sleep(0.3)
                continue
            if frame is not last_sent:
                yield (b"--frame\r\n"
                       b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n")
                last_sent = frame
            time.sleep(0.1)
    return Response(generate(), mimetype="multipart/x-mixed-replace; boundary=frame")


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