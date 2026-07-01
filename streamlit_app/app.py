# # app.py
# import streamlit as st
# from streamlit_webrtc import webrtc_streamer, VideoProcessorBase, WebRtcMode
# import cv2
# import av
# import time
# import pandas as pd
# from skeleton_overlay import AdvancedRehabProcessor

# st.set_page_config(page_title="AI Physiotherapy Kinematic Studio", layout="wide")

# # --- Initialize Persistent Session Workspace Configuration ---
# if "processor" not in st.session_state:
#     st.session_state.processor = AdvancedRehabProcessor()

# if "unlocked_exercises" not in st.session_state:
#     st.session_state.unlocked_exercises = ["Pelvic Tilt"]

# if "adaptive_hold_durations" not in st.session_state:
#     st.session_state.adaptive_hold_durations = {"Pelvic Tilt": 3.0, "Cat Cow": 3.0, "Bird Dog": 3.0, "Knee to Chest": 3.0}

# if "adaptive_rom_targets" not in st.session_state:
#     st.session_state.adaptive_rom_targets = {"Pelvic Tilt": 160.0, "Cat Cow": 165.0, "Bird Dog": 160.0, "Knee to Chest": 155.0}

# EXERCISE_HIERARCHY = ["Pelvic Tilt", "Cat Cow", "Bird Dog", "Knee to Chest"]

# # --- Sidebar UI Control Deck ---
# st.sidebar.markdown("## ⚙️ Clinical Engine Configuration")
# selected_ex = st.sidebar.selectbox("Active Prescription Protocol", EXERCISE_HIERARCHY)

# # Hard Gating Exercise Progression Safeguards
# if selected_ex not in st.session_state.unlocked_exercises:
#     st.sidebar.error(f"🔒 Exercise Locked. Complete previous modules with high accuracy to advance.")
#     st.stop()

# prescribed_reps = st.sidebar.number_input("Target Repetition Count", min_value=1, max_value=20, value=5)

# current_adaptive_hold = st.session_state.adaptive_hold_durations[selected_ex]
# current_adaptive_rom = st.session_state.adaptive_rom_targets[selected_ex]

# st.sidebar.metric("Adaptive Hold Threshold", f"{current_adaptive_hold:.1f}s")
# st.sidebar.metric("Adaptive Target Angle", f"{current_adaptive_rom:.1f}°")

# # --- Multi-Threaded WebRTC Video Transformer Class ---
# class ClinicalVideoTransformer(VideoProcessorBase):
#     def __init__(self, processor, exercise_name, hold_dur, rom_min):
#         self.processor = processor
#         self.exercise_name = exercise_name
#         self.hold_dur = hold_dur
#         self.rom_min = rom_min

#     def recv(self, frame: av.VideoFrame) -> av.VideoFrame:
#         img = frame.to_ndarray(format="bgr24")
        
#         # Mirror image for natural user feedback
#         img = cv2.flip(img, 1)
        
#         # Send raw frame through our computing engine
#         processed_frame, _ = self.processor.process_single_frame(
#             img, self.exercise_name, self.hold_dur, self.hold_dur, self.rom_min
#         )
        
#         return av.VideoFrame.from_ndarray(processed_frame, format="bgr24")

# # --- Main Page Layout UI Construction ---
# st.title("🤸‍♂️ Digital Bio-Feedback Kinematic Engine")
# st.markdown("### High-Fidelity Neuromuscular Assessment Interface")

# proc = st.session_state.processor

# # Calibration Initialization Controls
# if proc.normal_hunch_index is None:
#     st.warning("⚠️ No personalized postural profile calibration found. Please calibrate before beginning.")
#     if st.button("📏 Run Automated Range Calibration Routine"):
#         proc.is_calibrating = True
#         proc.calibration_start_time = time.time()

# col_tgt, col_feed = st.columns([1, 1])

# with col_tgt:
#     st.subheader("🧠 Animated Movement Target Template")
#     # Instead of an independent animation loop, we use a lightweight button or component placeholder
#     st.info(f"Perform {selected_ex}. Maintain alignment with the on-screen markers.")
    
#     # Render static placeholder or dynamic canvas snippet safely
#     ref_frame = proc.generate_animated_reference(selected_ex, 360, 480)
#     st.image(ref_frame, channels="BGR", use_container_width=True)

# with col_feed:
#     st.subheader("📹 Live Analysis Feed")
    
