"""
components/ui_components.py
============================
Reusable Streamlit UI components.

Design rules:
- Every component is a pure function that takes data and renders UI.
- Components never read from session_state directly.
  They receive data as arguments and return user actions via return values.
- This makes components testable and reusable across screens.
"""

from __future__ import annotations
from typing import Optional, List, Callable
import streamlit as st

from models.exercise_model import (
    Exercise, DifficultyLevel, ExerciseCategory, SessionConfig, SessionStatus
)


# ---------------------------------------------------------------------------
# Difficulty badge rendering
# ---------------------------------------------------------------------------

DIFFICULTY_CONFIG = {
    DifficultyLevel.BEGINNER: {
        "label":  "Beginner",
        "color":  "#52B788",
        "bg":     "#D8F3DC",
        "icon":   "🟢",
    },
    DifficultyLevel.INTERMEDIATE: {
        "label":  "Intermediate",
        "color":  "#E76F51",
        "bg":     "#FDEBD0",
        "icon":   "🟡",
    },
    DifficultyLevel.ADVANCED: {
        "label":  "Advanced",
        "color":  "#C0392B",
        "bg":     "#FADBD8",
        "icon":   "🔴",
    },
}

CATEGORY_ICONS = {
    ExerciseCategory.MOBILITY:      "🔄",
    ExerciseCategory.STRENGTHENING: "💪",
    ExerciseCategory.STABILITY:     "⚖️",
    ExerciseCategory.STRETCHING:    "🧘",
}


def difficulty_badge(level: DifficultyLevel) -> str:
    """Return an HTML badge string for a difficulty level."""
    cfg = DIFFICULTY_CONFIG[level]
    return (
        f'<span style="'
        f'background:{cfg["bg"]};'
        f'color:{cfg["color"]};'
        f'padding:3px 10px;'
        f'border-radius:12px;'
        f'font-size:0.78em;'
        f'font-weight:600;'
        f'border:1px solid {cfg["color"]}33;'
        f'">{cfg["icon"]} {cfg["label"]}</span>'
    )


# ---------------------------------------------------------------------------
# Exercise Card
# ---------------------------------------------------------------------------

