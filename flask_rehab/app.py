"""
Minimal Flask + Socket.IO server dedicated to the real-time rehab session.

This app does ONE job: take webcam frames pushed from the browser over a
WebSocket, run them through AdvancedRehabProcessor (unchanged biomechanics
engine), and stream back the annotated frame + telemetry. All reporting,
history, settings and calibration UI stay in the existing Streamlit app,
which reads/writes the same rehab_storage.json file.

Session model
-------------
This page is launched from Streamlit with an exercise and a mode already
baked into the URL (?exercise=...&mode=calibration|rehab) — there is no
dropdown here anymore, so the browser can never send a different exercise
than the one Streamlit selected.

"calibration" and "rehab" are treated as two separate sessions:
  * A calibration session only runs posture validation + the calibration
    countdown. It never counts reps, and any rep/phase state that happens
    to accumulate while the patient is getting into position is wiped
    before the calibration session starts AND the moment it finishes, so
    none of it leaks into the rehab session that follows. There is also no
    such thing as a "bad rep" during calibration — the overlay always
    stays in its neutral/good state (see skeleton_overlay.py), since
    calibration is what defines correct form in the first place.
  * The engine may finish computing a calibration profile internally
    within a couple of seconds of good posture, but the browser is NOT
    redirected the moment that happens. It stays on this page showing a
    "Calibration captured!" prompt until the patient/clinician explicitly
    clicks "Finish Calibration" — that click is the only thing that ever
    triggers the redirect back to Streamlit (?calibrated=1&exercise=...).
  * A rehab session requires a calibration profile to already exist. When
    the patient clicks "Finish Session", the summary is saved (as before)
    and the browser is told to redirect back to Streamlit
    (?session_complete=1&exercise=...) so the report shows up there
    automatically instead of via a JS alert().

On top of the raw telemetry, this version also derives a short, plain-
language "instruction" string for every step of the flow (calibration,
alignment, warm-up, hold, transition, flaws/compensations, fatigue, and
session finish) so the browser can just render `telemetry.instruction`
without needing to re-implement any of that logic client-side.

Each telemetry payload also carries `form_status` ("good" | "bad"),
produced by the engine, which the browser uses to color the skeleton
overlay's border blue (matching calibrated form) or red (deviating from
it) and to decide whether the rep in progress will count.
"""

import base64
import threading
import time
import urllib.parse

import cv2
import numpy as np
from flask import Flask, render_template, request, redirect
from flask_socketio import SocketIO

from skeleton_overlay import AdvancedRehabProcessor
from shared_config import (
    EXERCISE_HIERARCHY,
    STREAMLIT_BASE_URL,
    DEFAULT_REHAB_STORAGE_PATH,
    resolve_session_ticket,
)

app = Flask(__name__)
app.config["SECRET_KEY"] = "dev-secret-change-me"
socketio = SocketIO(app, cors_allowed_origins="*", max_http_buffer_size=10_000_000)

# One processor instance per server process, shared across connected clients.
# AdvancedRehabProcessor already guards its state with an internal lock, so
# this is safe for the single-user clinical kiosk use case this app targets.
#
# IMPORTANT: storage_path must be shared_config's DEFAULT_REHAB_STORAGE_PATH,
# not skeleton_overlay's own file-relative default. Without this, if app.py
# and streamlit_app.py live in different folders (each with their own copy
# of skeleton_overlay.py), Flask and Streamlit silently write/read two
# different rehab_storage.json files — calibration and session reports
# from one process never show up in the other.
processor = AdvancedRehabProcessor(storage_path=DEFAULT_REHAB_STORAGE_PATH)
processor_init_lock = threading.Lock()

DEFAULT_EXERCISE = EXERCISE_HIERARCHY[0]
VALID_MODES = ("calibration", "rehab")

# Mirrors the browser's own sessionGeneration counter (see live.js). Bumped
# whenever a session is restarted so that a frame the browser sent *before*
# hitting Restart, but which only reaches the server *after* the reset, gets
# rejected outright here instead of being run through process_single_frame
# and mutating the just-reset processor state. The client-side generation
# check in live.js only filters what gets *displayed*; this is what stops
# a stray straggler frame from being *processed* at all.
current_session_generation = 0


def _clean_exercise(name):
    return name if name in EXERCISE_HIERARCHY else DEFAULT_EXERCISE


def _clean_mode(mode):
    return mode if mode in VALID_MODES else "rehab"


