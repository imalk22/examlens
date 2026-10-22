import streamlit as st
import webui

from examlens import charts, insights, metrics

df, settings = webui.page_data("Overview", "Pass rates, trends and key insights at a glance.")

kpis = metrics.session_kpis(df)
last = kpis.iloc[-1]
prev = kpis.iloc[-2] if len(kpis) > 1 else None


def pts(key: str) -> tuple[float | None, str]:
    """Change in a rate (percentage points) between the last two sessions."""
    if prev is None or prev[key] != prev[key] or last[key] != last[key]:
        return None, ""
    delta = (last[key] - prev[key]) * 100
    return delta, f"{abs(delta):.1f} pts"


risk_now = webui.cached_risk(df, settings["weights"], settings["levels"])
level_counts = risk_now["risk_level"].value_counts().to_dict()
high_now = int(level_counts.get("High", 0))
high_delta = None
if prev is not None:
    before = df[df["session_date"] <= prev["session_date"]]
    risk_before = webui.cached_risk(before, settings["weights"], settings["levels"])
    high_delta = high_now - int((risk_before["risk_level"] == "High").sum())

summary = webui.cached_summary(df)
pass_rate = metrics.pass_rate(df)
first_rate = metrics.first_attempt_pass_rate(df)
absence = metrics.absence_rate(df)
n_sessions = df["exam_session"].nunique()
never_count = len(metrics.never_passed(df))

# --- hero ---------------------------------------------------------------------------------------
webui.hero(
    f"Overview · {last['exam_session']}",
    "Cohort performance",
    f"{pass_rate:.0%} of graded attempts were passed across {n_sessions} sessions. "
    f"{high_now} students are at high risk and {never_count:,} subject results are still outstanding.",
    [
        f"{df['student_id'].nunique():,} students",
        f"{df['subject_code'].nunique()} subjects",
        f"{n_sessions} sessions",
        f"{kpis.iloc[0]['exam_session']} → {last['exam_session']}",
    ],
    webui.rings_svg(
        [
            ("Pass rate", pass_rate, "#34C759", f"{pass_rate:.0%}"),
            ("First attempt", first_rate, "#FF9500", f"{first_rate:.0%}"),
            ("Attendance", 1 - absence, "#007AFF", f"{1 - absence:.0%}"),
        ]
    ),
)

# --- KPI row ------------------------------------------------------------------------------------
cols = st.columns(5)
with cols[0]:
    delta = None if prev is None else float(last["students"] - prev["students"])
    webui.kpi_card(
        "Students",
        f"{df['student_id'].nunique():,}",
        "#007AFF",
        delta,
        "" if delta is None else f"{abs(delta):,.0f}",
        spark=kpis["students"].tolist(),
        note="sitting per session",
    )
with cols[1]:
    d, t = pts("pass_rate")
    webui.kpi_card(
        "Pass rate",
        f"{pass_rate:.1%}",
        "#34C759",
        d,
        t,
        spark=kpis["pass_rate"].tolist(),
        note="vs previous session",
    )
with cols[2]:
    d, t = pts("first_attempt_pass_rate")
    webui.kpi_card(
        "First attempt",
        f"{first_rate:.1%}",
        "#FF9500",
        d,
        t,
        spark=kpis["first_attempt_pass_rate"].tolist(),
        note="pass rate, attempt 1",
    )
with cols[3]:
    d, t = pts("absence_rate")
    webui.kpi_card(
        "Absence rate",
        f"{absence:.1%}",
        "#AF52DE",
        d,
        t,
        up_is_good=False,
        spark=kpis["absence_rate"].tolist(),
        note="of registered attempts",
    )
with cols[4]:
    bar = webui.stack_bar(
        [
            (level_counts.get("High", 0), "#FF3B30"),
            (level_counts.get("Medium", 0), "#FF9500"),
            (level_counts.get("Low", 0), "#34C759"),
        ]
    )
    webui.kpi_card(
        "High risk",
        f"{high_now:,}",
        "#FF3B30",
        None if high_delta is None else float(high_delta),
        "" if high_delta is None else f"{abs(high_delta):,}",
        up_is_good=False,
        footer=bar,
        note="students needing support",
    )

# --- trend + insights ----------------------------------------------------------------------------
left, right = st.columns([2, 1])
with left:
    fig = charts.pass_rate_trend(metrics.session_trend(df))
    fig.update_layout(height=340)
    webui.plot(fig)
with right:
    items = insights.key_insights(df)
    webui.widget(
        "Key insights",
        "".join(
            f'<p style="margin:.55rem 0;font-size:.9rem;line-height:1.4">• {i}</p>' for i in items
        ),
        "Generated from the current filters",
    )

# --- distribution charts ---------------------------------------------------------------------------
c1, c2, c3 = st.columns(3)
fig = charts.grade_distribution(df)
fig.update_layout(height=300)
with c1:
    webui.plot(fig)
for col, group in ((c2, "programme"), (c3, "intake")):
    rates = (
        df.groupby(group)
        .apply(metrics.pass_rate, include_groups=False)
        .rename("pass_rate")
        .reset_index()
    )
    fig = charts.pass_rate_by_group(rates, group)
    fig.update_layout(height=300)
    if group == "programme":
        fig.update_xaxes(
            tickvals=rates[group], ticktext=[p.replace("Diploma in ", "") for p in rates[group]]
        )
    with col:
        webui.plot(fig)

# --- widgets ---------------------------------------------------------------------------------------
w1, w2, w3 = st.columns(3)
with w1:
    top = summary.head(5)
    webui.widget(
        "Hardest subjects",
        webui.bar_rows(
            [
                (
                    r.subject_code,
                    r.subject_name,
                    r.difficulty_index,
                    100,
                    webui.difficulty_color(r.difficulty_index),
                    f"{r.difficulty_index:.0f}",
                )
                for r in top.itertuples()
            ]
        ),
        "Difficulty index, 0-100",
    )
with w2:
    urgent = risk_now.head(6)
    webui.widget(
        "Needs attention",
        webui.people_rows(
            [
                (r.student_name, f"{r.student_id} · {r.intake}", f"{r.risk_score}", r.risk_level)
                for r in urgent.itertuples()
            ]
        ),
        "Highest risk scores right now",
    )
with w3:
    fig = charts.risk_donut(level_counts)
    fig.update_layout(height=300)
    webui.plot(fig)
