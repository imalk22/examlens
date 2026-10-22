import streamlit as st
import webui
from streamlit.errors import StreamlitPageNotFoundError

webui.header("Exam results, made clear", "Turn scattered result spreadsheets into insight.")

data = st.session_state.get("data")
if data is None:
    st.markdown(
        '<div class="hero"><h3 style="margin-top:0">Get started</h3>'
        "<p style='color:#6c6c70'>Upload your result files, or explore the app with "
        "synthetic demo data.</p></div>",
        unsafe_allow_html=True,
    )
    webui.sample_button("sample_home")
else:
    webui.status_row(
        "ok",
        f"{len(data):,} records · {data['student_id'].nunique():,} students · "
        f"{data['subject_code'].nunique()} subjects · {data['exam_session'].nunique()} sessions",
    )

st.subheader("Explore")
cards = [
    ("pages/1_Upload_and_Data_Health.py", "Upload & Data Health", ":material/upload_file:"),
    ("pages/2_Overview.py", "Overview", ":material/dashboard:"),
    ("pages/3_Subject_Analysis.py", "Subject Analysis", ":material/menu_book:"),
    ("pages/4_Repeat_Attempts.py", "Repeat Attempts", ":material/replay:"),
    ("pages/5_At_Risk_Students.py", "At-Risk Students", ":material/flag:"),
    ("pages/6_Student_Lookup.py", "Student Lookup", ":material/person_search:"),
]
cols = st.columns(3)
for i, (path, label, icon) in enumerate(cards):
    with cols[i % 3]:
        try:
            st.page_link(path, label=label, icon=icon, use_container_width=True)
        except StreamlitPageNotFoundError:  # page run outside app.py (e.g. in tests)
            st.write(label)
st.caption("Demo data is synthetic. Uploaded files stay in memory and are never stored.")
