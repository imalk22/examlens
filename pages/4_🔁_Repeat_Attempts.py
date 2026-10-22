import streamlit as st
import webui

from examlens import charts, export, metrics

df, settings = webui.page_data("Repeat Attempts", "🔁")

summary = webui.cached_summary(df)
labels = webui.code_labels(summary["subject_code"], summary["subject_name"])

left, right = st.columns(2)
scope = right.selectbox(
    "Distribution for",
    ["All subjects", *summary["subject_code"]],
    format_func=lambda c: labels.get(c, c),
)
dist = metrics.attempts_to_pass_distribution(df, None if scope == "All subjects" else scope)
if dist.empty:
    left.info("No passes in this selection.")
else:
    st.plotly_chart(
        charts.attempts_distribution(dist, f"Attempts needed to pass: {scope}"),
        use_container_width=True,
    )

st.subheader("Subjects ranked by repeat rate")
st.dataframe(
    summary.sort_values("repeat_rate", ascending=False)[
        ["subject_code", "subject_name", "repeat_rate", "mean_attempts_to_pass", "never_passed"]
    ],
    hide_index=True,
    use_container_width=True,
    column_config={
        "subject_code": "Code",
        "subject_name": "Subject",
        "repeat_rate": st.column_config.ProgressColumn(
            "Repeat rate", min_value=0, max_value=1, format="percent"
        ),
        "mean_attempts_to_pass": st.column_config.NumberColumn(
            "Avg attempts to pass", format="%.2f"
        ),
        "never_passed": "Never passed",
    },
)

st.subheader("Funnel")
code = st.selectbox(
    "Subject", summary["subject_code"], format_func=labels.get, key="funnel_subject"
)
st.plotly_chart(
    charts.funnel_chart(metrics.subject_funnel(df, code), f"{labels[code]}: journey to a pass"),
    use_container_width=True,
)

st.subheader("Never passed")
never = metrics.never_passed(df)
picked = st.multiselect("Filter by subject", summary["subject_code"], format_func=labels.get)
if picked:
    never = never[never["subject_code"].isin(picked)]
st.caption(f"{len(never):,} student-subject pairs with no pass yet.")
st.dataframe(never, hide_index=True, use_container_width=True)
st.download_button(
    "Download list (Excel)",
    export.to_excel_bytes({"Never passed": never}),
    "never_passed.xlsx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)
