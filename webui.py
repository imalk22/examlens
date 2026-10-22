"""Streamlit helpers shared by every page (state, sidebar, filters, reusable components).

Kept outside ``src/examlens`` so that package stays free of Streamlit imports.
"""

from __future__ import annotations

import difflib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))  # lets `streamlit run app.py` work without pip install

import html  # noqa: E402
import re  # noqa: E402

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402
import streamlit.components.v1 as components  # noqa: E402

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


FX_SCRIPT = """
<script>
const P = window.parent, D = P.document;
if (!P.__examlensFX) {
  P.__examlensFX = true; P.__seen = new Set();
  const tilt = (el) => {
    if (el.__tilt) return; el.__tilt = true;
    el.addEventListener('mousemove', (e) => {
      const r = el.getBoundingClientRect();
      const x = (e.clientX - r.left) / r.width - 0.5, y = (e.clientY - r.top) / r.height - 0.5;
      el.style.transform = `perspective(900px) rotateX(${(-y * 7).toFixed(2)}deg) rotateY(${(x * 9).toFixed(2)}deg) translateY(-4px)`;
      el.style.setProperty('--mx', ((x + 0.5) * 100) + '%'); el.style.setProperty('--my', ((y + 0.5) * 100) + '%');
    });
    el.addEventListener('mouseleave', () => { el.style.transform = ''; });
  };
  const count = (el) => {
    if (el.__count) return; el.__count = true;
    const target = parseFloat(el.dataset.count); if (isNaN(target)) return;
    const key = (el.closest('.kpi')?.querySelector('.kpi-label')?.textContent || '') + '|' + el.dataset.count;
    if (P.__seen.has(key)) return; P.__seen.add(key);
    const dec = parseInt(el.dataset.dec || '0'), pre = el.dataset.pre || '', suf = el.dataset.suf || '';
    const t0 = performance.now(), dur = 1000;
    const step = (t) => {
      const p = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - p, 4);
      el.textContent = pre + (target * e).toLocaleString('en-US', {minimumFractionDigits: dec, maximumFractionDigits: dec}) + suf;
      if (p < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  };
  let queued = false;
  const scan = () => {
    queued = false;
    D.querySelectorAll('.kpi, .widget, .hero, [data-testid="stPlotlyChart"]').forEach(tilt);
    D.querySelectorAll('[data-count]').forEach(count);
  };
  new MutationObserver(() => { if (!queued) { queued = true; requestAnimationFrame(scan); } })
    .observe(D.body, {childList: true, subtree: true});
  scan();
}
</script>
"""


def dark_mode() -> bool:
    """Whether the sidebar dark-mode toggle is on."""
    return bool(st.session_state.get("dark_mode", False))


def inject_css() -> None:
    """Apply the stylesheet, dark overrides and interaction script (once per run, from app.py)."""
    css = (ASSETS / "style.css").read_text(encoding="utf-8")
    if dark_mode():
        css += (ASSETS / "dark.css").read_text(encoding="utf-8")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
    components.html(FX_SCRIPT, height=0)


def theme_toggle() -> None:
    """Sidebar switch for dark mode."""
    st.sidebar.toggle("Dark mode", key="dark_mode", help="Switch between light and dark appearance")


def plot(fig, key: str | None = None) -> None:
    """Render a Plotly figure with the active light/dark theme applied."""
    dark = dark_mode()
    text, muted, grid = (
        ("#F5F5F7", "#A1A1A8", "rgba(255,255,255,0.10)")
        if dark
        else (
            "#1C1C1E",
            "#8E8E93",
            "rgba(60,60,67,0.10)",
        )
    )
    fig.update_layout(font_color=text, title_font_color=text, legend_font_color=text)
    fig.update_xaxes(tickfont_color=muted, title_font_color=muted)
    fig.update_yaxes(tickfont_color=muted, title_font_color=muted, gridcolor=grid)
    if dark:
        fig.update_traces(marker_line_color="rgba(0,0,0,0)", selector={"type": "pie"})
        for ann in fig.layout.annotations:
            ann.font.color = text
    st.plotly_chart(fig, use_container_width=True, key=key)


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
        f'<div class="kpi-row"><span class="kpi-value"{_count_attrs(value)}{_text_style(value)}>'
        f"{value}</span>{chip}</div>"
        f"{note_html}"
        f'<div class="kpi-foot">{foot}</div></div>',
        unsafe_allow_html=True,
    )


_NUMBER = re.compile(r"^([^\d\-]*)(-?[\d,]*\.?\d+)([^\d]*)$")


def _count_attrs(value: str) -> str:
    """data-* attributes so the page script can count a numeric KPI up (empty if not numeric)."""
    m = _NUMBER.match(value)
    if not m or "<" in value:
        return ""
    pre, num, suf = m.groups()
    dec = len(num.split(".")[1]) if "." in num else 0
    return (
        f' data-count="{num.replace(",", "")}" data-dec="{dec}" '
        f'data-pre="{html.escape(pre)}" data-suf="{html.escape(suf)}"'
    )


def _text_style(value: str) -> str:
    """Smaller type for long text values (e.g. a programme name) so they fit the card."""
    return (
        ' style="font-size:1.2rem;line-height:1.25"' if len(value) > 12 and "<" not in value else ""
    )


def widget(title: str, body: str, subtitle: str = "") -> None:
    """Glass widget card with a title, optional subtitle and an HTML body."""
    sub = (
        f'<div class="widget-sub">{subtitle}</div>'
        if subtitle
        else '<div style="height:.6rem"></div>'
    )
    st.markdown(
        f'<div class="widget"><div class="widget-title">{title}</div>{sub}{body}</div>',
        unsafe_allow_html=True,
    )