def _reset_rep_tracking_state():
    """Clear per-session rep/telemetry state without touching calibration.

    Called (a) right before a calibration session starts, (b) right after
    a calibration session finishes, (c) right after a rehab session is
    finalized, and (d) whenever a session is explicitly restarted or the
    browser disconnects mid-session (see on_restart_session/on_disconnect
    below). This is what actually keeps calibration and rehab from
    bleeding into each other / into the next session.

    This is now a thin wrapper around processor.reset_session() — the
    field list used to be duplicated here and had drifted out of sync
    with skeleton_overlay.py (missing current_rep_min_rom,
    current_rep_reached_target, the 3D-biomechanics/compensation-hysteresis
    trackers, ...), which is exactly the kind of gap that lets stale state
    leak into a new session. Keeping one authoritative reset implementation
    on the processor itself means app.py can't drift out of sync with it
    again.
    """
    processor.reset_session()


def _redirect_url(**params):
    return STREAMLIT_BASE_URL + "?" + urllib.parse.urlencode(params)


# ----------------------------------------------------------------------
# Instructional copy — one place to edit the wording shown to the patient
# ----------------------------------------------------------------------
COMPENSATION_INSTRUCTIONS = {
    "Lateral Asymmetry": "Keep your left and right hips level with each other.",
    "Shoulder Hunching": "Relax your shoulders down and gently squeeze your shoulder blades together.",
    "Knee Flexion Break": "Keep your knees extended — avoid letting them bend during the movement.",
    "Torso Coronal Lean": "Keep your torso centered over your hips, don't lean side to side.",
    "Forward Head Posture": "Tuck your chin slightly and keep your ears stacked over your shoulders.",
}

FLAW_INSTRUCTIONS = {
    "Insufficent Isometric Hold Duration": "Hold the end position a little longer before releasing.",
}


def build_instruction(telemetry: dict) -> str:
    """Translate the raw telemetry dict into one short instruction for the patient."""

    # 1. Calibration takes priority over everything else.
    if telemetry.get("is_calibrating"):
        return "Stand naturally in your normal resting posture. Hold still while we calibrate..."

    # 2. Starting-position validation.
    if not telemetry.get("position_validated"):
        return "Align your body in the camera frame: keep shoulders and hips level, then hold still to begin."

    # 3. Warm-up phase.
    if telemetry.get("warmup_active"):
        remaining = telemetry.get("warmup_reps_remaining", 0)
        return f"Warm-up rep — focus on smooth, controlled form. {remaining} warm-up rep(s) left."

    # 4. Compensation cues take priority over generic phase text, since they
    #    are the most actionable feedback for the patient right now.
    compensations = telemetry.get("compensations") or []
    for comp in compensations:
        if comp in COMPENSATION_INSTRUCTIONS:
            return COMPENSATION_INSTRUCTIONS[comp]

    # 5. Fatigue warnings.
    fatigue_warnings = telemetry.get("fatigue_warnings") or []
    if fatigue_warnings:
        return fatigue_warnings[-1]

    # 6. Flaw cues (e.g. hold not long enough).
    flaws = telemetry.get("flaws") or []
    for flaw in flaws:
        if flaw in FLAW_INSTRUCTIONS:
            return FLAW_INSTRUCTIONS[flaw]

    # 7. Generic phase-based guidance.
    phase = telemetry.get("phase")
    hold_time = telemetry.get("hold_time", 0.0)
    if phase == "HOLDING":
        if hold_time > 0:
            return f"Hold this position steady... {hold_time:.1f}s so far."
        return "Move into the target position and hold."
    if phase == "MOVING":
        return "Transitioning — move smoothly and under control."

    return "Continue your repetitions."


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
    """Streamlit is the only thing that links here, and it always attaches
    ?session=<ticket> — a token registered ahead of time (via
    shared_config.create_session_ticket) that pins down exactly which
    exercise/hold_dur/rom_min/mode this page is for. Flask never reads
    exercise/hold_dur/rom_min/mode off the URL itself, so hand-editing the
    address bar can't switch the exercise — it can, at worst, hand us an
    unknown token, which just bounces back to Streamlit.
    """
    ticket = resolve_session_ticket(request.args.get("session", ""))

    if ticket is None:
        return redirect(_redirect_url(error="missing_session"))

    exercise = _clean_exercise(ticket.get("exercise", DEFAULT_EXERCISE))

    try:
        hold_dur = float(ticket.get("hold_dur", 3.0))
    except (TypeError, ValueError):
        hold_dur = 3.0

    try:
        rom_min = float(ticket.get("rom_min", 160.0))
    except (TypeError, ValueError):
        rom_min = 160.0

    mode = _clean_mode(ticket.get("mode", "rehab"))

    return render_template(
        "live.html",
        exercise=exercise,
        hold_dur=hold_dur,
        rom_min=rom_min,
        mode=mode,
    )


