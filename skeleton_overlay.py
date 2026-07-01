# import cv2
# import mediapipe as mp
# import math
# import time
# import json
# import os
# import threading

# class AdvancedRehabProcessor:
#     def __init__(self, storage_path="rehab_storage.json"):
#         self.lock = threading.Lock()
#         self.storage_path = storage_path
        
#         # Initialize MediaPipe Solutions once to prevent memory leaks across threads
#         self.mp_drawing = mp.solutions.drawing_utils
#         self.mp_pose = mp.solutions.pose
#         self.pose = self.mp_pose.Pose(
#             min_detection_confidence=0.5,
#             min_tracking_confidence=0.5
#         )
        
#         # --- State Configuration & Telemetry Stores ---
#         self.normal_hunch_index = None
#         self.calibration_start_time = None
#         self.CALIBRATION_DELAY = 3.0
#         self.is_calibrating = False

#         self.hold_start_time = None
#         self.total_hold_time = 0.0

#         self.prev_left_angle = None
#         self.prev_time = None
#         self.speed = 0.0

#         self.phase = "HOLDING"
#         self.phase_counter = 0
#         self.PHASE_SWITCH_FRAMES = 5
#         self.SPEED_THRESHOLD = 20.0

#         self.rep_count = 0
#         self.correct_rep_count = 0
#         self.last_phase = "HOLDING"          
#         self.WARMUP_REPS = 4                 
#         self.session_start_time = time.time()
        
#         # --- Expanded Clinical Telemetry State ---
#         self.current_rep_flaws = set()
#         self.current_rep_compensations = set()
#         self.session_reps_log = [] # List of dicts per rep
#         self.position_validated = False
#         self.validation_stable_start = None
        
#         # Fatigue Engine State
#         self.fatigue_score = 0.0
#         self.fatigue_warnings = []
#         self.baseline_max_rom = 0.0
#         self.baseline_avg_speed = 0.0
        
#         # High-Fidelity Metrics Trackers
#         self.current_rep_max_rom = 0.0
#         self.current_rep_speeds = []
#         self.current_rep_start_time = None

#         # Load Persistent Profiles
#         self.persistent_data = self._load_storage()
#         if "calibration" in self.persistent_data and self.persistent_data["calibration"]:
#             self.normal_hunch_index = self.persistent_data["calibration"].get("normal_hunch_index")
#             self.baseline_max_rom = self.persistent_data["calibration"].get("baseline_max_rom", 0.0)
#             self.baseline_avg_speed = self.persistent_data["calibration"].get("baseline_avg_speed", 0.0)

#     def _load_storage(self):
#         if os.path.exists(self.storage_path):
#             try:
#                 with open(self.storage_path, "r") as f:
#                     return json.load(f)
#             except Exception:
#                 return {"calibration": {}, "history": []}
#         return {"calibration": {}, "history": []}

#     def _save_storage(self):
#         try:
#             with open(self.storage_path, "w") as f:
#                 json.dump(self.persistent_data, f, indent=4)
#         except Exception as e:
#             print(f"Storage serialization error: {e}")

#     def calculate_angle(self, a, b, c):
#         vec1 = (a[0] - b[0], a[1] - b[1])
#         vec2 = (c[0] - b[0], c[1] - b[1])
#         dot = vec1[0]*vec2[0] + vec1[1]*vec2[1]
#         mag1 = math.sqrt(vec1[0]**2 + vec1[1]**2)
#         mag2 = math.sqrt(vec2[0]**2 + vec2[1]**2)
#         if mag1 > 0 and mag2 > 0:
#             cos = dot / (mag1 * mag2)
#             cos = max(-1.0, min(1.0, cos))
#             return math.degrees(math.acos(cos))
#         return 0.0

#     def euclidean(self, a, b):
#         return math.sqrt((a[0]-b[0])**2 + (a[1]-b[1])**2)

#     def generate_animated_reference(self, exercise_name, h, w):
#         """Generates a dynamic target skeleton map demonstrating ideal rhythmic execution."""
#         canvas = cv2.bitwise_not(cv2.getStructuringElement(cv2.MORPH_RECT, (w, h))) * 0
#         t = time.time() * 2.0  # Controls speed of demonstration
#         oscillation = (math.sin(t) + 1.0) / 2.0  # Normalized to range [0, 1]

#         center_x, center_y = w // 2, h // 2
#         color = (0, 165, 255) # Therapeutic Amber

#         # Define dynamic joint anchors depending on movement type
#         if exercise_name == "Pelvic Tilt":
#             tilt_offset = int(15 * oscillation)
#             cv2.circle(canvas, (center_x, center_y - 80), 20, color, -1) # Head
#             cv2.line(canvas, (center_x, center_y - 60), (center_x, center_y + 20), color, 4) # Torso
#             cv2.line(canvas, (center_x, center_y + 20), (center_x - 40, center_y + tilt_offset + 20), color, 4) # Pelvis
#         elif exercise_name == "Cat Cow":
#             arch_offset = int(25 * math.sin(t))
#             cv2.circle(canvas, (center_x - 80, center_y - 20), 18, color, -1)
#             cv2.line(canvas, (center_x - 60, center_y - 10), (center_x + 60, center_y - 10 + arch_offset), color, 4)
#         elif exercise_name == "Bird Dog":
#             ext = int(50 * oscillation)
#             cv2.circle(canvas, (center_x, center_y - 60), 18, color, -1)
#             cv2.line(canvas, (center_x, center_y - 40), (center_x, center_y + 20), color, 4)
#             cv2.line(canvas, (center_x, center_y - 40), (center_x - ext, center_y - 20), color, 4) # Arm Ext
#             cv2.line(canvas, (center_x, center_y + 20), (center_x + ext, center_y + 40), color, 4) # Leg Ext
#         else: # Knee to Chest default
#             knee_travel = int(40 * oscillation)
#             cv2.circle(canvas, (center_x, center_y - 80), 18, color, -1)
#             cv2.line(canvas, (center_x, center_y - 60), (center_x, center_y + 20), color, 4)
#             cv2.line(canvas, (center_x, center_y + 20), (center_x - 30, center_y - knee_travel), color, 4)

