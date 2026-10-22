"""Streamlit helpers shared by every page (state, sidebar, filters, reusable components).

Kept outside ``src/examlens`` so that package stays free of Streamlit imports.
"""

from __future__ import annotations

import difflib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))  # lets `streamlit run app.py` work without pip install

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from examlens import charts, config, export, metrics, risk  # noqa: E402
from examlens.ingestion import apply_results, load_paths, sample_paths  # noqa: E402

SAMPLE_DIR = ROOT / "data" / "sample"
ASSETS = ROOT / "assets"
RESULT_CSS = {
    "Pass": "background-color: #e3f7e8; color: #1f8a3b",
    "Fail": "background-color: #ffe5e3; color: #c9261b",
    "Absent": "background-color: #ececf0; color: #6c6c70",
}
LEVEL_CSS = {
    "High": "background-color: #ffe5e3; color: #c9261b; font-weight: 600",
    "Medium": "background-color: #fff0d9; color: #b25f00; font-weight: 600",
    "Low": "background-color: #e3f7e8; color: #1f8a3b; font-weight: 600",
}
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


# --- look & feel -----------------------------------------------------------------------------


def inject_css() -> None:
    """Apply the iOS-style stylesheet (called once per run from ``app.py``)."""
    css = (ASSETS / "style.css").read_text(encoding="utf-8")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def header(title: str, subtitle: str = "") -> None:
    """Large iOS-style page title with a quiet subtitle."""
    sub = f'<p class="subtitle">{subtitle}</p>' if subtitle else ""
    st.markdown(f'<h1 class="large-title">{title}</h1>{sub}', unsafe_allow_html=True)


def badge(level: str) -> str:
    """HTML pill for a risk level."""
    return f'<span class="pill {level.lower()}">{level}</span>'


def status_row(kind: str, text: str) -> None:
    """One status line with a coloured dot; ``kind`` is ``ok``, ``warn`` or ``info``."""
    st.markdown(
        f'<div class="status-row"><span class="dot {kind}"></span><span>{text}</span></div>',
        unsafe_allow_html=True,
    )


def insight_box(lines: list[str]) -> None:
    """Card listing short insight sentences."""
    body = "".join(f'<p><span class="bullet"></span><span>{line}</span></p>' for line in lines)
    st.markdown(f'<div class="insight">{body}</div>', unsafe_allow_html=True)


def sparkline(values: list[float], color: str) -> str:
    """Tiny inline SVG area sparkline (empty string if fewer than 2 points)."""
    vals = [v for v in values if v == v]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1.0
    pts = [(i / (len(vals) - 1) * 100, 26 - (v - lo) / span * 22) for i, v in enumerate(vals)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = f"0,30 {line} 100,30"
    return (
        f'<svg class="spark" viewBox="0 0 100 30" preserveAspectRatio="none">'
        f'<polygon points="{area}" fill="{color}" fill-opacity="0.12"/>'
        f'<polyline points="{line}" fill="none" stroke="{color}" stroke-width="2" '
        f'stroke-linecap="round" stroke-linejoin="round" vector-effect="non-scaling-stroke"/></svg>'
    )


def kpi_card(
    label: str,
    value: str,
    color: str = "#007AFF",
    delta: float | None = None,
    delta_text: str = "",
    up_is_good: bool = True,
    spark: list[float] | None = None,
    note: str = "",
    footer: str = "",
) -> None:
    """Dashboard KPI card: coloured label, big value, delta chip and optional sparkline."""
    chip = ""
    if delta_text:
        if delta is None or abs(delta) < 1e-9:
            kind = "flat"
        else:
            kind = "good" if (delta > 0) == up_is_good else "bad"
        arrow = "" if delta is None else ("↑ " if delta > 0 else "↓ " if delta < 0 else "")
        chip = f'<span class="kpi-delta {kind}">{arrow}{delta_text}</span>'
    foot = footer or (sparkline(spark, color) if spark else "")
    note_html = f'<div class="kpi-note">{note}</div>' if note else ""
    st.markdown(
        f'<div class="kpi" style="--accent:{color}">'
        f'<div class="kpi-label" style="color:{color}">{label}</div>'
        f'<div class="kpi-row"><span class="kpi-value">{value}</span>{chip}</div>{note_html}'
        f'<div class="kpi-foot">{foot}</div></div>',
        unsafe_allow_html=True,
    )


def stack_bar(parts: list[tuple[float, str]]) -> str:
    """Horizontal stacked proportion bar from (value, colour) parts."""
    total = sum(v for v, _ in parts) or 1
    spans = "".join(
        f'<span style="width:{v / total * 100:.1f}%;background:{c}"></span>' for v, c in parts if v
    )
    return f'<div class="stackbar">{spans}</div>'


def style_risk(table: pd.DataFrame, column: str = "risk_level"):
    """Pandas Styler colouring the risk-level column."""
    return table.style.map(lambda v: LEVEL_CSS.get(v, ""), subset=[column])


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
            '<div class="empty"><div class="tile"><svg width="28" height="28" viewBox="0 0 28 28" '
            'fill="none" stroke="#fff" stroke-width="2.2" stroke-linecap="round">'
            '<circle cx="14" cy="14" r="8"/><circle cx="14" cy="14" r="2.6" fill="#fff"/>'
            "</svg></div>"
            "<h2>Welcome to ExamLens</h2>"
            "<p>Add your result files on the Upload page, or explore with synthetic demo data.</p>"
            "</div>",
            unsafe_allow_html=True,
        )
        _, middle, _ = st.columns([2, 1, 2])
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


