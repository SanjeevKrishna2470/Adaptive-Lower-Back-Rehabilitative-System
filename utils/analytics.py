"""
utils/analytics.py
==================
Progress analytics for the rehabilitation system.

Uses NumPy for computation and Matplotlib for charts.
Matplotlib figures are returned as objects — the UI layer
decides how to render them (st.pyplot()).

This module is pure computation — no Streamlit imports.
"""

from __future__ import annotations
from typing import List, Dict, Optional, Tuple
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.figure import Figure
from datetime import datetime, timedelta
from collections import defaultdict

from models.exercise_model import DifficultyLevel, SessionStatus


# ---------------------------------------------------------------------------
# Colour palette — consistent across all charts
# ---------------------------------------------------------------------------

PALETTE = {
    "primary":      "#2D6A4F",   # Deep clinic green
    "accent":       "#52B788",   # Mid green
    "light":        "#B7E4C7",   # Pale green (background fill)
    "beginner":     "#52B788",
    "intermediate": "#F4A261",
    "advanced":     "#E76F51",
    "completed":    "#2D6A4F",
    "abandoned":    "#ADB5BD",
    "background":   "#F8F9FA",
    "grid":         "#DEE2E6",
    "text":         "#212529",
}

DIFFICULTY_COLORS = {
    DifficultyLevel.BEGINNER:     PALETTE["beginner"],
    DifficultyLevel.INTERMEDIATE: PALETTE["intermediate"],
    DifficultyLevel.ADVANCED:     PALETTE["advanced"],
}


def _style_axes(ax: plt.Axes) -> None:
    """Apply consistent styling to a matplotlib axes."""
    ax.set_facecolor(PALETTE["background"])
    ax.grid(True, color=PALETTE["grid"], linewidth=0.7, linestyle="--", alpha=0.8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(PALETTE["grid"])
    ax.spines["bottom"].set_color(PALETTE["grid"])
    ax.tick_params(colors=PALETTE["text"], labelsize=9)
    ax.title.set_color(PALETTE["text"])
    ax.xaxis.label.set_color(PALETTE["text"])
    ax.yaxis.label.set_color(PALETTE["text"])


# ---------------------------------------------------------------------------
# 1. Session frequency chart — sessions per day over last N days
# ---------------------------------------------------------------------------

def plot_session_frequency(history: List[Dict], days: int = 14) -> Figure:
    """
    Bar chart: number of sessions completed per day over the last N days.
    Uses NumPy for date bucketing.
    """
    fig, ax = plt.subplots(figsize=(8, 3.5))
    fig.patch.set_facecolor(PALETTE["background"])

    # Build date range
    today = datetime.utcnow().date()
    date_range = [today - timedelta(days=i) for i in range(days - 1, -1, -1)]
    date_labels = [d.strftime("%d %b") for d in date_range]

    # Count sessions per day
    counts = np.zeros(days, dtype=int)
    for session in history:
        if session.get("status") != SessionStatus.COMPLETED.value:
            continue
        completed_at = session.get("completed_at")
        if not completed_at:
            continue
        try:
            session_date = datetime.fromisoformat(completed_at).date()
            if session_date in date_range:
                idx = date_range.index(session_date)
                counts[idx] += 1
        except (ValueError, TypeError):
            continue

    # Bar colours: today is accent, past days are lighter
    bar_colors = [PALETTE["accent"] if i == days - 1 else PALETTE["light"]
                  for i in range(days)]

    bars = ax.bar(date_labels, counts, color=bar_colors, width=0.6, zorder=3)

    # Annotate non-zero bars
    for bar, count in zip(bars, counts):
        if count > 0:
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.05,
                str(count),
                ha="center", va="bottom",
                fontsize=9, color=PALETTE["text"], fontweight="bold",
            )

    ax.set_title("Sessions Completed (Last 14 Days)", fontsize=12, fontweight="bold", pad=10)
    ax.set_ylabel("Sessions", fontsize=9)
    ax.set_ylim(0, max(counts.max() + 1, 4))
    ax.set_xticks(range(0, days, 2))
    ax.set_xticklabels([date_labels[i] for i in range(0, days, 2)], rotation=30, ha="right")
    _style_axes(ax)
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# 2. Reps over time — per exercise trend line
# ---------------------------------------------------------------------------

