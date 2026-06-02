#!/usr/bin/env python3
"""
Mock pyniryo — simule l'API Niryo Ned 2 sans robot physique.

Usage :
    USE_MOCK=1 python app.py
    USE_MOCK=1 python main.py
"""
import time
import random
from enum import Enum


# ── Enums ────────────────────────────────────────────────────────────────────

class ObjectColor(Enum):
    RED   = "RED"
    BLUE  = "BLUE"
    GREEN = "GREEN"


class ObjectShape(Enum):
    CIRCLE = "CIRCLE"
    SQUARE = "SQUARE"
    ANY    = "ANY"


# ── JointsPosition ────────────────────────────────────────────────────────────

class JointsPosition:
    def __init__(self, j1=0.0, j2=0.0, j3=0.0, j4=0.0, j5=0.0, j6=0.0):
        self._data = [float(j1), float(j2), float(j3),
                      float(j4), float(j5), float(j6)]

    def __iter__(self):      return iter(self._data)
    def __getitem__(self, i): return self._data[i]
    def __len__(self):        return 6
    def __repr__(self):
        return f"JointsPosition({', '.join(f'{v:.3f}' for v in self._data)})"


# ── Pose cartésienne simulée ──────────────────────────────────────────────────

class _MockPose:
    x = 0.15
    y = 0.0
    z = 0.25


# ── Robot mock ────────────────────────────────────────────────────────────────

class MockNiryoRobot:

    def __init__(self, ip: str):
        _log(f"Connexion simulée → {ip}")
        self._joints     = [0.0] * 6
        self._last_color = None
        self._last_shape = None

    # Cycle de vie ──────────────────────────────────────────────────────────

    def calibrate_auto(self):
        _log("calibrate_auto() — simulation 1 s")
        time.sleep(1.0)

    def update_tool(self):
        _log("update_tool()")

    def set_conveyor(self) -> int:
        _log("set_conveyor() → conveyor_id=1")
        return 1

    def close_connection(self):
        _log("close_connection()")

    def stop_move(self):
        _log("stop_move()")

    # Mouvements ────────────────────────────────────────────────────────────

    def move(self, position):
        joints = list(position)
        self._joints = joints
        _log(f"move(JointsPosition({[round(j, 3) for j in joints]}))")
        time.sleep(0.35)

    def move_joints(self, *args):
        joints = list(args[0]) if len(args) == 1 else list(args)
        self._joints = joints
        _log(f"move_joints({[round(j, 3) for j in joints]})")
        time.sleep(0.35)

    def move_pose(self, *args):
        _log(f"move_pose({args})")
        time.sleep(0.35)

    def jog_joints(self, *args):
        _log(f"jog_joints({args})")

    def set_arm_max_velocity(self, pct: int):
        _log(f"set_arm_max_velocity({pct} %)")

    # Outil (ventouse) ──────────────────────────────────────────────────────

    def pull_air_vacuum_pump(self):
        _log("pull_air_vacuum_pump() ← aspiration")
        time.sleep(0.15)

    def push_air_vacuum_pump(self):
        _log("push_air_vacuum_pump() → relâchement")
        time.sleep(0.15)

    # Convoyeur ─────────────────────────────────────────────────────────────

    def run_conveyor(self, conveyor_id: int, speed: int = 50):
        _log(f"run_conveyor({conveyor_id}, speed={speed})")

    def stop_conveyor(self, conveyor_id: int):
        _log(f"stop_conveyor({conveyor_id})")

    # Vision ────────────────────────────────────────────────────────────────

    def vision_pick(self, workspace: str):
        _log(f"vision_pick('{workspace}') — analyse en cours…")
        time.sleep(0.6)

        # Distribution : 50 % rouge, 30 % bleu, 20 % vert
        color = random.choices(
            [ObjectColor.RED, ObjectColor.BLUE, ObjectColor.GREEN],
            weights=[50, 30, 20]
        )[0]
        shape = ObjectShape.CIRCLE if color == ObjectColor.RED else ObjectShape.SQUARE

        self._last_color = color
        self._last_shape = shape
        _log(f"  → détecté : {color.name} / {shape.name}")
        return True, shape, color

    # Télémétrie ────────────────────────────────────────────────────────────

    def get_joints(self) -> list:
        noise = [random.uniform(-0.001, 0.001) for _ in range(6)]
        return [j + n for j, n in zip(self._joints, noise)]

    def get_pose(self) -> _MockPose:
        return _MockPose()

    def get_img_compressed(self) -> bytes:
        return _make_frame(self._last_color, self._last_shape)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _log(msg: str):
    print(f"\033[96m[MOCK]\033[0m {msg}")


