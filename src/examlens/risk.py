"""Transparent, rule-based at-risk scoring. No machine learning: every flag is explainable."""

from __future__ import annotations

import pandas as pd

from examlens import config

OUTPUT_COLUMNS = [
    "student_id",
    "student_name",
    "programme",
    "intake",
    "risk_score",
    "risk_level",
    "reasons",
    "outstanding_subjects",
    "latest_avg",
]


def risk_level(score: float, levels: dict[str, int] | None = None) -> str:
    """Highest level whose threshold ``score`` reaches."""
    levels = levels or config.RISK_LEVELS
    for name, threshold in sorted(levels.items(), key=lambda kv: kv[1], reverse=True):
        if score >= threshold:
            return name
    return min(levels, key=levels.get)


def _times(n: int) -> str:
    return "twice" if n == 2 else f"{n} times"


def score_student(
    sub: pd.DataFrame,
    weights: dict[str, int] | None = None,
    params: dict[str, int] | None = None,
) -> dict:
    """Score one student's rows. Returns score, reasons and supporting numbers."""
    w = weights or config.RISK_WEIGHTS
    p = params or config.RISK_PARAMS
    score = 0
    reasons: list[str] = []

    fails = sub[sub["result"] == "Fail"].groupby("subject_code").size()
    repeated = fails[fails >= 2]
    if len(repeated):
        score += w["repeat_fail_same_subject"]
        reasons += [f"Failed {code} {_times(int(n))}" for code, n in repeated.items()]

    passed = set(sub.loc[sub["result"] == "Pass", "subject_code"])
    outstanding = sorted(set(sub["subject_code"]) - passed)
    if outstanding:
        score += w["outstanding_fails"] * min(len(outstanding), p["outstanding_cap"])
        noun = "subject" if len(outstanding) == 1 else "subjects"
        reasons.append(f"{len(outstanding)} {noun} outstanding")

    absences = int((sub["status"] == "Absent").sum())
    if absences:
        score += w["absences"] * min(absences, p["absence_cap"])
        reasons.append(f"Absent {_times(absences)}" if absences > 1 else "Absent once")

    by_session = (
        sub.dropna(subset=["marks", "session_date"]).groupby("session_date")["marks"].mean()
    ).sort_index()
    latest_avg = float(by_session.iloc[-1]) if len(by_session) else float("nan")
    if len(by_session) >= 2:
        drop = float(by_session.iloc[-2] - by_session.iloc[-1])
        if drop >= p["decline_points"]:
            score += w["declining_trend"]
            reasons.append(f"Average dropped {drop:.0f} marks since last session")
    if len(by_session) and latest_avg < p["low_average"]:
        score += w["low_recent_average"]
        reasons.append(f"Latest average {latest_avg:.0f} is below {p['low_average']}")

    return {
        "risk_score": score,
        "reasons": " · ".join(reasons),
        "outstanding_subjects": len(outstanding),
        "latest_avg": latest_avg,
    }


def compute_risk(
    df: pd.DataFrame,
    weights: dict[str, int] | None = None,
    levels: dict[str, int] | None = None,
    params: dict[str, int] | None = None,
) -> pd.DataFrame:
    """Risk table for every student, highest score first."""
    rows = []
    for sid, sub in df.groupby("student_id"):
        first = sub.iloc[0]
        row = {
            "student_id": sid,
            "student_name": first["student_name"],
            "programme": first["programme"],
            "intake": first["intake"],
            **score_student(sub, weights, params),
        }
        row["risk_level"] = risk_level(row["risk_score"], levels)
        rows.append(row)
    out = pd.DataFrame(rows, columns=OUTPUT_COLUMNS)
    return out.sort_values(["risk_score", "student_id"], ascending=[False, True], ignore_index=True)
