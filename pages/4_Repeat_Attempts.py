import webui

from examlens import viewmodel

df, settings = webui.page_data(
    "Repeat Attempts", "How many attempts students need, and who is still outstanding."
)

summary = webui.cached_summary(df)
webui.canvas("repeats", viewmodel.repeats(df, summary), height=1300)
