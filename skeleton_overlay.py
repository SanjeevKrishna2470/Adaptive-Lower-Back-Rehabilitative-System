import cv2
import mediapipe as mp
import math
import time

# --- Setup ---
mp_drawing = mp.solutions.drawing_utils
mp_pose = mp.solutions.pose

cap = cv2.VideoCapture(0)
if not cap.isOpened():
    cap = cv2.VideoCapture(1)
if not cap.isOpened():
    print("Camera not accessible")
    exit(1)

# --- Calibration ---
normal_hunch_index = None
calibration_start_time = None
CALIBRATION_DELAY = 3.0

# --- Hold time ---
hold_start_time = None
total_hold_time = 0.0

# --- Motion speed ---
prev_left_angle = None
prev_time = None
speed = 0.0

# --- Rep phase tracking ---
phase = "HOLDING"
phase_counter = 0
PHASE_SWITCH_FRAMES = 5
SPEED_THRESHOLD = 20.0

# --- Rep counting & Cold Start (Feature 13) ---
rep_count = 0
last_phase = "HOLDING"          # previous phase, used to detect transitions
WARMUP_REPS = 3                 # number of initial reps with relaxed thresholds
session_start_time = time.time() # (optional, could be used later)

# --- Main loop ---
with mp_pose.Pose(
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5) as pose:

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        h, w, _ = frame.shape
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = pose.process(rgb)

        if results.pose_landmarks:
            # --- Skeleton ---
            mp_drawing.draw_landmarks(
                frame,
                results.pose_landmarks,
                mp_pose.POSE_CONNECTIONS,
                landmark_drawing_spec=mp_drawing.DrawingSpec(
                    color=(0, 255, 0), thickness=2, circle_radius=2),
                connection_drawing_spec=mp_drawing.DrawingSpec(
                    color=(255, 0, 0), thickness=2)
            )

            # --- Helper functions ---
            def calculate_angle(a, b, c):
                vec1 = (a[0] - b[0], a[1] - b[1])
                vec2 = (c[0] - b[0], c[1] - b[1])
                dot = vec1[0]*vec2[0] + vec1[1]*vec2[1]
                mag1 = math.sqrt(vec1[0]**2 + vec1[1]**2)
                mag2 = math.sqrt(vec2[0]**2 + vec2[1]**2)
                if mag1 > 0 and mag2 > 0:
                    cos = dot / (mag1 * mag2)
                    cos = max(-1.0, min(1.0, cos))
                    return math.degrees(math.acos(cos))
                return 0.0

            def euclidean(a, b):
                return math.sqrt((a[0]-b[0])**2 + (a[1]-b[1])**2)

            # --- Landmarks ---
            lm = results.pose_landmarks.landmark

            l_shoulder = (int(lm[mp_pose.PoseLandmark.LEFT_SHOULDER.value].x * w),
                          int(lm[mp_pose.PoseLandmark.LEFT_SHOULDER.value].y * h))
            l_hip = (int(lm[mp_pose.PoseLandmark.LEFT_HIP.value].x * w),
                     int(lm[mp_pose.PoseLandmark.LEFT_HIP.value].y * h))
            l_knee = (int(lm[mp_pose.PoseLandmark.LEFT_KNEE.value].x * w),
                      int(lm[mp_pose.PoseLandmark.LEFT_KNEE.value].y * h))
            l_ankle = (int(lm[mp_pose.PoseLandmark.LEFT_ANKLE.value].x * w),
                       int(lm[mp_pose.PoseLandmark.LEFT_ANKLE.value].y * h))

            r_shoulder = (int(lm[mp_pose.PoseLandmark.RIGHT_SHOULDER.value].x * w),
                          int(lm[mp_pose.PoseLandmark.RIGHT_SHOULDER.value].y * h))
            r_hip = (int(lm[mp_pose.PoseLandmark.RIGHT_HIP.value].x * w),
                     int(lm[mp_pose.PoseLandmark.RIGHT_HIP.value].y * h))
            r_knee = (int(lm[mp_pose.PoseLandmark.RIGHT_KNEE.value].x * w),
                      int(lm[mp_pose.PoseLandmark.RIGHT_KNEE.value].y * h))
            r_ankle = (int(lm[mp_pose.PoseLandmark.RIGHT_ANKLE.value].x * w),
                       int(lm[mp_pose.PoseLandmark.RIGHT_ANKLE.value].y * h))

            # --- Hip angles ---
            left_angle = calculate_angle(l_shoulder, l_hip, l_knee)
            right_angle = calculate_angle(r_shoulder, r_hip, r_knee)

            # Motion speed
            now = time.time()
            if prev_left_angle is not None and prev_time is not None:
                dt = now - prev_time
                speed = abs(left_angle - prev_left_angle) / dt if dt > 0 else 0.0
            else:
                speed = 0.0
            prev_left_angle = left_angle
            prev_time = now

            # --- Rep phase tracking ---
            target_phase = "MOVING" if speed > SPEED_THRESHOLD else "HOLDING"
            if target_phase == phase:
                phase_counter = 0
            else:
                phase_counter += 1
                if phase_counter >= PHASE_SWITCH_FRAMES:
                    phase = target_phase
                    phase_counter = 0

            # --- Rep counting (transition from HOLDING to MOVING) ---
            if last_phase == "HOLDING" and phase == "MOVING":
                rep_count += 1
            last_phase = phase

            # --- Cold Start: determine if we are still warming up ---
            warmup = (rep_count < WARMUP_REPS)
            warmup_text = "WARM-UP" if warmup else "ACTIVE"
            warmup_color = (0, 255, 255) if warmup else (0, 255, 0)

            # Dynamic thresholds based on warmup
            if warmup:
                ASYMMETRY_THRESHOLD = 25.0        # relaxed
                KNEE_BEND_THRESHOLD = 130.0       # allow more bend
                HUNCH_MULTIPLIER = 1.08           # need larger increase to flag
                TARGET_MIN, TARGET_MAX = 150.0, 180.0   # wider range
            else:
                ASYMMETRY_THRESHOLD = 15.0        # normal
                KNEE_BEND_THRESHOLD = 150.0
                HUNCH_MULTIPLIER = 1.06
                TARGET_MIN, TARGET_MAX = 160.0, 180.0

            # Draw measurement lines
            cv2.line(frame, l_shoulder, l_hip, (0, 255, 255), 1)
            cv2.line(frame, l_hip, l_knee, (0, 255, 255), 1)
            cv2.line(frame, r_shoulder, r_hip, (255, 255, 0), 1)
            cv2.line(frame, r_hip, r_knee, (255, 255, 0), 1)

            cv2.putText(frame, f"L: {left_angle:.1f}", (l_hip[0]+10, l_hip[1]-10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
            cv2.putText(frame, f"R: {right_angle:.1f}", (r_hip[0]+10, r_hip[1]-10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)

            # Knee angles
            left_knee_angle = calculate_angle(l_hip, l_knee, l_ankle)
            right_knee_angle = calculate_angle(r_hip, r_knee, r_ankle)
            cv2.putText(frame, f"L knee: {left_knee_angle:.1f}", (l_knee[0]+10, l_knee[1]-10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 2)
            cv2.putText(frame, f"R knee: {right_knee_angle:.1f}", (r_knee[0]+10, r_knee[1]-10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 2)

            # Asymmetry detection
            asymmetry = abs(left_angle - right_angle)
            cv2.putText(frame, f"Diff: {asymmetry:.1f}", (w-200, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
            if asymmetry > ASYMMETRY_THRESHOLD:
                cv2.putText(frame, "WARNING: Asymmetry!", (w-400, 70),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

            # --- Hunching detection (scale‑invariant) ---
            left_vert = abs(l_shoulder[1] - l_hip[1])
            right_vert = abs(r_shoulder[1] - r_hip[1])
            avg_shoulder_hip_vert = (left_vert + right_vert) / 2.0
            shoulder_width = euclidean(l_shoulder, r_shoulder)
            if shoulder_width > 0:
                hunch_index = avg_shoulder_hip_vert / shoulder_width
            else:
                hunch_index = 0.0

            cv2.putText(frame, f"Hunch idx: {hunch_index:.3f}", (w-400, 50),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)

            if calibration_start_time is not None:
                elapsed = time.time() - calibration_start_time
                remaining = max(0, CALIBRATION_DELAY - elapsed)
                if remaining > 0:
                    cv2.putText(frame, f"Calibrating in: {remaining:.1f}s",
                                (w//2 - 100, h//2), cv2.FONT_HERSHEY_SIMPLEX,
                                1.0, (0, 0, 255), 2)
                else:
                    normal_hunch_index = hunch_index
                    calibration_start_time = None
                    print(f"Calibrated hunch index = {normal_hunch_index:.3f}")

            if normal_hunch_index is not None:
                if hunch_index > normal_hunch_index * HUNCH_MULTIPLIER:
                    cv2.putText(frame, "WARNING: Shoulder Hunching!", (w-500, 110),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

            # Knee compensation
            if left_knee_angle < KNEE_BEND_THRESHOLD or right_knee_angle < KNEE_BEND_THRESHOLD:
                cv2.putText(frame, "WARNING: Knee Bending!", (w-500, 150),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

            # Starting position + hold time
            position_ok = (TARGET_MIN <= left_angle <= TARGET_MAX)
            if position_ok:
                status = "Position OK"
                color = (0, 255, 0)
                if hold_start_time is None:
                    hold_start_time = time.time()
            else:
                status = "Adjust Position"
                color = (0, 0, 255)
                if hold_start_time is not None:
                    total_hold_time += time.time() - hold_start_time
                    hold_start_time = None

            cv2.putText(frame, status, (20, 50),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0, color, 2)

            current_hold = (time.time() - hold_start_time) if hold_start_time else 0.0
            cv2.putText(frame, f"Current hold: {current_hold:.1f}s", (20, 90),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
            cv2.putText(frame, f"Total hold: {total_hold_time:.1f}s", (20, 120),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)

            cv2.putText(frame, f"Speed: {speed:.1f} deg/s", (w-400, 90),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)

            # Rep phase display
            phase_color = (0, 255, 0) if phase == "HOLDING" else (0, 0, 255)
            cv2.putText(frame, f"Phase: {phase}", (20, 150),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, phase_color, 2)

            # --- Rep count & Warmup status ---
            cv2.putText(frame, f"Reps: {rep_count}", (20, 190),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)
            cv2.putText(frame, warmup_text, (20, 220),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, warmup_color, 2)

        # --- On‑screen instructions ---
        if normal_hunch_index is None and calibration_start_time is None:
            cv2.putText(frame, "Press 'c' to start calibration", (20, h-30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
        elif normal_hunch_index is not None:
            cv2.putText(frame, f"Normal idx: {normal_hunch_index:.3f}",
                        (20, h-30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 150, 0), 1)

        cv2.imshow('Skeleton Overlay', frame)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('c'):
            if calibration_start_time is None:
                calibration_start_time = time.time()

cap.release()
cv2.destroyAllWindows()