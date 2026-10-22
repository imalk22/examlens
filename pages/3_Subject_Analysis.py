import webui

from examlens import viewmodel

df, settings = webui.page_data(
    "Subject Analysis", "Which subjects are hardest, and how they change over time."
)

summary = webui.cached_summary(df)
webui.canvas(
    "subjects",
    viewmodel.subjects(df, summary, settings["pass_mark"]),
    pass_mark=settings["pass_mark"],
    height=900,
)
