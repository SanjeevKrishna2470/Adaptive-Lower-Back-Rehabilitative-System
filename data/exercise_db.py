"""
data/exercise_db.py
===================
The exercise "database" for Feature 1.

In production this would be a PostgreSQL table seeded by a physio admin.
For the Streamlit prototype, this is our single source of truth — a
Python dict keyed by slug, loaded once at app startup.

Every exercise is fully specified including AI metadata so that when
MediaPipe integration arrives (Feature 2), zero schema changes are needed.
"""

from models.exercise_model import (
    Exercise, ExerciseCategory, DifficultyLevel, JointName,
    JointAngleConstraint, CalibrationParameters
)


# ---------------------------------------------------------------------------
# Exercise Definitions
# ---------------------------------------------------------------------------

EXERCISES: dict[str, Exercise] = {

    # ── 1. PELVIC TILT ────────────────────────────────────────────────────
    "pelvic_tilt": Exercise(
        id="ex_001",
        name="Pelvic Tilt",
        slug="pelvic_tilt",
        category=ExerciseCategory.MOBILITY,
        description=(
            "A gentle foundational exercise that activates the deep core and "
            "teaches lumbar spine control. The patient lies supine and "
            "alternately flattens and arches the lower back against the floor."
        ),
        instructions=[
            "Lie on your back with knees bent, feet flat on the floor.",
            "Breathe in to prepare.",
            "Exhale: gently flatten your lower back against the floor by tightening your abdominals.",
            "Hold for the prescribed duration.",
            "Inhale: slowly return to the neutral arch position.",
            "That is one repetition.",
        ],
        image_path="assets/pelvic_tilt.png",
        video_path=None,
        difficulty=DifficultyLevel.BEGINNER,
        difficulty_notes="Safe for most acute and chronic low back conditions.",
        default_reps=10,
        min_reps=5,
        max_reps=20,
        default_hold_sec=3,
        max_hold_sec=10,
        rep_cadence_target_sec=4.0,
        rest_between_reps_sec=1.0,
        target_joints=[JointName.LUMBAR_SPINE, JointName.PELVIS],
        compensation_joints=[JointName.HIP_LEFT, JointName.HIP_RIGHT],
        joint_constraints=[
            JointAngleConstraint(
                joint=JointName.LUMBAR_SPINE,
                min_angle_deg=5,
                max_angle_deg=25,
                is_primary=True,
                tolerance_deg=5.0,
                description="Lumbar flexion during posterior tilt phase",
            ),
            JointAngleConstraint(
                joint=JointName.PELVIS,
                min_angle_deg=10,
                max_angle_deg=30,
                is_primary=True,
                tolerance_deg=4.0,
                description="Posterior pelvic tilt range",
            ),
        ],
        calibration=CalibrationParameters(
            requires_standing_reference=False,
            requires_neutral_spine_ref=True,
            camera_distance_cm=150,
            landmark_visibility_min=0.75,
        ),
        contraindications=["Acute nerve root compression with leg symptoms (seek advice)"],
        progression_from=None,
        progression_to="dead_bug",
        tags=["supine", "core", "lumbar", "beginner", "foundation"],
    ),

    # ── 2. CAT-COW ────────────────────────────────────────────────────────
    "cat_cow": Exercise(
        id="ex_002",
        name="Cat-Cow",
        slug="cat_cow",
        category=ExerciseCategory.MOBILITY,
        description=(
            "A spinal mobility exercise performed on hands and knees. "
            "Alternates between thoracic flexion (cat) and extension (cow) "
            "to restore spinal segmental movement and reduce stiffness."
        ),
        instructions=[
            "Start on hands and knees: wrists under shoulders, knees under hips.",
            "Ensure spine is in neutral — flat back, head aligned.",
            "COW: Inhale, drop your belly toward the floor, lift your head and tailbone.",
            "CAT: Exhale, round your spine toward the ceiling, tuck chin and tailbone.",
            "Move slowly and smoothly through the full range.",
            "One cat + one cow = one repetition.",
        ],
        image_path="assets/cat_cow.png",
        video_path=None,
        difficulty=DifficultyLevel.BEGINNER,
        difficulty_notes="Excellent for morning stiffness. Avoid if wrist pain present.",
        default_reps=10,
        min_reps=5,
        max_reps=20,
        default_hold_sec=2,
        max_hold_sec=5,
        rep_cadence_target_sec=5.0,
        rest_between_reps_sec=0.5,
        target_joints=[
            JointName.LUMBAR_SPINE,
            JointName.THORACIC_SPINE,
        ],
        compensation_joints=[
            JointName.HIP_LEFT,
            JointName.HIP_RIGHT,
            JointName.SHOULDER_LEFT,
            JointName.SHOULDER_RIGHT,
        ],
        joint_constraints=[
            JointAngleConstraint(
                joint=JointName.THORACIC_SPINE,
                min_angle_deg=15,
                max_angle_deg=45,
                is_primary=True,
                tolerance_deg=6.0,
                description="Thoracic flexion in cat position",
            ),
            JointAngleConstraint(
                joint=JointName.LUMBAR_SPINE,
                min_angle_deg=10,
                max_angle_deg=35,
                is_primary=True,
                tolerance_deg=6.0,
                description="Lumbar extension in cow position",
            ),
        ],
        calibration=CalibrationParameters(
            requires_standing_reference=False,
            requires_neutral_spine_ref=True,
            camera_distance_cm=180,
            landmark_visibility_min=0.70,
        ),
        contraindications=[
            "Acute wrist injury — use fists or forearm modification",
            "Severe spinal stenosis with extension intolerance",
        ],
        progression_from=None,
        progression_to="bird_dog",
        tags=["quadruped", "mobility", "thoracic", "lumbar", "beginner"],
    ),

    # ── 3. BIRD DOG ───────────────────────────────────────────────────────
    "bird_dog": Exercise(
        id="ex_003",
        name="Bird Dog",
        slug="bird_dog",
        category=ExerciseCategory.STABILITY,
        description=(
            "A quadruped stability exercise requiring simultaneous opposite "
            "arm and leg extension while maintaining a neutral spine. "
            "Challenges deep stabilisers (multifidus, transversus abdominis) "
            "without loading the spine."
        ),
        instructions=[
            "Start on hands and knees with spine in neutral.",
            "Engage your core — imagine bracing for a gentle punch.",
            "Slowly extend your RIGHT arm and LEFT leg simultaneously.",
            "Keep hips level — do not rotate or hike one hip higher.",
            "Hold for the prescribed duration.",
            "Return slowly to the start position — this is one rep.",
            "Alternate sides each rep (or complete one side, then switch).",
        ],
        image_path="assets/bird_dog.png",
        video_path=None,
        difficulty=DifficultyLevel.INTERMEDIATE,
        difficulty_notes=(
            "Requires prior mastery of Pelvic Tilt and Cat-Cow. "
            "If lumbar rotation occurs, regress to single leg only."
        ),
        default_reps=8,
        min_reps=3,
        max_reps=15,
        default_hold_sec=5,
        max_hold_sec=10,
        rep_cadence_target_sec=6.0,
        rest_between_reps_sec=2.0,
        target_joints=[
            JointName.LUMBAR_SPINE,
            JointName.HIP_LEFT,
            JointName.HIP_RIGHT,
            JointName.SHOULDER_LEFT,
            JointName.SHOULDER_RIGHT,
        ],
        compensation_joints=[
            JointName.PELVIS,  # Watch for pelvic hike
            JointName.THORACIC_SPINE,
        ],
        joint_constraints=[
            JointAngleConstraint(
                joint=JointName.LUMBAR_SPINE,
                min_angle_deg=-5,
                max_angle_deg=5,
                is_primary=False,
                tolerance_deg=3.0,
                description="Lumbar must remain neutral (near 0°) — no rotation",
            ),
            JointAngleConstraint(
                joint=JointName.HIP_LEFT,
                min_angle_deg=160,
                max_angle_deg=185,
                is_primary=True,
                tolerance_deg=5.0,
                description="Hip extension during leg raise phase",
            ),
        ],
        calibration=CalibrationParameters(
            requires_standing_reference=False,
            requires_neutral_spine_ref=True,
            camera_distance_cm=200,
            landmark_visibility_min=0.72,
        ),
        contraindications=[
            "Acute disc herniation with leg pain — modify to dead bug",
            "Wrist pain — use fist modification",
        ],
        progression_from="cat_cow",
        progression_to="single_leg_deadlift",
        tags=["quadruped", "stability", "core", "intermediate", "multifidus"],
    ),

    # ── 4. KNEE TO CHEST ─────────────────────────────────────────────────
    "knee_to_chest": Exercise(
        id="ex_004",
        name="Knee to Chest",
        slug="knee_to_chest",
        category=ExerciseCategory.STRETCHING,
        description=(
            "A supine stretch that decompresses the lumbar spine by bringing "
            "one or both knees toward the chest. Reduces facet joint compression "
            "and stretches the erector spinae and gluteal muscles."
        ),
        instructions=[
            "Lie on your back with both knees bent.",
            "Grasp behind your RIGHT knee with both hands.",
            "Gently draw the knee toward your chest until you feel a comfortable stretch.",
            "Keep the opposite foot flat on the floor (or extend it for more stretch).",
            "Hold for the prescribed duration.",
            "Slowly lower the leg back — that is one repetition.",
            "Repeat on the LEFT side.",
        ],
        image_path="assets/knee_to_chest.png",
        video_path=None,
        difficulty=DifficultyLevel.BEGINNER,
        difficulty_notes="Excellent for morning pain. Always stay within comfortable range.",
        default_reps=5,
        min_reps=3,
        max_reps=10,
        default_hold_sec=10,
        max_hold_sec=30,
        rep_cadence_target_sec=15.0,
        rest_between_reps_sec=3.0,
        target_joints=[
            JointName.LUMBAR_SPINE,
            JointName.HIP_LEFT,
            JointName.HIP_RIGHT,
            JointName.KNEE_LEFT,
            JointName.KNEE_RIGHT,
        ],
        compensation_joints=[JointName.PELVIS],
        joint_constraints=[
            JointAngleConstraint(
                joint=JointName.HIP_LEFT,
                min_angle_deg=60,
                max_angle_deg=130,
                is_primary=True,
                tolerance_deg=10.0,
                description="Hip flexion range during knee draw",
            ),
        ],
        calibration=CalibrationParameters(
            requires_standing_reference=False,
            requires_neutral_spine_ref=False,
            camera_distance_cm=150,
            landmark_visibility_min=0.70,
        ),
        contraindications=[
            "Recent hip replacement — check surgeon's ROM restrictions",
            "Total hip arthroplasty — limit flexion per surgeon protocol",
        ],
        progression_from=None,
        progression_to="pelvic_tilt",
        tags=["supine", "stretch", "lumbar", "beginner", "decompression"],
    ),

    # ── 5. DEAD BUG ───────────────────────────────────────────────────────
    "dead_bug": Exercise(
        id="ex_005",
        name="Dead Bug",
        slug="dead_bug",
        category=ExerciseCategory.STABILITY,
        description=(
            "A supine core stability exercise where opposite arm and leg "
            "extend away from the body while maintaining a flat lumbar spine. "
            "Trains the anti-extension function of the core."
        ),
        instructions=[
            "Lie on your back with arms pointing to the ceiling.",
            "Raise both knees to 90° — thighs vertical, shins horizontal.",
            "Press your lower back firmly into the floor — hold it there.",
            "Inhale to prepare.",
            "Exhale: slowly lower RIGHT arm overhead AND LEFT leg toward the floor.",
            "Stop before your back lifts off the floor.",
            "Inhale: return to the start position. That is one rep.",
            "Alternate sides each repetition.",
        ],
        image_path="assets/dead_bug.png",
        video_path=None,
        difficulty=DifficultyLevel.INTERMEDIATE,
        difficulty_notes=(
            "Harder than it looks. If back lifts off the floor, reduce range. "
            "Master Pelvic Tilt first."
        ),
        default_reps=8,
        min_reps=4,
        max_reps=16,
        default_hold_sec=2,
        max_hold_sec=5,
        rep_cadence_target_sec=5.0,
        rest_between_reps_sec=1.5,
        target_joints=[
            JointName.LUMBAR_SPINE,
            JointName.CORE,
            JointName.HIP_LEFT,
            JointName.HIP_RIGHT,
        ],
        compensation_joints=[
            JointName.PELVIS,
            JointName.THORACIC_SPINE,
        ],
        joint_constraints=[
            JointAngleConstraint(
                joint=JointName.LUMBAR_SPINE,
                min_angle_deg=-2,
                max_angle_deg=2,
                is_primary=False,
                tolerance_deg=2.0,
                description="Lumbar must stay flat — zero extension during limb lowering",
            ),
        ],
        calibration=CalibrationParameters(
            requires_standing_reference=False,
            requires_neutral_spine_ref=True,
            camera_distance_cm=160,
            landmark_visibility_min=0.72,
        ),
        contraindications=["Acute disc herniation with flex-intolerance"],
        progression_from="pelvic_tilt",
        progression_to="bird_dog",
        tags=["supine", "core", "anti-extension", "intermediate"],
    ),

    # ── 6. GLUTE BRIDGE ───────────────────────────────────────────────────
    "glute_bridge": Exercise(
        id="ex_006",
        name="Glute Bridge",
        slug="glute_bridge",
        category=ExerciseCategory.STRENGTHENING,
        description=(
            "A supine hip extension exercise that strengthens the gluteus maximus "
            "and hamstrings while training lumbopelvic stability. "
            "A cornerstone of low back rehabilitation."
        ),
        instructions=[
            "Lie on your back, knees bent, feet hip-width apart.",
            "Place arms by your sides, palms down.",
            "Engage your core and squeeze your glutes.",
            "Push through your heels to lift your hips off the floor.",
            "Rise until your body forms a straight line from knees to shoulders.",
            "Hold for the prescribed duration.",
            "Lower slowly — do not let hips crash down. That is one rep.",
        ],
        image_path="assets/glute_bridge.png",
        video_path=None,
        difficulty=DifficultyLevel.BEGINNER,
        difficulty_notes="Safe entry-level strengthening for most LBP presentations.",
        default_reps=12,
        min_reps=5,
        max_reps=25,
        default_hold_sec=3,
        max_hold_sec=10,
        rep_cadence_target_sec=4.0,
        rest_between_reps_sec=1.0,
        target_joints=[
            JointName.HIP_LEFT,
            JointName.HIP_RIGHT,
            JointName.LUMBAR_SPINE,
            JointName.PELVIS,
        ],
        compensation_joints=[
            JointName.KNEE_LEFT,
            JointName.KNEE_RIGHT,
            JointName.LUMBAR_SPINE,
        ],
        joint_constraints=[
            JointAngleConstraint(
                joint=JointName.HIP_LEFT,
                min_angle_deg=160,
                max_angle_deg=185,
                is_primary=True,
                tolerance_deg=5.0,
                description="Hip extension at the top of the bridge",
            ),
            JointAngleConstraint(
                joint=JointName.LUMBAR_SPINE,
                min_angle_deg=-5,
                max_angle_deg=10,
                is_primary=False,
                tolerance_deg=4.0,
                description="Avoid lumbar hyperextension at the top",
            ),
        ],
        calibration=CalibrationParameters(
            requires_standing_reference=False,
            requires_neutral_spine_ref=True,
            camera_distance_cm=160,
            landmark_visibility_min=0.75,
        ),
        contraindications=["Acute posterior element pain — may aggravate facet joints"],
        progression_from="pelvic_tilt",
        progression_to="single_leg_glute_bridge",
        tags=["supine", "glutes", "hips", "strengthening", "beginner"],
    ),
}


def get_all_exercises() -> list[Exercise]:
    """Return all exercises sorted by difficulty then name."""
    order = {
        DifficultyLevel.BEGINNER: 0,
        DifficultyLevel.INTERMEDIATE: 1,
        DifficultyLevel.ADVANCED: 2,
    }
    return sorted(
        EXERCISES.values(),
        key=lambda e: (order[e.difficulty], e.name)
    )


def get_exercise_by_slug(slug: str) -> Exercise | None:
    return EXERCISES.get(slug)


def get_exercises_by_difficulty(level: DifficultyLevel) -> list[Exercise]:
    return [e for e in EXERCISES.values() if e.difficulty == level]


def get_exercises_by_category(category: ExerciseCategory) -> list[Exercise]:
    return [e for e in EXERCISES.values() if e.category == category]
