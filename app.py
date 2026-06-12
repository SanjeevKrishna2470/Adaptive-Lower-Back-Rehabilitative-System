"""
app.py
======
RehabAI — Lower Back Rehabilitation System
Feature 1: Exercise Selection and Rep Setting

Entry point for the Streamlit application.
Run with:  streamlit run app.py

Architecture:
- Single-file router pattern: screen() functions are called based on
  st.session_state[CURRENT_SCREEN].
- Each screen function is self-contained: it renders UI, handles interactions,
  and calls state_manager to transition state.
- No screen function imports another screen — they only call state_manager.

Adding Feature 2 (Pose Tracking):
- Add Screen.SESSION case to the router below.
- Implement screen_session() in a new file.
- That function reads get_active_session() and get_selected_exercise().
- Feature 1 code here does NOT change.
"""

import streamlit as st

# ── Page config must be the first Streamlit call ──────────────────────────
st.set_page_config(
    page_title="RehabAI",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Internal imports ───────────────────────────────────────────────────────
from utils.state_manager import (
    init_state, navigate_to, get_current_screen,
    get_selected_exercise, select_exercise, clear_selected_exercise,
    create_session, get_active_session, get_user_profile,
    get_session_history, abandon_active_session,
    Screen, StateKeys,
)
from utils.validation import validate_session_config
from utils.analytics import (
    plot_session_frequency, plot_reps_over_time,
    plot_exercise_distribution, compute_summary_stats,
)
from data.exercise_db import (
    get_all_exercises, get_exercise_by_slug,
    get_exercises_by_difficulty, get_exercises_by_category,
)
from models.exercise_model import (
    DifficultyLevel, ExerciseCategory, SessionStatus
)
from components.ui_components import (
    exercise_card, exercise_detail_panel, session_summary_card,
    metric_cards_row, pain_level_selector, page_header, difficulty_badge,
    CATEGORY_ICONS,
)

# ── Global CSS ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
    /* Root variables */
    :root {
        --primary:    #2D6A4F;
        --accent:     #52B788;
        --light-bg:   #F0FFF4;
        --text:       #212529;
        --muted:      #6C757D;
        --border:     #DEE2E6;
    }

    /* Global reset */
    .stApp { background-color: #F8F9FA; }
    .block-container { padding-top: 1.5rem; max-width: 900px; }

    /* Button overrides */
    .stButton > button[kind="primary"] {
        background-color: #2D6A4F !important;
        border-color: #2D6A4F !important;
        color: white !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
    }
    .stButton > button[kind="primary"]:hover {
        background-color: #1B4332 !important;
    }
    .stButton > button[kind="secondary"] {
        border-radius: 8px !important;
        font-weight: 500 !important;
    }

    /* Remove Streamlit default padding on metric */
    div[data-testid="metric-container"] { padding: 0; }

    /* Slider accent */
    div[data-testid="stSlider"] > div > div > div {
        background-color: #2D6A4F !important;
    }

    /* Selectbox and number input */
    .stSelectbox > div, .stNumberInput > div {
        border-radius: 8px !important;
    }

    /* Divider */
    hr { border-color: #DEE2E6; margin: 20px 0; }

    /* Info/Warning overrides */
    div[data-testid="stAlert"] { border-radius: 8px; }

    /* Success banner */
    .success-banner {
        background: linear-gradient(135deg, #D8F3DC 0%, #B7E4C7 100%);
        border: 1px solid #52B788;
        border-radius: 12px;
        padding: 16px 20px;
        margin: 12px 0;
        color: #1B4332;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)


# ===========================================================================
# SCREEN: HOME
# ===========================================================================

def screen_home() -> None:
    """
    Home screen: greeting, stats overview, quick start, and history preview.
    """
    profile  = get_user_profile()
    history  = get_session_history()
    stats    = compute_summary_stats(history)
    active   = get_active_session()

    # ── Header ────────────────────────────────────────────────────────────
    st.markdown(
        f"""
        <div style="
            background: linear-gradient(135deg, #2D6A4F 0%, #1B4332 100%);
            border-radius: 16px;
            padding: 24px 28px;
            margin-bottom: 20px;
            color: white;
        ">
            <div style="font-size:0.9em; opacity:0.8; margin-bottom:4px;">
                Lower Back Rehabilitation
            </div>
            <div style="font-size:1.9em; font-weight:700;">
                Good {_time_greeting()}, {profile.name} 👋
            </div>
            <div style="font-size:0.88em; opacity:0.75; margin-top:6px;">
                {"🔥 " + str(stats["streak_days"]) + "-day streak — keep it up!" if stats["streak_days"] > 0 else "Ready to start your rehabilitation today?"}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Active session banner (if user has a configured session) ──────────
    if active and active.status == SessionStatus.CONFIGURED:
        st.markdown(
            f"""
            <div class="success-banner">
                ⏳ Session ready: <strong>{active.exercise_name}</strong>
                — {active.reps} reps{f", {active.hold_sec}s hold" if active.hold_sec else ""}
            </div>
            """,
            unsafe_allow_html=True,
        )
        col1, col2 = st.columns(2)
        col1.button(
            "▶ Start Session",
            use_container_width=True,
            type="primary",
            key="home_start_active",
            on_click=lambda: navigate_to(Screen.CONFIRM),
        )
        col2.button(
            "✗ Cancel",
            use_container_width=True,
            key="home_cancel_session",
            on_click=abandon_active_session,
        )
        st.divider()

    # ── KPI metric cards ──────────────────────────────────────────────────
    if stats["total_sessions"] > 0:
        st.markdown("#### Your Progress")
        metric_cards_row(stats)
        st.markdown("<br>", unsafe_allow_html=True)

    # ── Quick start button ────────────────────────────────────────────────
    col_a, col_b = st.columns([2, 1])
    with col_a:
        if st.button(
            "🏋️  Start New Exercise Session",
            use_container_width=True,
            type="primary",
            key="home_new_session",
        ):
            navigate_to(Screen.EXERCISE_LIST)

    # ── Progress charts ───────────────────────────────────────────────────
    if history:
        st.divider()
        st.markdown("#### Activity Overview")

        tab1, tab2, tab3 = st.tabs(["📅 Frequency", "📈 Progression", "🥧 Distribution"])

        with tab1:
            fig = plot_session_frequency(history, days=14)
            st.pyplot(fig, use_container_width=True)

        with tab2:
            # Show rep progression for the most-done exercise
            exercise_counts = {}
            for s in history:
                slug = s.get("exercise_slug", "")
                exercise_counts[slug] = exercise_counts.get(slug, 0) + 1
            if exercise_counts:
                top_slug = max(exercise_counts, key=exercise_counts.get)
                fig2 = plot_reps_over_time(history, top_slug)
                if fig2:
                    ex = get_exercise_by_slug(top_slug)
                    st.caption(f"Showing progression for: **{ex.name if ex else top_slug}**")
                    st.pyplot(fig2, use_container_width=True)
                else:
                    st.info("Complete more sessions to see your progression trend.")

        with tab3:
            fig3 = plot_exercise_distribution(history)
            if fig3:
                st.pyplot(fig3, use_container_width=True)

        # ── Recent sessions list ──────────────────────────────────────────
        st.divider()
        st.markdown("#### Recent Sessions")
        recent = [s for s in history[:5]]
        for s in recent:
            status_icon = {"completed": "✅", "abandoned": "❌", "configured": "⏳"}.get(
                s.get("status", ""), "📋"
            )
            date_str = ""
            try:
                dt = s.get("completed_at") or s.get("created_at", "")
                if dt:
                    from datetime import datetime
                    date_str = datetime.fromisoformat(dt).strftime("%d %b %Y, %H:%M")
            except Exception:
                pass

            st.markdown(
                f"""
                <div style="
                    border:1px solid #DEE2E6;
                    border-radius:8px;
                    padding:10px 14px;
                    margin-bottom:6px;
                    background:white;
                    display:flex;
                    justify-content:space-between;
                ">
                    <span>{status_icon} <strong>{s.get("exercise_name", "—")}</strong></span>
                    <span style="color:#6C757D; font-size:0.85em;">
                        {s.get("reps", 0)} reps &nbsp;·&nbsp; {date_str}
                    </span>
                </div>
                """,
                unsafe_allow_html=True,
            )
    else:
        # Empty state
        st.markdown(
            """
            <div style="
                text-align:center;
                padding:40px 20px;
                color:#6C757D;
            ">
                <div style="font-size:3em;">🏥</div>
                <div style="font-size:1.1em; margin-top:10px; font-weight:600; color:#495057;">
                    No sessions yet
                </div>
                <div style="font-size:0.88em; margin-top:6px;">
                    Select an exercise above to begin your rehabilitation programme.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


# ===========================================================================
# SCREEN: EXERCISE LIST
# ===========================================================================

def screen_exercise_list() -> None:
    """
    Exercise selection screen.
    User picks an exercise; selection is stored in session_state.
    """
    went_back = page_header(
        "Select Exercise",
        "Choose the exercise prescribed by your physiotherapist.",
    )
    if went_back:
        navigate_to(Screen.HOME)
        return

    selected = get_selected_exercise()

    # ── Filter controls ────────────────────────────────────────────────────
    with st.expander("🔍 Filter exercises", expanded=False):
        col1, col2 = st.columns(2)
        filter_difficulty = col1.selectbox(
            "Difficulty",
            options=["All"] + [d.value.title() for d in DifficultyLevel],
            key="filter_difficulty",
        )
        filter_category = col2.selectbox(
            "Category",
            options=["All"] + [c.value.title() for c in ExerciseCategory],
            key="filter_category",
        )

    # ── Exercise list ─────────────────────────────────────────────────────
    exercises = get_all_exercises()

    # Apply filters
    if filter_difficulty != "All":
        target_d = DifficultyLevel(filter_difficulty.lower())
        exercises = [e for e in exercises if e.difficulty == target_d]
    if filter_category != "All":
        target_c = ExerciseCategory(filter_category.lower())
        exercises = [e for e in exercises if e.category == target_c]

    if not exercises:
        st.info("No exercises match your filters. Try adjusting the criteria.")
        return

    st.caption(f"Showing {len(exercises)} exercise{'s' if len(exercises) != 1 else ''}")

    for exercise in exercises:
        is_sel = selected and selected.slug == exercise.slug

        if exercise_card(exercise, is_selected=is_sel):
            select_exercise(exercise)
            navigate_to(Screen.CONFIGURE)
            return

        exercise_detail_panel(exercise)

    # ── Sticky bottom: proceed if selection made ──────────────────────────
    if selected:
        st.divider()
        st.success(f"✓ **{selected.name}** selected — tap 'Configure' to set your reps.")
        if st.button("Configure Session →", type="primary", use_container_width=True):
            navigate_to(Screen.CONFIGURE)


# ===========================================================================
# SCREEN: CONFIGURE
# ===========================================================================

def screen_configure() -> None:
    """
    Rep and hold configuration screen.
    Validates input, creates SessionConfig on confirmation.
    """
    exercise = get_selected_exercise()
    if not exercise:
        st.error("No exercise selected. Please go back and pick one.")
        if st.button("← Back to Exercises"):
            navigate_to(Screen.EXERCISE_LIST)
        return

    went_back = page_header(
        f"Configure: {exercise.name}",
        "Set your repetitions, hold time, and difficulty.",
    )
    if went_back:
        navigate_to(Screen.EXERCISE_LIST)
        return

    # ── Exercise quick-reference ──────────────────────────────────────────
    st.markdown(
        f"""
        <div style="
            background:#F8F9FA;
            border-left:4px solid #2D6A4F;
            padding:12px 16px;
            border-radius:0 8px 8px 0;
            margin-bottom:20px;
        ">
            <strong>{exercise.name}</strong> &nbsp;
            {difficulty_badge(exercise.difficulty)} &nbsp;
            <span style="font-size:0.82em; color:#6C757D;">
                {exercise.category.value.title()}
            </span>
            <br/>
            <span style="font-size:0.85em; color:#495057;">{exercise.description[:120]}…</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Configuration form ────────────────────────────────────────────────
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### Rep Settings")

        reps = st.number_input(
            f"Number of Reps (min {exercise.min_reps}, max {exercise.max_reps})",
            min_value=1,
            max_value=exercise.max_reps,
            value=exercise.default_reps,
            step=1,
            key="config_reps",
            help=f"This exercise is most effective between {exercise.min_reps}–{exercise.max_reps} reps.",
        )

        hold_sec = st.slider(
            f"Hold Time per Rep (seconds)",
            min_value=0,
            max_value=exercise.max_hold_sec,
            value=exercise.default_hold_sec,
            step=1,
            key="config_hold",
            help="0 = no hold (just the movement). Increases time-under-tension.",
        )

        sets = st.number_input(
            "Number of Sets",
            min_value=1,
            max_value=5,
            value=1,
            step=1,
            key="config_sets",
            help="Start with 1 set for the first few sessions.",
        )

    with col2:
        st.markdown("#### Difficulty & Safety")

        difficulty_labels = {
            DifficultyLevel.BEGINNER:     "🟢 Beginner",
            DifficultyLevel.INTERMEDIATE: "🟡 Intermediate",
            DifficultyLevel.ADVANCED:     "🔴 Advanced",
        }
        difficulty_options = list(difficulty_labels.keys())

        # Default to the exercise's prescribed difficulty
        default_diff_idx = difficulty_options.index(exercise.difficulty)

        chosen_diff_label = st.selectbox(
            "AI Form Strictness / Difficulty",
            options=list(difficulty_labels.values()),
            index=default_diff_idx,
            key="config_difficulty",
            help=(
                "This controls how strictly the AI evaluates your form. "
                "Beginner = more lenient; Advanced = tightest angle tolerances."
            ),
        )
        # Reverse-map label → enum
        difficulty = next(
            k for k, v in difficulty_labels.items()
            if v == chosen_diff_label
        )

        st.markdown("<br>", unsafe_allow_html=True)
        pain_level = pain_level_selector(default=0)

    # ── Live validation ────────────────────────────────────────────────────
    result = validate_session_config(
        exercise=exercise,
        reps=int(reps),
        hold_sec=int(hold_sec),
        difficulty=difficulty,
        sets=int(sets),
    )

    # Display validation errors
    if not result.is_valid:
        for error in result.error_messages:
            st.error(f"⛔ {error}")

    # Display warnings (non-blocking)
    for warning in result.warnings:
        st.warning(f"⚠️ {warning}")

    # ── Pain gate ─────────────────────────────────────────────────────────
    if pain_level >= 7:
        st.error(
            "🔴 **Pain level too high to safely exercise.** "
            "Please contact your physiotherapist before proceeding."
        )

    # ── Estimated duration ────────────────────────────────────────────────
    rep_time    = exercise.rep_cadence_target_sec + hold_sec + exercise.rest_between_reps_sec
    total_sec   = reps * rep_time * sets
    duration_str = f"{total_sec/60:.1f} min" if total_sec >= 60 else f"{int(total_sec)}s"
    st.caption(f"⏱ Estimated duration: **{duration_str}**")

    st.divider()

    # ── Action buttons ────────────────────────────────────────────────────
    col_confirm, col_reset = st.columns([3, 1])

    with col_confirm:
        can_proceed = result.is_valid and pain_level < 7
        if st.button(
            "Review Session →",
            type="primary",
            use_container_width=True,
            disabled=not can_proceed,
            key="config_confirm",
        ):
            create_session(
                exercise=exercise,
                reps=int(reps),
                hold_sec=int(hold_sec),
                difficulty=difficulty,
                sets=int(sets),
                pain_level=pain_level,
            )
            navigate_to(Screen.CONFIRM)

    with col_reset:
        if st.button("Reset", use_container_width=True, key="config_reset"):
            # Streamlit reruns and widget defaults are restored
            st.rerun()

    # ── Instructions reminder ─────────────────────────────────────────────
    with st.expander("📋 Exercise Instructions", expanded=False):
        for i, step in enumerate(exercise.instructions, 1):
            st.markdown(f"**{i}.** {step}")


# ===========================================================================
# SCREEN: CONFIRM
# ===========================================================================

def screen_confirm() -> None:
    """
    Session confirmation screen — final review before starting.
    """
    config   = get_active_session()
    exercise = get_exercise_by_slug(config.exercise_slug) if config else None

    if not config or not exercise:
        st.error("Session configuration lost. Please start again.")
        if st.button("← Home"):
            navigate_to(Screen.HOME)
        return

    went_back = page_header("Confirm Your Session", "Review and begin when ready.")
    if went_back:
        navigate_to(Screen.CONFIGURE)
        return

    # ── Summary card ──────────────────────────────────────────────────────
    session_summary_card(
        exercise=exercise,
        reps=config.reps,
        hold_sec=config.hold_sec,
        difficulty=config.difficulty,
        sets=config.sets,
        pain_level=get_user_profile().pain_level,
    )

    # ── Instructions ──────────────────────────────────────────────────────
    st.markdown("#### What to expect")
    cols = st.columns(len(exercise.instructions[:4]))
    for i, (col, step) in enumerate(zip(cols, exercise.instructions[:4]), 1):
        col.markdown(
            f"""
            <div style="
                background:#F0FFF4;
                border-radius:8px;
                padding:10px 12px;
                font-size:0.82em;
                color:#2D6A4F;
                height:100%;
                border:1px solid #B7E4C7;
            ">
                <strong>Step {i}</strong><br/>{step}
            </div>
            """,
            unsafe_allow_html=True,
        )

    # ── Pre-session checklist ─────────────────────────────────────────────
    st.markdown("#### Pre-session checklist")
    checks = [
        "I have a clear, non-slip area to exercise.",
        "I have a mat or soft surface (for floor exercises).",
        "My camera/device is positioned to see my full body.",
        "I have my physiotherapist's contact available if needed.",
    ]
    all_checked = True
    for check in checks:
        if not st.checkbox(check, key=f"check_{check[:20]}"):
            all_checked = False

    if exercise.contraindications:
        st.markdown("#### Safety reminder")
        for c in exercise.contraindications:
            st.warning(f"⚠️ {c}")

    st.divider()

    # ── Final action buttons ──────────────────────────────────────────────
    col_start, col_back = st.columns([3, 1])

    with col_start:
        if st.button(
            "▶  Begin Session",
            type="primary",
            use_container_width=True,
            disabled=not all_checked,
            key="confirm_start",
        ):
            # Feature 1 ends here.
            # Feature 2 (Pose Tracking) will be triggered from Screen.SESSION.
            # For now, mark as active and show a placeholder.
            config.start()
            st.session_state[StateKeys.ACTIVE_SESSION] = config
            navigate_to(Screen.SESSION)

    with col_back:
        if st.button("Edit", use_container_width=True, key="confirm_back"):
            navigate_to(Screen.CONFIGURE)


# ===========================================================================
# SCREEN: SESSION (Feature 2 Placeholder)
# ===========================================================================

def screen_session() -> None:
    """
    Placeholder for Feature 2 (MediaPipe Pose Tracking).
    Shows the active session config and simulates session completion.
    """
    config   = get_active_session()
    exercise = get_exercise_by_slug(config.exercise_slug) if config else None

    if not config or not exercise:
        navigate_to(Screen.HOME)
        return

    page_header("Active Session", show_back=False)

    st.info(
        "🔧 **Feature 2 (MediaPipe Pose Tracking) will render here.**\n\n"
        "The active session configuration is fully loaded and available:\n"
        f"- Exercise: **{exercise.name}**\n"
        f"- Reps: **{config.reps}**\n"
        f"- Hold: **{config.hold_sec}s**\n"
        f"- Difficulty: **{config.difficulty.value.title()}**\n"
        f"- Session ID: `{config.session_id}`",
    )

    # Temporary: allow user to manually complete the session for testing
    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        if st.button("✅ Mark Complete (dev)", type="primary", use_container_width=True):
            from utils.state_manager import complete_active_session
            complete_active_session()
            st.success("Session completed!")
            navigate_to(Screen.HOME)
    with col2:
        if st.button("✗ Abandon Session", use_container_width=True):
            abandon_active_session()
            navigate_to(Screen.HOME)


# ===========================================================================
# ROUTER
# ===========================================================================

def main() -> None:
    # Initialise state on every rerun (idempotent)
    init_state()

    # Route to correct screen
    screen = get_current_screen()
    routes = {
        Screen.HOME:          screen_home,
        Screen.EXERCISE_LIST: screen_exercise_list,
        Screen.CONFIGURE:     screen_configure,
        Screen.CONFIRM:       screen_confirm,
        Screen.SESSION:       screen_session,
    }

    handler = routes.get(screen, screen_home)
    handler()

    # ── Footer ─────────────────────────────────────────────────────────────
    st.markdown(
        """
        <div style="
            text-align:center;
            color:#ADB5BD;
            font-size:0.75em;
            margin-top:40px;
            padding-top:16px;
            border-top:1px solid #DEE2E6;
        ">
            RehabAI · Feature 1: Exercise Selection &amp; Rep Setting ·
            Always follow your physiotherapist's advice.
        </div>
        """,
        unsafe_allow_html=True,
    )


# ===========================================================================
# HELPERS
# ===========================================================================

def _time_greeting() -> str:
    from datetime import datetime
    hour = datetime.now().hour
    if hour < 12:  return "Morning"
    if hour < 17:  return "Afternoon"
    return "Evening"


# ===========================================================================
# ENTRY POINT
# ===========================================================================

if __name__ == "__main__":
    main()