#     # WebRTC Context Component (Safe, Non-Blocking)
#     ctx = webrtc_streamer(
#         key="rehab-streamer",
#         mode=WebRtcMode.SENDRECV,
#         rtc_configuration={"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]},
#         video_processor_factory=lambda: ClinicalVideoTransformer(
#             st.session_state.processor, selected_ex, current_adaptive_hold, current_adaptive_rom
#         ),
#         media_stream_constraints={"video": True, "audio": False},
#         async_processing=True
#     )

# st.markdown("---")

# # Session Evaluation Trigger Button (Replaces the broken loop logic)
# if st.button("🏁 Finish Workout Session & Generate Evaluation Report"):
#     summary = proc.finalize_session_data(selected_ex)
    
#     if summary:
#         st.success("## 🎉 Workout Session Report Generated!")
        
#         col_a, col_b, col_c = st.columns(3)
#         with col_a:
#             st.metric("Execution Precision", f"{summary['accuracy_percentage']}%")
#             st.metric("Mean Range of Motion", f"{summary['average_rom']}°")
#         with col_b:
#             st.metric("Mean Hold Time", f"{summary['average_hold_time']}s")
#             st.metric("Transition Speed", f"{summary['average_movement_speed']}°/s")
#         with col_c:
#             st.metric("Symmetry Score", f"{summary['symmetry_score']}/100")
#             st.metric("Fatigue Index", f"{summary['fatigue_score']}%")
            
#         st.markdown(f"""
#         ### Clinical Inferences
#         * **Common Compensation:** `{summary['most_common_compensation']}`
#         * **Common Form Flaw:** `{summary['most_common_flaw']}`
        
#         👉 **Clinical Directive:** *{summary['clinical_recommendation']}*
#         """)
        
#         # Performance Adaptive Progress Calculations
#         if summary["accuracy_percentage"] >= 80.0:
#             st.session_state.adaptive_hold_durations[selected_ex] += 0.5
#             st.session_state.adaptive_rom_targets[selected_ex] = min(180.0, st.session_state.adaptive_rom_targets[selected_ex] + 2.0)
            
#             current_idx = EXERCISE_HIERARCHY.index(selected_ex)
#             if current_idx + 1 < len(EXERCISE_HIERARCHY):
#                 next_ex = EXERCISE_HIERARCHY[current_idx + 1]
#                 if next_ex not in st.session_state.unlocked_exercises:
#                     st.session_state.unlocked_exercises.append(next_ex)
#                     st.balloons()
#         elif summary["accuracy_percentage"] < 50.0:
#             st.session_state.adaptive_hold_durations[selected_ex] = max(1.0, st.session_state.adaptive_hold_durations[selected_ex] - 0.5)
#             st.session_state.adaptive_rom_targets[selected_ex] = max(140.0, st.session_state.adaptive_rom_targets[selected_ex] - 3.0)

#         # Render Longitudinal Historical Trend Tracker
#         st.markdown("### 📈 Long-Term Symmetry Analysis Trend Profiles")
#         all_history = proc.persistent_data.get("history", [])
#         if all_history:
#             df_hist = pd.DataFrame(all_history)
#             df_filtered = df_hist[df_hist["exercise_name"] == selected_ex]
#             if not df_filtered.empty:
#                 st.line_chart(df_filtered.set_index(pd.to_datetime(df_filtered['timestamp'], unit='s'))[['symmetry_score', 'accuracy_percentage']])
#     else:
#         st.info("No repetitions were tracked during this streaming window. Complete your exercises, then click finish.")

# app.py
import streamlit as st
import time
import urllib.parse
import pandas as pd
from skeleton_overlay import AdvancedRehabProcessor

st.set_page_config(page_title="AI Physiotherapy Kinematic Studio", layout="wide")

# --- Initialize Persistent Session Workspace Configuration ---
if "processor" not in st.session_state:
    st.session_state.processor = AdvancedRehabProcessor()

if "unlocked_exercises" not in st.session_state:
    st.session_state.unlocked_exercises = ["Pelvic Tilt"]

if "adaptive_hold_durations" not in st.session_state:
    st.session_state.adaptive_hold_durations = {"Pelvic Tilt": 3.0, "Cat Cow": 3.0, "Bird Dog": 3.0, "Knee to Chest": 3.0}

if "adaptive_rom_targets" not in st.session_state:
    st.session_state.adaptive_rom_targets = {"Pelvic Tilt": 160.0, "Cat Cow": 165.0, "Bird Dog": 160.0, "Knee to Chest": 155.0}