def exercise_card(
    exercise: Exercise,
    is_selected: bool = False,
    on_select: Optional[Callable] = None,
) -> bool:
    """
    Renders a single exercise card.
    Returns True if the user clicked 'Select'.
    """
    border_color = "#2D6A4F" if is_selected else "#DEE2E6"
    bg_color     = "#F0FFF4" if is_selected else "#FFFFFF"
    cfg          = DIFFICULTY_CONFIG[exercise.difficulty]
    cat_icon     = CATEGORY_ICONS.get(exercise.category, "📋")

    selected = False

    with st.container():
        st.markdown(
            f"""
            <div style="
                border: 2px solid {border_color};
                border-radius: 12px;
                padding: 16px 18px 12px 18px;
                background: {bg_color};
                margin-bottom: 4px;
                transition: border-color 0.2s;
            ">
                <div style="display:flex; justify-content:space-between; align-items:flex-start;">
                    <div>
                        <span style="font-size:1.1em; font-weight:700; color:#212529;">
                            {cat_icon} {exercise.name}
                        </span>
                        <br/>
                        <span style="font-size:0.82em; color:#6C757D;">
                            {exercise.category.value.title()} &nbsp;·&nbsp;
                            Default: {exercise.default_reps} reps
                            {f" · {exercise.default_hold_sec}s hold" if exercise.default_hold_sec else ""}
                        </span>
                    </div>
                    <div>{difficulty_badge(exercise.difficulty)}</div>
                </div>
                <p style="font-size:0.88em; color:#495057; margin:10px 0 8px 0; line-height:1.4;">
                    {exercise.description[:160]}{"…" if len(exercise.description) > 160 else ""}
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        col_btn, col_check = st.columns([3, 1])
        with col_btn:
            if st.button(
                "✓ Selected" if is_selected else "Select Exercise",
                key=f"select_{exercise.slug}",
                use_container_width=True,
                type="primary" if not is_selected else "secondary",
            ):
                selected = True

        with col_check:
            if is_selected:
                st.markdown(
                    '<div style="text-align:center;font-size:1.5em;color:#2D6A4F;">✓</div>',
                    unsafe_allow_html=True,
                )

    return selected


# ---------------------------------------------------------------------------
# Exercise Detail Expander
# ---------------------------------------------------------------------------

def exercise_detail_panel(exercise: Exercise) -> None:
    """Shows full exercise details in an expander."""
    with st.expander(f"📖 Full details: {exercise.name}", expanded=False):
        st.markdown(f"**Description:** {exercise.description}")

        st.markdown("**Step-by-step instructions:**")
        for i, step in enumerate(exercise.instructions, 1):
            st.markdown(f"{i}. {step}")

        col1, col2, col3 = st.columns(3)
        col1.metric("Default Reps", exercise.default_reps)
        col2.metric("Hold Time", f"{exercise.default_hold_sec}s" if exercise.default_hold_sec else "None")
        col3.metric("Cadence", f"~{exercise.rep_cadence_target_sec}s/rep")

        if exercise.contraindications:
            st.warning(
                "⚠️ **Precautions:** " + "; ".join(exercise.contraindications),
                icon="⚠️",
            )

        if exercise.progression_to:
            st.info(f"📈 **Next progression:** {exercise.progression_to.replace('_', ' ').title()}")

        if exercise.tags:
            tags_html = " ".join(
                f'<span style="background:#E9ECEF;color:#495057;padding:2px 8px;'
                f'border-radius:10px;font-size:0.75em;margin-right:4px;">{t}</span>'
                for t in exercise.tags
            )
            st.markdown(f"**Tags:** {tags_html}", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Session Summary Card (for confirmation screen)
# ---------------------------------------------------------------------------

def session_summary_card(
    exercise: Exercise,
    reps: int,
    hold_sec: int,
    difficulty: DifficultyLevel,
    sets: int,
    pain_level: int,
) -> None:
    """Renders a summary of the configured session before the user confirms."""
    cfg = DIFFICULTY_CONFIG[difficulty]

    # Estimate session duration
    rep_time = exercise.rep_cadence_target_sec + hold_sec + exercise.rest_between_reps_sec
    total_sec = reps * rep_time * sets
    duration_str = (
        f"{total_sec/60:.1f} min" if total_sec >= 60
        else f"{int(total_sec)}s"
    )

    st.markdown(
        f"""
        <div style="
            background: linear-gradient(135deg, #F0FFF4 0%, #E8F5E9 100%);
            border: 2px solid #2D6A4F;
            border-radius: 14px;
            padding: 20px 24px;
            margin: 8px 0 16px 0;
        ">
            <div style="font-size:1.3em; font-weight:700; color:#2D6A4F; margin-bottom:4px;">
                🏥 Session Ready
            </div>
            <div style="font-size:1.15em; font-weight:600; color:#212529; margin-bottom:16px;">
                {exercise.name}
            </div>
            <div style="display:grid; grid-template-columns:1fr 1fr 1fr; gap:12px; margin-bottom:14px;">
                <div style="text-align:center;">
                    <div style="font-size:1.8em; font-weight:700; color:#2D6A4F;">{reps}</div>
                    <div style="font-size:0.78em; color:#6C757D; text-transform:uppercase; letter-spacing:.5px;">REPS</div>
                </div>
                <div style="text-align:center;">
                    <div style="font-size:1.8em; font-weight:700; color:#2D6A4F;">{hold_sec}s</div>
                    <div style="font-size:0.78em; color:#6C757D; text-transform:uppercase; letter-spacing:.5px;">HOLD</div>
                </div>
                <div style="text-align:center;">
                    <div style="font-size:1.8em; font-weight:700; color:#2D6A4F;">{sets}</div>
                    <div style="font-size:0.78em; color:#6C757D; text-transform:uppercase; letter-spacing:.5px;">SETS</div>
                </div>
            </div>
            <div style="display:flex; gap:10px; flex-wrap:wrap; align-items:center;">
                {difficulty_badge(difficulty)}
                <span style="font-size:0.82em; color:#6C757D;">⏱ Est. {duration_str}</span>
                <span style="font-size:0.82em; color:#6C757D;">
                    {'🟡 Pain: ' + str(pain_level) + '/10' if pain_level > 0 else ''}
                </span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Metric Cards Row (for home screen stats)
# ---------------------------------------------------------------------------

def metric_cards_row(stats: dict) -> None:
    """Renders a row of 4 KPI metric cards."""
    col1, col2, col3, col4 = st.columns(4)

    metrics = [
        (col1, "🏋️ Total Sessions", stats.get("total_sessions", 0), ""),
        (col2, "🔁 Total Reps",     stats.get("total_reps", 0), ""),
        (col3, "🔥 Streak",         stats.get("streak_days", 0), "days"),
        (col4, "✅ Completion",     f"{stats.get('completion_rate_pct', 0):.0f}", "%"),
    ]

    for col, label, value, unit in metrics:
        col.markdown(
            f"""
            <div style="
                background:#FFFFFF;
                border:1px solid #DEE2E6;
                border-radius:10px;
                padding:14px 12px;
                text-align:center;
            ">
                <div style="font-size:0.78em; color:#6C757D; margin-bottom:4px;">{label}</div>
                <div style="font-size:1.9em; font-weight:700; color:#2D6A4F;">
                    {value}<span style="font-size:0.5em; color:#6C757D;">{unit}</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


# ---------------------------------------------------------------------------
# Pain Level Selector
# ---------------------------------------------------------------------------

def pain_level_selector(default: int = 0) -> int:
    """
    Returns a pain level 0–10.
    VAS (Visual Analogue Scale) standard used in physiotherapy.
    """
    st.markdown("**Current Pain Level** (Visual Analogue Scale, 0 = no pain)")
    pain = st.slider(
        label="Pain Level",
        min_value=0,
        max_value=10,
        value=default,
        step=1,
        help=(
            "0 = No pain at all  |  "
            "1–3 = Mild  |  "
            "4–6 = Moderate  |  "
            "7–10 = Severe. "
            "If pain is 7 or above, please consult your physiotherapist before exercising."
        ),
        label_visibility="collapsed",
    )

    # Colour-coded feedback
    if pain == 0:
        st.caption("✅ No pain — great!")
    elif pain <= 3:
        st.caption("🟢 Mild discomfort — proceed with care.")
    elif pain <= 6:
        st.caption("🟡 Moderate pain — exercise gently, stop if it worsens.")
    else:
        st.caption("🔴 High pain — please consult your physiotherapist before this session.")

    return pain


# ---------------------------------------------------------------------------
# Page header with back button
# ---------------------------------------------------------------------------

def page_header(title: str, subtitle: str = "", show_back: bool = True) -> bool:
    """
    Renders a consistent page header.
    Returns True if the user clicked Back.
    """
    went_back = False
    if show_back:
        if st.button("← Back", key=f"back_{title.replace(' ', '_')}"):
            went_back = True

    st.markdown(
        f"""
        <div style="margin: 4px 0 20px 0;">
            <h2 style="color:#2D6A4F; margin:0; font-size:1.6em;">{title}</h2>
            {"<p style='color:#6C757D; margin:4px 0 0 0; font-size:0.9em;'>" + subtitle + "</p>" if subtitle else ""}
        </div>
        """,
        unsafe_allow_html=True,
    )
    return went_back