def _make_frame(color=None, shape=None) -> bytes:
    """Génère une frame JPEG 640×480 simulant le retour caméra."""
    try:
        import cv2
        import numpy as np

        frame = np.full((480, 640, 3), (36, 24, 20), dtype=np.uint8)

        # Couleur de la forme en BGR
        bgr_map = {
            ObjectColor.RED:   (50,  50,  220),
            ObjectColor.BLUE:  (220, 80,  20),
            ObjectColor.GREEN: (50,  210, 50),
        }
        bgr = bgr_map.get(color, (80, 80, 80))

        # Dessine cercle (rouge) ou carré (bleu/vert/aucun)
        if color == ObjectColor.RED or shape == ObjectShape.CIRCLE:
            cv2.circle(frame, (320, 250), 75, bgr, -1)
            cv2.circle(frame, (320, 250), 75, (255, 255, 255), 2)
        else:
            cv2.rectangle(frame, (245, 175), (395, 325), bgr, -1)
            cv2.rectangle(frame, (245, 175), (395, 325), (255, 255, 255), 2)

        # Texte overlay
        cv2.putText(frame, "MOCK MODE", (215, 55),
                    cv2.FONT_HERSHEY_DUPLEX, 1.0, (0, 229, 255), 2)
        cv2.putText(frame, "Camera simulee", (210, 85),
                    cv2.FONT_HERSHEY_PLAIN, 1.2, (106, 116, 144), 1)

        if color:
            label = f"{color.name} / {shape.name if shape else '?'}"
            cv2.putText(frame, label, (240, 430),
                        cv2.FONT_HERSHEY_DUPLEX, 0.75, bgr, 2)

        _, buf = cv2.imencode(".jpg", frame)
        return buf.tobytes()

    except ImportError:
        # Fallback : JPEG minimal 1×1 pixel noir (valide)
        return (
            b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00'
            b'\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n'
            b'\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d'
            b'\x1a\x1c\x1c $.\' ",#\x1c\x1c(7),01444\x1f\'9=82<.342\x1e\x1f&7\x1e'
            b'&7\'81=-\x02\x01\x02\x02\x02\x01\x02\x02\x02\xff\xc0\x00\x0b\x08\x00'
            b'\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01'
            b'\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05'
            b'\x06\x07\x08\t\n\x0b\xff\xc4\x00\xb5\x10\x00\x02\x01\x03\x03\x02\x04'
            b'\x03\x05\x05\x04\x04\x00\x00\x01}\x01\x02\x03\x00\x04\x11\x05\x12!1A'
            b'\x06\x13Qa\x07"q\x142\x81\x91\xa1\x08#B\xb1\xc1\x15R\xd1\xf0$3br\x82'
            b'\t\n\x16\x17\x18\x19\x1a%&\'()*456789:CDEFGHIJSTUVWXYZ\xff\xda\x00\x08'
            b'\x01\x01\x00\x00?\x00\xfb\xd3P\x00\x00\x1f\xff\xd9'
        )


# ── Alias racine (compatibilité `from mock_niryo import NiryoRobot`) ──────────
NiryoRobot = MockNiryoRobot