#         return canvas

#     def process_single_frame(self, frame, exercise_name, target_hold_time, strict_hold_duration, strict_rom_min):
#         """Single-frame callback entrypoint processing kinematic tracking with thread safety."""
#         with self.lock:
#             h, w, _ = frame.shape
#             rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
#             results = self.pose.process(rgb)

#             # Base telemetry template returned to UI
#             telemetry = {
#                 "rep_count": self.rep_count,
#                 "correct_rep_count": self.correct_rep_count,
#                 "phase": self.phase,
#                 "flaws": list(self.current_rep_flaws),
#                 "compensations": list(self.current_rep_compensations),
#                 "position_validated": self.position_validated,
#                 "fatigue_score": round(self.fatigue_score, 2),
#                 "fatigue_warnings": self.fatigue_warnings,
#                 "is_calibrating": self.is_calibrating,
#                 "normal_hunch_index": self.normal_hunch_index
#             }

#             if not results.pose_landmarks:
#                 return frame, telemetry

#             # Draw standard skeleton over live frame
#             self.mp_drawing.draw_landmarks(
#                 frame, results.pose_landmarks, self.mp_pose.POSE_CONNECTIONS,
#                 landmark_drawing_spec=self.mp_drawing.DrawingSpec(color=(0, 255, 0), thickness=2, circle_radius=2),
#                 connection_drawing_spec=self.mp_drawing.DrawingSpec(color=(255, 0, 0), thickness=2)
#             )

#             # Map Landmark Keypoints
#             lm = results.pose_landmarks.landmark
#             def get_xy(point):
#                 return (int(lm[point.value].x * w), int(lm[point.value].y * h))

#             l_sh = get_xy(self.mp_pose.PoseLandmark.LEFT_SHOULDER)
#             r_sh = get_xy(self.mp_pose.PoseLandmark.RIGHT_SHOULDER)
#             l_hip = get_xy(self.mp_pose.PoseLandmark.LEFT_HIP)
#             r_hip = get_xy(self.mp_pose.PoseLandmark.RIGHT_HIP)
#             l_knee = get_xy(self.mp_pose.PoseLandmark.LEFT_KNEE)
#             r_knee = get_xy(self.mp_pose.PoseLandmark.RIGHT_KNEE)
#             l_ank = get_xy(self.mp_pose.PoseLandmark.LEFT_ANKLE)
#             r_ank = get_xy(self.mp_pose.PoseLandmark.RIGHT_ANKLE)
#             l_ear = get_xy(self.mp_pose.PoseLandmark.LEFT_EAR)

#             # Extrapolate Key Kinematic Metrics
#             left_hip_angle = self.calculate_angle(l_sh, l_hip, l_knee)
#             right_hip_angle = self.calculate_angle(r_sh, r_hip, r_knee)
#             primary_angle = left_hip_angle # Base standard reference point

#             # Tracking Peak Range of Motion
#             if primary_angle > self.current_rep_max_rom:
#                 self.current_rep_max_rom = primary_angle

#             # Track Dynamic Translation Speed
#             now = time.time()
#             if self.prev_left_angle is not None and self.prev_time is not None:
#                 dt = now - self.prev_time
#                 self.speed = abs(primary_angle - self.prev_left_angle) / dt if dt > 0 else 0.0
#             else:
#                 self.speed = 0.0
#             self.prev_left_angle = primary_angle
#             self.prev_time = now
#             if self.phase == "MOVING":
#                 self.current_rep_speeds.append(self.speed)

#             # Phase Segment Switching Mechanics
#             target_phase = "MOVING" if self.speed > self.SPEED_THRESHOLD else "HOLDING"
#             if target_phase == self.phase:
#                 self.phase_counter = 0
#             else:
#                 self.phase_counter += 1
#                 if self.phase_counter >= self.PHASE_SWITCH_FRAMES:
#                     self.phase = target_phase
#                     self.phase_counter = 0

#             # --- Feature: Gradual Warmup Threshold Interpolation Matrix ---
#             interpolation_factor = min(1.0, self.rep_count / self.WARMUP_REPS)
#             asymmetry_thresh = 25.0 - (10.0 * interpolation_factor)   # Blends smoothly from 25.0 down to 15.0
#             knee_bend_thresh = 130.0 + (20.0 * interpolation_factor)   # Blends smoothly from 130.0 up to 150.0
#             hunch_mult = 1.08 - (0.02 * interpolation_factor)          # Blends smoothly from 1.08 down to 1.06
#             target_min_bound = strict_rom_min - 10.0 + (10.0 * interpolation_factor)

#             # Draw Kinematic Vector Lines
#             cv2.line(frame, l_sh, l_hip, (0, 255, 255), 1)
#             cv2.line(frame, l_hip, l_knee, (0, 255, 255), 1)

#             # --- Feature: Advanced Multi-Joint Starting Position Validation ---
#             shoulder_balance = abs(l_sh[1] - r_sh[1])
#             hip_balance = abs(l_hip[1] - r_hip[1])
#             torso_len_l = self.euclidean(l_sh, l_hip)
#             torso_len_r = self.euclidean(r_sh, r_hip)
#             symmetry_ratio = abs(torso_len_l - torso_len_r)
            
#             is_posture_aligned = (
#                 (target_min_bound <= primary_angle <= 180.0) and
#                 (shoulder_balance < 25) and
#                 (hip_balance < 25) and
#                 (symmetry_ratio < 30)
#             )

