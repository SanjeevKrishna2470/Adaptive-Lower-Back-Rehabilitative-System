"""
Minimal Flask + Socket.IO server dedicated to the real-time rehab session.

This app does ONE job: take webcam frames pushed from the browser over a
WebSocket, run them through AdvancedRehabProcessor (unchanged biomechanics
engine), and stream back the annotated frame + telemetry. All reporting,
history, settings and calibration UI stay in the existing Streamlit app,
which reads/writes the same rehab_storage.json file.
"""

import base64
import threading

import cv2
import numpy as np
from flask import Flask, render_template
from flask_socketio import SocketIO

from skeleton_overlay import AdvancedRehabProcessor

app = Flask(__name__)
app.config["SECRET_KEY"] = "dev-secret-change-me"
socketio = SocketIO(app, cors_allowed_origins="*", max_http_buffer_size=10_000_000)

# One processor instance per server process, shared across connected clients.
# AdvancedRehabProcessor already guards its state with an internal lock, so
# this is safe for the single-user clinical kiosk use case this app targets.
processor = AdvancedRehabProcessor()
processor_init_lock = threading.Lock()


def decode_frame(data_url: str):
    """Decode a base64 data-URL (e.g. 'data:image/jpeg;base64,...') to a BGR ndarray."""
    if "," in data_url:
        data_url = data_url.split(",", 1)[1]
    raw = base64.b64decode(data_url)
    arr = np.frombuffer(raw, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def encode_frame(frame) -> str:
    """Encode a BGR ndarray back to a base64 JPEG data-URL."""
    ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
    if not ok:
        return ""
    return "data:image/jpeg;base64," + base64.b64encode(buf).decode("utf-8")


@app.route("/")
def index():
    return render_template("live.html")


@socketio.on("connect")
def on_connect():
    socketio.emit("ready", {"normal_hunch_index": processor.normal_hunch_index})


@socketio.on("start_calibration")
def on_start_calibration():
    import time
    processor.is_calibrating = True
    processor.calibration_start_time = time.time()
    socketio.emit("calibration_started", {})


@socketio.on("frame")
def on_frame(payload):
    """
    payload: {
      image: "data:image/jpeg;base64,...",
      exercise_name: "Pelvic Tilt",
      hold_dur: 3.0,
      rom_min: 160.0
    }
    """
    img = decode_frame(payload.get("image", ""))
    if img is None:
        return

    exercise_name = payload.get("exercise_name", "Pelvic Tilt")
    hold_dur = float(payload.get("hold_dur", 3.0))
    rom_min = float(payload.get("rom_min", 160.0))

    # Mirror for natural user feedback, matching the Streamlit transformer.
    img = cv2.flip(img, 1)

    processed_frame, telemetry = processor.process_single_frame(
        img, exercise_name, hold_dur, hold_dur, rom_min
    )

    socketio.emit("processed_frame", {
        "image": encode_frame(processed_frame),
        "telemetry": telemetry,
    })


@socketio.on("finalize_session")
def on_finalize_session(payload):
    exercise_name = payload.get("exercise_name", "Pelvic Tilt")
    summary = processor.finalize_session_data(exercise_name)
    socketio.emit("session_summary", summary or {})


if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)