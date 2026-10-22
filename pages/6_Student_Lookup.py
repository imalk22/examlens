import streamlit as st
import webui

from examlens import export, viewmodel

df, settings = webui.page_data(
    "Student Lookup", "Full exam history, what remains, and a downloadable transcript."
)

table = webui.cached_risk(df, settings["weights"], settings["levels"])

search, pick = st.columns([1, 1])
query = search.text_input(
    "Search by student ID or name",
    placeholder="Student number (e.g. 2024/A1/3154) or part of a name",
)
if not query.strip():
    st.info("Type part of a student ID or name to begin. Try a surname like “Perera”.")
    st.stop()

matches = webui.search_students(df, query)
if matches.empty:
    st.warning("No students match that search.")
    st.stop()

labels = webui.code_labels(matches["student_id"], matches["student_name"])
choice = pick.selectbox(f"{len(matches)} match(es)", matches["student_id"], format_func=labels.get)

history = df[df["student_id"] == choice]
passed = set(history.loc[history["result"] == "Pass", "subject_code"])
remaining = (
    history[~history["subject_code"].isin(passed)]
    .groupby(["subject_code", "subject_name"])
    .agg(attempts=("attempt_no", "max"), best_mark=("marks", "max"))
    .reset_index()
)
first = history.iloc[0]
level_row = table[table["student_id"] == choice]
info = {
    "Student ID": choice,
    "Name": first["student_name"],
    "Programme": first["programme"],
    "Intake": first["intake"],
    "Risk level": level_row.iloc[0]["risk_level"] if len(level_row) else "Low",
}
st.download_button(
    "Download transcript (Excel)",
    export.transcript_workbook(info, history, remaining),
    file_name=f"transcript_{choice}.xlsx",
    mime=webui.XLSX_MIME,
    icon=":material/download:",
)
webui.canvas(
    "student",
    viewmodel.student_page(df, choice, table, settings["pass_mark"]),
    pass_mark=settings["pass_mark"],
    height=900,
)
