"""
models/exercise_model.py
========================
Core data models for the RehabAI system.

Design philosophy:
- All models are pure Python dataclasses (no ORM dependency yet).
- Every field that future AI/MediaPipe modules will need is already
  present — even if Feature 1 doesn't use it, it must be defined here
  so downstream features have a stable contract.
- Dataclasses + TypedDicts give us type safety without heavy frameworks.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from enum import Enum
import uuid
import json
from datetime import datetime


# ---------------------------------------------------------------------------
# Enumerations — single source of truth for all categorical values
# ---------------------------------------------------------------------------

class DifficultyLevel(str, Enum):
    BEGINNER     = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED     = "advanced"


class ExerciseCategory(str, Enum):
    MOBILITY      = "mobility"       # Range-of-motion exercises
    STRENGTHENING = "strengthening"  # Muscle activation
    STABILITY     = "stability"      # Core / balance
    STRETCHING    = "stretching"     # Flexibility


class JointName(str, Enum):
    """
    Maps directly to MediaPipe Pose landmark groups.
    Future Feature (Pose Tracking) will use these to select
    which landmark pairs to measure angles between.
    """
    LUMBAR_SPINE   = "lumbar_spine"
    THORACIC_SPINE = "thoracic_spine"
    HIP_LEFT       = "hip_left"
    HIP_RIGHT      = "hip_right"
    KNEE_LEFT      = "knee_left"
    KNEE_RIGHT     = "knee_right"
    SHOULDER_LEFT  = "shoulder_left"
    SHOULDER_RIGHT = "shoulder_right"
    PELVIS         = "pelvis"
    CORE           = "core"


class SessionStatus(str, Enum):
    CONFIGURED = "configured"  # User set reps/hold, not started
    ACTIVE     = "active"      # Timer running, reps being counted
    PAUSED     = "paused"      # Mid-session pause
    COMPLETED  = "completed"   # All reps done
    ABANDONED  = "abandoned"   # User exited early


# ---------------------------------------------------------------------------
# Joint Angle Constraint
# Used by future AI validation to detect correct form vs compensation
# ---------------------------------------------------------------------------

@dataclass
class JointAngleConstraint:
    """
    Defines the expected angular range for a joint during an exercise.

    Example for Pelvic Tilt:
        joint        = JointName.LUMBAR_SPINE
        min_angle_deg = 10   (minimum posterior tilt)
        max_angle_deg = 30   (maximum — beyond this = compensation)
        is_primary    = True (this is the movement we're measuring)

    Future MediaPipe module will:
    1. Detect these landmark positions
    2. Calculate the angle
    3. Compare against min/max
    4. Flag compensation if violated
    """
    joint:           JointName
    min_angle_deg:   float
    max_angle_deg:   float
    is_primary:      bool = True       # Primary = the exercise movement itself
    tolerance_deg:   float = 5.0       # ±5° tolerance before flagging
    description:     str = ""          # Human-readable hint for UI feedback


@dataclass
class CalibrationParameters:
    """
    Placeholder for the per-user calibration that MediaPipe
    will require in Feature 3 (Pose Calibration).

    Stored here so the Exercise model is already extensible.
    """
    requires_standing_reference: bool = False
    requires_neutral_spine_ref:  bool = True
    camera_distance_cm:          Optional[float] = None   # Ideal cam distance
    landmark_visibility_min:     float = 0.7              # MediaPipe confidence threshold


# ---------------------------------------------------------------------------
# Exercise — the canonical definition of a rehabilitation movement
# ---------------------------------------------------------------------------

@dataclass
class Exercise:
    """
    Immutable exercise definition. Think of this as the 'prescription template'
    created by a physiotherapist. Users configure their own session on top of
    this, but the Exercise itself never changes per user.

    Designed for:
    - Feature 1 : display in UI, configure reps/hold
    - Feature 2 : MediaPipe landmark selection via target_joints
    - Feature 3 : angle validation via joint_constraints
    - Feature 4 : adaptive difficulty via difficulty_levels
    - Feature 5 : fatigue detection via rep_cadence_target_sec
    """
    # Identity
    id:               str
    name:             str
    slug:             str              # URL/key safe: "pelvic_tilt"
    category:         ExerciseCategory

    # Display
    description:      str
    instructions:     List[str]        # Step-by-step cues shown to user
    image_path:       Optional[str]    # Path to static image asset
    video_path:       Optional[str]    # Path to demo video

    # Difficulty
    difficulty:       DifficultyLevel
    difficulty_notes: str = ""         # e.g. "Avoid if acute disc herniation"

    # Rep & Hold defaults (user can override in session config)
    default_reps:     int = 10
    min_reps:         int = 3
    max_reps:         int = 30
    default_hold_sec: int = 0          # 0 = no hold, just rep-based
    max_hold_sec:     int = 60

    # Pacing
    rep_cadence_target_sec: float = 3.0   # Expected seconds per rep
    rest_between_reps_sec:  float = 1.0

    # AI / Pose tracking metadata
    target_joints:       List[JointName] = field(default_factory=list)
    compensation_joints: List[JointName] = field(default_factory=list)
    joint_constraints:   List[JointAngleConstraint] = field(default_factory=list)
    calibration:         CalibrationParameters = field(default_factory=CalibrationParameters)

    # Safety
    contraindications:   List[str] = field(default_factory=list)
    progression_from:    Optional[str] = None   # slug of easier exercise
    progression_to:      Optional[str] = None   # slug of harder exercise

    # Metadata
    created_at:  str = field(default_factory=lambda: datetime.utcnow().isoformat())
    tags:        List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to plain dict for JSON storage / session state."""
        return {
            "id": self.id,
            "name": self.name,
            "slug": self.slug,
            "category": self.category.value,
            "description": self.description,
            "instructions": self.instructions,
            "difficulty": self.difficulty.value,
            "difficulty_notes": self.difficulty_notes,
            "default_reps": self.default_reps,
            "min_reps": self.min_reps,
            "max_reps": self.max_reps,
            "default_hold_sec": self.default_hold_sec,
            "max_hold_sec": self.max_hold_sec,
            "rep_cadence_target_sec": self.rep_cadence_target_sec,
            "rest_between_reps_sec": self.rest_between_reps_sec,
            "target_joints": [j.value for j in self.target_joints],
            "compensation_joints": [j.value for j in self.compensation_joints],
            "contraindications": self.contraindications,
            "progression_from": self.progression_from,
            "progression_to": self.progression_to,
            "tags": self.tags,
        }


# ---------------------------------------------------------------------------
# SessionConfig — what the USER chose for THIS session
# ---------------------------------------------------------------------------

@dataclass
class SessionConfig:
    """
    A single user's configuration for one rehabilitation session.

    This is the OUTPUT of Feature 1 and the INPUT contract
    that every subsequent feature depends on.

    Separation of concerns:
    - Exercise = what the physio prescribed (immutable)
    - SessionConfig = what the patient chose today (mutable)
    """
    session_id:     str = field(default_factory=lambda: str(uuid.uuid4()))
    exercise_id:    str = ""
    exercise_slug:  str = ""
    exercise_name:  str = ""

    # User-configured parameters
    reps:           int = 10
    hold_sec:       int = 0
    difficulty:     DifficultyLevel = DifficultyLevel.BEGINNER
    sets:           int = 1               # Future: multi-set sessions

    # Session lifecycle
    status:         SessionStatus = SessionStatus.CONFIGURED
    created_at:     str = field(default_factory=lambda: datetime.utcnow().isoformat())
    started_at:     Optional[str] = None
    completed_at:   Optional[str] = None

    # Progress (updated by Feature 2+ in real time)
    reps_completed:      int = 0
    sets_completed:      int = 0
    form_score:          Optional[float] = None   # 0.0–1.0, from AI validation
    compensation_count:  int = 0                   # Times bad form detected

    # User context (set at login / profile)
    user_id:        Optional[str] = None
    notes:          str = ""                       # Patient's own session notes

    def start(self) -> None:
        self.status = SessionStatus.ACTIVE
        self.started_at = datetime.utcnow().isoformat()

    def complete(self) -> None:
        self.status = SessionStatus.COMPLETED
        self.completed_at = datetime.utcnow().isoformat()

    def abandon(self) -> None:
        self.status = SessionStatus.ABANDONED
        self.completed_at = datetime.utcnow().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id":        self.session_id,
            "exercise_id":       self.exercise_id,
            "exercise_slug":     self.exercise_slug,
            "exercise_name":     self.exercise_name,
            "reps":              self.reps,
            "hold_sec":          self.hold_sec,
            "difficulty":        self.difficulty.value,
            "sets":              self.sets,
            "status":            self.status.value,
            "created_at":        self.created_at,
            "started_at":        self.started_at,
            "completed_at":      self.completed_at,
            "reps_completed":    self.reps_completed,
            "sets_completed":    self.sets_completed,
            "form_score":        self.form_score,
            "compensation_count":self.compensation_count,
            "user_id":           self.user_id,
            "notes":             self.notes,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SessionConfig":
        return cls(
            session_id=d.get("session_id", str(uuid.uuid4())),
            exercise_id=d.get("exercise_id", ""),
            exercise_slug=d.get("exercise_slug", ""),
            exercise_name=d.get("exercise_name", ""),
            reps=d.get("reps", 10),
            hold_sec=d.get("hold_sec", 0),
            difficulty=DifficultyLevel(d.get("difficulty", "beginner")),
            sets=d.get("sets", 1),
            status=SessionStatus(d.get("status", "configured")),
            created_at=d.get("created_at", datetime.utcnow().isoformat()),
            started_at=d.get("started_at"),
            completed_at=d.get("completed_at"),
            reps_completed=d.get("reps_completed", 0),
            sets_completed=d.get("sets_completed", 0),
            form_score=d.get("form_score"),
            compensation_count=d.get("compensation_count", 0),
            user_id=d.get("user_id"),
            notes=d.get("notes", ""),
        )


# ---------------------------------------------------------------------------
# UserProfile — minimal user model for Feature 1 scope
# ---------------------------------------------------------------------------

@dataclass
class UserProfile:
    user_id:          str = field(default_factory=lambda: str(uuid.uuid4()))
    name:             str = "Patient"
    age:              Optional[int] = None
    diagnosis:        str = ""           # e.g. "L4-L5 disc bulge"
    pain_level:       int = 0            # 0–10 VAS scale, set at session start
    prescribed_exercises: List[str] = field(default_factory=list)  # Exercise slugs
    session_history:  List[str] = field(default_factory=list)      # Session IDs
    preferred_difficulty: DifficultyLevel = DifficultyLevel.BEGINNER
    created_at:       str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "name": self.name,
            "age": self.age,
            "diagnosis": self.diagnosis,
            "pain_level": self.pain_level,
            "prescribed_exercises": self.prescribed_exercises,
            "session_history": self.session_history,
            "preferred_difficulty": self.preferred_difficulty.value,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "UserProfile":
        return cls(
            user_id=d.get("user_id", str(uuid.uuid4())),
            name=d.get("name", "Patient"),
            age=d.get("age"),
            diagnosis=d.get("diagnosis", ""),
            pain_level=d.get("pain_level", 0),
            prescribed_exercises=d.get("prescribed_exercises", []),
            session_history=d.get("session_history", []),
            preferred_difficulty=DifficultyLevel(d.get("preferred_difficulty", "beginner")),
            created_at=d.get("created_at", datetime.utcnow().isoformat()),
        )
