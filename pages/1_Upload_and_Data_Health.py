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
    st.caption("No files yet? Try the synthetic demo data.")

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

# --- summary cards ----------------------------------------------------------------------------
k = st.columns(4)
with k[0]:
    webui.kpi_card("Rows loaded", f"{report.rows_loaded:,}", "#007AFF", note="across all files")
with k[1]:
    webui.kpi_card(
        "After cleaning", f"{report.rows_final:,}", "#34C759", note="valid, de-duplicated"
    )
with k[2]:
    webui.kpi_card("Students", f"{data['student_id'].nunique():,}", "#AF52DE", note="unique IDs")
with k[3]:
    webui.kpi_card(
        "Files", f"{len(report.rows_per_file)}", "#FF9500", note="merged into one dataset"
    )

# --- quality checks + files --------------------------------------------------------------------
checks, files_col = st.columns([3, 2])
with checks:
    st.subheader("Quality checks")
    webui.status_row(
        "ok" if report.duplicates_removed == 0 else "warn",
        f"Duplicate rows removed (kept highest mark): <b>{report.duplicates_removed}</b>",
    )
    webui.status_row(
        "ok" if report.invalid_marks == 0 else "warn",
        f"Marks outside 0–100 (excluded): <b>{report.invalid_marks}</b>",
    )
    webui.status_row(
        "ok" if not report.name_conflicts else "warn",
        f"Student IDs with conflicting names: <b>{len(report.name_conflicts)}</b>",
    )
    webui.status_row(
        "ok" if report.rows_dropped_missing_required == 0 else "warn",
        f"Rows dropped for missing ID, subject or session: <b>{report.rows_dropped_missing_required}</b>",
    )
    webui.status_row(
        "info",
        f"Absent attempts: <b>{report.absent_count}</b> · Medical: <b>{report.medical_count}</b>",
    )
    if report.wide_files:
        webui.status_row("info", f"Wide-format files converted: {', '.join(report.wide_files)}")
with files_col:
    st.subheader("Rows per file")
    per_file = pd.DataFrame(
        {"file": list(report.rows_per_file), "rows": list(report.rows_per_file.values())}
    )
    webui.html_table(
        per_file,
        [
            {"key": "file", "label": "File"},
            {"key": "rows", "label": "Rows", "kind": "num", "fmt": "{:,}"},
        ],
    )

# --- issue details ------------------------------------------------------------------------------
if report.name_conflicts or report.invalid_mark_rows or report.duplicate_keys:
    st.subheader("Details")
    if report.name_conflicts:
        with st.expander(f"Name conflicts ({len(report.name_conflicts)})"):
            st.dataframe(pd.DataFrame(report.name_conflicts), hide_index=True)
    if report.invalid_mark_rows:
        with st.expander(f"Invalid marks ({len(report.invalid_mark_rows)})"):
            st.dataframe(pd.DataFrame(report.invalid_mark_rows), hide_index=True)
    if report.duplicate_keys:
        with st.expander(f"Duplicates removed ({len(report.duplicate_keys)})"):
            st.dataframe(pd.DataFrame(report.duplicate_keys), hide_index=True)

# --- cleaned dataset ---------------------------------------------------------------------------
head, d1, d2 = st.columns([6, 1.3, 1.3])
head.subheader("Cleaned dataset")
with d1:
    st.download_button(
        "CSV",
        export.to_csv_bytes(data),
        "examlens_clean.csv",
        "text/csv",
        icon=":material/download:",
    )
with d2:
    st.download_button(
        "Excel",
        export.to_excel_bytes({"Results": data}),
        "examlens_clean.xlsx",
        webui.XLSX_MIME,
        icon=":material/download:",
    )
preview = data[
    [
        "student_id",
        "student_name",
        "programme",
        "intake",
        "subject_code",
        "exam_session",
        "attempt_no",
        "marks",
        "grade",
        "result",
    ]
].head(150)
st.dataframe(
    preview,
    hide_index=True,
    use_container_width=True,
    height=380,
    column_config={
        "student_id": "ID",
        "student_name": "Name",
        "programme": "Programme",
        "intake": "Intake",
        "subject_code": "Subject",
        "exam_session": "Session",
        "attempt_no": st.column_config.NumberColumn("Attempt", format="%d"),
        "marks": st.column_config.NumberColumn("Marks", format="%.0f"),
        "grade": "Grade",
        "result": "Result",
    },
)
st.caption(
    f"Showing the first {len(preview)} of {len(data):,} rows. Download for the full dataset."
)
