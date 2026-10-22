"""ExamLens entry point: global styling and navigation. Pages live in ``pages/``."""

import streamlit as st
import webui

st.set_page_config(page_title="ExamLens", page_icon=":material/query_stats:", layout="wide")
webui.inject_css()
st.logo(str(webui.ASSETS / ("logo_dark.svg" if webui.dark_mode() else "logo.svg")), size="large")

navigation = st.navigation(
    [
        st.Page("pages/2_Overview.py", title="Overview", icon=":material/dashboard:", default=True),
        st.Page(
            "pages/3_Subject_Analysis.py", title="Subject Analysis", icon=":material/menu_book:"
        ),
        st.Page("pages/4_Repeat_Attempts.py", title="Repeat Attempts", icon=":material/replay:"),
        st.Page(
            "pages/5_At_Risk_Students.py",
            title="At-Risk Students",
            icon=":material/flag:",
            url_path="at-risk",
        ),
        st.Page(
            "pages/6_Student_Lookup.py", title="Student Lookup", icon=":material/person_search:"
        ),
        st.Page(
            "pages/1_Upload_and_Data_Health.py",
            title="Upload & Data Health",
            icon=":material/upload_file:",
            url_path="upload",
        ),
    ]
)
webui.theme_toggle()
navigation.run()
