import streamlit as st
import time
import urllib.parse
import tempfile
import os
import cv2
import pandas as pd
from skeleton_overlay import AdvancedRehabProcessor
from shared_config import EXERCISE_HIERARCHY, FLASK_LIVE_SESSION_URL, create_session_ticket

st.set_page_config(page_title="AI Physiotherapy Kinematic Studio", layout="wide")

# --- Initialize Persistent Session Workspace Configuration ---
if "processor" not in st.session_state:
    st.session_state.processor = AdvancedRehabProcessor()

if "adaptive_hold_durations" not in st.session_state:
    st.session_state.adaptive_hold_durations = {ex: 3.0 for ex in EXERCISE_HIERARCHY}

if "adaptive_rom_targets" not in st.session_state:
    st.session_state.adaptive_rom_targets = {"Glute Bridge": 160.0, "Cat Cow": 165.0, "Bird Dog": 160.0, "Standing Hip Hinge": 155.0}

if "applied_summary_keys" not in st.session_state:
    # Guards against re-applying the adaptive hold/ROM progression more than
    # once for the same rehab session if this page reruns after a redirect.
    st.session_state.applied_summary_keys = set()


# ----------------------------------------------------------------------
# Flask <-> Streamlit are separate processes. They only agree with each
# other through rehab_storage.json — this app's in-memory `proc` was
# loaded once at session start and won't know about anything Flask wrote
# to disk unless we explicitly refresh it.
# ----------------------------------------------------------------------
def refresh_shared_state(proc):
    """Reload calibration + history from rehab_storage.json."""
    proc.persistent_data = proc._load_storage()
    calibration = proc.persistent_data.get("calibration") or {}
    proc.normal_hunch_index = calibration.get("normal_hunch_index")
    proc.baseline_max_rom = calibration.get("baseline_max_rom", 0.0)
    proc.baseline_avg_speed = calibration.get("baseline_avg_speed", 0.0)


def latest_summary_for(proc, exercise_name):
    history = proc.persistent_data.get("history", [])
    matches = [h for h in history if h.get("exercise_name") == exercise_name]
    if not matches:
        return None
    return max(matches, key=lambda h: h.get("timestamp", 0))


def render_summary(summary, selected_ex):
    """Renders one rehab session's report. Used automatically when Flask
    redirects back here after "Finish Session", and again any time the
    same report is re-displayed on a rerun."""
    st.success("## 🎉 Workout Session Report Generated!")

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.metric("Execution Precision", f"{summary['accuracy_percentage']}%")
        st.metric("Mean Range of Motion", f"{summary['average_rom']}°")
    with col_b:
        st.metric("Mean Hold Time", f"{summary['average_hold_time']}s")
        st.metric("Transition Speed", f"{summary['average_movement_speed']}°/s")
    with col_c:
        st.metric("Symmetry Score", f"{summary['symmetry_score']}/100")
        st.metric("Fatigue Index", f"{summary['fatigue_score']}%")

    st.markdown(f"""
    ### Clinical Inferences
    * **Common Compensation:** `{summary['most_common_compensation']}`
    * **Common Form Flaw:** `{summary['most_common_flaw']}`

    👉 **Clinical Directive:** *{summary['clinical_recommendation']}*
    """)

    # Apply the adaptive hold/ROM progression exactly once per session,
    # even if Streamlit reruns several times while this report is showing.
    session_key = (summary.get("exercise_name"), summary.get("timestamp"))
    if session_key not in st.session_state.applied_summary_keys:
        st.session_state.applied_summary_keys.add(session_key)
        if summary["accuracy_percentage"] >= 80.0:
            st.session_state.adaptive_hold_durations[selected_ex] += 0.5
            st.session_state.adaptive_rom_targets[selected_ex] = min(
                180.0, st.session_state.adaptive_rom_targets[selected_ex] + 2.0
            )
            st.balloons()
        elif summary["accuracy_percentage"] < 50.0:
            st.session_state.adaptive_hold_durations[selected_ex] = max(
                1.0, st.session_state.adaptive_hold_durations[selected_ex] - 0.5
            )
            st.session_state.adaptive_rom_targets[selected_ex] = max(
                140.0, st.session_state.adaptive_rom_targets[selected_ex] - 3.0
            )

    # Render Longitudinal Historical Trend Tracker
    st.markdown("### 📈 Long-Term Symmetry Analysis Trend Profiles")
    all_history = st.session_state.processor.persistent_data.get("history", [])
    if all_history:
        df_hist = pd.DataFrame(all_history)
        df_filtered = df_hist[df_hist["exercise_name"] == selected_ex]
        if not df_filtered.empty:
            st.line_chart(df_filtered.set_index(pd.to_datetime(df_filtered['timestamp'], unit='s'))[['symmetry_score', 'accuracy_percentage']])


