from io import BytesIO

import pandas as pd
import streamlit as st
import webui

from examlens import export
from examlens.ingestion import (
    IngestionError,
    MissingColumnsError,
    MissingSessionError,
    ingest,
    read_raw,
)

webui.header(
    "Upload & Data Health",
    "Add result files (.xlsx, .xls, .csv). They are cleaned and merged here.",
)

overrides: dict = st.session_state.setdefault("overrides", {})
wide_sessions: dict = st.session_state.setdefault("wide_sessions", {})

left, right = st.columns([3, 1])
files = left.file_uploader(
    "Result files", type=["xlsx", "xls", "csv"], accept_multiple_files=True, key="uploader"
)
with right:
    st.write("")
    st.write("")
    webui.sample_button("sample_upload")

if files:
    frames: dict[str, pd.DataFrame] = {}
    for f in files:
        try:
            frames[f.name] = read_raw(BytesIO(f.getvalue()), f.name)
        except IngestionError as exc:
            st.error(str(exc))
    if frames:
        try:
            df, report = ingest(frames, overrides, wide_sessions)
            webui.set_dataset(df, report)
        except MissingColumnsError as exc:
            st.warning(f"**{exc.filename}** needs help: map the missing column(s) below.")
            with st.form("mapping"):
                chosen = {
                    col: st.selectbox(f"Which column is `{col}`?", exc.available, key=f"map_{col}")
                    for col in exc.missing
                }
                if st.form_submit_button("Apply mapping"):
                    overrides.setdefault(exc.filename, {}).update(chosen)
                    st.rerun()
        except MissingSessionError as exc:
            st.warning(f"**{exc.filename}** is one column per subject, so I need the exam session.")
            with st.form("session"):
                session = st.text_input("Exam session (e.g. 2025-Dec)")
                if st.form_submit_button("Use this session") and session.strip():
                    wide_sessions[exc.filename] = session.strip()
                    st.rerun()
        except IngestionError as exc:
            st.error(str(exc))
        except Exception:
            st.error(
                "Something went wrong while cleaning these files. Check they are result sheets."
            )

report = st.session_state.get("report")
data = st.session_state.get("data")
if report is None or data is None:
    st.info("Upload files or load the sample data to see the Data Health report.")
    st.stop()

st.subheader("Data health")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Rows loaded", f"{report.rows_loaded:,}")
c2.metric("Rows after cleaning", f"{report.rows_final:,}")
c3.metric("Students", f"{data['student_id'].nunique():,}")
c4.metric("Files", len(report.rows_per_file))


def flag(ok: bool, text: str) -> None:
    webui.status_row("ok" if ok else "warn", text)


flag(
    report.duplicates_removed == 0,
    f"Duplicate rows removed (kept highest mark): <b>{report.duplicates_removed}</b>",
)
flag(report.invalid_marks == 0, f"Marks outside 0–100 (excluded): <b>{report.invalid_marks}</b>")
flag(
    not report.name_conflicts,
    f"Student IDs with conflicting names: <b>{len(report.name_conflicts)}</b>",
)
flag(
    report.rows_dropped_missing_required == 0,
    f"Rows dropped for missing ID/subject/session: <b>{report.rows_dropped_missing_required}</b>",
)
webui.status_row(
    "info",
    f"Absent attempts: <b>{report.absent_count}</b> · Medical: <b>{report.medical_count}</b>",
)
if report.wide_files:
    webui.status_row("info", f"Wide-format files converted: {', '.join(report.wide_files)}")

with st.expander("Rows per file", expanded=True):
    st.dataframe(
        pd.DataFrame(
            {"file": list(report.rows_per_file), "rows": list(report.rows_per_file.values())}
        ),
        hide_index=True,
    )
if report.name_conflicts:
    with st.expander("Name conflicts"):
        st.dataframe(pd.DataFrame(report.name_conflicts), hide_index=True)
if report.invalid_mark_rows:
    with st.expander("Invalid marks"):
        st.dataframe(pd.DataFrame(report.invalid_mark_rows), hide_index=True)
if report.duplicate_keys:
    with st.expander("Duplicates removed"):
        st.dataframe(pd.DataFrame(report.duplicate_keys), hide_index=True)
with st.expander("Missing values per column"):
    missing = pd.DataFrame({"column": data.columns, "missing": data.isna().sum().to_numpy()})
    st.dataframe(missing, hide_index=True)

st.subheader("Cleaned dataset")
st.dataframe(data.head(200), hide_index=True, use_container_width=True)
d1, d2 = st.columns(2)
d1.download_button(
    "Download CSV",
    export.to_csv_bytes(data),
    "examlens_clean.csv",
    "text/csv",
    icon=":material/download:",
)
d2.download_button(
    "Download Excel",
    export.to_excel_bytes({"Results": data}),
    "examlens_clean.xlsx",
    webui.XLSX_MIME,
    icon=":material/download:",
)
