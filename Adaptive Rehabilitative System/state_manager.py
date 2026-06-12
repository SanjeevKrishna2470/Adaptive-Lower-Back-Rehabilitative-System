"""
utils/state_manager.py
======================
All Streamlit session state management lives here.

Why centralise this?
- Streamlit's st.session_state is a global dict. Without a manager,
  every file in the app can read/write any key, creating hidden coupling.
- This module is the SINGLE authoritative contract for what keys exist,
  what their types are, and how they are initialised.
- Future features (MediaPipe, analytics) call these same functions;
  they never write to session_state directly.

Pattern: every function either reads or writes a specific key.
No magic strings scattered across UI files.
"""

from __future__ import annotations
import json
import os
from typing import Optional
import streamlit as st

from models.exercise_model import (
    Exercise, SessionConfig, UserProfile, SessionStatus, DifficultyLevel
)
from data.exercise_db import get_exercise_by_slug


# ---------------------------------------------------------------------------
# State Keys — single source of truth for all session_state key names
# ---------------------------------------------------------------------------

class StateKeys:
    # Feature 1
    ACTIVE_SESSION      = "active_session"          # SessionConfig | None
    SELECTED_EXERCISE   = "selected_exercise"       # Exercise | None
    USER_PROFILE        = "user_profile"            # UserProfile
    SESSION_HISTORY     = "session_history"         # list[dict]
    CURRENT_SCREEN      = "current_screen"          # str: page router
    PAIN_LEVEL          = "pain_level"              # int 0-10

    # Feature 2+ placeholders (declared now, used later)
    MEDIAPIPE_ACTIVE    = "mediapipe_active"        # bool
    CURRENT_REP_COUNT   = "current_rep_count"       # int
    CURRENT_FORM_SCORE  = "current_form_score"      # float
    CAMERA_READY        = "camera_ready"            # bool


# ---------------------------------------------------------------------------
# Screen names — router constants
# ---------------------------------------------------------------------------

class Screen:
    HOME          = "home"
    EXERCISE_LIST = "exercise_list"
    CONFIGURE     = "configure"
    CONFIRM       = "confirm"
    SESSION       = "session"           # Feature 2+
    RESULTS       = "results"           # Feature 2+


# ---------------------------------------------------------------------------
# Initialisation — call once at app startup
# ---------------------------------------------------------------------------

def init_state() -> None:
    """
    Idempotent initialiser — safe to call on every Streamlit rerun.
    Only sets keys that don't already exist (Streamlit's rerun model
    preserves state between reruns, so we never overwrite live values).
    """
    defaults = {
        StateKeys.ACTIVE_SESSION:    None,
        StateKeys.SELECTED_EXERCISE: None,
        StateKeys.USER_PROFILE:      _load_or_create_profile(),
        StateKeys.SESSION_HISTORY:   _load_session_history(),
        StateKeys.CURRENT_SCREEN:    Screen.HOME,
        StateKeys.PAIN_LEVEL:        0,

        # Feature 2+ — initialised false/zero so they're safe to read
        StateKeys.MEDIAPIPE_ACTIVE:  False,
        StateKeys.CURRENT_REP_COUNT: 0,
        StateKeys.CURRENT_FORM_SCORE: None,
        StateKeys.CAMERA_READY:      False,
    }

    for key, default_value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default_value


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------

def navigate_to(screen: str) -> None:
    st.session_state[StateKeys.CURRENT_SCREEN] = screen
    st.rerun()


def get_current_screen() -> str:
    return st.session_state.get(StateKeys.CURRENT_SCREEN, Screen.HOME)


# ---------------------------------------------------------------------------
# Exercise selection
# ---------------------------------------------------------------------------

def select_exercise(exercise: Exercise) -> None:
    """User tapped an exercise card."""
    st.session_state[StateKeys.SELECTED_EXERCISE] = exercise


def get_selected_exercise() -> Optional[Exercise]:
    return st.session_state.get(StateKeys.SELECTED_EXERCISE)


def clear_selected_exercise() -> None:
    st.session_state[StateKeys.SELECTED_EXERCISE] = None


# ---------------------------------------------------------------------------
# Session config
# ---------------------------------------------------------------------------

