import streamlit as st
import webui

from examlens import charts, metrics

df, settings = webui.page_data(
    "Subject Analysis", "Which subjects are hardest, and how they change over time."
)

summary = webui.cached_summary(df)
labels = webui.code_labels(summary["subject_code"], summary["subject_name"])

board, detail = st.tabs(["Leaderboard", "Subject detail"])

with board:
    left, right = st.columns([5, 3])
    with left:
        webui.html_table(
            summary,
            [
                {"key": "subject_code", "label": "Code", "kind": "code"},
                {"key": "subject_name", "label": "Subject"},
                {
                    "key": "difficulty_index",
                    "label": "Difficulty",
                    "kind": "bar",
                    "max": 100,
                    "fmt": "{:.0f}",
                    "color": webui.difficulty_color,
                },
                {
                    "key": "pass_rate",
                    "label": "Pass rate",
                    "kind": "bar",
                    "max": 1,
                    "fmt": "{:.0%}",
                    "color": "#34C759",
                },
                {
                    "key": "first_attempt_pass_rate",
                    "label": "1st attempt",
                    "kind": "bar",
                    "max": 1,
                    "fmt": "{:.0%}",
                    "color": "#FF9500",
                },
                {"key": "repeat_rate", "label": "Repeat", "kind": "num", "fmt": "{:.0%}"},
                {"key": "mean_mark", "label": "Mean", "kind": "num", "fmt": "{:.1f}"},
                {"key": "never_passed", "label": "Never passed", "kind": "num", "fmt": "{:.0f}"},
            ],
        )
    with right:
        fig = charts.difficulty_scatter(summary)
        fig.update_layout(height=560)
        webui.plot(fig)

with detail:
    code = st.selectbox("Subject", summary["subject_code"], format_func=labels.get)
    sub = df[df["subject_code"] == code]
    row = summary[summary["subject_code"] == code].iloc[0]
    k = st.columns(5)
    with k[0]:
        webui.kpi_card(
            "Difficulty",
            f"{row['difficulty_index']:.0f}",
            "#FF3B30",
            note="0-100, higher is harder",
        )
    with k[1]:
        webui.kpi_card("Pass rate", f"{row['pass_rate']:.0%}", "#34C759", note="all attempts")
    with k[2]:
        webui.kpi_card("First attempt", f"{row['first_attempt_pass_rate']:.0%}", "#FF9500")
    with k[3]:
        webui.kpi_card(
            "Mean mark",
            f"{row['mean_mark']:.1f}",
            "#007AFF",
            note=f"median {row['median_mark']:.1f}",
        )
    with k[4]:
        webui.kpi_card(
            "Never passed",
            f"{int(row['never_passed'])}",
            "#AF52DE",
            note=f"{int(row['candidates'])} candidates",
        )
    c1, c2, c3 = st.columns(3)
    for col, fig in (
        (c1, charts.mark_histogram(sub, settings["pass_mark"])),
        (c2, charts.pass_rate_trend(metrics.session_trend(sub))),
        (c3, charts.first_vs_repeat(sub, metrics.pass_rate)),
    ):
        fig.update_layout(height=330)
        with col:
            webui.plot(fig)
