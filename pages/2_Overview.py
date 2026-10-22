import streamlit as st
import webui

from examlens import charts, insights, metrics

df, settings = webui.page_data("Overview", "Pass rates, trends and key insights at a glance.")

kpis = metrics.session_kpis(df)
last = kpis.iloc[-1]
prev = kpis.iloc[-2] if len(kpis) > 1 else None


def delta_pts(key: str) -> str | None:
    if prev is None or prev[key] != prev[key] or last[key] != last[key]:
        return None
    return f"{(last[key] - prev[key]) * 100:+.1f} pts"


risk_now = webui.cached_risk(df, settings["weights"], settings["levels"])
high_now = int((risk_now["risk_level"] == "High").sum())
high_delta = None
if prev is not None:
    before = df[df["session_date"] <= prev["session_date"]]
    risk_before = webui.cached_risk(before, settings["weights"], settings["levels"])
    high_delta = high_now - int((risk_before["risk_level"] == "High").sum())

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric(
    "Students",
    f"{df['student_id'].nunique():,}",
    None if prev is None else f"{int(last['students'] - prev['students']):+d} vs prev session",
)
c2.metric("Pass rate", f"{metrics.pass_rate(df):.1%}", delta_pts("pass_rate"))
c3.metric(
    "First-attempt pass rate",
    f"{metrics.first_attempt_pass_rate(df):.1%}",
    delta_pts("first_attempt_pass_rate"),
)
c4.metric(
    "Absence rate",
    f"{metrics.absence_rate(df):.1%}",
    delta_pts("absence_rate"),
    delta_color="inverse",
)
c5.metric(
    "High-risk students",
    f"{high_now:,}",
    None if high_delta is None else f"{high_delta:+d} since prev session",
    delta_color="inverse",
)
st.caption(f"Changes compare the latest session ({last['exam_session']}) with the one before it.")

st.subheader("Key insights")
items = insights.key_insights(df)
if items:
    webui.insight_box(items)

left, right = st.columns(2)
left.plotly_chart(charts.pass_rate_trend(metrics.session_trend(df)), use_container_width=True)
right.plotly_chart(charts.grade_distribution(df), use_container_width=True)

group = st.radio("Pass rate by", ["programme", "intake"], horizontal=True)
rates = (
    df.groupby(group)
    .apply(metrics.pass_rate, include_groups=False)
    .rename("pass_rate")
    .reset_index()
)
st.plotly_chart(charts.pass_rate_by_group(rates, group), use_container_width=True)
