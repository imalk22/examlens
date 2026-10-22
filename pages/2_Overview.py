import webui

from examlens import viewmodel

df, settings = webui.page_data("Overview", "Pass rates, trends and key insights at a glance.")

risk_now = webui.cached_risk(df, settings["weights"], settings["levels"])
summary = webui.cached_summary(df)

# High-risk count as of the previous session, for the delta chip.
sessions = df.drop_duplicates("exam_session").sort_values("session_date")
before_high = None
if len(sessions) > 1:
    prev_date = sessions.iloc[-2]["session_date"]
    earlier = webui.cached_risk(
        df[df["session_date"] <= prev_date], settings["weights"], settings["levels"]
    )
    before_high = int((earlier["risk_level"] == "High").sum())

webui.canvas("overview", viewmodel.overview(df, risk_now, summary, before_high), height=1500)