@socketio.on("connect")
def on_connect():
    global current_session_generation
    current_session_generation = 0
    socketio.emit("ready", {
        "normal_hunch_index": processor.normal_hunch_index,
        "instruction": (
            "Get ready — position yourself so your full body is visible in the camera, "
            "then start calibration if you haven't already."
        ),
    })


@socketio.on("start_calibration")
def on_start_calibration(payload=None):
    # A calibration session is its own isolated pass: wipe any leftover
    # rehab state (reps, phase, hold timers) before it begins so nothing
    # from a previous session contaminates it.
    _reset_rep_tracking_state()
    processor.is_calibrating = True
    processor.calibration_start_time = time.time()
    socketio.emit("calibration_started", {
        "instruction": "Stand naturally in your normal resting posture. Hold still while we calibrate...",
        "session_generation": (payload or {}).get("session_generation"),
    })


@socketio.on("finish_calibration_now")
def on_finish_calibration_now(payload):
    """The only thing that redirects the browser out of calibration mode."""
    payload = payload or {}
    exercise_name = _clean_exercise(payload.get("exercise_name", DEFAULT_EXERCISE))
    session_generation = payload.get("session_generation")

    # Reject manual override if the engine hasn't auto-captured a stable profile yet
    if processor.is_calibrating or processor.normal_hunch_index is None:
        socketio.emit("calibration_started", {
            "instruction": "Please hold a stable posture for 3 seconds to auto-calibrate before finishing.",
            "session_generation": session_generation,
        })
        return

    # If is_calibrating is False, the engine successfully captured the stable profile.
    _reset_rep_tracking_state()
    socketio.emit("calibration_complete", {
        "instruction": "Calibration complete! Redirecting you back to the main app...",
        "redirect_url": _redirect_url(calibrated="1", exercise=exercise_name),
        "session_generation": session_generation,
    })


@socketio.on("frame")
def on_frame(payload):
    """
    payload: {
      image: "data:image/jpeg;base64,...",
      exercise_name: "Glute Bridge",
      hold_dur: 3.0,
      rom_min: 160.0,
      mode: "calibration" | "rehab"
    }
    """
    img = decode_frame(payload.get("image", ""))
    if img is None:
        return

    # A frame the browser queued up before clicking Restart, but which only
    # arrived here after the reset — drop it silently rather than let it
    # mutate the freshly-reset processor state.
    incoming_generation = payload.get("session_generation")
    if incoming_generation is not None and incoming_generation < current_session_generation:
        return

    exercise_name = _clean_exercise(payload.get("exercise_name", DEFAULT_EXERCISE))
    hold_dur = float(payload.get("hold_dur", 3.0))
    rom_min = float(payload.get("rom_min", 160.0))
    mode = _clean_mode(payload.get("mode", "rehab"))
    session_generation = payload.get("session_generation")

    # Mirror for natural user feedback, matching the Streamlit transformer.
    img = cv2.flip(img, 1)

    if mode == "calibration":
        # is_calibrating's before/after transition (not profile existence)
        # is what tells us the engine just finished the math for this pass.
        was_calibrating = processor.is_calibrating
        processed_frame, telemetry = processor.process_single_frame(
            img, exercise_name, hold_dur, hold_dur, rom_min, calibration_session=True
        )
        just_finished_internally = was_calibrating and (not processor.is_calibrating)

        if just_finished_internally:
            # The engine has computed and saved a calibration profile for
            # this pass. We deliberately do NOT redirect the browser here
            # anymore — that used to make the whole calibration flow (click
            # "Calibrate" -> redirected out) finish in a couple of seconds
            # with no chance to look things over. Instead we just clear
            # rep-tracking state now (so nothing that accumulated while
            # validating posture leaks into the screen) and wait for an
            # explicit "Finish Calibration" click to actually leave this
            # page — see finish_calibration_now, which is now the *only*
            # thing that redirects out of calibration.
            _reset_rep_tracking_state()
            socketio.emit("processed_frame", {
                "image": encode_frame(processed_frame),
                "telemetry": {
                    **telemetry,
                    "form_status": "good",
                    "instruction": "Calibration captured! Click \"Finish Calibration\" whenever you're ready to continue.",
                },
                "session_generation": session_generation,
            })
            return

        # Force "good" form status during calibration frames — matches the
        # engine's own guarantee (see skeleton_overlay.py) that there's no
        # such thing as a bad rep while calibrating.
        telemetry["form_status"] = "good"
        if (not processor.is_calibrating) and processor.normal_hunch_index is not None:
            # Calibration is already done (this pass or a stale profile)
            # and we're just waiting on the button — keep showing the
            # "ready" prompt rather than generic phase/rep guidance, since
            # calibration mode never actually counts reps for real.
            telemetry["instruction"] = "Calibration captured! Click \"Finish Calibration\" whenever you're ready to continue."
        else:
            telemetry["instruction"] = build_instruction(telemetry)

        socketio.emit("processed_frame", {
            "image": encode_frame(processed_frame),
            "telemetry": telemetry,
            "session_generation": session_generation,
        })
        return

    # --- mode == "rehab" ---
    if processor.normal_hunch_index is None:
        socketio.emit("processed_frame", {
            "image": encode_frame(img),
            "telemetry": {"instruction": "No calibration profile found yet. Please calibrate first.", "form_status": "good"},
            "session_generation": session_generation,
        })
        return

    processed_frame, telemetry = processor.process_single_frame(
        img, exercise_name, hold_dur, hold_dur, rom_min
    )
    telemetry["instruction"] = build_instruction(telemetry)
    socketio.emit("processed_frame", {
        "image": encode_frame(processed_frame),
        "telemetry": telemetry,
        "session_generation": session_generation,
    })


