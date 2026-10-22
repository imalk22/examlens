"""Plotly figure builders. No Streamlit code lives here."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

PASS_COLOR = "#34C759"
FAIL_COLOR = "#FF3B30"
ABSENT_COLOR = "#8E8E93"
ACCENT = "#007AFF"
FONT = '-apple-system, BlinkMacSystemFont, "SF Pro Text", Inter, "Segoe UI", sans-serif'
GRID = "rgba(60,60,67,0.10)"
RESULT_COLORS = {"Pass": PASS_COLOR, "Fail": FAIL_COLOR, "Absent": ABSENT_COLOR}
GRADE_ORDER = ["A", "B", "C", "D", "F"]
GRADE_COLORS = {"A": "#34C759", "B": "#30B0C7", "C": "#007AFF", "D": "#FF9500", "F": "#FF3B30"}
PALETTE = ["#007AFF", "#5856D6", "#30B0C7", "#FF9500", "#AF52DE", "#FF2D55"]


def _style(fig: go.Figure, title: str, x: str, y: str) -> go.Figure:
    fig.update_layout(
        title=title,
        xaxis_title=x,
        yaxis_title=y,
        margin={"l": 10, "r": 10, "t": 56, "b": 10},
        template="plotly_white",
        legend_title_text="",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"family": FONT, "color": "#1C1C1E", "size": 12},
        title_font={"family": FONT, "size": 17, "color": "#1C1C1E"},
        title_x=0.02,
        bargap=0.35,
        colorway=PALETTE,
    )
    muted = {"color": "#8E8E93", "size": 11}
    fig.update_xaxes(showgrid=False, showline=False, title_font=muted, tickfont=muted)
    fig.update_yaxes(gridcolor=GRID, zeroline=False, title_font=muted, tickfont=muted)
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
    fig.update_traces(line={"width": 3, "shape": "spline"}, marker={"size": 8})
    if color is None:
        fig.update_traces(fill="tozeroy", fillcolor="rgba(0,122,255,0.08)")
    fig.update_yaxes(range=[0, 100])
    return _style(fig, "Pass rate by exam session", "Exam session", "Pass rate (%)")


def grade_distribution(df: pd.DataFrame) -> go.Figure:
    """Bar chart of grade counts."""
    counts = (
        df["grade"].value_counts().reindex(GRADE_ORDER, fill_value=0).rename_axis("grade")
    ).reset_index(name="count")
    fig = px.bar(counts, x="grade", y="count", color="grade", color_discrete_map=GRADE_COLORS)
    fig.update_layout(showlegend=False)
    return _style(fig, "Grade distribution", "Grade", "Number of results")


def pass_rate_by_group(rates: pd.DataFrame, group: str) -> go.Figure:
    """Bar chart of pass rate for each value of ``group`` (columns: group, pass_rate)."""
    data = rates.assign(pass_pct=rates["pass_rate"] * 100)
    fig = px.bar(data, x=group, y="pass_pct", color=group, color_discrete_sequence=PALETTE)
    fig.update_layout(showlegend=False)
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


def risk_donut(counts: dict[str, int]) -> go.Figure:
    """Donut of students by risk level."""
    levels = ["High", "Medium", "Low"]
    colors = {"High": FAIL_COLOR, "Medium": "#FF9500", "Low": PASS_COLOR}
    fig = go.Figure(
        go.Pie(
            labels=levels,
            values=[counts.get(level, 0) for level in levels],
            hole=0.68,
            sort=False,
            marker={
                "colors": [colors[level] for level in levels],
                "line": {"color": "#fff", "width": 3},
            },
            textinfo="none",
            hovertemplate="%{label}: %{value} students (%{percent})<extra></extra>",
        )
    )
    total = sum(counts.values())
    fig.update_layout(
        title="Students by risk level",
        title_font={"family": FONT, "size": 17, "color": "#1C1C1E"},
        title_x=0.02,
        margin={"l": 10, "r": 10, "t": 56, "b": 10},
        paper_bgcolor="rgba(0,0,0,0)",
        font={"family": FONT, "size": 12},
        legend={"orientation": "v", "y": 0.5},
        annotations=[
            {"text": f"<b>{total:,}</b><br>students", "showarrow": False, "font": {"size": 15}}
        ],
    )
    return fig


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
    fig.update_layout(
        title=title,
        template="plotly_white",
        margin={"l": 10, "r": 10, "t": 56},
        paper_bgcolor="rgba(0,0,0,0)",
        font={"family": FONT, "color": "#1C1C1E", "size": 12},
        title_font={"family": FONT, "size": 16},
        title_x=0.02,
    )
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