def plot_reps_over_time(history: List[Dict], exercise_slug: str) -> Optional[Figure]:
    """
    Line chart showing rep counts across sessions for a given exercise.
    Returns None if fewer than 2 data points (nothing to trend).
    """
    sessions = [
        s for s in history
        if s.get("exercise_slug") == exercise_slug
        and s.get("status") == SessionStatus.COMPLETED.value
    ]

    if len(sessions) < 2:
        return None

    sessions_sorted = sorted(sessions, key=lambda s: s.get("created_at", ""))

    dates = []
    reps  = []
    for s in sessions_sorted:
        try:
            dates.append(datetime.fromisoformat(s["created_at"]))
            reps.append(s.get("reps", 0))
        except (KeyError, ValueError):
            continue

    if len(dates) < 2:
        return None

    reps_arr  = np.array(reps)
    x_indices = np.arange(len(dates))

    # Trend line via numpy polyfit (linear)
    if len(x_indices) >= 2:
        z = np.polyfit(x_indices, reps_arr, 1)
        trend = np.poly1d(z)
        trend_y = trend(x_indices)
    else:
        trend_y = None

    fig, ax = plt.subplots(figsize=(8, 3.5))
    fig.patch.set_facecolor(PALETTE["background"])

    ax.plot(x_indices, reps_arr, "o-", color=PALETTE["primary"],
            linewidth=2, markersize=6, zorder=4, label="Reps per session")

    if trend_y is not None:
        ax.plot(x_indices, trend_y, "--", color=PALETTE["accent"],
                linewidth=1.5, alpha=0.8, label="Trend", zorder=3)

    x_labels = [d.strftime("%d %b") for d in dates]
    ax.set_xticks(x_indices)
    ax.set_xticklabels(x_labels, rotation=30, ha="right", fontsize=8)
    ax.set_ylabel("Reps", fontsize=9)
    ax.set_title(f"Rep Progression", fontsize=12, fontweight="bold", pad=10)
    ax.legend(fontsize=8)
    _style_axes(ax)
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# 3. Exercise distribution pie chart
# ---------------------------------------------------------------------------

def plot_exercise_distribution(history: List[Dict]) -> Optional[Figure]:
    """
    Pie chart showing which exercises the user has done most.
    """
    completed = [
        s for s in history
        if s.get("status") == SessionStatus.COMPLETED.value
    ]
    if not completed:
        return None

    counts: Dict[str, int] = defaultdict(int)
    for s in completed:
        name = s.get("exercise_name", "Unknown")
        counts[name] += 1

    labels = list(counts.keys())
    sizes  = np.array(list(counts.values()))

    # Pick enough distinct colours
    cmap   = plt.cm.get_cmap("Set2", len(labels))
    colors = [cmap(i) for i in range(len(labels))]

    fig, ax = plt.subplots(figsize=(6, 4))
    fig.patch.set_facecolor(PALETTE["background"])
    ax.set_facecolor(PALETTE["background"])

    wedges, texts, autotexts = ax.pie(
        sizes,
        labels=None,
        autopct="%1.0f%%",
        colors=colors,
        startangle=140,
        pctdistance=0.82,
        wedgeprops={"linewidth": 1.5, "edgecolor": "white"},
    )
    for at in autotexts:
        at.set_fontsize(8)
        at.set_color("white")
        at.set_fontweight("bold")

    ax.legend(
        wedges, labels,
        loc="lower center",
        bbox_to_anchor=(0.5, -0.15),
        ncol=2,
        fontsize=8,
        frameon=False,
    )
    ax.set_title("Exercise Distribution", fontsize=12, fontweight="bold", pad=10)
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# 4. Summary statistics using NumPy
# ---------------------------------------------------------------------------

def compute_summary_stats(history: List[Dict]) -> Dict:
    """
    Returns a dict of summary stats for the dashboard header cards.
    Pure NumPy computation — no rendering.
    """
    completed = [
        s for s in history
        if s.get("status") == SessionStatus.COMPLETED.value
    ]

    if not completed:
        return {
            "total_sessions": 0,
            "total_reps": 0,
            "avg_reps_per_session": 0.0,
            "streak_days": 0,
            "favourite_exercise": "—",
            "completion_rate_pct": 0.0,
        }

    reps_list = np.array([s.get("reps", 0) for s in completed], dtype=float)

    # Completion rate
    total_sessions = len(history)
    completion_rate = len(completed) / total_sessions * 100 if total_sessions > 0 else 0.0

    # Streak — consecutive days with at least 1 session
    session_dates = set()
    for s in completed:
        try:
            d = datetime.fromisoformat(s["completed_at"]).date()
            session_dates.add(d)
        except (KeyError, ValueError, TypeError):
            pass

    streak = 0
    check_date = datetime.utcnow().date()
    while check_date in session_dates:
        streak += 1
        check_date -= timedelta(days=1)

    # Favourite exercise
    exercise_counts: Dict[str, int] = defaultdict(int)
    for s in completed:
        exercise_counts[s.get("exercise_name", "Unknown")] += 1
    favourite = max(exercise_counts, key=exercise_counts.get) if exercise_counts else "—"

    return {
        "total_sessions":         len(completed),
        "total_reps":             int(reps_list.sum()),
        "avg_reps_per_session":   float(np.mean(reps_list)),
        "streak_days":            streak,
        "favourite_exercise":     favourite,
        "completion_rate_pct":    round(completion_rate, 1),
    }
