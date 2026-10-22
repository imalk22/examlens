"""Plotly figure builders. No Streamlit code lives here."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

PASS_COLOR = "#16a34a"
FAIL_COLOR = "#dc2626"
ABSENT_COLOR = "#9ca3af"
ACCENT = "#2563eb"
RESULT_COLORS = {"Pass": PASS_COLOR, "Fail": FAIL_COLOR, "Absent": ABSENT_COLOR}
GRADE_ORDER = ["A", "B", "C", "D", "F"]


def _style(fig: go.Figure, title: str, x: str, y: str) -> go.Figure:
    fig.update_layout(
        title=title,
        xaxis_title=x,
        yaxis_title=y,
        margin={"l": 10, "r": 10, "t": 50, "b": 10},
        template="plotly_white",
        legend_title_text="",
    )
    return fig


def pass_rate_trend(trend: pd.DataFrame, color: str | None = None) -> go.Figure:
    """Line chart of pass rate (%) per session. ``trend`` comes from ``metrics.session_trend``."""
    data = trend.assign(pass_pct=trend["pass_rate"] * 100)
    fig = px.line(
        data,
        x="exam_session",
        y="pass_pct",
        color=color,
        markers=True,
        hover_data={"pass_pct": ":.1f", "candidates": True},
        color_discrete_sequence=[ACCENT] if color is None else None,
    )
    fig.update_yaxes(range=[0, 100])
    return _style(fig, "Pass rate by exam session", "Exam session", "Pass rate (%)")


def grade_distribution(df: pd.DataFrame) -> go.Figure:
    """Bar chart of grade counts."""
    counts = (
        df["grade"].value_counts().reindex(GRADE_ORDER, fill_value=0).rename_axis("grade")
    ).reset_index(name="count")
    fig = px.bar(counts, x="grade", y="count", color_discrete_sequence=[ACCENT])
    return _style(fig, "Grade distribution", "Grade", "Number of results")


def pass_rate_by_group(rates: pd.DataFrame, group: str) -> go.Figure:
    """Bar chart of pass rate for each value of ``group`` (columns: group, pass_rate)."""
    data = rates.assign(pass_pct=rates["pass_rate"] * 100)
    fig = px.bar(data, x=group, y="pass_pct", color_discrete_sequence=[ACCENT])
    fig.update_yaxes(range=[0, 100])
    label = group.replace("_", " ").title()
    return _style(fig, f"Pass rate by {label.lower()}", label, "Pass rate (%)")


def mark_histogram(df: pd.DataFrame, pass_mark: float) -> go.Figure:
    """Histogram of marks with a pass-mark line."""
    fig = px.histogram(df.dropna(subset=["marks"]), x="marks", nbins=20, range_x=[0, 100])
    fig.update_traces(marker_color=ACCENT)
    fig.add_vline(x=pass_mark, line_dash="dash", line_color=FAIL_COLOR, annotation_text="Pass mark")
    return _style(fig, "Mark distribution", "Marks", "Number of attempts")


def first_vs_repeat(df: pd.DataFrame, pass_rate_fn) -> go.Figure:
    """Bar chart comparing first-attempt and repeat-attempt pass rates."""
    first = pass_rate_fn(df[df["attempt_no"] == 1])
    repeat = pass_rate_fn(df[df["attempt_no"] > 1])
    data = pd.DataFrame(
        {"attempt": ["First attempt", "Repeat attempts"], "pass_pct": [first * 100, repeat * 100]}
    )
    fig = px.bar(data, x="attempt", y="pass_pct", color_discrete_sequence=[ACCENT])
    fig.update_yaxes(range=[0, 100])
    return _style(fig, "First attempt vs repeat pass rate", "Attempt type", "Pass rate (%)")


def difficulty_scatter(summary: pd.DataFrame) -> go.Figure:
    """Mean mark vs pass rate per subject; bubble size = candidates."""
    data = summary.assign(pass_pct=summary["pass_rate"] * 100)
    fig = px.scatter(
        data,
        x="mean_mark",
        y="pass_pct",
        size="candidates",
        hover_name="subject_code",
        hover_data={"subject_name": True, "difficulty_index": ":.0f", "candidates": True},
        text="subject_code",
        color_discrete_sequence=[ACCENT],
    )
    fig.update_traces(textposition="top center")
    return _style(fig, "Mean mark vs pass rate by subject", "Mean mark", "Pass rate (%)")


def attempts_distribution(counts: pd.Series, title: str) -> go.Figure:
    """Bar chart of how many attempts passes took."""
    data = counts.rename("passes").reset_index()
    data.columns = ["attempts_to_pass", "passes"]
    fig = px.bar(data, x="attempts_to_pass", y="passes", color_discrete_sequence=[ACCENT])
    fig.update_xaxes(dtick=1)
    return _style(fig, title, "Attempts needed to pass", "Student-subject passes")


def funnel_chart(funnel: dict[str, int], title: str) -> go.Figure:
    """Funnel: attempted -> passed first time -> passed second time -> outstanding."""
    stages = ["Attempted", "Passed first time", "Passed second time", "Still outstanding"]
    values = [
        funnel["attempted"],
        funnel["passed_first_time"],
        funnel["passed_second_time"],
        funnel["outstanding"],
    ]
    fig = go.Figure(go.Funnel(y=stages, x=values, marker={"color": ACCENT}))
    fig.update_layout(title=title, template="plotly_white", margin={"l": 10, "r": 10, "t": 50})
    return fig


def student_marks_chart(history: pd.DataFrame) -> go.Figure:
    """Marks over time for one student, one point per attempt, coloured by result."""
    data = history.dropna(subset=["marks"])
    fig = px.scatter(
        data,
        x="exam_session",
        y="marks",
        color="result",
        symbol="subject_code",
        color_discrete_map=RESULT_COLORS,
        hover_data=["subject_name", "attempt_no", "grade"],
        category_orders={
            "exam_session": list(history.sort_values("session_date")["exam_session"].unique())
        },
    )
    fig.update_traces(marker_size=11)
    fig.update_yaxes(range=[0, 100])
    return _style(fig, "Marks over time", "Exam session", "Marks")
