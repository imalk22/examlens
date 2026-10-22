"""Template-based "Key insights" sentences generated from the data."""

from __future__ import annotations

import pandas as pd

from examlens import metrics


def key_insights(df: pd.DataFrame, max_items: int = 5) -> list[str]:
    """Return up to ``max_items`` plain-English insights about ``df``."""
    if df.empty:
        return []
    out: list[str] = []
    summary = metrics.subject_summary(df)
    summary = summary[summary["first_attempt_pass_rate"].notna()]
    if len(summary):
        hard = summary.iloc[0]
        out.append(
            f"{hard['subject_code']} ({hard['subject_name']}) is the hardest subject "
            f"(difficulty {hard['difficulty_index']:.0f}/100) with a "
            f"{hard['first_attempt_pass_rate']:.0%} first-attempt pass rate."
        )
        easy = summary.iloc[-1]
        if easy["subject_code"] != hard["subject_code"]:
            out.append(
                f"{easy['subject_code']} is the easiest subject, with a "
                f"{easy['pass_rate']:.0%} overall pass rate."
            )

    kpis = metrics.session_kpis(df)
    if len(kpis) >= 2:
        last, prev = kpis.iloc[-1], kpis.iloc[-2]
        diff = (last["pass_rate"] - prev["pass_rate"]) * 100
        if abs(diff) >= 0.5:
            direction = "improved" if diff > 0 else "fell"
            out.append(
                f"The pass rate {direction} by {abs(diff):.1f} points in {last['exam_session']} "
                f"compared with {prev['exam_session']} ({last['pass_rate']:.0%})."
            )
        else:
            out.append(
                f"The pass rate was steady in {last['exam_session']} ({last['pass_rate']:.0%})."
            )

    rep = metrics.repeat_rate(df)
    never = len(metrics.never_passed(df))
    if rep == rep:
        out.append(
            f"{rep:.0%} of student-subject pairs needed more than one attempt, and "
            f"{never:,} have not passed yet."
        )

    by_prog = df.groupby("programme").apply(metrics.pass_rate, include_groups=False).dropna()
    if len(by_prog) >= 2:
        out.append(
            f"{by_prog.idxmax()} has the highest pass rate ({by_prog.max():.0%}); "
            f"{by_prog.idxmin()} has the lowest ({by_prog.min():.0%})."
        )
    return out[:max_items]