# --- reusable components ---------------------------------------------------------------------


def student_profile(df: pd.DataFrame, student_id: str, risk_table: pd.DataFrame, key: str) -> None:
    """Profile header, history, chart, 'what remains' panel and transcript download."""
    history = df[df["student_id"] == student_id]
    if history.empty:
        st.warning("That student has no records in the current filter.")
        return
    first = history.iloc[0]
    row = risk_table[risk_table["student_id"] == student_id]
    level = row.iloc[0]["risk_level"] if len(row) else "Low"
    st.subheader(f"{first['student_name']} · {student_id}")
    graded = history[history["result"].isin(["Pass", "Fail"])]
    pass_pct = (graded["result"] == "Pass").mean() * 100 if len(graded) else float("nan")
    n_passed = history.loc[history["result"] == "Pass", "subject_code"].nunique()
    n_subjects = history["subject_code"].nunique()
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        kpi_card("Programme", first["programme"], "#007AFF", note=f"Intake {first['intake']}")
    with k2:
        kpi_card("Subjects passed", f"{n_passed} / {n_subjects}", "#34C759")
    with k3:
        kpi_card(
            "Attempt pass rate", f"{pass_pct:.0f}%" if pass_pct == pass_pct else "–", "#FF9500"
        )
    with k4:
        kpi_card(
            "Risk",
            badge(level),
            "#FF3B30",
            note=f"Score {row.iloc[0]['risk_score']}" if len(row) else "",
        )
    if len(row) and row.iloc[0]["reasons"]:
        st.caption(row.iloc[0]["reasons"])

    cols = [
        "exam_session",
        "subject_code",
        "subject_name",
        "attempt_no",
        "marks",
        "grade",
        "result",
    ]
    table = history.sort_values(["session_date", "subject_code"])[cols]
    styled = table.style.apply(lambda r: [RESULT_CSS.get(r["result"], "")] * len(r), axis=1).format(
        {"marks": "{:.0f}"}, na_rep="–"
    )
    left, right = st.columns([3, 2])
    left.dataframe(
        styled, hide_index=True, use_container_width=True, height=min(38 + 35 * len(table), 380)
    )
    fig = charts.student_marks_chart(history)
    fig.update_layout(height=min(38 + 35 * len(table), 380))
    right.plotly_chart(fig, use_container_width=True, key=f"{key}_c")

    passed = set(history.loc[history["result"] == "Pass", "subject_code"])
    remaining = (
        history[~history["subject_code"].isin(passed)]
        .groupby(["subject_code", "subject_name"])
        .agg(attempts=("attempt_no", "max"), best_mark=("marks", "max"))
        .reset_index()
    )
    st.subheader("What remains")
    st.caption("Subjects attempted but not yet passed.")
    if remaining.empty:
        st.success("Nothing outstanding. Every attempted subject has been passed.")
    else:
        st.dataframe(remaining, hide_index=True, use_container_width=True)

    info = {
        "Student ID": student_id,
        "Name": first["student_name"],
        "Programme": first["programme"],
        "Intake": first["intake"],
        "Risk level": level,
    }
    st.download_button(
        "Download transcript (Excel)",
        export.transcript_workbook(info, history, remaining),
        file_name=f"transcript_{student_id}.xlsx",
        mime=XLSX_MIME,
        key=f"{key}_dl",
        icon=":material/download:",
    )


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
