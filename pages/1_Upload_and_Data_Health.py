from io import BytesIO

import streamlit as st
import webui

from examlens import export, viewmodel
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


@st.cache_data(show_spinner="Reading and merging your files…")
def load_files(payload: tuple[tuple[str, bytes], ...], overrides: dict, wide_sessions: dict):
    """Read every uploaded file and merge them (cached so reruns are instant)."""
    frames = {name: read_raw(BytesIO(data), name) for name, data in payload}
    return ingest(frames, overrides, wide_sessions)


if files:
    payload = tuple((f.name, f.getvalue()) for f in files)
    if payload:
        try:
            df, report = load_files(payload, overrides, wide_sessions)
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

# --- downloads + health canvas -------------------------------------------------------------------
d1, d2, _ = st.columns([2, 2, 5])
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
webui.canvas("health", viewmodel.health(report, data), height=1500)
