import streamlit as st
import webui

from examlens import export

df, settings = webui.page_data("At-Risk Students", "🚩")

table = webui.cached_risk(df, settings["weights"], settings["levels"])

counts = table["risk_level"].value_counts()
c1, c2, c3 = st.columns(3)
c1.metric("🔴 High", int(counts.get("High", 0)))
c2.metric("🟠 Medium", int(counts.get("Medium", 0)))
c3.metric("🟢 Low", int(counts.get("Low", 0)))

levels = st.multiselect("Risk level", ["High", "Medium", "Low"], default=["High", "Medium"])
query = st.text_input("Search by ID, name or reason")
view = table[table["risk_level"].isin(levels)]
if query.strip():
    q = query.strip().lower()
    hay = (view["student_id"] + " " + view["student_name"] + " " + view["reasons"]).str.lower()
    view = view[hay.str.contains(q, regex=False)]
view = view.reset_index(drop=True)

st.caption("Select a row to open the student's profile below.")
shown = view.assign(risk_level=view["risk_level"].map(webui.RISK_ICONS))
event = st.dataframe(
    shown,
    hide_index=True,
    use_container_width=True,
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

st.download_button(
    "Download at-risk list (Excel)",
    export.at_risk_workbook(view),
    "at_risk_students.xlsx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)

rows = event.selection.rows if event and event.selection else []
if rows and rows[0] < len(view):
    st.divider()
    webui.student_profile(df, view.loc[rows[0], "student_id"], table, key="risk_profile")
