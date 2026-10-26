"""Streamlit helpers shared by every page (state, sidebar, filters, dashboard canvas).

Kept outside ``src/examlens`` so that package stays free of Streamlit imports.
"""

from __future__ import annotations

import difflib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))  # lets `streamlit run app.py` work without pip install

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402
import streamlit.components.v1 as components  # noqa: E402

from examlens import config, metrics, risk  # noqa: E402
from examlens.ingestion import apply_results, load_paths, sample_paths  # noqa: E402

SAMPLE_DIR = ROOT / "data" / "sample"
ASSETS = ROOT / "assets"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


# --- look & feel -----------------------------------------------------------------------------


def dark_mode() -> bool:
    """Whether the sidebar dark-mode toggle is on."""
    return bool(st.session_state.get("dark_mode", False))


def inject_css() -> None:
    """Apply the shell stylesheet (page background, sidebar, controls); called from app.py."""
    css = (ASSETS / "style.css").read_text(encoding="utf-8")
    if dark_mode():
        css += (ASSETS / "dark.css").read_text(encoding="utf-8")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def theme_toggle() -> None:
    """Sidebar switch for dark mode."""
    st.sidebar.toggle("Dark mode", key="dark_mode", help="Switch between light and dark")


def header(title: str, subtitle: str = "") -> None:
    """Large page title with a quiet subtitle."""
    sub = f'<p class="subtitle">{subtitle}</p>' if subtitle else ""
    st.markdown(f'<h1 class="large-title">{title}</h1>{sub}', unsafe_allow_html=True)


def canvas(page: str, data: dict, pass_mark: float | None = None, height: int = 1200) -> None:
    """Render a dashboard page: a self-sizing HTML canvas drawn from JSON ``data``."""
    boot = {
        "page": page,
        "theme": "dark" if dark_mode() else "light",
        "pass_mark": pass_mark,
        "data": data,
    }
    payload = json.dumps(boot, allow_nan=False).replace("</", "<\\/")
    css = (ASSETS / "canvas.css").read_text(encoding="utf-8")
    js = (ASSETS / "canvas.js").read_text(encoding="utf-8")
    html = (
        f'<!doctype html><html data-theme="{boot["theme"]}"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1"><style>{css}</style></head>'
        f'<body><div id="app"></div><script>window.__EXAMLENS__={payload};</script>'
        f"<script>{js}</script></body></html>"
    )
    components.html(html, height=height, scrolling=False)


# --- state ----------------------------------------------------------------------------------


def set_dataset(df: pd.DataFrame, report) -> None:
    """Store a cleaned dataset and its health report for all pages."""
    st.session_state["data"] = df
    st.session_state["report"] = report


@st.cache_data(show_spinner=False)
def _load_sample():
    return load_paths(sample_paths(SAMPLE_DIR))


def load_sample() -> None:
    """Load the bundled synthetic dataset into session state."""
    try:
        df, report = _load_sample()
    except Exception:
        st.error("Could not load the sample data. Run `python scripts/generate_sample_data.py`.")
        return
    set_dataset(df, report)


def sample_button(key: str) -> None:
    """Button that loads the sample data and reruns."""
    if st.button("Load sample data", type="primary", key=key, icon=":material/database:"):
        load_sample()
        st.rerun()


# --- cached compute --------------------------------------------------------------------------


