import streamlit as st
import webui

from examlens import charts, export

df, settings = webui.page_data(
    "At-Risk Students", "Transparent, rule-based flags with plain-English reasons."
)

table = webui.cached_risk(df, settings["weights"], settings["levels"])
counts = table["risk_level"].value_counts().to_dict()

left, right = st.columns([3, 2])
with left:
    k = st.columns(3)
    with k[0]:
        webui.kpi_card(
            "High risk", f"{counts.get('High', 0)}", "#FF3B30", note="score 50+ by default"
        )
    with k[1]:
        webui.kpi_card("Medium risk", f"{counts.get('Medium', 0)}", "#FF9500", note="score 25-49")
    with k[2]:
        webui.kpi_card("Low risk", f"{counts.get('Low', 0)}", "#34C759", note="score below 25")
    f1, f2, f3 = st.columns([3, 3, 2])
    levels = f1.multiselect("Risk level", ["High", "Medium", "Low"], default=["High", "Medium"])
    query = f2.text_input("Search by ID, name or reason")
view = table[table["risk_level"].isin(levels)]
if query.strip():
    q = query.strip().lower()
    hay = (view["student_id"] + " " + view["student_name"] + " " + view["reasons"]).str.lower()
    view = view[hay.str.contains(q, regex=False)]
view = view.reset_index(drop=True)
with left:
    with f3:
        st.write("")
        st.download_button(
            "Excel",
            export.at_risk_workbook(view),
            "at_risk_students.xlsx",
            webui.XLSX_MIME,
            icon=":material/download:",
        )
with right:
    fig = charts.risk_donut(counts)
    fig.update_layout(height=290)
    webui.plot(fig)

st.caption(f"{len(view):,} students shown. Select a row to open their profile below.")
event = st.dataframe(
    webui.style_risk(view),
    hide_index=True,
    use_container_width=True,
    height=min(40 + 35 * max(len(view), 1), 420),
    on_select="rerun",
    selection_mode="single-row",
    key="risk_table",
    column_config={
        "student_id": "ID",
        "student_name": "Name",
        "programme": "Programme",
        "intake": "Intake",
        "risk_score": "Score",
        "risk_level": "Risk",
        "reasons": st.column_config.TextColumn("Reasons", width="large"),
        "outstanding_subjects": "Outstanding",
        "latest_avg": st.column_config.NumberColumn("Latest avg", format="%.1f"),
    },
)

rows = event.selection.rows if event and event.selection else []
if rows and rows[0] < len(view):
    st.divider()
    webui.student_profile(df, view.loc[rows[0], "student_id"], table, key="risk_profile")