@socketio.on("restart_session")
def on_restart_session(payload=None):
    """Patient/clinician abandoned the session in progress — a Restart
    click, or the browser's beforeunload handler firing on tab close/
    navigation — and wants a clean slate. Wipes whatever this processor
    has accumulated for the session (reps, phase/hold timers, an
    in-progress calibration countdown) WITHOUT touching the saved
    calibration profile (normal_hunch_index / baseline_*), so restarting a
    rehab session never forces the patient to recalibrate.

    Also bumps current_session_generation so any frame the browser already
    had in flight for the old session gets rejected by on_frame above
    instead of being processed against the now-reset state.
    """
    global current_session_generation
    payload = payload or {}
    session_generation = payload.get("session_generation")
    current_session_generation = (
        session_generation if session_generation is not None else current_session_generation + 1
    )

    _reset_rep_tracking_state()

    socketio.emit("session_reset", {
        "instruction": "Session reset. Ready to begin again.",
        "session_generation": session_generation,
    })


@socketio.on("disconnect")
def on_disconnect():
    """Backstop for the client-side beforeunload handler, which is only
    best-effort — the browser can tear the WebSocket down before that emit
    makes it out. Treat any disconnect as a possible abandoned session and
    reset the shared processor's per-session state so it can never bleed
    into whatever gets started next. Safe to call even when the previous
    session already finished cleanly (finalize/finish-calibration already
    reset this state, so this is a harmless no-op in that case).
    """
    _reset_rep_tracking_state()


@socketio.on("finalize_session")
def on_finalize_session(payload):
    exercise_name = _clean_exercise(payload.get("exercise_name", DEFAULT_EXERCISE))
    session_generation = (payload or {}).get("session_generation")
    summary = processor.finalize_session_data(exercise_name)

    # Whether or not there was anything to summarize, clear rep-tracking
    # state so a second rehab session (without recalibrating first) doesn't
    # inherit stale reps from this one.
    _reset_rep_tracking_state()

    # Always send the browser back to Streamlit — a session that tracked
    # zero reps is still a session that needs to end somewhere, not one
    # that leaves the patient stranded on this page with a JS alert().
    if summary:
        summary["instruction"] = (
            f"Session complete! You hit {summary['accuracy_percentage']}% accuracy over "
            f"{summary['total_reps']} attempted rep(s), {summary['correct_reps']} of which counted. "
            f"Redirecting you to your full report..."
        )
        summary["redirect_url"] = _redirect_url(session_complete="1", exercise=exercise_name)
        summary["session_generation"] = session_generation
        socketio.emit("session_summary", summary)
    else:
        socketio.emit("session_summary", {
            "instruction": "No repetitions were tracked during that session. Redirecting you back...",
            "redirect_url": _redirect_url(session_empty="1", exercise=exercise_name),
            "session_generation": session_generation,
        })


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "false").lower() in ("1", "true")
    socketio.run(app, host="0.0.0.0", port=port, debug=debug)