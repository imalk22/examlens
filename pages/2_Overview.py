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
        f"{metrics.pass_rate(df):.1%}",
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
        f"{metrics.first_attempt_pass_rate(df):.1%}",
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
        f"{metrics.absence_rate(df):.1%}",
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

left, right = st.columns([2, 1])
with left:
    fig = charts.pass_rate_trend(metrics.session_trend(df))
    fig.update_layout(height=330)
    st.plotly_chart(fig, use_container_width=True)
with right:
    st.subheader("Key insights")
    items = insights.key_insights(df)
    if items:
        webui.insight_box(items)

c1, c2, c3 = st.columns(3)
fig = charts.grade_distribution(df)
fig.update_layout(height=300)
c1.plotly_chart(fig, use_container_width=True)
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
    col.plotly_chart(fig, use_container_width=True)

c4, c5 = st.columns([3, 2])
with c4:
    st.subheader("Hardest subjects")
    st.dataframe(
        webui.cached_summary(df)[
            [
                "subject_code",
                "subject_name",
                "difficulty_index",
                "first_attempt_pass_rate",
                "never_passed",
            ]
        ].head(5),
        hide_index=True,
        use_container_width=True,
        column_config={
            "subject_code": "Code",
            "subject_name": "Subject",
            "difficulty_index": st.column_config.ProgressColumn(
                "Difficulty", min_value=0, max_value=100, format="%.0f"
            ),
            "first_attempt_pass_rate": st.column_config.NumberColumn(
                "First-attempt pass", format="percent"
            ),
            "never_passed": "Never passed",
        },
    )
with c5:
    fig = charts.risk_donut(level_counts)
    fig.update_layout(height=240)
    st.plotly_chart(fig, use_container_width=True)