EXERCISE_HIERARCHY = ["Pelvic Tilt", "Cat Cow", "Bird Dog", "Knee to Chest"]

# --- Address of the dedicated Flask real-time rehabilitation service ---
FLASK_LIVE_SESSION_URL = "http://localhost:5000/"

# --- Sidebar UI Control Deck ---
st.sidebar.markdown("## ⚙️ Clinical Engine Configuration")
selected_ex = st.sidebar.selectbox("Active Prescription Protocol", EXERCISE_HIERARCHY)

# Hard Gating Exercise Progression Safeguards
if selected_ex not in st.session_state.unlocked_exercises:
    st.sidebar.error(f"🔒 Exercise Locked. Complete previous modules with high accuracy to advance.")
    st.stop()

prescribed_reps = st.sidebar.number_input("Target Repetition Count", min_value=1, max_value=20, value=5)

current_adaptive_hold = st.session_state.adaptive_hold_durations[selected_ex]
current_adaptive_rom = st.session_state.adaptive_rom_targets[selected_ex]

st.sidebar.metric("Adaptive Hold Threshold", f"{current_adaptive_hold:.1f}s")
st.sidebar.metric("Adaptive Target Angle", f"{current_adaptive_rom:.1f}°")

# --- Main Page Layout UI Construction ---
st.title("🤸‍♂️ Digital Bio-Feedback Kinematic Engine")
st.markdown("### High-Fidelity Neuromuscular Assessment Interface")

proc = st.session_state.processor

# Calibration Initialization Controls
if proc.normal_hunch_index is None:
    st.warning("⚠️ No personalized postural profile calibration found. Please calibrate before beginning.")
    if st.button("📏 Run Automated Range Calibration Routine"):
        proc.is_calibrating = True
        proc.calibration_start_time = time.time()

# --- Live Session Launch Control ---
st.subheader("📹 Live Analysis Session")
st.info(f"Perform {selected_ex}. The live camera session runs in a dedicated browser tab.")

live_session_params = {
    "exercise": selected_ex,
    "rom_min": current_adaptive_rom,
    "hold_dur": current_adaptive_hold,
}
live_session_url = f"{FLASK_LIVE_SESSION_URL}?{urllib.parse.urlencode(live_session_params)}"

st.link_button("🚀 Start Live Rehabilitation", live_session_url)

st.markdown("---")

# Session Evaluation Trigger Button (Replaces the broken loop logic)
if st.button("🏁 Finish Workout Session & Generate Evaluation Report"):
    summary = proc.finalize_session_data(selected_ex)
    
    if summary:
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
        
        # Performance Adaptive Progress Calculations
        if summary["accuracy_percentage"] >= 80.0:
            st.session_state.adaptive_hold_durations[selected_ex] += 0.5
            st.session_state.adaptive_rom_targets[selected_ex] = min(180.0, st.session_state.adaptive_rom_targets[selected_ex] + 2.0)
            
            current_idx = EXERCISE_HIERARCHY.index(selected_ex)
            if current_idx + 1 < len(EXERCISE_HIERARCHY):
                next_ex = EXERCISE_HIERARCHY[current_idx + 1]
                if next_ex not in st.session_state.unlocked_exercises:
                    st.session_state.unlocked_exercises.append(next_ex)
                    st.balloons()
        elif summary["accuracy_percentage"] < 50.0:
            st.session_state.adaptive_hold_durations[selected_ex] = max(1.0, st.session_state.adaptive_hold_durations[selected_ex] - 0.5)
            st.session_state.adaptive_rom_targets[selected_ex] = max(140.0, st.session_state.adaptive_rom_targets[selected_ex] - 3.0)

        # Render Longitudinal Historical Trend Tracker
        st.markdown("### 📈 Long-Term Symmetry Analysis Trend Profiles")
        all_history = proc.persistent_data.get("history", [])
        if all_history:
            df_hist = pd.DataFrame(all_history)
            df_filtered = df_hist[df_hist["exercise_name"] == selected_ex]
            if not df_filtered.empty:
                st.line_chart(df_filtered.set_index(pd.to_datetime(df_filtered['timestamp'], unit='s'))[['symmetry_score', 'accuracy_percentage']])
    else:
        st.info("No repetitions were tracked during this streaming window. Complete your exercises, then click finish.")