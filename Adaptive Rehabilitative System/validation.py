"""
utils/validation.py
===================
All business-rule validation for session configuration.

Separation of concerns:
- This module knows NOTHING about Streamlit or the UI.
- It receives plain data, returns ValidationResult objects.
- The UI layer calls these and renders error messages accordingly.

This design means validation logic can be reused by:
- Feature 1 (UI form validation)
- Future REST API (server-side validation)
- Future mobile app
- Automated testing
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional
from models.exercise_model import Exercise, DifficultyLevel, SessionConfig


# ---------------------------------------------------------------------------
# Validation Result — clean contract between validation and UI
# ---------------------------------------------------------------------------

@dataclass
class ValidationError:
    field:   str    # Which field caused the error, e.g. "reps"
    message: str    # Human-readable message shown in UI
    code:    str    # Machine-readable code for logging/analytics


@dataclass
class ValidationResult:
    is_valid: bool = True
    errors:   List[ValidationError] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)   # Non-blocking advisories

    def add_error(self, field: str, message: str, code: str) -> None:
        self.errors.append(ValidationError(field=field, message=message, code=code))
        self.is_valid = False

    def add_warning(self, message: str) -> None:
        self.warnings.append(message)

    @property
    def error_messages(self) -> List[str]:
        return [e.message for e in self.errors]

    @property
    def first_error(self) -> Optional[str]:
        return self.errors[0].message if self.errors else None


# ---------------------------------------------------------------------------
# Core validation logic
# ---------------------------------------------------------------------------

class SessionConfigValidator:
    """
    Validates a proposed SessionConfig against the chosen Exercise's rules.

    Usage:
        validator = SessionConfigValidator()
        result = validator.validate(exercise=ex, reps=12, hold_sec=5, ...)
        if not result.is_valid:
            for msg in result.error_messages:
                st.error(msg)
    """

    # Beginner safeguards — regardless of exercise's own max_reps
    BEGINNER_MAX_REPS     = 15
    BEGINNER_MAX_HOLD_SEC = 10

    # Absolute system limits — no user can exceed these
    SYSTEM_MAX_REPS     = 50
    SYSTEM_MAX_HOLD_SEC = 120
    SYSTEM_MAX_SETS     = 5

    def validate(
        self,
        exercise:   Exercise,
        reps:       int,
        hold_sec:   int,
        difficulty: DifficultyLevel,
        sets:       int = 1,
    ) -> ValidationResult:

        result = ValidationResult()

        self._validate_reps(result, exercise, reps, difficulty)
        self._validate_hold(result, exercise, hold_sec, difficulty)
        self._validate_sets(result, sets)
        self._validate_difficulty_progression(result, exercise, difficulty)
        self._check_safety_warnings(result, exercise, reps, hold_sec, difficulty)

        return result

    # ── Private validators ────────────────────────────────────────────────

    def _validate_reps(
        self,
        result: ValidationResult,
        exercise: Exercise,
        reps: int,
        difficulty: DifficultyLevel,
    ) -> None:

        # Type safety
        if not isinstance(reps, int) or reps != reps:  # NaN guard
            result.add_error("reps", "Rep count must be a whole number.", "INVALID_TYPE")
            return

        # System floor
        if reps < 1:
            result.add_error("reps", "Rep count must be at least 1.", "BELOW_MINIMUM")
            return

        # Exercise-defined minimum
        if reps < exercise.min_reps:
            result.add_error(
                "reps",
                f"This exercise requires at least {exercise.min_reps} reps "
                f"to be therapeutically effective.",
                "BELOW_EXERCISE_MINIMUM",
            )

        # Exercise-defined maximum
        if reps > exercise.max_reps:
            result.add_error(
                "reps",
                f"{exercise.name} should not exceed {exercise.max_reps} reps per session. "
                f"More volume ≠ more benefit for this exercise.",
                "ABOVE_EXERCISE_MAXIMUM",
            )

        # Beginner safeguard
        if difficulty == DifficultyLevel.BEGINNER and reps > self.BEGINNER_MAX_REPS:
            result.add_error(
                "reps",
                f"For beginners, we limit reps to {self.BEGINNER_MAX_REPS} "
                f"to prevent fatigue-related compensation. Increase difficulty level to unlock more.",
                "BEGINNER_SAFEGUARD_REPS",
            )

        # Absolute system cap
        if reps > self.SYSTEM_MAX_REPS:
            result.add_error(
                "reps",
                f"Rep count cannot exceed {self.SYSTEM_MAX_REPS}.",
                "SYSTEM_MAX_EXCEEDED",
            )

    def _validate_hold(
        self,
        result: ValidationResult,
        exercise: Exercise,
        hold_sec: int,
        difficulty: DifficultyLevel,
    ) -> None:

        if hold_sec < 0:
            result.add_error("hold_sec", "Hold time cannot be negative.", "NEGATIVE_HOLD")
            return

        if hold_sec > exercise.max_hold_sec:
            result.add_error(
                "hold_sec",
                f"Hold time for {exercise.name} should not exceed {exercise.max_hold_sec}s. "
                f"Longer holds do not improve outcomes and increase fatigue risk.",
                "ABOVE_EXERCISE_HOLD_MAX",
            )

        if difficulty == DifficultyLevel.BEGINNER and hold_sec > self.BEGINNER_MAX_HOLD_SEC:
            result.add_error(
                "hold_sec",
                f"For beginners, hold time is capped at {self.BEGINNER_MAX_HOLD_SEC}s. "
                f"Progress to Intermediate to unlock longer holds.",
                "BEGINNER_SAFEGUARD_HOLD",
            )

        if hold_sec > self.SYSTEM_MAX_HOLD_SEC:
            result.add_error(
                "hold_sec",
                f"Hold time cannot exceed {self.SYSTEM_MAX_HOLD_SEC}s.",
                "SYSTEM_MAX_HOLD_EXCEEDED",
            )

    def _validate_sets(self, result: ValidationResult, sets: int) -> None:
        if sets < 1:
            result.add_error("sets", "Must have at least 1 set.", "BELOW_MIN_SETS")
        if sets > self.SYSTEM_MAX_SETS:
            result.add_error(
                "sets",
                f"Maximum {self.SYSTEM_MAX_SETS} sets per session.",
                "ABOVE_MAX_SETS",
            )

    def _validate_difficulty_progression(
        self,
        result: ValidationResult,
        exercise: Exercise,
        difficulty: DifficultyLevel,
    ) -> None:
        """
        Warn if user selects Advanced difficulty for a Beginner exercise.
        This doesn't block but helps prevent misunderstanding.
        """
        if (
            exercise.difficulty == DifficultyLevel.BEGINNER
            and difficulty == DifficultyLevel.ADVANCED
        ):
            result.add_warning(
                f"{exercise.name} is a beginner-level exercise. "
                f"Selecting Advanced difficulty will use tighter AI form criteria but "
                f"won't change the exercise itself. Consider progressing to: "
                f"{exercise.progression_to or 'a more challenging exercise'}."
            )

    def _check_safety_warnings(
        self,
        result: ValidationResult,
        exercise: Exercise,
        reps: int,
        hold_sec: int,
        difficulty: DifficultyLevel,
    ) -> None:
        """
        Non-blocking warnings that inform the user without stopping them.
        """
        # High total time-under-tension warning
        estimated_duration_sec = reps * (exercise.rep_cadence_target_sec + hold_sec)
        if estimated_duration_sec > 300:  # > 5 minutes of continuous exercise
            result.add_warning(
                f"Estimated session duration: {estimated_duration_sec/60:.1f} minutes. "
                f"For rehabilitation, shorter frequent sessions often outperform "
                f"single long sessions."
            )

        # Contraindication reminder (non-blocking — physio responsibility)
        if exercise.contraindications:
            result.add_warning(
                f"Precaution: {'; '.join(exercise.contraindications)}"
            )


# ---------------------------------------------------------------------------
# Convenience function for direct use in UI
# ---------------------------------------------------------------------------

def validate_session_config(
    exercise: Exercise,
    reps: int,
    hold_sec: int,
    difficulty: DifficultyLevel,
    sets: int = 1,
) -> ValidationResult:
    """Top-level function — import this in the Streamlit app."""
    return SessionConfigValidator().validate(
        exercise=exercise,
        reps=reps,
        hold_sec=hold_sec,
        difficulty=difficulty,
        sets=sets,
    )
