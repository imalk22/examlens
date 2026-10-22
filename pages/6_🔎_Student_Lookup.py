import streamlit as st
import webui

df, settings = webui.page_data("Student Lookup", "🔎")

table = webui.cached_risk(df, settings["weights"], settings["levels"])

query = st.text_input("Search by student ID or name", placeholder="e.g. ST2023-0017 or Perera")
if not query.strip():
    st.info("Type part of a student ID or name to begin.")
    st.stop()

matches = webui.search_students(df, query)
if matches.empty:
    st.warning("No students match that search.")
    st.stop()

labels = webui.code_labels(matches["student_id"], matches["student_name"])
choice = st.selectbox(f"{len(matches)} match(es)", matches["student_id"], format_func=labels.get)
webui.student_profile(df, choice, table, key="lookup")