#             if not self.position_validated:
#                 if is_posture_aligned:
#                     if self.validation_stable_start is None:
#                         self.validation_stable_start = now
#                     elif now - self.validation_stable_start >= 2.0:
#                         self.position_validated = True
#                         self.current_rep_start_time = now
#                     cv2.putText(frame, "HOLDING START STABILITY...", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
#                 else:
#                     self.validation_stable_start = None
#                     cv2.putText(frame, "ALIGN PROFILE & SYMMETRY TO START", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
#                 return frame, telemetry

#             # --- Feature: Expanded Clinical Compensation Inference Engine ---
#             # 1. Lateral Shoulder/Pelvis Asymmetry
#             asymmetry = abs(left_hip_angle - right_hip_angle)
#             if asymmetry > asymmetry_thresh:
#                 self.current_rep_compensations.add("Lateral Asymmetry")
#                 cv2.putText(frame, "ALERT: Hip Asymmetry", (w-350, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

#             # 2. Scale-Invariant Hunching Calculation
#             avg_vert_torso = (abs(l_sh[1] - l_hip[1]) + abs(r_sh[1] - r_hip[1])) / 2.0
#             sh_width = self.euclidean(l_sh, r_sh)
#             hunch_idx = avg_vert_torso / sh_width if sh_width > 0 else 0.0
            
#             if self.is_calibrating and self.calibration_start_time is not None:
#                 elapsed = now - self.calibration_start_time
#                 if elapsed < self.CALIBRATION_DELAY:
#                     cv2.putText(frame, f"CALIBRATING PROFILE: {self.CALIBRATION_DELAY - elapsed:.1f}s", (w//2-150, h//2), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 0, 0), 2)
#                 else:
#                     self.normal_hunch_index = hunch_idx
#                     self.baseline_max_rom = primary_angle
#                     self.baseline_avg_speed = 25.0
#                     self.is_calibrating = False
#                     self.calibration_start_time = None
#                     self.persistent_data["calibration"] = {
#                         "normal_hunch_index": self.normal_hunch_index,
#                         "baseline_max_rom": self.baseline_max_rom,
#                         "baseline_avg_speed": self.baseline_avg_speed
#                     }
#                     self._save_storage()

#             if self.normal_hunch_index is not None and hunch_idx > self.normal_hunch_index * hunch_mult:
#                 self.current_rep_compensations.add("Shoulder Hunching")
#                 cv2.putText(frame, "ALERT: Cervico-Thoracic Hunching", (w-350, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

#             # 3. Knee Sagittal Flexion Drift
#             left_knee_angle = self.calculate_angle(l_hip, l_knee, l_ank)
#             right_knee_angle = self.calculate_angle(r_hip, r_knee, r_ank)
#             if left_knee_angle < knee_bend_thresh or right_knee_angle < knee_bend_thresh:
#                 self.current_rep_compensations.add("Knee Flexion Break")
#                 cv2.putText(frame, "ALERT: Unintended Knee Bending", (w-350, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

#             # 4. Torso Coronal Lean Break
#             torso_center_x = (l_sh[0] + r_sh[0]) / 2.0
#             pelvis_center_x = (l_hip[0] + r_hip[0]) / 2.0
#             lateral_lean = abs(torso_center_x - pelvis_center_x)
#             if lateral_lean > (sh_width * 0.25):
#                 self.current_rep_compensations.add("Torso Coronal Lean")
#                 cv2.putText(frame, "ALERT: Torso Coronal Lean", (w-350, 130), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

#             # 5. Cervical/Neck Posture Forward Shift
#             ear_to_shoulder = abs(l_ear[0] - l_sh[0])
#             if ear_to_shoulder > (sh_width * 0.4):
#                 self.current_rep_compensations.add("Forward Head Posture")
#                 cv2.putText(frame, "ALERT: Forward Head Posture", (w-350, 160), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

#             # Active Isometric Hold Computations
#             if primary_angle >= strict_rom_min:
#                 if self.hold_start_time is None:
#                     self.hold_start_time = now
#             else:
#                 if self.hold_start_time is not None:
#                     self.total_hold_time += now - self.hold_start_time
#                     self.hold_start_time = None

#             current_hold = (now - self.hold_start_time) if self.hold_start_time else 0.0
#             if current_hold < strict_hold_duration and self.phase == "HOLDING":
#                 self.current_rep_flaws.add("Insufficent Isometric Hold Duration")

#             # --- Transition Management & Per-Rep Evaluation Model ---
#             if self.last_phase == "HOLDING" and self.phase == "MOVING":
#                 self.rep_count += 1
#                 rep_duration = (now - self.current_rep_start_time) if self.current_rep_start_time else 1.0
#                 avg_speed = sum(self.current_rep_speeds) / len(self.current_rep_speeds) if self.current_rep_speeds else 0.0
                
#                 # Biomechanical Validation Assertions
#                 is_rep_correct = (len(self.current_rep_compensations) == 0) and (current_hold >= strict_hold_duration)
#                 if is_rep_correct:
#                     self.correct_rep_count += 1

#                 # Append to High-Fidelity Session Log Array
#                 rep_metrics_payload = {
#                     "rep_number": self.rep_count,
#                     "correctness": is_rep_correct,
#                     "detected_flaws": list(self.current_rep_flaws),
#                     "hold_duration": round(max(current_hold, self.total_hold_time), 2),
#                     "range_of_motion": round(self.current_rep_max_rom, 1),
#                     "movement_speed": round(avg_speed, 1),
#                     "compensations_detected": list(self.current_rep_compensations)
#                 }
#                 self.session_reps_log.append(rep_metrics_payload)