def run_video_calibration(proc, uploaded_file, exercise_name, hold_dur, rom_min,
                           progress_bar=None, frame_preview=None, status_box=None):
    """Drive AdvancedRehabProcessor's calibration routine from an uploaded video file.

    Feeds the same process_single_frame() pipeline used by the live Flask
    session, but sources frames from an uploaded video instead of a webcam.
    Because the engine's timing (position-stability window + calibration
    delay) is based on wall-clock time.time(), frames are throttled to the
    video's native frame rate so a short recording still requires a few
    real seconds of "holding still" just like the live flow does.

    Returns True if calibration completed (normal_hunch_index got set),
    False otherwise (e.g. video ended before a stable posture was held
    long enough, or no person was detected).
    """
    tmp_path = None
    try:
        suffix = os.path.splitext(uploaded_file.name)[1] or ".mp4"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(uploaded_file.getbuffer())
            tmp_path = tmp.name

        cap = cv2.VideoCapture(tmp_path)
        if not cap.isOpened():
            if status_box:
                status_box.error("Could not open the uploaded video file. Try a standard MP4/MOV export.")
            return False

        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        frame_delay = 1.0 / fps if fps > 0 else 1.0 / 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or None

        # Reset the relevant per-session state so a fresh calibration pass
        # isn't polluted by whatever phase the processor was previously in.
        proc.position_validated = False
        proc.validation_stable_start = None
        proc.is_calibrating = True
        proc.calibration_start_time = time.time()

        frame_idx = 0
        calibrated = False

        while True:
            ret, frame = cap.read()
            if not ret:
                break
            frame_idx += 1

            # Mirror to match the live-session convention (natural user feedback).
            frame = cv2.flip(frame, 1)

            processed_frame, telemetry = proc.process_single_frame(
                frame, exercise_name, hold_dur, hold_dur, rom_min
            )

            if frame_preview is not None and frame_idx % 3 == 0:
                frame_preview.image(cv2.cvtColor(processed_frame, cv2.COLOR_BGR2RGB), channels="RGB")

            if progress_bar is not None and total_frames:
                progress_bar.progress(min(1.0, frame_idx / total_frames))

            if status_box is not None:
                if not telemetry.get("position_validated"):
                    status_box.info("Aligning posture in frame...")
                elif telemetry.get("is_calibrating"):
                    status_box.info("Holding steady — calibrating...")

            if not proc.is_calibrating and proc.normal_hunch_index is not None:
                calibrated = True
                break

            time.sleep(frame_delay)

        cap.release()
        return calibrated
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)

# --- Sidebar UI Control Deck ---
st.sidebar.markdown("## ⚙️ Clinical Engine Configuration")
selected_ex = st.sidebar.selectbox("Active Prescription Protocol", EXERCISE_HIERARCHY)

prescribed_reps = st.sidebar.number_input("Target Repetition Count", min_value=1, max_value=20, value=5)

current_adaptive_hold = st.session_state.adaptive_hold_durations[selected_ex]
current_adaptive_rom = st.session_state.adaptive_rom_targets[selected_ex]

st.sidebar.metric("Adaptive Hold Threshold", f"{current_adaptive_hold:.1f}s")
st.sidebar.metric("Adaptive Target Angle", f"{current_adaptive_rom:.1f}°")

# --- Main Page Layout UI Construction ---
st.title("🤸‍♂️ Digital Bio-Feedback Kinematic Engine")
st.markdown("### High-Fidelity Neuromuscular Assessment Interface")

proc = st.session_state.processor

# ----------------------------------------------------------------------
# Handle redirects coming back from the Flask live-session server. Flask
# attaches ?calibrated=1 after a calibration session finishes,
# ?session_complete=1 after a rehab session produced a report,
# ?session_empty=1 after a rehab session ended with zero reps tracked, and
# ?error=missing_session if the browser showed up with no valid/known
# session ticket (e.g. a stale tab, or someone hand-typing the Flask URL).
# The first three mean rehab_storage.json changed underneath us, so
# refresh before doing anything else.
# ----------------------------------------------------------------------
query_params = st.query_params
redirected_from_calibration = query_params.get("calibrated") == "1"
redirected_from_rehab = query_params.get("session_complete") == "1"
redirected_from_empty_rehab = query_params.get("session_empty") == "1"
redirected_with_missing_session = query_params.get("error") == "missing_session"
redirect_exercise = query_params.get("exercise", selected_ex)

if redirected_from_calibration or redirected_from_rehab or redirected_from_empty_rehab:
    refresh_shared_state(proc)

pending_summary = None
if redirected_from_rehab:
    pending_summary = latest_summary_for(proc, redirect_exercise)

if (
    redirected_from_calibration
    or redirected_from_rehab
    or redirected_from_empty_rehab
    or redirected_with_missing_session
):
    # Clear the query string so a manual refresh/rerun doesn't keep
    # re-triggering these banners.
    st.query_params.clear()

if redirected_from_calibration:
    st.success(f"✅ Calibration complete for **{redirect_exercise}**! You can now start your rehabilitation session below.")

