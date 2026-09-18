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


# Anchored to this file's own directory rather than left as a bare relative
# filename — otherwise the Flask process and the Streamlit process (each
# with their own AdvancedRehabProcessor instance) end up reading/writing
# two different rehab_storage.json files whenever they're launched from
# different working directories, and silently never see each other's
# calibration/history data.
DEFAULT_STORAGE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rehab_storage.json")


class AdvancedRehabProcessor:
    # --- Tunable constants kept at class scope for clarity / single source of truth ---
    CALIBRATION_DELAY = 3.0
    PHASE_SWITCH_FRAMES = 5
    SPEED_THRESHOLD = 20.0
    WARMUP_REPS = 4
    POSITION_STABILITY_SECONDS = 2.0

    # A rep counts as correct if at least this fraction of its frames
    # matched calibrated form — adjusted from 0.90 to 0.80 so minor wiggles 
    # don't completely invalidate an otherwise clean repetition.
    MIN_FORM_MATCH_RATIO = 0.80

    # Most exercises here hold their target position near full extension —
    # the tracked shoulder-hip-knee angle is HIGH at the held posture (e.g.
    # Glute Bridge's hip lift, Bird Dog's reach). For those, "in position"
    # correctly means angle >= the target ROM value.
    FLEXION_HOLD_EXERCISES = {"Standing Hip Hinge"}

    # --- 3D biomechanics constants ---

    # Minimum MediaPipe visibility * presence confidence required before a
    # landmark is trusted for compensation detection. Below this threshold
    # the landmark is considered unreliable and any compensation that
    # depends on it is skipped rather than producing a false positive.
    VISIBILITY_THRESHOLD = 0.5

    # Temporal hysteresis: require this many consecutive frames of raw
    # detection before a compensation is confirmed active, and this many
    # consecutive clean frames before it clears. Prevents single-frame
    # MediaPipe jitter from flashing false positives.
    COMP_ACTIVATION_FRAMES = 4
    COMP_DEACTIVATION_FRAMES = 4

    # Number of frames to smooth the camera orientation vote across.
    ORIENTATION_SMOOTH_WINDOW = 15

    # Lateral trunk lean threshold in degrees (3D coronal-plane angle).
    TORSO_LATERAL_LEAN_DEG = 12.0

    def _init_mediapipe(self):
        if hasattr(self, "pose") and self.pose is not None:
            return
        mp_obj = None
        solutions_obj = None
        try:
            import mediapipe as mp_obj
            try:
                from mediapipe import solutions as solutions_obj
            except ImportError:
                solutions_obj = getattr(mp_obj, "solutions", None)
        except Exception:
            mp_obj = None

        if solutions_obj is None or not hasattr(solutions_obj, "pose"):
            raise RuntimeError(
                "MediaPipe Pose Solutions API is not available on this Python runtime version. "
                "MediaPipe requires Python 3.10 or 3.11. "
                "Ensure your deployment uses Python 3.10 (set PYTHON_VERSION=3.10.13 or runtime.txt)."
            )

        self.mp_drawing = solutions_obj.drawing_utils
        self.mp_pose = solutions_obj.pose
        self.pose = self.mp_pose.Pose(
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )

    def __init__(self, storage_path=DEFAULT_STORAGE_PATH):
        self.lock = threading.Lock()
        self.storage_path = storage_path
        self._init_mediapipe()

        # --- State Configuration & Telemetry Stores ---
        # normal_hunch_index / baseline_max_rom / baseline_avg_speed are the
        # patient's saved calibration profile — they live outside
        # _init_transient_state() (below) because a session reset/restart
        # must NOT wipe them; only _load_storage() below should set them.
        self.normal_hunch_index = None
        self.baseline_max_rom = 0.0
        self.baseline_avg_speed = 0.0

        # Calibrated ear-shoulder-hip alignment angle, captured at the SAME
        # moment as normal_hunch_index. Unlike normal_hunch_index (a
        # shoulder-hip vertical/width ratio, which is confounded by how far
        # the torso has hinged forward), this angle stays close to its
        # calibrated value for a rigid, straight-backed torso no matter how
        # deep the hinge is — because ear, shoulder and hip all rotate
        # together as one unit when the back is straight. That makes it the
        # metric that can actually detect back-rounding/shoulder-hunching
        # DURING a flexion-hold exercise like Standing Hip Hinge, where the
        # old ratio-based check can structurally never fire (see
        # _detect_compensations below).
        self.normal_spine_angle = None

        self._init_transient_state()

        # Load Persistent Profiles
        self.persistent_data = self._load_storage()
        calibration = self.persistent_data.get("calibration") or {}
        self.normal_hunch_index = calibration.get("normal_hunch_index")
        self.normal_spine_angle = calibration.get("normal_spine_angle")
        self.baseline_max_rom = calibration.get("baseline_max_rom", 0.0)
        self.baseline_avg_speed = calibration.get("baseline_avg_speed", 0.0)

    def _init_transient_state(self):
        """Set/reset every piece of state that belongs to a single session
        attempt (rep counts, in-progress calibration timer, fatigue
        telemetry, per-rep trackers, compensation hysteresis, ...).

        Deliberately excludes self.persistent_data and the calibration
        profile (normal_hunch_index / baseline_max_rom / baseline_avg_speed)
        — those represent the patient's saved baseline across sessions and
        must survive a reset. Called once from __init__, and again by
        reset_session()/finalize_session_data() so a restarted or newly
        started session never inherits telemetry from a prior attempt.
        """
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

        # Per-frame (not per-rep) form-match status. True = this exact
        # frame's posture matches the calibrated form; False = it's
        # currently deviating. Used to color the live skeleton overlay and
        # reported to the frontend as telemetry["form_status"]. 
        self.frame_form_ok = True
        self.current_frame_compensations = set()

        # Fatigue Engine State (fatigue readings are per-session; the ROM/
        # speed *baselines* they're measured against are calibration
        # profile data and are NOT reset here — see docstring above)
        self.fatigue_score = 0.0
        self.fatigue_warnings = []

        # High-Fidelity Metrics Trackers
        self.current_rep_max_rom = 0.0
        self.current_rep_min_rom = 360.0
        self.current_rep_speeds = []
        self.current_rep_start_time = None
        self._last_achieved_rom = 0.0

        # Frame counting workspace variables
        self.current_rep_frame_count = 0
        self.current_rep_bad_frame_count = 0
        self.current_rep_reached_target = False

        # --- 3D Biomechanics State ---
        self.camera_orientation = "FRONT"
        self._orientation_history = []

        # Temporal hysteresis state for each compensation type.
        self._comp_activation_counts = {}
        self._comp_deactivation_counts = {}
        self._active_temporal_comps = set()

        # Workspace cross-method communication variables
        self._filtered_deviation_active = False

    def reset_session(self):
        """Public entry point for the server to call when the patient
        restarts or abandons a session (e.g. a Socket.IO "restart_session"
        event) — throws away all in-progress rep counts, calibration
        timers, and fatigue telemetry from the unwanted attempt without
        touching the saved calibration profile or session history.
        Safe to call at any point in process_single_frame's lifecycle.
        """
        with self.lock:
            self._init_transient_state()

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
        """2D joint angle at vertex b formed by rays b->a and b->c."""
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

    def calculate_angle_3d(self, a, b, c):
        """3D joint angle at vertex b formed by rays b->a and b->c."""
        vec1 = (a[0] - b[0], a[1] - b[1], a[2] - b[2])
        vec2 = (c[0] - b[0], c[1] - b[1], c[2] - b[2])
        dot = vec1[0] * vec2[0] + vec1[1] * vec2[1] + vec1[2] * vec2[2]
        mag1 = math.sqrt(vec1[0] ** 2 + vec1[1] ** 2 + vec1[2] ** 2)
        mag2 = math.sqrt(vec2[0] ** 2 + vec2[1] ** 2 + vec2[2] ** 2)
        if mag1 > 0 and mag2 > 0:
            cos_val = dot / (mag1 * mag2)
            cos_val = max(-1.0, min(1.0, cos_val))
            return math.degrees(math.acos(cos_val))
        return 0.0

    def euclidean(self, a, b):
        return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)

    # ------------------------------------------------------------------
    # Visibility / confidence helpers (3D biomechanics)
    # ------------------------------------------------------------------
    def _landmarks_visible(self, visibility_dict, *landmark_names):
        for name in landmark_names:
            if visibility_dict.get(name, 0.0) < self.VISIBILITY_THRESHOLD:
                return False
        return True

    # ------------------------------------------------------------------
    # Camera orientation detection (3D biomechanics)
    # ------------------------------------------------------------------
    def _detect_camera_orientation(self, world):
        if world is None:
            return

        l_sh, r_sh = world["l_sh"], world["r_sh"]
        l_hip, r_hip = world["l_hip"], world["r_hip"]

        sh_x_spread = abs(l_sh[0] - r_sh[0])
        sh_z_spread = abs(l_sh[2] - r_sh[2])
        hip_x_spread = abs(l_hip[0] - r_hip[0])
        hip_z_spread = abs(l_hip[2] - r_hip[2])

        avg_x = (sh_x_spread + hip_x_spread) / 2.0
        avg_z = (sh_z_spread + hip_z_spread) / 2.0
        ratio = avg_z / (avg_x + 1e-6)

        if ratio < 0.5:
            orientation = "FRONT"
        elif ratio > 2.0:
            orientation = "SIDE"
        else:
            orientation = "OBLIQUE"

        self._orientation_history.append(orientation)
        if len(self._orientation_history) > self.ORIENTATION_SMOOTH_WINDOW:
            self._orientation_history.pop(0)

        counts = {}
        for o in self._orientation_history:
            counts[o] = counts.get(o, 0) + 1
        self.camera_orientation = max(counts, key=counts.get)

    # ------------------------------------------------------------------
    # Temporal smoothing for compensation detection
    # ------------------------------------------------------------------
    def _update_compensation_temporal(self, comp_name, detected_this_frame):
        if detected_this_frame:
            self._comp_activation_counts[comp_name] = (
                self._comp_activation_counts.get(comp_name, 0) + 1
            )
            self._comp_deactivation_counts[comp_name] = max(
                0, self._comp_deactivation_counts.get(comp_name, 0) - 1
            )
            if self._comp_activation_counts[comp_name] >= self.COMP_ACTIVATION_FRAMES:
                self._active_temporal_comps.add(comp_name)
                self._comp_activation_counts[comp_name] = 0
                self._comp_deactivation_counts[comp_name] = 0
        else:
            self._comp_deactivation_counts[comp_name] = (
                self._comp_deactivation_counts.get(comp_name, 0) + 1
            )
            self._comp_activation_counts[comp_name] = max(
                0, self._comp_activation_counts.get(comp_name, 0) - 1
            )
            if self._comp_deactivation_counts[comp_name] >= self.COMP_DEACTIVATION_FRAMES:
                self._active_temporal_comps.discard(comp_name)
                self._comp_deactivation_counts[comp_name] = 0
                self._comp_activation_counts[comp_name] = 0

        return comp_name in self._active_temporal_comps

    # ------------------------------------------------------------------
    # 3D torso lateral lean calculation
    # ------------------------------------------------------------------
    def _compute_3d_lateral_lean(self, world):
        pelvis_cx = (world["l_hip"][0] + world["r_hip"][0]) / 2.0
        pelvis_cy = (world["l_hip"][1] + world["r_hip"][1]) / 2.0
        pelvis_cz = (world["l_hip"][2] + world["r_hip"][2]) / 2.0

        sh_cx = (world["l_sh"][0] + world["r_sh"][0]) / 2.0
        sh_cy = (world["l_sh"][1] + world["r_sh"][1]) / 2.0
        sh_cz = (world["l_sh"][2] + world["r_sh"][2]) / 2.0

        torso_x = sh_cx - pelvis_cx
        torso_y = sh_cy - pelvis_cy
        torso_z = sh_cz - pelvis_cz

        torso_length = math.sqrt(torso_x ** 2 + torso_y ** 2 + torso_z ** 2)
        if torso_length < 1e-6:
            return 0.0

        lateral_ratio = abs(torso_x) / torso_length
        lateral_ratio = min(1.0, lateral_ratio)
        return math.degrees(math.asin(lateral_ratio))

    # ------------------------------------------------------------------
    # Reference animation (pure data/image generation — no UI framework)
    # ------------------------------------------------------------------
    def generate_animated_reference(self, exercise_name, h, w):
        canvas = cv2.bitwise_not(cv2.getStructuringElement(cv2.MORPH_RECT, (w, h))) * 0
        t = time.time() * 2.0
        oscillation = (math.sin(t) + 1.0) / 2.0

        center_x, center_y = w // 2, h // 2
        color = (0, 165, 255)

        if exercise_name == "Glute Bridge":
            lift_offset = int(35 * oscillation)
            cv2.circle(canvas, (center_x - 70, center_y + 20), 18, color, -1)
            cv2.line(canvas, (center_x - 70, center_y + 20), (center_x, center_y + 20 - int(lift_offset * 0.4)), color, 4)
            cv2.line(canvas, (center_x, center_y + 20 - int(lift_offset * 0.4)), (center_x + 50, center_y + 20), color, 4)
            cv2.line(canvas, (center_x + 50, center_y + 20), (center_x + 50, center_y + 70), color, 4)
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
        elif exercise_name == "Standing Posture Hold":
            sway = int(4 * math.sin(t * 0.5))
            cv2.circle(canvas, (center_x + sway, center_y - 90), 18, color, -1)
            cv2.line(canvas, (center_x + sway, center_y - 70), (center_x + sway, center_y + 20), color, 4)
            cv2.line(canvas, (center_x + sway, center_y + 20), (center_x + sway, center_y + 90), color, 4)
        else:
            hinge_offset = int(45 * oscillation)
            cv2.circle(canvas, (center_x, center_y - 90), 18, color, -1)
            cv2.line(canvas, (center_x, center_y - 70), (center_x + hinge_offset, center_y - 10), color, 4)
            cv2.line(canvas, (center_x + hinge_offset, center_y - 10), (center_x, center_y + 20), color, 4)
            cv2.line(canvas, (center_x, center_y + 20), (center_x, center_y + 80), color, 4)

        return canvas

    # ------------------------------------------------------------------
    # Main per-frame entrypoint
    # ------------------------------------------------------------------
    def process_single_frame(self, frame, exercise_name, target_hold_time, strict_hold_duration, strict_rom_min, calibration_session=False):
        with self.lock:
            h, w, _ = frame.shape
            results = self._run_pose_estimation(frame)

            telemetry = self._base_telemetry()

            if not results.pose_landmarks:
                return frame, telemetry

            landmarks = self._extract_landmarks(results, w, h)

            self._detect_camera_orientation(landmarks.get("world"))

            kinematics = self._compute_kinematics(landmarks)
            now = time.time()
            
            self._update_speed_and_phase(kinematics["primary_angle"], now)

            # Reset frame pools when leaving the starting hold to begin a rep
            if self.last_phase == "HOLDING" and self.phase == "MOVING" and not self.current_rep_reached_target:
                self.current_rep_frame_count = 0
                self.current_rep_bad_frame_count = 0

            thresholds = self._warmup_interpolated_thresholds(strict_rom_min)

            self._update_hunch_index_cache(landmarks)

            if not self.position_validated:
                self.frame_form_ok = True
                self._draw_skeleton(frame, results, self.frame_form_ok)
                self._draw_vector_lines(frame, landmarks, self.frame_form_ok)
                
                aligned = self._is_posture_aligned(exercise_name, landmarks, kinematics["primary_angle"], thresholds)
                
                self._handle_position_validation(frame, aligned, now)
                telemetry.update(self._base_telemetry())
                return frame, telemetry

            self._detect_compensations(frame, landmarks, kinematics, thresholds, exercise_name)
            if calibration_session:
                self.frame_form_ok = True
            self._draw_skeleton(frame, results, self.frame_form_ok)
            self._draw_vector_lines(frame, landmarks, self.frame_form_ok)

            # Tally this frame toward the current rep's form-match ratio.
            if not calibration_session:
                self.current_rep_frame_count += 1
                # Increment the bad frame count using the decoupled filtered active deviation status, 
                # ensuring camera noise doesn't corrupt the actual repetition evaluation scoring metrics.
                if self._filtered_deviation_active:
                    self.current_rep_bad_frame_count += 1

            self._update_isometric_hold(exercise_name, kinematics["primary_angle"], strict_rom_min, strict_hold_duration, now)

            # Rep now finalizes when they come to a stop outside the target zone 
            # (meaning they have completed the eccentric return journey).
            in_target_now = self._is_in_target_position(exercise_name, kinematics["primary_angle"], strict_rom_min)
            if self.last_phase == "MOVING" and self.phase == "HOLDING" and self.current_rep_reached_target and not in_target_now:
                self._finalize_rep(exercise_name, strict_hold_duration, now, calibration_session)

            self._handle_calibration(frame, exercise_name, landmarks, kinematics, now)

            self.last_phase = self.phase

            telemetry.update(self._base_telemetry())
            self._draw_hud(frame, h)
            return frame, telemetry

    # ------------------------------------------------------------------
    # process_single_frame helpers (internal only)
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
            "rom": round(getattr(self, "_last_achieved_rom", self.current_rep_max_rom), 1),
            "movement_speed": round(self.speed, 1),
            "hold_time": round(getattr(self, "_current_hold", 0.0), 1),
            "warmup_active": self.rep_count < self.WARMUP_REPS,
            "warmup_reps_remaining": max(0, self.WARMUP_REPS - self.rep_count),
            "form_status": "good" if self.frame_form_ok else "bad",
            "camera_orientation": self.camera_orientation,
        }

    def _draw_skeleton(self, frame, results, form_ok=True):
        line_color = (255, 0, 0) if form_ok else (0, 0, 255)
        self.mp_drawing.draw_landmarks(
            frame, results.pose_landmarks, self.mp_pose.POSE_CONNECTIONS,
            landmark_drawing_spec=self.mp_drawing.DrawingSpec(color=(0, 255, 0), thickness=2, circle_radius=2),
            connection_drawing_spec=self.mp_drawing.DrawingSpec(color=line_color, thickness=2)
        )

    def _extract_landmarks(self, results, w, h):
        lm = results.pose_landmarks.landmark

        def get_xy(point):
            return (int(lm[point.value].x * w), int(lm[point.value].y * h))

        def get_visibility(point):
            landmark = lm[point.value]
            vis = getattr(landmark, 'visibility', 0.0)
            pres = getattr(landmark, 'presence', vis)
            return min(vis, pres)

        P = self.mp_pose.PoseLandmark

        landmarks = {
            "l_sh": get_xy(P.LEFT_SHOULDER),
            "r_sh": get_xy(P.RIGHT_SHOULDER),
            "l_hip": get_xy(P.LEFT_HIP),
            "r_hip": get_xy(P.RIGHT_HIP),
            "l_knee": get_xy(P.LEFT_KNEE),
            "r_knee": get_xy(P.RIGHT_KNEE),
            "l_ank": get_xy(P.LEFT_ANKLE),
            "r_ank": get_xy(P.RIGHT_ANKLE),
            "l_ear": get_xy(P.LEFT_EAR),
            "visibility": {
                "l_sh": get_visibility(P.LEFT_SHOULDER),
                "r_sh": get_visibility(P.RIGHT_SHOULDER),
                "l_hip": get_visibility(P.LEFT_HIP),
                "r_hip": get_visibility(P.RIGHT_HIP),
                "l_knee": get_visibility(P.LEFT_KNEE),
                "r_knee": get_visibility(P.RIGHT_KNEE),
                "l_ank": get_visibility(P.LEFT_ANKLE),
                "r_ank": get_visibility(P.RIGHT_ANKLE),
                "l_ear": get_visibility(P.LEFT_EAR),
            },
        }

        if results.pose_world_landmarks:
            wlm = results.pose_world_landmarks.landmark

            def get_xyz(point):
                p = wlm[point.value]
                return (p.x, p.y, p.z)

            landmarks["world"] = {
                "l_sh": get_xyz(P.LEFT_SHOULDER),
                "r_sh": get_xyz(P.RIGHT_SHOULDER),
                "l_hip": get_xyz(P.LEFT_HIP),
                "r_hip": get_xyz(P.RIGHT_HIP),
                "l_knee": get_xyz(P.LEFT_KNEE),
                "r_knee": get_xyz(P.RIGHT_KNEE),
                "l_ank": get_xyz(P.LEFT_ANKLE),
                "r_ank": get_xyz(P.RIGHT_ANKLE),
                "l_ear": get_xyz(P.LEFT_EAR),
            }
        else:
            landmarks["world"] = None

        return landmarks

    def _compute_kinematics(self, lmk):
        world = lmk.get("world")
        vis = lmk.get("visibility", {})

        use_3d = (
            world is not None
            and self._landmarks_visible(
                vis, "l_sh", "l_hip", "l_knee", "r_sh", "r_hip", "r_knee"
            )
        )

        if use_3d:
            left_hip_angle = self.calculate_angle_3d(
                world["l_sh"], world["l_hip"], world["l_knee"]
            )
            right_hip_angle = self.calculate_angle_3d(
                world["r_sh"], world["r_hip"], world["r_knee"]
            )
        else:
            left_hip_angle = self.calculate_angle(
                lmk["l_sh"], lmk["l_hip"], lmk["l_knee"]
            )
            right_hip_angle = self.calculate_angle(
                lmk["r_sh"], lmk["r_hip"], lmk["r_knee"]
            )

        primary_angle = left_hip_angle

        if primary_angle > self.current_rep_max_rom:
            self.current_rep_max_rom = primary_angle
        if primary_angle < getattr(self, "current_rep_min_rom", 360.0):
            self.current_rep_min_rom = primary_angle

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
        interpolation_factor = min(1.0, self.rep_count / self.WARMUP_REPS)
        return {
            "interpolation_factor": interpolation_factor,
            "asymmetry_thresh": 25.0 - (10.0 * interpolation_factor),
            "knee_bend_thresh": 130.0 + (20.0 * interpolation_factor),
            "hunch_mult": 1.08 - (0.02 * interpolation_factor),
            "target_min_bound": strict_rom_min - 10.0 + (10.0 * interpolation_factor),
            "target_max_bound_flexion": strict_rom_min + 10.0 - (10.0 * interpolation_factor),
        }

    def _draw_vector_lines(self, frame, lmk, form_ok=True):
        line_color = (255, 0, 0) if form_ok else (0, 0, 255)
        cv2.line(frame, lmk["l_sh"], lmk["l_hip"], line_color, 2)
        cv2.line(frame, lmk["l_hip"], lmk["l_knee"], line_color, 2)

    def _is_posture_aligned(self, exercise_name, lmk, primary_angle, thresholds):
        """Validates starting position layout based on active camera perspective."""
        if exercise_name in self.FLEXION_HOLD_EXERCISES:
            # FIX: Flexion-hold exercises (e.g. Standing Hip Hinge) start from an upright, 
            # fully extended posture, independent of the deep hinge target angle.
            angle_ok = primary_angle >= 160.0
        else:
            angle_ok = thresholds["target_min_bound"] <= primary_angle <= 180.0

        # If standing sideways, bypass frontal bilateral symmetry requirements
        if self.camera_orientation == "SIDE":
            # For profile view, we just need the primary joint angle to be stable/correct
            return angle_ok

        # Enforce strict bilateral balance ONLY when facing frontways
        shoulder_balance = abs(lmk["l_sh"][1] - lmk["r_sh"][1])
        hip_balance = abs(lmk["l_hip"][1] - lmk["r_hip"][1])
        torso_len_l = self.euclidean(lmk["l_sh"], lmk["l_hip"])
        torso_len_r = self.euclidean(lmk["r_sh"], lmk["r_hip"])
        symmetry_ratio = abs(torso_len_l - torso_len_r)

        return (
            angle_ok and
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

    def _handle_calibration(self, frame, exercise_name, lmk, kinematics, now):
        """Auto-capture a calibration profile once the patient has held a
        validated position steady for CALIBRATION_DELAY seconds.
        No-op unless is_calibrating is True.
        """
        if not self.is_calibrating:
            return
            
        if self.calibration_start_time is None:
            self.calibration_start_time = now
            return
            
        elapsed = now - self.calibration_start_time
        remaining = max(0.0, self.CALIBRATION_DELAY - elapsed)
        
        cv2.putText(
            frame, f"CALIBRATING... {remaining:.1f}s", (20, 80),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2
        )
        
        if elapsed >= self.CALIBRATION_DELAY:
            self.normal_hunch_index = self._last_hunch_idx
            self.normal_spine_angle = self._capture_spine_angle(lmk)

            # FIX: Flexion-hold exercises (e.g. Standing Hip Hinge) hold
            # their target position at a LOW angle — the deep hinge — so
            # the meaningful calibration baseline is current_rep_min_rom,
            # not current_rep_max_rom. current_rep_max_rom for these
            # exercises just reflects the upright starting stance (~180),
            # which is unrelated to the depth the patient can achieve, and
            # was previously stored as "baseline_max_rom", causing bogus
            # fatigue/ROM-drop readings (achieved_rom is compared against
            # it and is itself computed from current_rep_min_rom for these
            # exercises — see _finalize_rep).
            if exercise_name in self.FLEXION_HOLD_EXERCISES:
                calibrated_rom = self.current_rep_min_rom
                rom_captured = calibrated_rom < 360.0
            else:
                calibrated_rom = self.current_rep_max_rom
                rom_captured = calibrated_rom > 0

            if rom_captured:
                self.baseline_max_rom = calibrated_rom

            self.baseline_avg_speed = self.baseline_avg_speed or 25.0
            
            self.is_calibrating = False
            self.calibration_start_time = None
            
            self.persistent_data["calibration"] = {
                "normal_hunch_index": self.normal_hunch_index,
                "normal_spine_angle": self.normal_spine_angle,
                "baseline_max_rom": self.baseline_max_rom,
                "baseline_avg_speed": self.baseline_avg_speed,
            }
            self._save_storage()

    def _capture_spine_angle(self, lmk):
        """Ear-shoulder-hip angle at the shoulder vertex, 3D where possible.

        Near 180 degrees means ear/shoulder/hip are roughly colinear (a
        straight, neutral back). This is what we compare against later to
        catch shoulder/back rounding — see _detect_compensations.
        """
        vis = lmk.get("visibility", {})
        world = lmk.get("world")
        if world is not None and self._landmarks_visible(vis, "l_ear", "l_sh", "l_hip"):
            return self.calculate_angle_3d(world["l_ear"], world["l_sh"], world["l_hip"])
        return self.calculate_angle(lmk["l_ear"], lmk["l_sh"], lmk["l_hip"])

    def _update_hunch_index_cache(self, lmk):
        l_sh, r_sh = lmk["l_sh"], lmk["r_sh"]
        l_hip, r_hip = lmk["l_hip"], lmk["r_hip"]
        avg_vert_torso = (abs(l_sh[1] - l_hip[1]) + abs(r_sh[1] - r_hip[1])) / 2.0
        sh_width = self.euclidean(l_sh, r_sh)
        self._last_hunch_idx = avg_vert_torso / sh_width if sh_width > 0 else 0.0
        self._last_sh_width = sh_width

    def _detect_compensations(self, frame, lmk, kinematics, thresholds, exercise_name=None):
        l_sh, r_sh = lmk["l_sh"], lmk["r_sh"]
        l_hip, r_hip = lmk["l_hip"], lmk["r_hip"]
        l_knee, r_knee = lmk["l_knee"], lmk["r_knee"]
        l_ank, r_ank = lmk["l_ank"], lmk["r_ank"]
        l_ear = lmk["l_ear"]
        vis = lmk.get("visibility", {})
        world = lmk.get("world")

        self.current_frame_compensations = set()
        sh_width = self._last_sh_width

        # 1. Lateral Shoulder/Pelvis Asymmetry
        can_check_asymmetry = self._landmarks_visible(
            vis, "l_hip", "r_hip", "l_knee", "r_knee", "l_sh", "r_sh"
        )
        raw_asymmetry = False
        if can_check_asymmetry:
            asymmetry = abs(kinematics["left_hip_angle"] - kinematics["right_hip_angle"])
            effective_thresh = thresholds["asymmetry_thresh"]
            if self.camera_orientation == "SIDE":
                effective_thresh *= 1.5
            raw_asymmetry = asymmetry > effective_thresh
            asym_active = self._update_compensation_temporal("Lateral Asymmetry", raw_asymmetry)
        else:
            asym_active = "Lateral Asymmetry" in self._active_temporal_comps

        if asym_active:
            self.current_rep_compensations.add("Lateral Asymmetry")
            cv2.putText(frame, "ALERT: Hip Asymmetry", (frame.shape[1] - 350, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

        # 2. Shoulder Hunching
        #
        # NOTE: for FLEXION_HOLD_EXERCISES (e.g. Standing Hip Hinge), the
        # old normal_hunch_index ratio check can never fire. That ratio is
        # (vertical shoulder-hip pixel distance / shoulder width), captured
        # once while standing upright, and it only flags when the ratio
        # rises ABOVE that baseline. But hinging forward — good form or
        # bad — always shrinks that vertical span as the torso tips toward
        # horizontal, so the ratio only ever goes down during the exercise,
        # never up. Rounding the back makes it shrink further, not less.
        # Structurally, "bad form" can't trip a "greater than" check here.
        #
        # Instead, for these exercises we track the ear-shoulder-hip angle
        # (see _capture_spine_angle) against its calibrated straight-back
        # baseline. That angle stays near its calibrated value regardless
        # of hinge depth as long as the back stays straight, since ear,
        # shoulder and hip rotate together as one rigid unit — it only
        # drops when the shoulders/upper back round forward relative to
        # the hips, which is exactly the compensation we want to catch.
        raw_hunching = False
        if exercise_name in self.FLEXION_HOLD_EXERCISES:
            if self._landmarks_visible(vis, "l_ear", "l_sh", "l_hip") and self.normal_spine_angle is not None:
                spine_angle = self._capture_spine_angle(lmk)
                # Allow a few degrees of natural wobble before flagging;
                # tightens slightly across warm-up like the other thresholds.
                spine_angle_slack = 15.0 - (5.0 * thresholds["interpolation_factor"])
                raw_hunching = spine_angle < (self.normal_spine_angle - spine_angle_slack)
                hunch_active = self._update_compensation_temporal("Shoulder Hunching", raw_hunching)
            else:
                hunch_active = "Shoulder Hunching" in self._active_temporal_comps
        elif self._landmarks_visible(vis, "l_sh", "r_sh", "l_hip", "r_hip"):
            hunch_idx = self._last_hunch_idx
            raw_hunching = self.normal_hunch_index is not None and hunch_idx > self.normal_hunch_index * thresholds["hunch_mult"]
            hunch_active = self._update_compensation_temporal("Shoulder Hunching", raw_hunching)
        else:
            hunch_active = "Shoulder Hunching" in self._active_temporal_comps

        if hunch_active:
            self.current_rep_compensations.add("Shoulder Hunching")
            cv2.putText(frame, "ALERT: Cervico-Thoracic Hunching", (frame.shape[1] - 350, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

        # 3. Knee Sagittal Flexion Drift
        #
        # Use the 3D world-landmark angle when it's available, same as the
        # hip angle in _compute_kinematics. A 2D pixel-plane angle badly
        # under-detects this compensation from a front-facing camera: knees
        # drifting forward during a hinge move mostly toward/away from the
        # camera (the depth/z axis), which barely shifts the x/y projection
        # even when the real 3D knee angle has changed substantially.
        raw_knee_flex = False
        if self._landmarks_visible(vis, "l_hip", "l_knee", "l_ank", "r_hip", "r_knee", "r_ank"):
            if world is not None:
                left_knee_angle = self.calculate_angle_3d(world["l_hip"], world["l_knee"], world["l_ank"])
                right_knee_angle = self.calculate_angle_3d(world["r_hip"], world["r_knee"], world["r_ank"])
            else:
                left_knee_angle = self.calculate_angle(l_hip, l_knee, l_ank)
                right_knee_angle = self.calculate_angle(r_hip, r_knee, r_ank)
            raw_knee_flex = left_knee_angle < thresholds["knee_bend_thresh"] or right_knee_angle < thresholds["knee_bend_thresh"]
            knee_active = self._update_compensation_temporal("Knee Flexion Break", raw_knee_flex)
        else:
            knee_active = "Knee Flexion Break" in self._active_temporal_comps

        if knee_active:
            self.current_rep_compensations.add("Knee Flexion Break")
            cv2.putText(frame, "ALERT: Unintended Knee Bending", (frame.shape[1] - 350, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

        # 4. Torso Lateral Lean (3D biomechanical detection)
        raw_torso_lean = False
        if self._landmarks_visible(vis, "l_sh", "r_sh", "l_hip", "r_hip"):
            if world is not None:
                torso_lean_deg = self._compute_3d_lateral_lean(world)
                raw_torso_lean = torso_lean_deg > self.TORSO_LATERAL_LEAN_DEG
            else:
                if self.camera_orientation != "SIDE":
                    torso_center_x = (l_sh[0] + r_sh[0]) / 2.0
                    pelvis_center_x = (l_hip[0] + r_hip[0]) / 2.0
                    lateral_lean = abs(torso_center_x - pelvis_center_x)
                    raw_torso_lean = lateral_lean > (sh_width * 0.25)
                else:
                    raw_torso_lean = False
            lean_active = self._update_compensation_temporal("Torso Coronal Lean", raw_torso_lean)
        else:
            lean_active = "Torso Coronal Lean" in self._active_temporal_comps

        if lean_active:
            self.current_rep_compensations.add("Torso Coronal Lean")
            cv2.putText(frame, "ALERT: Torso Lateral Lean", (frame.shape[1] - 350, 130), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

        # 5. Cervical/Neck Posture Forward Shift
        raw_fwd_head = False
        if self._landmarks_visible(vis, "l_ear", "l_sh"):
            ear_to_shoulder = abs(l_ear[0] - l_sh[0])
            raw_fwd_head = ear_to_shoulder > (sh_width * 0.4)
            head_active = self._update_compensation_temporal("Forward Head Posture", raw_fwd_head)
        else:
            head_active = "Forward Head Posture" in self._active_temporal_comps

        if head_active:
            self.current_rep_compensations.add("Forward Head Posture")
            cv2.putText(frame, "ALERT: Forward Head Posture", (frame.shape[1] - 350, 160), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

        # --- RE-ENGINEERED FEEDBACK AND GRADING ROUTINES ---
        # 1. Check RAW frame status instantly for highly responsive visual red lines
        if raw_asymmetry: self.current_frame_compensations.add("Lateral Asymmetry")
        if raw_hunching: self.current_frame_compensations.add("Shoulder Hunching")
        if raw_knee_flex: self.current_frame_compensations.add("Knee Flexion Break")
        if raw_torso_lean: self.current_frame_compensations.add("Torso Coronal Lean")
        if raw_fwd_head: self.current_frame_compensations.add("Forward Head Posture")

        # Visual overlay status turns bad instantly if any raw deviation occurs on this frame
        self.frame_form_ok = (len(self.current_frame_compensations) == 0) or self.is_calibrating

        # 2. Track sustained/filtered deviations separately so minor single-frame wobbles don't fail reps
        self._filtered_deviation_active = (asym_active or hunch_active or knee_active or lean_active or head_active)

    def _is_in_target_position(self, exercise_name, primary_angle, target_angle):
        if exercise_name in self.FLEXION_HOLD_EXERCISES:
            return primary_angle <= target_angle
        return primary_angle >= target_angle

    def _update_isometric_hold(self, exercise_name, primary_angle, strict_rom_min, strict_hold_duration, now):
        in_target = self._is_in_target_position(exercise_name, primary_angle, strict_rom_min)

        if in_target:
            self.current_rep_reached_target = True

        is_actually_holding = in_target and self.phase == "HOLDING"
        if is_actually_holding:
            if self.hold_start_time is None:
                self.hold_start_time = now
        else:
            if self.hold_start_time is not None:
                self.total_hold_time += now - self.hold_start_time
                self.hold_start_time = None

        current_hold = (now - self.hold_start_time) if self.hold_start_time else 0.0
        self._current_hold = current_hold
        if current_hold < strict_hold_duration and self.phase == "HOLDING":
            self.current_rep_flaws.add("Insufficent Isometric Hold Duration")

    def _reset_rep_state(self, now):
        self.current_rep_flaws = set()
        self.current_rep_compensations = set()
        self.current_rep_max_rom = 0.0
        self.current_rep_min_rom = 360.0
        self.current_rep_speeds = []
        self.current_rep_start_time = now
        self.total_hold_time = 0.0
        self.current_rep_frame_count = 0
        self.current_rep_bad_frame_count = 0
        self.current_rep_reached_target = False
        if self.hold_start_time is not None:
            self.hold_start_time = now

    def _finalize_rep(self, exercise_name, strict_hold_duration, now, calibration_session=False):
        """Transition management & per-rep evaluation model."""
        rom_excursion = self.current_rep_max_rom - getattr(self, "current_rep_min_rom", 0.0)

        if rom_excursion < 15.0:
            self._reset_rep_state(now)
            return

        current_hold = getattr(self, "_current_hold", 0.0)
        effective_hold = max(current_hold, self.total_hold_time)

        self.rep_count += 1

        if calibration_session:
            self._reset_rep_state(now)
            return

        avg_speed = sum(self.current_rep_speeds) / len(self.current_rep_speeds) if self.current_rep_speeds else 0.0

        form_match_ratio = (
            1.0 - (self.current_rep_bad_frame_count / self.current_rep_frame_count)
            if self.current_rep_frame_count > 0 else 1.0
        )
        is_rep_correct = (form_match_ratio >= self.MIN_FORM_MATCH_RATIO) and (effective_hold >= strict_hold_duration)
        if is_rep_correct:
            self.correct_rep_count += 1

        # DYNAMIC ROM EVALUATION
        achieved_rom = (
            self.current_rep_min_rom 
            if exercise_name in self.FLEXION_HOLD_EXERCISES 
            else self.current_rep_max_rom
        )
        self._last_achieved_rom = achieved_rom 

        rep_metrics_payload = {
            "rep_number": self.rep_count,
            "correctness": is_rep_correct,
            "detected_flaws": list(self.current_rep_flaws),
            "hold_duration": round(effective_hold, 2),
            "range_of_motion": round(achieved_rom, 1),
            "movement_speed": round(avg_speed, 1),
            "compensations_detected": list(self.current_rep_compensations),
            "form_match_percentage": round(form_match_ratio * 100.0, 1),
        }
        self.session_reps_log.append(rep_metrics_payload)

        self._update_fatigue_score()
        self._reset_rep_state(now)

    def _update_fatigue_score(self):
        achieved_rom = getattr(self, "_last_achieved_rom", self.baseline_max_rom)
        
        if self.rep_count > 1 and self.baseline_max_rom > 0:
            rom_drop = max(0.0, abs(self.baseline_max_rom - achieved_rom) / self.baseline_max_rom)
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

            # This summary has been persisted — the reps/telemetry that
            # produced it must not still be sitting in session_reps_log
            # (etc.) the next time a session starts on this same processor
            # instance. Already holding self.lock here, so reset the
            # transient state directly rather than via reset_session()
            # (which would try to re-acquire the lock and deadlock).
            self._init_transient_state()

            return summary_payload