#                 # --- Feature: Fatigue Modeler Logic Engine ---
#                 if self.rep_count > 1 and self.baseline_max_rom > 0:
#                     rom_drop = max(0.0, (self.baseline_max_rom - self.current_rep_max_rom) / self.baseline_max_rom)
#                     compensation_penalty = len(self.current_rep_compensations) * 0.15
#                     self.fatigue_score = min(100.0, (rom_drop * 60.0 + compensation_penalty * 40.0) * 100.0)
                    
#                     self.fatigue_warnings = []
#                     if self.fatigue_score > 40.0:
#                         self.fatigue_warnings.append("Warning: Kinematic Tremor/Compensation climbing. Slow down your transitions.")
#                     if self.fatigue_score > 70.0:
#                         self.fatigue_warnings.append("CRITICAL: High Fatigue Metric. Complete the current rep and cease movement sequence.")

#                 # Reset Inter-Rep Local Workspace States
#                 self.current_rep_flaws = set()
#                 self.current_rep_compensations = set()
#                 self.current_rep_max_rom = 0.0
#                 self.current_rep_speeds = []
#                 self.current_rep_start_time = now
#                 self.total_hold_time = 0.0
#                 if self.hold_start_time is not None:
#                     self.hold_start_time = now

#             self.last_phase = self.phase

#             # UI Update Package Assembly
#             telemetry.update({
#                 "rep_count": self.rep_count,
#                 "correct_rep_count": self.correct_rep_count,
#                 "phase": self.phase,
#                 "fatigue_score": round(self.fatigue_score, 2),
#                 "fatigue_warnings": self.fatigue_warnings,
#                 "is_calibrating": self.is_calibrating,
#                 "normal_hunch_index": self.normal_hunch_index
#             })

#             # Render Dynamic HUD Data
#             cv2.putText(frame, f"REPS: {self.rep_count} | CORRECT: {self.correct_rep_count}", (20, h - 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
#             return frame, telemetry

#     def finalize_session_data(self, exercise_name):
#         """Compiles raw metrics data arrays into an end-of-session database profile payload."""
#         with self.lock:
#             if not self.session_reps_log:
#                 return None

#             total_reps = len(self.session_reps_log)
#             correct_reps = sum(1 for r in self.session_reps_log if r["correctness"])
#             accuracy_pct = (correct_reps / total_reps) * 100.0 if total_reps > 0 else 0.0
            
#             avg_rom = sum(r["range_of_motion"] for r in self.session_reps_log) / total_reps
#             avg_hold = sum(r["hold_duration"] for r in self.session_reps_log) / total_reps
#             avg_speed = sum(r["movement_speed"] for r in self.session_reps_log) / total_reps

#             # Parse structural flaw frequency indices
#             flaw_counts = {}
#             comp_counts = {}
#             lateral_asymmetry_events = 0

#             for r in self.session_reps_log:
#                 for f in r["detected_flaws"]:
#                     flaw_counts[f] = flaw_counts.get(f, 0) + 1
#                 for c in r["compensations_detected"]:
#                     comp_counts[c] = comp_counts.get(c, 0) + 1
#                     if c == "Lateral Asymmetry":
#                         lateral_asymmetry_events += 1

#             most_common_flaw = max(flaw_counts, key=flaw_counts.get) if flaw_counts else "None"
#             most_common_comp = max(comp_counts, key=comp_counts.get) if comp_counts else "None"

#             # Compute Cross-Session Long-Term Symmetry Indices
#             symmetry_score = max(0.0, 100.0 - (lateral_asymmetry_events * 12.5))
            
#             # Formulate Personalized Clinical Recommendation Matrices
#             recommendation = "Excellent kinematics. Structural posture and target stability thresholds are verified."
#             if symmetry_score < 75.0:
#                 recommendation = "High asymmetric structural drift detected. Focus on keeping your left and right sides level."
#             elif self.fatigue_score > 60.0:
#                 recommendation = "Movement velocity and range of motion degraded significantly toward the end of the session. Increase rest intervals between repetitions."
#             elif most_common_comp == "Shoulder Hunching":
#                 recommendation = "Cervico-thoracic compensation pattern detected. Keep your scapula retracted and shoulders relaxed down away from your neck."

#             summary_payload = {
#                 "timestamp": time.time(),
#                 "exercise_name": exercise_name,
#                 "total_reps": total_reps,
#                 "correct_reps": correct_reps,
#                 "accuracy_percentage": round(accuracy_pct, 1),
#                 "average_rom": round(avg_rom, 1),
#                 "average_hold_time": round(avg_hold, 1),
#                 "average_movement_speed": round(avg_speed, 1),
#                 "fatigue_score": round(self.fatigue_score, 1),
#                 "symmetry_score": round(symmetry_score, 1),
#                 "most_common_flaw": most_common_flaw,
#                 "most_common_compensation": most_common_comp,
#                 "clinical_recommendation": recommendation
#             }

#             self.persistent_data["history"].append(summary_payload)
#             self._save_storage()
#             return summary_payload

"""
AdvancedRehabProcessor

A framework-independent biomechanics/kinematics engine. It accepts a raw
NumPy BGR frame and returns an annotated NumPy frame plus a telemetry
dictionary. It has no dependency on any UI or web framework — it can be
driven by Streamlit, Flask, a CLI script, or a unit test with identical
behavior.

No Streamlit imports. No Flask imports. No UI code.
"""

import cv2
import mediapipe as mp
import math
import time
import json
import os
import threading


