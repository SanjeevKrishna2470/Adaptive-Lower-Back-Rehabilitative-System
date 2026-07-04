"""Single source of truth shared by app.py (Flask) and streamlit_app.py.

Flask and Streamlit run as two separate processes. Before this file existed,
each one hard-coded its own copy of the exercise list, which is exactly how
they'd eventually drift out of sync (e.g. someone adds an exercise in
Streamlit's sidebar but forgets the Flask dropdown — which used to exist
separately). Importing from here instead means there's only one place to
edit, and Flask can validate incoming exercise names against the same list
Streamlit uses to populate its selectbox.

Session tickets
----------------
Passing ?exercise=...&hold_dur=...&rom_min=... straight in the URL means
anyone can hand-edit the address bar and point the live Flask page at a
different exercise than the one Streamlit actually selected — Flask has no
way to tell the difference between "Streamlit built this URL" and "someone
typed this URL". To close that off, Streamlit registers a one-time session
ticket here (a random token mapped to the exercise/hold/rom/mode it chose)
and only ever hands the browser the token, never the raw values. Flask
looks the token up here and uses *only* what's on file for it — the
exercise/hold_dur/rom_min/mode query params themselves no longer exist on
the Flask side at all. Editing the URL just gets you an invalid/unknown
token, not a different exercise.

Where these files live
-----------------------
Anchoring these paths to *this file's own directory* only works if
app.py and streamlit_app.py (and their own copy of this file) live in
the same project folder. If they're split into separate directories —
e.g. a "backend" folder for Flask and a "frontend" folder for Streamlit,
each with its own copy of shared_config.py — anchoring to __file__ gives
each copy a *different* absolute path, and Flask can never see a ticket
Streamlit just wrote (or vice versa for rehab_storage.json).

To make this work regardless of how the two apps are laid out on disk,
the shared state directory defaults to a fixed location in the OS temp
directory (the same for every process on the same machine/user account),
and can be overridden with the REHAB_SHARED_DIR environment variable if
you need it to live somewhere specific (e.g. in a container or on a
shared clinical workstation with multiple accounts).
"""

import json
import os
import threading
import time
import uuid

EXERCISE_HIERARCHY = ["Glute Bridge", "Cat Cow", "Bird Dog", "Standing Hip Hinge"]

# Base URL Streamlit is served from. Flask uses this to build the redirect
# links it sends the browser back to after calibration finishes and after a
# rehab session is finalized.
STREAMLIT_BASE_URL = "http://localhost:8501/"

# Base URL Flask's live session is served from. Streamlit uses this to build
# the links it hands to the user (with ?session=<ticket> attached).
FLASK_LIVE_SESSION_URL = "http://localhost:5000/"

# Directory both processes read/write shared state from (session tickets,
# and — via DEFAULT_REHAB_STORAGE_PATH, used by skeleton_overlay.py —
# calibration + report history).
#
# By default this is computed automatically: this file lives one level
# down from the project root in both copies (root/streamlit_app/shared_config.py
# and root/flask_rehab/shared_config.py), so going up one directory from
# wherever *this* copy sits lands on the same root folder either way — no
# manual configuration needed, and it can't drift out of sync between the
# two copies the way an env var you have to remember to set in two
# different terminals can.
#
# If your layout is different (the two app folders aren't siblings under
# one root), set REHAB_SHARED_DIR to an absolute path yourself and that
# takes priority over the auto-detected root.
_this_app_dir = os.path.dirname(os.path.abspath(__file__))
_inferred_root = os.path.dirname(_this_app_dir)

_raw_shared_dir = os.environ.get("REHAB_SHARED_DIR")
SHARED_STATE_DIR = (
    os.path.abspath(_raw_shared_dir)
    if _raw_shared_dir
    else os.path.join(_inferred_root, "shared_folder")
)
os.makedirs(SHARED_STATE_DIR, exist_ok=True)
print(f"[shared_config] Using shared state directory: {SHARED_STATE_DIR}")

# Used as the default storage_path for AdvancedRehabProcessor in
# skeleton_overlay.py, so Flask's and Streamlit's processor instances read
# and write the exact same calibration/history file.
DEFAULT_REHAB_STORAGE_PATH = os.path.join(SHARED_STATE_DIR, "rehab_storage.json")

_SESSION_STORE_PATH = os.path.join(SHARED_STATE_DIR, "flask_sessions.json")
_SESSION_TTL_SECONDS = 60 * 60  # prune tickets older than an hour
_session_lock = threading.Lock()


def _load_sessions():
    if os.path.exists(_SESSION_STORE_PATH):
        try:
            with open(_SESSION_STORE_PATH, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save_sessions(sessions):
    try:
        with open(_SESSION_STORE_PATH, "w") as f:
            json.dump(sessions, f, indent=2)
    except Exception:
        pass


def create_session_ticket(exercise, hold_dur, rom_min, mode):
    """Called by Streamlit. Registers exactly which exercise/hold/rom/mode
    the upcoming Flask live session is for, and returns an opaque token
    that identifies that registration. Streamlit only ever puts this token
    in the URL it hands to the browser — never the exercise name itself.
    """
    with _session_lock:
        sessions = _load_sessions()

        now = time.time()
        sessions = {
            token: entry
            for token, entry in sessions.items()
            if now - entry.get("created_at", 0) < _SESSION_TTL_SECONDS
        }

        token = uuid.uuid4().hex
        sessions[token] = {
            "exercise": exercise,
            "hold_dur": hold_dur,
            "rom_min": rom_min,
            "mode": mode,
            "created_at": now,
        }
        _save_sessions(sessions)
        return token


def resolve_session_ticket(token):
    """Called by Flask. Returns the dict registered for this token, or
    None if the token is missing, unknown, or expired — e.g. someone
    opened the live page directly or hand-edited the URL rather than
    clicking through from Streamlit.
    """
    if not token:
        return None
    with _session_lock:
        sessions = _load_sessions()
        return sessions.get(token)