if redirected_from_empty_rehab:
    st.info(f"No repetitions were tracked in that session for **{redirect_exercise}** — nothing to report yet.")

if redirected_with_missing_session:
    st.warning(
        "That live session link was invalid or had expired. Please click "
        "**Open Live Session for Calibration** or **Start Live Rehabilitation** below to start a fresh one."
    )

# Calibration and rehab each get their own one-time session ticket (with
# mode baked in) registered in shared_config, so the Flask side can treat
# them as two fully separate sessions — and can't be pointed at a
# different exercise by hand-editing the URL, since the URL only carries
# an opaque token, never the exercise name itself.
def build_live_url(mode):
    token = create_session_ticket(
        exercise=selected_ex,
        hold_dur=current_adaptive_hold,
        rom_min=current_adaptive_rom,
        mode=mode,
    )
    return f"{FLASK_LIVE_SESSION_URL}?{urllib.parse.urlencode({'session': token})}"


calibration_url = build_live_url("calibration")
rehab_url = build_live_url("rehab")

# --- Calibration section: always visible, its own button, independent of
# whether the rehab section below is also shown. ---
st.subheader("📏 Postural Profile Calibration")

if proc.normal_hunch_index is None:
    st.warning("⚠️ No personalized postural profile calibration found. Please calibrate before beginning.")

    calib_live_tab, calib_upload_tab = st.tabs(["📹 Live Camera (Flask)", "🎞️ Upload Video"])

    with calib_live_tab:
        st.markdown(
            "Open the live session in a browser tab, stand naturally in your "
            "normal resting posture, and use the **Calibrate** control there. "
            "You'll be brought back here automatically as soon as it's done."
        )
        st.link_button("🚀 Open Live Session for Calibration", calibration_url)
        st.caption("If the automatic redirect doesn't fire for some reason, use the button below.")
        if st.button("🔄 Refresh Calibration Status"):
            refresh_shared_state(proc)
            st.rerun()

    with calib_upload_tab:
        st.markdown(
            "Upload a short video (5–10s) of yourself standing/positioned in "
            "your normal resting posture, full body visible in frame."
        )
        uploaded_calib_video = st.file_uploader(
            "Calibration video", type=["mp4", "mov", "avi", "mkv", "webm"], key="calib_video_uploader"
        )
        if uploaded_calib_video is not None:
            if st.button("📏 Run Calibration From Video"):
                progress_bar = st.progress(0.0)
                frame_preview = st.empty()
                status_box = st.empty()
                with st.spinner("Analyzing posture from uploaded video..."):
                    success = run_video_calibration(
                        proc,
                        uploaded_calib_video,
                        selected_ex,
                        current_adaptive_hold,
                        current_adaptive_rom,
                        progress_bar=progress_bar,
                        frame_preview=frame_preview,
                        status_box=status_box,
                    )
                if success:
                    st.success("✅ Calibration complete from uploaded video!")
                    st.rerun()
                else:
                    st.error(
                        "Calibration didn't complete. Make sure your full body "
                        "(shoulders, hips, knees, ankles) stays visible, you hold "
                        "a steady natural posture for several seconds, and the "
                        "video is long enough (~6s or more)."
                    )
else:
    st.success("✅ Postural profile is calibrated.")
    st.link_button("🚀 Open Live Session for Calibration", calibration_url)
    with st.expander("Need to recalibrate?"):
        st.caption("This clears your saved postural profile and brings back the calibration flow above.")
        if st.button("♻️ Recalibrate"):
            proc.normal_hunch_index = None
            proc.persistent_data["calibration"] = {}
            proc._save_storage()
            st.rerun()

st.markdown("---")

# --- Rehab section: always visible as its own separate button, regardless
# of calibration status. Flask itself will politely tell the patient to
# calibrate first if they start a rehab session without a profile yet. ---
st.subheader("📹 Live Rehabilitation Session")
if proc.normal_hunch_index is None:
    st.info(
        f"You can open a live session for {selected_ex}, but form-compensation "
        "detection won't be accurate until you calibrate above."
    )
else:
    st.info(f"Perform {selected_ex}. Finishing the session in that tab brings your report back here automatically.")
st.link_button("🚀 Start Live Rehabilitation", rehab_url)

st.markdown("---")

# --- Session Report ---
# The live rehab session runs in Flask's own process/AdvancedRehabProcessor
# instance, so this app never has the per-rep data to compute a summary
# itself — it only ever reads the summary Flask already saved to
# rehab_storage.json when the patient clicked "Finish Session" there.
if pending_summary:
    render_summary(pending_summary, selected_ex)
else:
    st.subheader("📊 Latest Report")
    st.caption(
        "Reports appear here automatically as soon as you click **Finish Session** "
        "in the live rehabilitation tab."
    )
    if st.button("🔄 Check for New Report"):
        refresh_shared_state(proc)
        st.rerun()