@st.cache_data(show_spinner=False)
def cached_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Cached ``metrics.subject_summary``."""
    return metrics.subject_summary(df)


@st.cache_data(show_spinner=False)
def cached_risk(df: pd.DataFrame, weights: dict, levels: dict) -> pd.DataFrame:
    """Cached ``risk.compute_risk``."""
    return risk.compute_risk(df, weights=weights, levels=levels)


# --- sidebar ---------------------------------------------------------------------------------


def _assumptions() -> tuple[float, dict, dict]:
    with st.sidebar.expander("Assumptions"):
        pass_mark = st.number_input("Pass mark", 0, 100, config.PASS_MARK, key="pass_mark")
        st.caption("Risk weights (points)")
        weights = {
            key: st.number_input(
                key.replace("_", " ").capitalize(), 0, 100, default, key=f"w_{key}"
            )
            for key, default in config.RISK_WEIGHTS.items()
        }
        st.caption("Risk level thresholds (score)")
        levels = {
            "High": st.number_input("High from", 0, 300, config.RISK_LEVELS["High"], key="lv_high"),
            "Medium": st.number_input(
                "Medium from", 0, 300, config.RISK_LEVELS["Medium"], key="lv_med"
            ),
            "Low": 0,
        }
        st.caption(
            "Other fixed rules: outstanding/absence caps of 3; decline of 10+ marks; average < 45."
        )
    return float(pass_mark), weights, levels


def _filters(df: pd.DataFrame) -> pd.DataFrame:
    st.sidebar.subheader("Filters")
    out = df
    for col, label in [("programme", "Programme"), ("intake", "Intake"), ("level", "Level")]:
        options = sorted(df[col].dropna().unique())
        chosen = st.sidebar.multiselect(label, options, key=f"f_{col}")
        if chosen:
            out = out[out[col].isin(chosen)]
    sessions = (
        df.drop_duplicates("exam_session").sort_values("session_date")["exam_session"].tolist()
    )
    if len(sessions) > 1:
        lo, hi = st.sidebar.select_slider(
            "Session range", options=sessions, value=(sessions[0], sessions[-1]), key="f_sessions"
        )
        keep = sessions[sessions.index(lo) : sessions.index(hi) + 1]
        out = out[out["exam_session"].isin(keep)]
    return out


def page_data(title: str, subtitle: str = "") -> tuple[pd.DataFrame, dict]:
    """Common page setup. Returns ``(filtered_df, settings)`` or stops with a friendly prompt."""
    header(title, subtitle)
    data = st.session_state.get("data")
    if data is None:
        st.markdown(
            '<div class="empty-card"><div class="tile"><svg width="28" height="28" viewBox="0 0 28 28" '
            'fill="none" stroke="#fff" stroke-width="2.2" stroke-linecap="round">'
            '<circle cx="14" cy="14" r="8"/><circle cx="14" cy="14" r="2.6" fill="#fff"/>'
            "</svg></div><h2>Welcome to ExamLens</h2>"
            "<p>Add your result files on the Upload page, or explore with synthetic demo data.</p>"
            "</div>",
            unsafe_allow_html=True,
        )
        _, middle, _ = st.columns([1, 1.2, 1])
        with middle:
            sample_button("sample_empty")
        st.stop()

    pass_mark, weights, levels = _assumptions()
    df = apply_results(data, pass_mark)
    st.sidebar.caption(
        f"{len(df):,} records · {df['student_id'].nunique():,} students · "
        f"{df['subject_code'].nunique()} subjects · {df['exam_session'].nunique()} sessions"
    )
    df = _filters(df)
    if df.empty:
        st.warning("No records match the current filters. Adjust them in the sidebar.")
        st.stop()
    return df, {"pass_mark": pass_mark, "weights": weights, "levels": levels}


# --- helpers ---------------------------------------------------------------------------------


def code_labels(codes: pd.Series, names: pd.Series) -> dict[str, str]:
    """Map each code to a 'CODE · Name' label for select boxes."""
    return dict(zip(codes, codes + " · " + names, strict=False))


def search_students(df: pd.DataFrame, query: str, limit: int = 25) -> pd.DataFrame:
    """Partial then fuzzy match on student ID or name; returns unique students."""
    students = df.drop_duplicates("student_id")[["student_id", "student_name"]].reset_index(
        drop=True
    )
    q = query.strip().lower()
    if not q:
        return students.head(0)
    hay = (students["student_id"] + " " + students["student_name"]).str.lower()
    hits = students[hay.str.contains(q, regex=False)]
    if len(hits) < limit:
        names = students["student_name"].str.lower().tolist()
        close = difflib.get_close_matches(q, names, n=limit, cutoff=0.6)
        fuzzy = students[students["student_name"].str.lower().isin(close)]
        hits = pd.concat([hits, fuzzy]).drop_duplicates("student_id")
    return hits.head(limit)
