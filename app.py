"""ExamLens entry point (home page). Other pages live in ``pages/``."""

import streamlit as st
import webui

st.set_page_config(page_title="ExamLens", page_icon="🎓", layout="wide")
st.title("🎓 ExamLens")
st.caption("Turn scattered exam result spreadsheets into clear academic insights.")

data = st.session_state.get("data")
if data is None:
    st.info("No results loaded yet. Upload your files, or explore with synthetic demo data.")
    webui.sample_button("sample_home")
else:
    st.success(
        f"Data loaded: {len(data):,} records · {data['student_id'].nunique():,} students · "
        f"{data['subject_code'].nunique()} subjects · {data['exam_session'].nunique()} sessions."
    )

st.markdown("### Pages")
st.page_link("pages/1_📥_Upload_and_Data_Health.py", label="Upload & Data Health", icon="📥")
st.page_link("pages/2_📊_Overview.py", label="Overview", icon="📊")
st.page_link("pages/3_📚_Subject_Analysis.py", label="Subject Analysis", icon="📚")
st.page_link("pages/4_🔁_Repeat_Attempts.py", label="Repeat Attempts", icon="🔁")
st.page_link("pages/5_🚩_At_Risk_Students.py", label="At-Risk Students", icon="🚩")
st.page_link("pages/6_🔎_Student_Lookup.py", label="Student Lookup", icon="🔎")
st.caption("All demo data is synthetic. Real data stays on your machine and is never stored.")