class AdvancedRehabProcessor:
    # --- Tunable constants kept at class scope for clarity / single source of truth ---
    CALIBRATION_DELAY = 3.0
    PHASE_SWITCH_FRAMES = 5
    SPEED_THRESHOLD = 20.0
    WARMUP_REPS = 4
    POSITION_STABILITY_SECONDS = 2.0

    def __init__(self, storage_path="rehab_storage.json"):
        self.lock = threading.Lock()
        self.storage_path = storage_path

        # Initialize MediaPipe Solutions once to prevent memory leaks across threads
        self.mp_drawing = mp.solutions.drawing_utils
        self.mp_pose = mp.solutions.pose
        self.pose = self.mp_pose.Pose(
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )

        # --- State Configuration & Telemetry Stores ---
        self.normal_hunch_index = None
        self.calibration_start_time = None
        self.is_calibrating = False

        self.hold_start_time = None
        self.total_hold_time = 0.0

        self.prev_left_angle = None
        self.prev_time = None
        self.speed = 0.0

        self.phase = "HOLDING"
        self.phase_counter = 0

        self.rep_count = 0
        self.correct_rep_count = 0
        self.last_phase = "HOLDING"
        self.session_start_time = time.time()

        # --- Expanded Clinical Telemetry State ---
        self.current_rep_flaws = set()
        self.current_rep_compensations = set()
        self.session_reps_log = []  # List of dicts per rep
        self.position_validated = False
        self.validation_stable_start = None

        # Fatigue Engine State
        self.fatigue_score = 0.0
        self.fatigue_warnings = []
        self.baseline_max_rom = 0.0
        self.baseline_avg_speed = 0.0

        # High-Fidelity Metrics Trackers
        self.current_rep_max_rom = 0.0
        self.current_rep_speeds = []
        self.current_rep_start_time = None

        # Load Persistent Profiles
        self.persistent_data = self._load_storage()
        calibration = self.persistent_data.get("calibration") or {}
        self.normal_hunch_index = calibration.get("normal_hunch_index")
        self.baseline_max_rom = calibration.get("baseline_max_rom", 0.0)
        self.baseline_avg_speed = calibration.get("baseline_avg_speed", 0.0)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def _load_storage(self):
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, "r") as f:
                    return json.load(f)
            except Exception:
                return {"calibration": {}, "history": []}
        return {"calibration": {}, "history": []}

    def _save_storage(self):
        try:
            with open(self.storage_path, "w") as f:
                json.dump(self.persistent_data, f, indent=4)
        except Exception as e:
            print(f"Storage serialization error: {e}")

    # ------------------------------------------------------------------
    # Geometry helpers
    # ------------------------------------------------------------------
    def calculate_angle(self, a, b, c):
        vec1 = (a[0] - b[0], a[1] - b[1])
        vec2 = (c[0] - b[0], c[1] - b[1])
        dot = vec1[0] * vec2[0] + vec1[1] * vec2[1]
        mag1 = math.sqrt(vec1[0] ** 2 + vec1[1] ** 2)
        mag2 = math.sqrt(vec2[0] ** 2 + vec2[1] ** 2)
        if mag1 > 0 and mag2 > 0:
            cos = dot / (mag1 * mag2)
            cos = max(-1.0, min(1.0, cos))
            return math.degrees(math.acos(cos))
        return 0.0

    def euclidean(self, a, b):
        return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)

    # ------------------------------------------------------------------
    # Reference animation (pure data/image generation — no UI framework)
    # ------------------------------------------------------------------
    def generate_animated_reference(self, exercise_name, h, w):
        """Generates a dynamic target skeleton map demonstrating ideal rhythmic execution.

        Returns a raw NumPy BGR image. Callers (Streamlit, Flask, etc.) are
        responsible for displaying it.
        """
        canvas = cv2.bitwise_not(cv2.getStructuringElement(cv2.MORPH_RECT, (w, h))) * 0
        t = time.time() * 2.0  # Controls speed of demonstration
        oscillation = (math.sin(t) + 1.0) / 2.0  # Normalized to range [0, 1]

        center_x, center_y = w // 2, h // 2
        color = (0, 165, 255)  # Therapeutic Amber

        if exercise_name == "Pelvic Tilt":
            tilt_offset = int(15 * oscillation)
            cv2.circle(canvas, (center_x, center_y - 80), 20, color, -1)
            cv2.line(canvas, (center_x, center_y - 60), (center_x, center_y + 20), color, 4)
            cv2.line(canvas, (center_x, center_y + 20), (center_x - 40, center_y + tilt_offset + 20), color, 4)
        elif exercise_name == "Cat Cow":
            arch_offset = int(25 * math.sin(t))
            cv2.circle(canvas, (center_x - 80, center_y - 20), 18, color, -1)
            cv2.line(canvas, (center_x - 60, center_y - 10), (center_x + 60, center_y - 10 + arch_offset), color, 4)
        elif exercise_name == "Bird Dog":
            ext = int(50 * oscillation)
            cv2.circle(canvas, (center_x, center_y - 60), 18, color, -1)
            cv2.line(canvas, (center_x, center_y - 40), (center_x, center_y + 20), color, 4)
            cv2.line(canvas, (center_x, center_y - 40), (center_x - ext, center_y - 20), color, 4)
            cv2.line(canvas, (center_x, center_y + 20), (center_x + ext, center_y + 40), color, 4)
        else:  # Knee to Chest default
            knee_travel = int(40 * oscillation)
            cv2.circle(canvas, (center_x, center_y - 80), 18, color, -1)
            cv2.line(canvas, (center_x, center_y - 60), (center_x, center_y + 20), color, 4)
            cv2.line(canvas, (center_x, center_y + 20), (center_x - 30, center_y - knee_travel), color, 4)

        return canvas

    # ------------------------------------------------------------------
    # Main per-frame entrypoint
    # ------------------------------------------------------------------
    def process_single_frame(self, frame, exercise_name, target_hold_time, strict_hold_duration, strict_rom_min):
        """Process one NumPy BGR frame.

        Args:
            frame: NumPy ndarray (BGR), as produced by any camera/video source.
            exercise_name: name of the active exercise.
            target_hold_time: reserved for future use / informational hold target.
            strict_hold_duration: required isometric hold duration in seconds.
            strict_rom_min: minimum range-of-motion angle target in degrees.

        Returns:
            (processed_frame: np.ndarray, telemetry: dict)
        """
        with self.lock:
            h, w, _ = frame.shape
            results = self._run_pose_estimation(frame)

            telemetry = self._base_telemetry()

            if not results.pose_landmarks:
                return frame, telemetry

            self._draw_skeleton(frame, results)
            landmarks = self._extract_landmarks(results, w, h)

            kinematics = self._compute_kinematics(landmarks)
            now = time.time()
            self._update_speed_and_phase(kinematics["primary_angle"], now)

            thresholds = self._warmup_interpolated_thresholds(strict_rom_min)

            self._draw_vector_lines(frame, landmarks)

            if not self.position_validated:
                aligned = self._is_posture_aligned(landmarks, kinematics["primary_angle"], thresholds)
                self._handle_position_validation(frame, aligned, now)
                return frame, telemetry

            self._detect_compensations(frame, landmarks, kinematics, thresholds)
            self._handle_calibration(frame, kinematics, now)
            self._update_isometric_hold(kinematics["primary_angle"], strict_rom_min, strict_hold_duration, now)

            if self.last_phase == "HOLDING" and self.phase == "MOVING":
                self._finalize_rep(strict_hold_duration, now)

            self.last_phase = self.phase

            telemetry.update(self._base_telemetry())
            self._draw_hud(frame, h)
            return frame, telemetry

    # ------------------------------------------------------------------
    # process_single_frame helpers (internal only — same logic as before)
    # ------------------------------------------------------------------
    def _run_pose_estimation(self, frame):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        return self.pose.process(rgb)

    def _base_telemetry(self):
        return {
            "rep_count": self.rep_count,
            "correct_rep_count": self.correct_rep_count,
            "phase": self.phase,
            "flaws": list(self.current_rep_flaws),
            "compensations": list(self.current_rep_compensations),
            "position_validated": self.position_validated,
            "fatigue_score": round(self.fatigue_score, 2),
            "fatigue_warnings": self.fatigue_warnings,
            "is_calibrating": self.is_calibrating,
            "normal_hunch_index": self.normal_hunch_index,
            "rom": round(self.current_rep_max_rom, 1),
            "movement_speed": round(self.speed, 1),
            "hold_time": round(getattr(self, "_current_hold", 0.0), 1),
            "warmup_active": self.rep_count < self.WARMUP_REPS,
            "warmup_reps_remaining": max(0, self.WARMUP_REPS - self.rep_count),
        }

    def _draw_skeleton(self, frame, results):
        self.mp_drawing.draw_landmarks(
            frame, results.pose_landmarks, self.mp_pose.POSE_CONNECTIONS,
            landmark_drawing_spec=self.mp_drawing.DrawingSpec(color=(0, 255, 0), thickness=2, circle_radius=2),
            connection_drawing_spec=self.mp_drawing.DrawingSpec(color=(255, 0, 0), thickness=2)
        )

    def _extract_landmarks(self, results, w, h):
        lm = results.pose_landmarks.landmark

        def get_xy(point):
            return (int(lm[point.value].x * w), int(lm[point.value].y * h))

        P = self.mp_pose.PoseLandmark
        return {
            "l_sh": get_xy(P.LEFT_SHOULDER),
            "r_sh": get_xy(P.RIGHT_SHOULDER),
            "l_hip": get_xy(P.LEFT_HIP),
            "r_hip": get_xy(P.RIGHT_HIP),
            "l_knee": get_xy(P.LEFT_KNEE),
            "r_knee": get_xy(P.RIGHT_KNEE),
            "l_ank": get_xy(P.LEFT_ANKLE),
            "r_ank": get_xy(P.RIGHT_ANKLE),
            "l_ear": get_xy(P.LEFT_EAR),
        }

    def _compute_kinematics(self, lmk):
        left_hip_angle = self.calculate_angle(lmk["l_sh"], lmk["l_hip"], lmk["l_knee"])
        right_hip_angle = self.calculate_angle(lmk["r_sh"], lmk["r_hip"], lmk["r_knee"])
        primary_angle = left_hip_angle  # Base standard reference point

        if primary_angle > self.current_rep_max_rom:
            self.current_rep_max_rom = primary_angle

        return {
            "left_hip_angle": left_hip_angle,
            "right_hip_angle": right_hip_angle,
            "primary_angle": primary_angle,
        }

    def _update_speed_and_phase(self, primary_angle, now):
        if self.prev_left_angle is not None and self.prev_time is not None:
            dt = now - self.prev_time
            self.speed = abs(primary_angle - self.prev_left_angle) / dt if dt > 0 else 0.0
        else:
            self.speed = 0.0
        self.prev_left_angle = primary_angle
        self.prev_time = now

        if self.phase == "MOVING":
            self.current_rep_speeds.append(self.speed)

        target_phase = "MOVING" if self.speed > self.SPEED_THRESHOLD else "HOLDING"
        if target_phase == self.phase:
            self.phase_counter = 0
        else:
            self.phase_counter += 1
            if self.phase_counter >= self.PHASE_SWITCH_FRAMES:
                self.phase = target_phase
                self.phase_counter = 0

    def _warmup_interpolated_thresholds(self, strict_rom_min):
        """Gradual warm-up threshold interpolation matrix."""
        interpolation_factor = min(1.0, self.rep_count / self.WARMUP_REPS)
        return {
            "interpolation_factor": interpolation_factor,
            "asymmetry_thresh": 25.0 - (10.0 * interpolation_factor),       # 25.0 -> 15.0
            "knee_bend_thresh": 130.0 + (20.0 * interpolation_factor),      # 130.0 -> 150.0
            "hunch_mult": 1.08 - (0.02 * interpolation_factor),             # 1.08 -> 1.06
            "target_min_bound": strict_rom_min - 10.0 + (10.0 * interpolation_factor),
        }

    def _draw_vector_lines(self, frame, lmk):
        cv2.line(frame, lmk["l_sh"], lmk["l_hip"], (0, 255, 255), 1)
        cv2.line(frame, lmk["l_hip"], lmk["l_knee"], (0, 255, 255), 1)

    def _is_posture_aligned(self, lmk, primary_angle, thresholds):
        """Advanced multi-joint starting position validation."""
        shoulder_balance = abs(lmk["l_sh"][1] - lmk["r_sh"][1])
        hip_balance = abs(lmk["l_hip"][1] - lmk["r_hip"][1])
        torso_len_l = self.euclidean(lmk["l_sh"], lmk["l_hip"])
        torso_len_r = self.euclidean(lmk["r_sh"], lmk["r_hip"])
        symmetry_ratio = abs(torso_len_l - torso_len_r)

        return (
            (thresholds["target_min_bound"] <= primary_angle <= 180.0) and
            (shoulder_balance < 25) and
            (hip_balance < 25) and
            (symmetry_ratio < 30)
        )

    def _handle_position_validation(self, frame, aligned, now):
        if aligned:
            if self.validation_stable_start is None:
                self.validation_stable_start = now
            elif now - self.validation_stable_start >= self.POSITION_STABILITY_SECONDS:
                self.position_validated = True
                self.current_rep_start_time = now
            cv2.putText(frame, "HOLDING START STABILITY...", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        else:
            self.validation_stable_start = None
            cv2.putText(frame, "ALIGN PROFILE & SYMMETRY TO START", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

    def _detect_compensations(self, frame, lmk, kinematics, thresholds):
        """Expanded clinical compensation inference engine."""
        l_sh, r_sh = lmk["l_sh"], lmk["r_sh"]
        l_hip, r_hip = lmk["l_hip"], lmk["r_hip"]
        l_knee, r_knee = lmk["l_knee"], lmk["r_knee"]
        l_ank, r_ank = lmk["l_ank"], lmk["r_ank"]
        l_ear = lmk["l_ear"]

        # 1. Lateral Shoulder/Pelvis Asymmetry
        asymmetry = abs(kinematics["left_hip_angle"] - kinematics["right_hip_angle"])
        if asymmetry > thresholds["asymmetry_thresh"]:
            self.current_rep_compensations.add("Lateral Asymmetry")
            cv2.putText(frame, "ALERT: Hip Asymmetry", (frame.shape[1] - 350, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

        # 2. Scale-Invariant Hunching Calculation
        avg_vert_torso = (abs(l_sh[1] - l_hip[1]) + abs(r_sh[1] - r_hip[1])) / 2.0
        sh_width = self.euclidean(l_sh, r_sh)
        hunch_idx = avg_vert_torso / sh_width if sh_width > 0 else 0.0
        self._last_hunch_idx = hunch_idx  # used by calibration step
        self._last_sh_width = sh_width

        if self.normal_hunch_index is not None and hunch_idx > self.normal_hunch_index * thresholds["hunch_mult"]:
            self.current_rep_compensations.add("Shoulder Hunching")
            cv2.putText(frame, "ALERT: Cervico-Thoracic Hunching", (frame.shape[1] - 350, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

        # 3. Knee Sagittal Flexion Drift
        left_knee_angle = self.calculate_angle(l_hip, l_knee, l_ank)
        right_knee_angle = self.calculate_angle(r_hip, r_knee, r_ank)
        if left_knee_angle < thresholds["knee_bend_thresh"] or right_knee_angle < thresholds["knee_bend_thresh"]:
            self.current_rep_compensations.add("Knee Flexion Break")
            cv2.putText(frame, "ALERT: Unintended Knee Bending", (frame.shape[1] - 350, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

        # 4. Torso Coronal Lean Break
        torso_center_x = (l_sh[0] + r_sh[0]) / 2.0
        pelvis_center_x = (l_hip[0] + r_hip[0]) / 2.0
        lateral_lean = abs(torso_center_x - pelvis_center_x)
        if lateral_lean > (sh_width * 0.25):
            self.current_rep_compensations.add("Torso Coronal Lean")
            cv2.putText(frame, "ALERT: Torso Coronal Lean", (frame.shape[1] - 350, 130), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

        # 5. Cervical/Neck Posture Forward Shift
        ear_to_shoulder = abs(l_ear[0] - l_sh[0])
        if ear_to_shoulder > (sh_width * 0.4):
            self.current_rep_compensations.add("Forward Head Posture")
            cv2.putText(frame, "ALERT: Forward Head Posture", (frame.shape[1] - 350, 160), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

    def _handle_calibration(self, frame, kinematics, now):
        if not (self.is_calibrating and self.calibration_start_time is not None):
            return

        elapsed = now - self.calibration_start_time
        h, w, _ = frame.shape
        if elapsed < self.CALIBRATION_DELAY:
            cv2.putText(frame, f"CALIBRATING PROFILE: {self.CALIBRATION_DELAY - elapsed:.1f}s", (w // 2 - 150, h // 2), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 0, 0), 2)
            return

        self.normal_hunch_index = getattr(self, "_last_hunch_idx", self.normal_hunch_index)
        self.baseline_max_rom = kinematics["primary_angle"]
        self.baseline_avg_speed = 25.0
        self.is_calibrating = False
        self.calibration_start_time = None
        self.persistent_data["calibration"] = {
            "normal_hunch_index": self.normal_hunch_index,
            "baseline_max_rom": self.baseline_max_rom,
            "baseline_avg_speed": self.baseline_avg_speed,
        }
        self._save_storage()

    def _update_isometric_hold(self, primary_angle, strict_rom_min, strict_hold_duration, now):
        if primary_angle >= strict_rom_min:
            if self.hold_start_time is None:
                self.hold_start_time = now
        else:
            if self.hold_start_time is not None:
                self.total_hold_time += now - self.hold_start_time
                self.hold_start_time = None

        current_hold = (now - self.hold_start_time) if self.hold_start_time else 0.0
        self._current_hold = current_hold  # cached for _finalize_rep
        if current_hold < strict_hold_duration and self.phase == "HOLDING":
            self.current_rep_flaws.add("Insufficent Isometric Hold Duration")

    def _finalize_rep(self, strict_hold_duration, now):
        """Transition management & per-rep evaluation model."""
        current_hold = getattr(self, "_current_hold", 0.0)

        self.rep_count += 1
        avg_speed = sum(self.current_rep_speeds) / len(self.current_rep_speeds) if self.current_rep_speeds else 0.0

        is_rep_correct = (len(self.current_rep_compensations) == 0) and (current_hold >= strict_hold_duration)
        if is_rep_correct:
            self.correct_rep_count += 1

        rep_metrics_payload = {
            "rep_number": self.rep_count,
            "correctness": is_rep_correct,
            "detected_flaws": list(self.current_rep_flaws),
            "hold_duration": round(max(current_hold, self.total_hold_time), 2),
            "range_of_motion": round(self.current_rep_max_rom, 1),
            "movement_speed": round(avg_speed, 1),
            "compensations_detected": list(self.current_rep_compensations),
        }
        self.session_reps_log.append(rep_metrics_payload)

        self._update_fatigue_score()

        # Reset Inter-Rep Local Workspace States
        self.current_rep_flaws = set()
        self.current_rep_compensations = set()
        self.current_rep_max_rom = 0.0
        self.current_rep_speeds = []
        self.current_rep_start_time = now
        self.total_hold_time = 0.0
        if self.hold_start_time is not None:
            self.hold_start_time = now

    def _update_fatigue_score(self):
        """Fatigue modeler logic engine."""
        if self.rep_count > 1 and self.baseline_max_rom > 0:
            rom_drop = max(0.0, (self.baseline_max_rom - self.current_rep_max_rom) / self.baseline_max_rom)
            compensation_penalty = len(self.current_rep_compensations) * 0.15
            self.fatigue_score = min(100.0, (rom_drop * 60.0 + compensation_penalty * 40.0) * 100.0)

            self.fatigue_warnings = []
            if self.fatigue_score > 40.0:
                self.fatigue_warnings.append("Warning: Kinematic Tremor/Compensation climbing. Slow down your transitions.")
            if self.fatigue_score > 70.0:
                self.fatigue_warnings.append("CRITICAL: High Fatigue Metric. Complete the current rep and cease movement sequence.")

    def _draw_hud(self, frame, h):
        cv2.putText(frame, f"REPS: {self.rep_count} | CORRECT: {self.correct_rep_count}", (20, h - 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------
    def finalize_session_data(self, exercise_name):
        """Compiles raw metrics data arrays into an end-of-session database profile payload."""
        with self.lock:
            if not self.session_reps_log:
                return None

            total_reps = len(self.session_reps_log)
            correct_reps = sum(1 for r in self.session_reps_log if r["correctness"])
            accuracy_pct = (correct_reps / total_reps) * 100.0 if total_reps > 0 else 0.0

            avg_rom = sum(r["range_of_motion"] for r in self.session_reps_log) / total_reps
            avg_hold = sum(r["hold_duration"] for r in self.session_reps_log) / total_reps
            avg_speed = sum(r["movement_speed"] for r in self.session_reps_log) / total_reps

            flaw_counts = {}
            comp_counts = {}
            lateral_asymmetry_events = 0

            for r in self.session_reps_log:
                for f in r["detected_flaws"]:
                    flaw_counts[f] = flaw_counts.get(f, 0) + 1
                for c in r["compensations_detected"]:
                    comp_counts[c] = comp_counts.get(c, 0) + 1
                    if c == "Lateral Asymmetry":
                        lateral_asymmetry_events += 1

            most_common_flaw = max(flaw_counts, key=flaw_counts.get) if flaw_counts else "None"
            most_common_comp = max(comp_counts, key=comp_counts.get) if comp_counts else "None"

            symmetry_score = max(0.0, 100.0 - (lateral_asymmetry_events * 12.5))

            recommendation = "Excellent kinematics. Structural posture and target stability thresholds are verified."
            if symmetry_score < 75.0:
                recommendation = "High asymmetric structural drift detected. Focus on keeping your left and right sides level."
            elif self.fatigue_score > 60.0:
                recommendation = "Movement velocity and range of motion degraded significantly toward the end of the session. Increase rest intervals between repetitions."
            elif most_common_comp == "Shoulder Hunching":
                recommendation = "Cervico-thoracic compensation pattern detected. Keep your scapula retracted and shoulders relaxed down away from your neck."

            summary_payload = {
                "timestamp": time.time(),
                "exercise_name": exercise_name,
                "total_reps": total_reps,
                "correct_reps": correct_reps,
                "accuracy_percentage": round(accuracy_pct, 1),
                "average_rom": round(avg_rom, 1),
                "average_hold_time": round(avg_hold, 1),
                "average_movement_speed": round(avg_speed, 1),
                "fatigue_score": round(self.fatigue_score, 1),
                "symmetry_score": round(symmetry_score, 1),
                "most_common_flaw": most_common_flaw,
                "most_common_compensation": most_common_comp,
                "clinical_recommendation": recommendation,
            }

            self.persistent_data["history"].append(summary_payload)
            self._save_storage()
            return summary_payload