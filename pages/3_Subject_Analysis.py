import streamlit as st
import webui

from examlens import charts, metrics

df, settings = webui.page_data(
    "Subject Analysis", "Which subjects are hardest, and how they change over time."
)

summary = webui.cached_summary(df)
st.subheader("Subject leaderboard (hardest first)")
st.dataframe(
    summary,
    hide_index=True,
    use_container_width=True,
    column_config={
        "subject_code": "Code",
        "subject_name": "Subject",
        "candidates": "Candidates",
        "attempts": "Attempts",
        "difficulty_index": st.column_config.ProgressColumn(
            "Difficulty (0–100)", min_value=0, max_value=100, format="%.0f"
        ),
        "pass_rate": st.column_config.ProgressColumn(
            "Pass rate", min_value=0, max_value=1, format="percent"
        ),
        "first_attempt_pass_rate": st.column_config.ProgressColumn(
            "First-attempt pass", min_value=0, max_value=1, format="percent"
        ),
        "absence_rate": st.column_config.NumberColumn("Absence", format="percent"),
        "repeat_rate": st.column_config.NumberColumn("Repeat rate", format="percent"),
        "mean_mark": st.column_config.NumberColumn("Mean mark", format="%.1f"),
        "median_mark": st.column_config.NumberColumn("Median", format="%.1f"),
        "never_passed": "Never passed",
        "mean_attempts_to_pass": st.column_config.NumberColumn(
            "Avg attempts to pass", format="%.2f"
        ),
    },
)

st.plotly_chart(charts.difficulty_scatter(summary), use_container_width=True)

st.subheader("Subject detail")
codes = summary["subject_code"].tolist()
labels = webui.code_labels(summary["subject_code"], summary["subject_name"])
code = st.selectbox("Subject", codes, format_func=labels.get)
sub = df[df["subject_code"] == code]

left, right = st.columns(2)
left.plotly_chart(charts.mark_histogram(sub, settings["pass_mark"]), use_container_width=True)
right.plotly_chart(charts.pass_rate_trend(metrics.session_trend(sub)), use_container_width=True)
st.plotly_chart(charts.first_vs_repeat(sub, metrics.pass_rate), use_container_width=True)