def rings_svg(rings: list[tuple[str, float, str, str]]) -> str:
    """Apple Activity-style concentric rings from (label, fraction 0-1, colour, display) items."""
    import math

    parts, legend = [], []
    for i, (label, frac, color, shown) in enumerate(rings):
        radius = 66 - i * 17
        circ = 2 * math.pi * radius
        frac = max(0.0, min(1.0, frac if frac == frac else 0.0))
        parts.append(
            f'<circle class="ring-track" cx="80" cy="80" r="{radius}" stroke="{color}" stroke-width="12"/>'
            f'<circle class="ring" cx="80" cy="80" r="{radius}" stroke="{color}" stroke-width="12" '
            f'style="--c:{circ:.1f};stroke-dasharray:{circ:.1f};stroke-dashoffset:{circ * (1 - frac):.1f}"/>'
        )
        legend.append(
            f'<div class="legend-row"><span class="legend-dot" style="background:{color}"></span>'
            f"{label}<b>{shown}</b></div>"
        )
    return (
        f'<div class="rings"><svg viewBox="0 0 160 160">{"".join(parts)}</svg>'
        f'<div class="legend">{"".join(legend)}</div></div>'
    )


def hero(kicker: str, title: str, copy: str, chips: list[str], rings_html: str) -> None:
    """Large Apple-style hero tile: headline, supporting copy, chips and a rings widget."""
    chip_html = "".join(f'<span class="chip">{c}</span>' for c in chips)
    st.markdown(
        f'<div class="hero"><div class="hero-text"><div class="hero-kicker">{kicker}</div>'
        f'<div class="hero-title">{title}</div><div class="hero-copy">{copy}</div>'
        f'<div class="chips">{chip_html}</div></div>{rings_html}</div>',
        unsafe_allow_html=True,
    )


def difficulty_color(value: float) -> str:
    """Green / orange / red by subject difficulty."""
    return "#34C759" if value < 25 else "#FF9500" if value < 45 else "#FF3B30"


def bar_rows(items: list[tuple[str, str, float, float, str, str]]) -> str:
    """Rows of (code, name, value, max, colour, shown) with a bar under each."""
    rows = []
    for code, name, value, vmax, color, shown in items:
        width = max(2.0, min(100.0, value / (vmax or 1) * 100))
        rows.append(
            f'<div class="row-item"><div class="row-main"><div class="row-title">'
            f'<span class="code-tag">{html.escape(code)}</span>{html.escape(name)}</div>'
            f'<div class="track"><i style="width:{width:.0f}%;background:{color}"></i></div></div>'
            f'<div class="row-val">{shown}</div></div>'
        )
    return f'<div class="rows">{"".join(rows)}</div>'


AVATAR_COLORS = ["#007AFF", "#5856D6", "#AF52DE", "#FF9500", "#30B0C7", "#FF2D55", "#34C759"]


def people_rows(people: list[tuple[str, str, str, str]]) -> str:
    """Rows of (name, subtitle, badge_text, badge_level) with initials avatars."""
    rows = []
    for name, sub, badge_text, level in people:
        initials = "".join(w[0] for w in name.split()[:2]).upper()
        color = AVATAR_COLORS[sum(map(ord, name)) % len(AVATAR_COLORS)]
        rows.append(
            f'<div class="row-item"><span class="avatar" style="background:{color}">{html.escape(initials)}</span>'
            f'<div class="row-main"><div class="row-title">{html.escape(name)}</div>'
            f'<div class="row-sub">{html.escape(sub)}</div></div>'
            f'<span class="pill {level.lower()}">{html.escape(badge_text)}</span></div>'
        )
    return f'<div class="rows">{"".join(rows)}</div>'


def html_table(df: pd.DataFrame, columns: list[dict], max_height: int | None = None) -> None:
    """Clean HTML table. Column dict keys: key, label, kind (text|code|num|bar|pill), fmt, max, color."""
    head = "".join(
        f'<th class="{"r" if c.get("kind") in ("num",) else ""}">{html.escape(c["label"])}</th>'
        for c in columns
    )
    body = []
    for _, row in df.iterrows():
        cells = []
        for c in columns:
            value = row[c["key"]]
            kind = c.get("kind", "text")
            fmt = c.get("fmt", "{}")
            if kind == "bar":
                vmax = c.get("max", 100)
                pct = max(0.0, min(100.0, (value / vmax * 100) if value == value else 0))
                color = c["color"](value) if callable(c.get("color")) else c.get("color", "#007AFF")
                shown = fmt.format(value) if value == value else "–"
                cells.append(
                    f'<td><div class="cellbar"><div class="track"><i style="width:{pct:.0f}%;'
                    f'background:{color}"></i></div><span>{shown}</span></div></td>'
                )
            elif kind == "num":
                cells.append(f'<td class="r">{fmt.format(value) if value == value else "–"}</td>')
            elif kind == "code":
                cells.append(f'<td><span class="code-tag">{html.escape(str(value))}</span></td>')
            elif kind == "pill":
                cells.append(
                    f'<td><span class="pill {str(value).lower()}">{html.escape(str(value))}</span></td>'
                )
            else:
                cells.append(f"<td>{html.escape(str(value))}</td>")
        body.append(f'<tr>{"".join(cells)}</tr>')
    style = f' style="max-height:{max_height}px"' if max_height else ""
    st.markdown(
        f'<div class="tbl-wrap"{style}><table class="tbl"><thead><tr>{head}</tr></thead>'
        f'<tbody>{"".join(body)}</tbody></table></div>',
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
    with right:
        plot(fig, key=f"{key}_c")

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
