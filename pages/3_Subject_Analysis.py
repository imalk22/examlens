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
    left, right = st.columns([3, 2])
    left.dataframe(
        summary[
            [
                "subject_code",
                "subject_name",
                "difficulty_index",
                "pass_rate",
                "first_attempt_pass_rate",
                "repeat_rate",
                "mean_mark",
                "candidates",
                "never_passed",
            ]
        ],
        hide_index=True,
        use_container_width=True,
        height=min(40 + 35 * len(summary), 480),
        column_config={
            "subject_code": "Code",
            "subject_name": "Subject",
            "difficulty_index": st.column_config.ProgressColumn(
                "Difficulty", min_value=0, max_value=100, format="%.0f"
            ),
            "pass_rate": st.column_config.ProgressColumn(
                "Pass rate", min_value=0, max_value=1, format="percent"
            ),
            "first_attempt_pass_rate": st.column_config.ProgressColumn(
                "1st attempt", min_value=0, max_value=1, format="percent"
            ),
            "repeat_rate": st.column_config.NumberColumn("Repeat", format="percent"),
            "mean_mark": st.column_config.NumberColumn("Mean", format="%.1f"),
            "candidates": "Candidates",
            "never_passed": "Never passed",
        },
    )
    fig = charts.difficulty_scatter(summary)
    fig.update_layout(height=min(40 + 35 * len(summary), 480))
    right.plotly_chart(fig, use_container_width=True)

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
        fig.update_layout(height=320)
        col.plotly_chart(fig, use_container_width=True)