def create_session(
    exercise:   Exercise,
    reps:       int,
    hold_sec:   int,
    difficulty: DifficultyLevel,
    sets:       int = 1,
    pain_level: int = 0,
) -> SessionConfig:
    """
    Creates and stores an active SessionConfig.
    This is the output of Feature 1 — the object all future features consume.
    """
    profile: UserProfile = st.session_state[StateKeys.USER_PROFILE]

    config = SessionConfig(
        exercise_id=exercise.id,
        exercise_slug=exercise.slug,
        exercise_name=exercise.name,
        reps=reps,
        hold_sec=hold_sec,
        difficulty=difficulty,
        sets=sets,
        user_id=profile.user_id,
        status=SessionStatus.CONFIGURED,
    )

    # Store pain level on the profile for this session
    profile.pain_level = pain_level
    st.session_state[StateKeys.USER_PROFILE] = profile
    st.session_state[StateKeys.ACTIVE_SESSION] = config

    # Persist immediately so a browser refresh doesn't lose the config
    _persist_session(config)

    return config


def get_active_session() -> Optional[SessionConfig]:
    return st.session_state.get(StateKeys.ACTIVE_SESSION)


def start_active_session() -> None:
    """Feature 2 will call this when the camera is ready."""
    config: Optional[SessionConfig] = get_active_session()
    if config:
        config.start()
        st.session_state[StateKeys.ACTIVE_SESSION] = config
        _persist_session(config)


def complete_active_session() -> None:
    config: Optional[SessionConfig] = get_active_session()
    if config:
        config.complete()
        _save_to_history(config)
        st.session_state[StateKeys.ACTIVE_SESSION] = None
        _persist_session(config)


def abandon_active_session() -> None:
    config: Optional[SessionConfig] = get_active_session()
    if config:
        config.abandon()
        _save_to_history(config)
        st.session_state[StateKeys.ACTIVE_SESSION] = None


# ---------------------------------------------------------------------------
# User profile
# ---------------------------------------------------------------------------

def get_user_profile() -> UserProfile:
    return st.session_state[StateKeys.USER_PROFILE]


def update_user_profile(**kwargs) -> None:
    profile: UserProfile = get_user_profile()
    for k, v in kwargs.items():
        if hasattr(profile, k):
            setattr(profile, k, v)
    st.session_state[StateKeys.USER_PROFILE] = profile
    _persist_profile(profile)


# ---------------------------------------------------------------------------
# Session history
# ---------------------------------------------------------------------------

def get_session_history() -> list[dict]:
    return st.session_state.get(StateKeys.SESSION_HISTORY, [])


def _save_to_history(config: SessionConfig) -> None:
    history: list = st.session_state.get(StateKeys.SESSION_HISTORY, [])
    history.insert(0, config.to_dict())    # newest first
    history = history[:50]                  # keep last 50 sessions in memory
    st.session_state[StateKeys.SESSION_HISTORY] = history
    _persist_history(history)


# ---------------------------------------------------------------------------
# Persistence layer
# File-based JSON for the Streamlit prototype.
# Swap these functions for DB calls when moving to production.
# ---------------------------------------------------------------------------

PERSISTENCE_DIR = os.path.join(os.path.dirname(__file__), "..", ".rehabai_data")


def _ensure_persistence_dir() -> None:
    os.makedirs(PERSISTENCE_DIR, exist_ok=True)


def _persist_session(config: SessionConfig) -> None:
    _ensure_persistence_dir()
    path = os.path.join(PERSISTENCE_DIR, f"session_{config.session_id}.json")
    with open(path, "w") as f:
        json.dump(config.to_dict(), f, indent=2)


def _persist_profile(profile: UserProfile) -> None:
    _ensure_persistence_dir()
    path = os.path.join(PERSISTENCE_DIR, "user_profile.json")
    with open(path, "w") as f:
        json.dump(profile.to_dict(), f, indent=2)


def _persist_history(history: list[dict]) -> None:
    _ensure_persistence_dir()
    path = os.path.join(PERSISTENCE_DIR, "session_history.json")
    with open(path, "w") as f:
        json.dump(history, f, indent=2)


def _load_or_create_profile() -> UserProfile:
    path = os.path.join(PERSISTENCE_DIR, "user_profile.json")
    if os.path.exists(path):
        try:
            with open(path) as f:
                return UserProfile.from_dict(json.load(f))
        except Exception:
            pass
    return UserProfile(name="Patient")


def _load_session_history() -> list[dict]:
    path = os.path.join(PERSISTENCE_DIR, "session_history.json")
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            pass
    return []
