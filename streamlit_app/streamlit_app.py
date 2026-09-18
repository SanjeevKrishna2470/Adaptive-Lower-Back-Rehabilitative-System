import streamlit as st
import time
import urllib.parse
import tempfile
import os
import cv2
import pandas as pd
from skeleton_overlay import AdvancedRehabProcessor
from shared_config import (
    EXERCISE_HIERARCHY,
    FLASK_LIVE_SESSION_URL,
    DEFAULT_REHAB_STORAGE_PATH,
    create_session_ticket,
)

st.set_page_config(
    page_title="Adaptive Rehabilitative System — Clinical Workspace",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Clinical UI Tokens & Scoped Styles ---
CLINICAL_CSS = """
<style>
/* Clinical Tokens */
:root {
  --cl-teal-primary: #0d9488;
  --cl-teal-hover: #14b8a6;
  --cl-teal-light: #5eead4;
  --cl-teal-glow: rgba(13, 148, 136, 0.25);
  --cl-bg-card: rgba(15, 23, 42, 0.55);
  --cl-border-subtle: rgba(255, 255, 255, 0.1);
  --cl-border-card: rgba(255, 255, 255, 0.14);
}

/* Stepper Bar */
.stepper-container {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 1rem 0 2rem 0;
  padding: 0.85rem 1.25rem;
  background: var(--cl-bg-card);
  border: 1px solid var(--cl-border-card);
  border-radius: 12px;
  gap: 8px;
  overflow-x: auto;
}

.step-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.86rem;
  font-weight: 500;
  color: #94a3b8;
  white-space: nowrap;
}

.step-item.active {
  color: #38bdf8;
  font-weight: 700;
}

.step-item.completed {
  color: #10b981;
}

.step-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  font-size: 0.75rem;
  font-weight: 700;
  background: rgba(255, 255, 255, 0.1);
  color: inherit;
}

.step-item.active .step-badge {
  background: #0284c7;
  color: #ffffff;
  box-shadow: 0 0 8px rgba(56, 189, 248, 0.4);
}

.step-item.completed .step-badge {
  background: #059669;
  color: #ffffff;
}

.step-arrow {
  color: #475569;
  font-size: 0.8rem;
}

/* Title & Section Bars */
.card-title-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.85rem;
  border-bottom: 1px solid var(--cl-border-subtle);
  padding-bottom: 0.5rem;
}

.card-title {
  font-size: 1.15rem;
  font-weight: 700;
  letter-spacing: -0.01em;
  margin: 0;
  display: flex;
  align-items: center;
  gap: 8px;
}

/* Badges & Status */
.cl-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 4px 10px;
  border-radius: 9999px;
  font-size: 0.76rem;
  font-weight: 600;
  letter-spacing: 0.02em;
  text-transform: uppercase;
}

.badge-success {
  background: rgba(16, 185, 129, 0.15);
  color: #34d399;
  border: 1px solid #059669;
}

.badge-warning {
  background: rgba(245, 158, 11, 0.15);
  color: #fbbf24;
  border: 1px solid #d97706;
}

.badge-danger {
  background: rgba(244, 63, 94, 0.15);
  color: #fb7185;
  border: 1px solid #e11d48;
}

.badge-info {
  background: rgba(56, 189, 248, 0.15);
  color: #38bdf8;
  border: 1px solid #0284c7;
}

.badge-neutral {
  background: rgba(255, 255, 255, 0.08);
  color: #94a3b8;
  border: 1px solid var(--cl-border-subtle);
}

/* Action CTA Buttons */
.cta-btn-primary {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  background: linear-gradient(135deg, #0d9488 0%, #0f766e 100%);
  color: #ffffff !important;
  padding: 12px 24px;
  font-size: 1rem;
  font-weight: 600;
  border-radius: 8px;
  text-decoration: none !important;
  box-shadow: 0 4px 14px rgba(13, 148, 136, 0.35);
  transition: all 0.2s ease;
  border: 1px solid #14b8a6;
  cursor: pointer;
  margin: 6px 0;
}

.cta-btn-primary:hover {
  background: linear-gradient(135deg, #14b8a6 0%, #0d9488 100%);
  box-shadow: 0 6px 18px rgba(13, 148, 136, 0.5);
  transform: translateY(-1px);
}

.cta-btn-secondary {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  background: rgba(255, 255, 255, 0.06);
  color: #e2e8f0 !important;
  padding: 10px 18px;
  font-size: 0.92rem;
  font-weight: 600;
  border-radius: 8px;
  text-decoration: none !important;
  border: 1px solid var(--cl-border-card);
  transition: all 0.2s ease;
  cursor: pointer;
  margin: 6px 0;
}

.cta-btn-secondary:hover {
  background: rgba(255, 255, 255, 0.12);
  border-color: rgba(255, 255, 255, 0.3);
}

/* Metric Display Cards */
.metric-summary-card {
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid var(--cl-border-subtle);
  border-radius: 8px;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.metric-summary-title {
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: #94a3b8;
  font-weight: 600;
}

.metric-summary-value {
  font-size: 1.6rem;
  font-weight: 700;
  color: #f8fafc;
  line-height: 1.2;
}

.metric-summary-sub {
  font-size: 0.72rem;
  color: #64748b;
}

/* Pre-flight Checklist */
.checklist-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 6px 0;
  font-size: 0.9rem;
  color: #cbd5e1;
}

.checklist-icon {
  color: #0d9488;
  flex-shrink: 0;
  margin-top: 2px;
}

/* Chips */
.param-chip-container {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 10px 0 16px 0;
}

.param-chip {
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid var(--cl-border-subtle);
  border-radius: 6px;
  padding: 5px 10px;
  font-size: 0.8rem;
  color: #cbd5e1;
}

.param-chip strong {
  color: #f8fafc;
}
</style>
"""
st.markdown(CLINICAL_CSS, unsafe_allow_html=True)

# --- Initialize Persistent Session Workspace Configuration ---
# IMPORTANT: storage_path must be shared_config's DEFAULT_REHAB_STORAGE_PATH,
# not skeleton_overlay's own file-relative default — otherwise this reads
# and writes a different rehab_storage.json than the Flask app does, and
# calibration status / session reports Flask saves never show up here.
if "processor" not in st.session_state:
    st.session_state.processor = AdvancedRehabProcessor(storage_path=DEFAULT_REHAB_STORAGE_PATH)

if "adaptive_hold_durations" not in st.session_state:
    st.session_state.adaptive_hold_durations = {ex: 3.0 for ex in EXERCISE_HIERARCHY}

if "adaptive_rom_targets" not in st.session_state:
    st.session_state.adaptive_rom_targets = {
        "Glute Bridge": 160.0,
        "Cat Cow": 165.0,
        "Bird Dog": 160.0,
        "Standing Hip Hinge": 155.0,
        # Near-full extension: this is basically where a person already is
        # just standing normally, so calibration/alignment validates fast
        # and the first hold comes quickly — see shared_config.py.
        "Standing Posture Hold": 170.0,
    }

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
    """Renders one rehab session's comprehensive clinical report."""
    acc = summary.get("accuracy_percentage", 0.0)
    if acc >= 80.0:
        quality_label = "Optimal Precision"
        quality_desc = "Target range of motion and hold stability achieved consistently."
        badge_class = "badge-success"
    elif acc >= 50.0:
        quality_label = "Functional Control"
        quality_desc = "Acceptable execution with minor postural deviations; focus on steady holds."
        badge_class = "badge-warning"
    else:
        quality_label = "Requires Form Focus"
        quality_desc = "Significant compensations detected; reduce movement speed and review alignment."
        badge_class = "badge-danger"

    st.markdown(f"""
    <div style="background: rgba(15, 23, 42, 0.6); border: 1px solid var(--cl-border-card); border-radius: 12px; padding: 18px 20px; margin-bottom: 1.5rem;">
      <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px; border-bottom: 1px solid var(--cl-border-subtle); padding-bottom: 12px; margin-bottom: 16px;">
        <div>
          <h3 style="margin: 0; font-size: 1.25rem; font-weight: 700; color: #f8fafc;">Session Performance Summary</h3>
          <span style="color: #94a3b8; font-size: 0.85rem;">Protocol: <strong>{selected_ex}</strong></span>
        </div>
        <div style="display: flex; align-items: center; gap: 8px;">
          <span class="cl-badge {badge_class}">{quality_label}</span>
        </div>
      </div>
      <p style="margin: 0 0 16px 0; color: #cbd5e1; font-size: 0.92rem;">{quality_desc}</p>
      
      <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px;">
        <div class="metric-summary-card">
          <span class="metric-summary-title">Execution Precision</span>
          <span class="metric-summary-value">{acc:.1f}%</span>
          <span class="metric-summary-sub">{summary.get('correct_reps', 0)} / {summary.get('total_reps', 0)} correct reps</span>
        </div>
        <div class="metric-summary-card">
          <span class="metric-summary-title">Mean Range of Motion</span>
          <span class="metric-summary-value">{summary.get('average_rom', 0):.1f}°</span>
          <span class="metric-summary-sub">Target kinematic threshold</span>
        </div>
        <div class="metric-summary-card">
          <span class="metric-summary-title">Mean Hold Duration</span>
          <span class="metric-summary-value">{summary.get('average_hold_time', 0):.1f}s</span>
          <span class="metric-summary-sub">Isometric contraction stability</span>
        </div>
        <div class="metric-summary-card">
          <span class="metric-summary-title">Transition Speed</span>
          <span class="metric-summary-value">{summary.get('average_movement_speed', 0):.1f}°/s</span>
          <span class="metric-summary-sub">Angular joint velocity</span>
        </div>
        <div class="metric-summary-card">
          <span class="metric-summary-title">Bilateral Symmetry</span>
          <span class="metric-summary-value">{summary.get('symmetry_score', 0)}/100</span>
          <span class="metric-summary-sub">Left vs. right coronal balance</span>
        </div>
        <div class="metric-summary-card">
          <span class="metric-summary-title">Fatigue Index</span>
          <span class="metric-summary-value">{summary.get('fatigue_score', 0)}%</span>
          <span class="metric-summary-sub">Kinematic deceleration load</span>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # Clinical Inferences Card
    comp_text = summary.get("most_common_compensation") or "None detected"
    flaw_text = summary.get("most_common_flaw") or "None detected"
    recommendation = summary.get("clinical_recommendation") or "Maintain current exercise pacing and form consistency."

    st.markdown(f"""
    <div style="background: rgba(255, 255, 255, 0.03); border: 1px solid var(--cl-border-subtle); border-radius: 10px; padding: 16px 18px; margin-bottom: 1.5rem;">
      <h4 style="margin: 0 0 12px 0; font-size: 1rem; font-weight: 700; color: #f8fafc;">Clinical Inferences & Directives</h4>
      <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 14px;">
        <div style="background: rgba(245, 158, 11, 0.08); border-left: 3px solid #f59e0b; padding: 8px 12px; border-radius: 4px;">
          <span style="font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.05em; color: #f59e0b; font-weight: 700;">Frequent Compensation</span>
          <div style="color: #f8fafc; font-size: 0.9rem; font-weight: 600; margin-top: 2px;">{comp_text}</div>
        </div>
        <div style="background: rgba(244, 63, 94, 0.08); border-left: 3px solid #f43f5e; padding: 8px 12px; border-radius: 4px;">
          <span style="font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.05em; color: #f43f5e; font-weight: 700;">Frequent Form Flaw</span>
          <div style="color: #f8fafc; font-size: 0.9rem; font-weight: 600; margin-top: 2px;">{flaw_text}</div>
        </div>
      </div>
      <div style="background: rgba(13, 148, 136, 0.1); border-left: 3px solid #0d9488; padding: 10px 14px; border-radius: 4px;">
        <span style="font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.05em; color: #5eead4; font-weight: 700;">Clinical Coaching Directive</span>
        <div style="color: #ffffff; font-size: 0.95rem; font-weight: 500; margin-top: 4px; line-height: 1.4;">{recommendation}</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

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
            st.success(f"Prescription Progression Applied: Target hold increased to {st.session_state.adaptive_hold_durations[selected_ex]:.1f}s, Target ROM increased to {st.session_state.adaptive_rom_targets[selected_ex]:.1f}°.")
        elif summary["accuracy_percentage"] < 50.0:
            st.session_state.adaptive_hold_durations[selected_ex] = max(
                1.0, st.session_state.adaptive_hold_durations[selected_ex] - 0.5
            )
            st.session_state.adaptive_rom_targets[selected_ex] = max(
                140.0, st.session_state.adaptive_rom_targets[selected_ex] - 3.0
            )
            st.info(f"Prescription Recovery Applied: Target hold adjusted to {st.session_state.adaptive_hold_durations[selected_ex]:.1f}s, Target ROM adjusted to {st.session_state.adaptive_rom_targets[selected_ex]:.1f}°.")

    # Render Longitudinal Historical Trend Tracker
    st.markdown("#### Longitudinal Kinematic Progression")
    st.caption("Tracking bilateral symmetry score and execution precision across historical sessions.")
    all_history = st.session_state.processor.persistent_data.get("history", [])
    if all_history:
        df_hist = pd.DataFrame(all_history)
        df_filtered = df_hist[df_hist["exercise_name"] == selected_ex]
        if not df_filtered.empty:
            df_chart = df_filtered.copy()
            df_chart["Session Date"] = pd.to_datetime(df_chart["timestamp"], unit="s")
            chart_data = df_chart.set_index("Session Date")[["symmetry_score", "accuracy_percentage"]]
            chart_data.columns = ["Symmetry Score (0-100)", "Accuracy Percentage (%)"]
            st.line_chart(chart_data)
        else:
            st.caption("No historical sessions recorded for this protocol yet.")
    else:
        st.caption("No historical sessions recorded yet.")


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
                frame, exercise_name, hold_dur, hold_dur, rom_min, calibration_session=True
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
st.sidebar.markdown("### Clinical Session Setup")
st.sidebar.caption("Configure protocol prescription and adaptive parameters.")

st.sidebar.markdown("---")
st.sidebar.markdown("#### Prescription Protocol")
selected_ex = st.sidebar.selectbox("Active Protocol", EXERCISE_HIERARCHY, label_visibility="collapsed")

st.sidebar.markdown("#### Target Prescription")
prescribed_reps = st.sidebar.number_input(
    "Target Repetitions",
    min_value=1,
    max_value=20,
    value=5,
    help="Prescribed repetition target for this rehabilitation set."
)

current_adaptive_hold = st.session_state.adaptive_hold_durations[selected_ex]
current_adaptive_rom = st.session_state.adaptive_rom_targets[selected_ex]

st.sidebar.markdown("---")
st.sidebar.markdown("#### Adaptive Biomechanical Thresholds")
st.sidebar.metric(
    "Target Isometric Hold",
    f"{current_adaptive_hold:.1f}s",
    help="Adaptive hold threshold. Automatically progresses (+0.5s) if execution accuracy is ≥ 80%."
)
st.sidebar.metric(
    "Adaptive Target ROM",
    f"{current_adaptive_rom:.1f}°",
    help="Target range of motion angle based on calibrated posture and session progression."
)

st.sidebar.markdown("---")
proc = st.session_state.processor
calib_status_sidebar = "Calibrated" if proc.normal_hunch_index is not None else "Calibration Needed"
status_class = "badge-success" if proc.normal_hunch_index is not None else "badge-warning"
st.sidebar.markdown(f"**Baseline Status:** <span class='cl-badge {status_class}'>{calib_status_sidebar}</span>", unsafe_allow_html=True)


# ----------------------------------------------------------------------
# Query Parameter & Redirect Handling
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
    st.query_params.clear()

# ----------------------------------------------------------------------
# Main Clinical Workspace Header
# ----------------------------------------------------------------------
st.markdown("## Adaptive Kinematic Rehabilitation Studio")
st.markdown("##### Evidence-Based Neuromuscular Movement Coaching & Biomechanical Telemetry")

# Dynamic Clinical Stepper Bar
is_calibrated = proc.normal_hunch_index is not None
has_report = pending_summary is not None

step1_cls = "completed"
step2_cls = "completed" if is_calibrated else "active"
step3_cls = "active" if (is_calibrated and not has_report) else ("completed" if has_report else "")
step4_cls = "active" if has_report else ""

st.markdown(f"""
<div class="stepper-container" role="navigation" aria-label="Rehabilitation Workflow Stepper">
  <div class="step-item {step1_cls}">
    <span class="step-badge">1</span>
    <span>Protocol: {selected_ex}</span>
  </div>
  <span class="step-arrow">➔</span>
  <div class="step-item {step2_cls}">
    <span class="step-badge">2</span>
    <span>Postural Calibration</span>
  </div>
  <span class="step-arrow">➔</span>
  <div class="step-item {step3_cls}">
    <span class="step-badge">3</span>
    <span>Live Rehabilitation</span>
  </div>
  <span class="step-arrow">➔</span>
  <div class="step-item {step4_cls}">
    <span class="step-badge">4</span>
    <span>Clinical Report</span>
  </div>
</div>
""", unsafe_allow_html=True)

if redirected_from_calibration:
    st.success(f"Postural profile successfully calibrated for **{redirect_exercise}**. You can now begin your rehabilitation session.")

if redirected_from_empty_rehab:
    st.info(f"No repetitions were completed in that session for **{redirect_exercise}**. Resume whenever you are ready.")

if redirected_with_missing_session:
    st.warning("The previous live session link was invalid or expired. Fresh session parameters have been generated below.")

def same_tab_link(label, url, variant="primary"):
    btn_class = "cta-btn-primary" if variant == "primary" else "cta-btn-secondary"
    st.markdown(
        f'<a href="{url}" target="_self" class="{btn_class}">'
        f'{label}</a>',
        unsafe_allow_html=True,
    )


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

# ----------------------------------------------------------------------
# Section 1: Postural Profile Calibration
# ----------------------------------------------------------------------
st.markdown("""
<div class="card-title-bar">
  <h3 class="card-title">
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2v20M2 12h20"></path><circle cx="12" cy="12" r="4"></circle></svg>
    Postural Profile Calibration
  </h3>
</div>
""", unsafe_allow_html=True)

if not is_calibrated:
    st.markdown("""
    <div style="margin-bottom: 1rem;">
      <span class="cl-badge badge-warning">Calibration Required</span>
      <p style="margin-top: 0.5rem; color: #cbd5e1; font-size: 0.92rem;">
        Establish your anatomical baseline before exercising. Calibration enables precise detection of spinal compensation, hip asymmetry, and movement fatigue.
      </p>
    </div>
    """, unsafe_allow_html=True)

    calib_live_tab, calib_upload_tab = st.tabs(["Live Camera (Recommended)", "Upload Pre-Recorded Video"])

    with calib_live_tab:
        st.markdown("""
        **Preparation Steps:**
        1. Click **Open Live Session for Calibration** below.
        2. Position yourself 6–8 feet from the camera with full body visible.
        3. Stand or align in your natural resting posture and hold steady for 3 seconds.
        4. You will automatically return here with your baseline stored.
        """)
        same_tab_link("Open Live Session for Calibration", calibration_url, variant="primary")
        st.caption("If you have completed calibration and need to refresh:")
        if st.button("Refresh Calibration Status", key="refresh_calib_btn"):
            refresh_shared_state(proc)
            st.rerun()

    with calib_upload_tab:
        st.markdown(
            "Upload a short 5–10 second video in your natural resting posture, "
            "with full body (head to ankles) in frame."
        )
        uploaded_calib_video = st.file_uploader(
            "Calibration video file", type=["mp4", "mov", "avi", "mkv", "webm"], key="calib_video_uploader"
        )
        if uploaded_calib_video is not None:
            if st.button("Process Video Calibration", key="run_video_calib_btn"):
                progress_bar = st.progress(0.0)
                frame_preview = st.empty()
                status_box = st.empty()
                with st.spinner("Analyzing anatomical alignment from video..."):
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
                    st.success("Calibration complete! Postural baseline profile saved.")
                    st.rerun()
                else:
                    st.error(
                        "Calibration incomplete. Ensure shoulders, hips, knees, and ankles "
                        "remain visible without obstruction for at least 3 seconds."
                    )
else:
    # Rich calibrated state card
    hunch_deg = f"{proc.normal_hunch_index:.1f}°" if isinstance(proc.normal_hunch_index, (int, float)) else "Normal"
    rom_val = f"{proc.baseline_max_rom:.1f}°" if proc.baseline_max_rom else "Adaptive"
    speed_val = f"{proc.baseline_avg_speed:.1f}°/s" if proc.baseline_avg_speed else "Nominal"

    st.markdown(f"""
    <div style="background: rgba(16, 185, 129, 0.08); border: 1px solid rgba(16, 185, 129, 0.3); border-radius: 10px; padding: 14px 18px; margin-bottom: 1rem;">
      <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px;">
        <div style="display: flex; align-items: center; gap: 8px;">
          <span class="cl-badge badge-success">Profile Calibrated</span>
          <strong style="color: #f8fafc; font-size: 0.95rem;">Anatomical Baseline Stored</strong>
        </div>
      </div>
      <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-top: 10px;">
        <div class="metric-summary-card">
          <span class="metric-summary-title">Spine Alignment Angle</span>
          <span class="metric-summary-value">{hunch_deg}</span>
          <span class="metric-summary-sub">Torso-head neutral axis</span>
        </div>
        <div class="metric-summary-card">
          <span class="metric-summary-title">Baseline Active ROM</span>
          <span class="metric-summary-value">{rom_val}</span>
          <span class="metric-summary-sub">Target kinematic threshold</span>
        </div>
        <div class="metric-summary-card">
          <span class="metric-summary-title">Baseline Control Velocity</span>
          <span class="metric-summary-value">{speed_val}</span>
          <span class="metric-summary-sub">Controlled transition speed</span>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    with st.expander("Recalibrate Anatomical Profile"):
        st.caption("Recalibrating will clear your current baseline posture metrics and require a new calibration session.")
        col_rec_a, col_rec_b = st.columns([1, 3])
        with col_rec_a:
            if st.button("Reset Baseline", key="reset_baseline_btn"):
                proc.normal_hunch_index = None
                proc.persistent_data["calibration"] = {}
                proc._save_storage()
                st.rerun()
        with col_rec_b:
            same_tab_link("Re-run Live Calibration", calibration_url, variant="secondary")

st.markdown("---")


# ----------------------------------------------------------------------
# Section 2: Live Rehabilitation Launch
# ----------------------------------------------------------------------
st.markdown("""
<div class="card-title-bar">
  <h3 class="card-title">
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><polygon points="10 8 16 12 10 16 10 8" fill="currentColor"></polygon></svg>
    Live Rehabilitation Session
  </h3>
</div>
""", unsafe_allow_html=True)

# Pre-flight Parameter Chips
st.markdown(f"""
<div class="param-chip-container">
  <div class="param-chip">Protocol: <strong>{selected_ex}</strong></div>
  <div class="param-chip">Prescription: <strong>{prescribed_reps} reps</strong></div>
  <div class="param-chip">Adaptive Target ROM: <strong>{current_adaptive_rom:.1f}°</strong></div>
  <div class="param-chip">Hold Duration: <strong>{current_adaptive_hold:.1f}s</strong></div>
</div>
""", unsafe_allow_html=True)

# Pre-flight Checklist
st.markdown("""
<div style="background: rgba(255, 255, 255, 0.02); border: 1px solid var(--cl-border-subtle); border-radius: 8px; padding: 12px 16px; margin-bottom: 16px;">
  <strong style="font-size: 0.84rem; text-transform: uppercase; letter-spacing: 0.05em; color: #94a3b8; display: block; margin-bottom: 6px;">
    Pre-Flight Clinical Checklist
  </strong>
  <div class="checklist-item">
    <span class="checklist-icon">✓</span>
    <span><strong>Positioning:</strong> Position your device 6–10 feet away with your full body visible on screen.</span>
  </div>
  <div class="checklist-item">
    <span class="checklist-icon">✓</span>
    <span><strong>Environment:</strong> Ensure adequate room lighting and a clear, stable exercise mat/floor area.</span>
  </div>
  <div class="checklist-item">
    <span class="checklist-icon">✓</span>
    <span><strong>Audio/Visual Cues:</strong> Watch the real-time clinical coaching bar and listen for phase transitions.</span>
  </div>
</div>
""", unsafe_allow_html=True)

if not is_calibrated:
    st.caption("Note: Calibration is recommended first for precise form-flaw detection, but you can launch now to practice movement.")

same_tab_link("Start Live Rehabilitation", rehab_url, variant="primary")

st.markdown("---")


# ----------------------------------------------------------------------
# Section 3: Session Report
# ----------------------------------------------------------------------
st.markdown("""
<div class="card-title-bar">
  <h3 class="card-title">
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>
    Clinical Session Report
  </h3>
</div>
""", unsafe_allow_html=True)

if pending_summary:
    render_summary(pending_summary, redirect_exercise)
else:
    hist_summary = latest_summary_for(proc, selected_ex)
    if hist_summary:
        st.markdown(f"<span class='cl-badge badge-neutral' style='margin-bottom: 12px;'>Showing Latest Saved Session for {selected_ex}</span>", unsafe_allow_html=True)
        render_summary(hist_summary, selected_ex)
    else:
        st.markdown("""
        <div style="background: rgba(255, 255, 255, 0.02); border: 1px dashed var(--cl-border-card); border-radius: 10px; padding: 24px; text-align: center; color: #94a3b8;">
          <p style="margin: 0 0 8px 0; font-size: 1rem; font-weight: 600; color: #cbd5e1;">Awaiting Next Completed Session</p>
          <p style="margin: 0; font-size: 0.85rem;">When you complete a live rehabilitation session and click <strong>Finish Session</strong> in the live interface, your clinical biomechanics report will appear here automatically.</p>
        </div>
        """, unsafe_allow_html=True)

        if st.button("Check for New Session Report", key="check_report_btn"):
            refresh_shared_state(proc)
            st.rerun()