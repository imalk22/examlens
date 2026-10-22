import webui

from examlens import viewmodel

df, settings = webui.page_data(
    "At-Risk Students", "Transparent, rule-based flags with plain-English reasons."
)

table = webui.cached_risk(df, settings["weights"], settings["levels"])
webui.canvas("risk", viewmodel.risk_page(df, table), pass_mark=settings["pass_mark"], height=1200)
