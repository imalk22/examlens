import streamlit as st
import webui

from examlens import charts, export, metrics

df, settings = webui.page_data(
    "Repeat Attempts", "How many attempts students need, and who is still outstanding."
)

summary = webui.cached_summary(df)
labels = webui.code_labels(summary["subject_code"], summary["subject_name"])
pairs = metrics.pair_table(df)
passed_pairs = pairs[pairs["pass_attempt"].notna()]
never = metrics.never_passed(df)

k = st.columns(4)
with k[0]:
    webui.kpi_card(
        "Repeat rate",
        f"{metrics.repeat_rate(df):.0%}",
        "#FF9500",
        note="pairs needing 2+ attempts",
    )
with k[1]:
    mean_att = passed_pairs["pass_attempt"].mean() if len(passed_pairs) else float("nan")
    webui.kpi_card("Avg attempts to pass", f"{mean_att:.2f}", "#007AFF", note="eventual passes")
with k[2]:
    first_time = (passed_pairs["pass_attempt"] == 1).mean() if len(passed_pairs) else float("nan")
    webui.kpi_card("Passed first time", f"{first_time:.0%}", "#34C759", note="of eventual passes")
with k[3]:
    webui.kpi_card("Never passed", f"{len(never):,}", "#FF3B30", note="student-subject pairs")

left, right = st.columns(2)
with left:
    scope = st.selectbox(
        "Attempts to pass for",
        ["All subjects", *summary["subject_code"]],
        format_func=lambda c: labels.get(c, c),
    )
    dist = metrics.attempts_to_pass_distribution(df, None if scope == "All subjects" else scope)
    if dist.empty:
        st.info("No passes in this selection.")
    else:
        fig = charts.attempts_distribution(dist, f"Attempts needed to pass: {scope}")
        fig.update_layout(height=330)
        webui.plot(fig)
with right:
    code = st.selectbox(
        "Funnel for", summary["subject_code"], format_func=labels.get, key="funnel_subject"
    )
    fig = charts.funnel_chart(
        metrics.subject_funnel(df, code), f"{labels[code]}: journey to a pass"
    )
    fig.update_layout(height=330)
    webui.plot(fig)

rank_tab, never_tab = st.tabs(["Repeat rate by subject", "Never passed"])
with rank_tab:
    ranked = summary.sort_values("repeat_rate", ascending=False)
    webui.html_table(
        ranked,
        [
            {"key": "subject_code", "label": "Code", "kind": "code"},
            {"key": "subject_name", "label": "Subject"},
            {
                "key": "repeat_rate",
                "label": "Repeat rate",
                "kind": "bar",
                "max": max(float(ranked["repeat_rate"].max()), 0.01),
                "fmt": "{:.0%}",
                "color": "#FF9500",
            },
            {
                "key": "mean_attempts_to_pass",
                "label": "Avg attempts",
                "kind": "num",
                "fmt": "{:.2f}",
            },
            {"key": "never_passed", "label": "Never passed", "kind": "num", "fmt": "{:.0f}"},
        ],
    )
with never_tab:
    f1, f2 = st.columns([3, 1])
    picked = f1.multiselect("Filter by subject", summary["subject_code"], format_func=labels.get)
    view = never[never["subject_code"].isin(picked)] if picked else never
    with f2:
        st.write("")
        st.download_button(
            "Download Excel",
            export.to_excel_bytes({"Never passed": view}),
            "never_passed.xlsx",
            webui.XLSX_MIME,
            icon=":material/download:",
        )
    st.caption(f"{len(view):,} student-subject pairs with no pass yet.")
    st.dataframe(
        view,
        hide_index=True,
        use_container_width=True,
        height=360,
        column_config={
            "student_id": "ID",
            "student_name": "Name",
            "subject_code": "Code",
            "subject_name": "Subject",
            "attempts": "Attempts",
        },
    )
