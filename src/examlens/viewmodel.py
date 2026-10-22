"""JSON-ready view models for the dashboard canvas. No Streamlit imports."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from examlens import insights, metrics

SHORT = "Diploma in "


def clean(obj: Any) -> Any:
    """Recursively convert numpy/pandas values to plain JSON types (NaN becomes None)."""
    if isinstance(obj, dict):
        return {str(k): clean(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [clean(v) for v in obj]
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating | float):
        return None if math.isnan(obj) or math.isinf(obj) else float(obj)
    if isinstance(obj, pd.Timestamp):
        return obj.strftime("%Y-%m-%d")
    if obj is pd.NaT or obj is pd.NA:
        return None
    if isinstance(obj, np.bool_):
        return bool(obj)
    return obj


def _pct(value: float) -> float | None:
    return None if value != value else round(value * 100, 1)


def _delta(last: float, prev: float | None, unit: str = " pts", up_is_good: bool = True) -> dict:
    if prev is None or prev != prev or last != last:
        return {}
    diff = (last - prev) * 100
    kind = "flat" if abs(diff) < 0.05 else "good" if (diff > 0) == up_is_good else "bad"
    arrow = "" if kind == "flat" else ("↑ " if diff > 0 else "↓ ")
    return {"text": f"{arrow}{abs(diff):.1f}{unit}", "kind": kind}


def overview(df: pd.DataFrame, risk: pd.DataFrame, summary: pd.DataFrame, before_high: int | None):
    """Everything the Overview page needs."""
    kpis = metrics.session_kpis(df)
    last = kpis.iloc[-1]
    prev = kpis.iloc[-2] if len(kpis) > 1 else None
    pass_rate = metrics.pass_rate(df)
    first = metrics.first_attempt_pass_rate(df)
    absence = metrics.absence_rate(df)
    counts = risk["risk_level"].value_counts().to_dict()
    high = int(counts.get("High", 0))
    never = len(metrics.never_passed(df))
    n_sessions = int(df["exam_session"].nunique())

    def d(key: str, up: bool = True) -> dict:
        return _delta(last[key], None if prev is None else prev[key], up_is_good=up)

    student_delta: dict = {}
    if prev is not None:
        diff = int(last["students"] - prev["students"])
        student_delta = {
            "text": f"{'↑' if diff > 0 else '↓'} {abs(diff):,}",
            "kind": "flat" if diff == 0 else "good" if diff > 0 else "bad",
        }
    high_delta: dict = {}
    if before_high is not None:
        diff = high - before_high
        high_delta = {
            "text": f"{'↑' if diff > 0 else '↓'} {abs(diff)}",
            "kind": "flat" if diff == 0 else "bad" if diff > 0 else "good",
        }

    by_prog = (
        df.groupby("programme").apply(metrics.pass_rate, include_groups=False).dropna().sort_index()
    )
    by_intake = (
        df.groupby("intake").apply(metrics.pass_rate, include_groups=False).dropna().sort_index()
    )
    grades = df["grade"].value_counts().reindex(["A", "B", "C", "D", "F"], fill_value=0)

    return clean(
        {
            "hero": {
                "kicker": f"Overview · {last['exam_session']}",
                "title": "Cohort performance",
                "copy": (
                    f"{pass_rate:.0%} of graded attempts were passed across {n_sessions} sessions. "
                    f"{high} students are at high risk and {never:,} subject results are still "
                    "outstanding."
                ),
                "chips": [
                    f"{df['student_id'].nunique():,} students",
                    f"{df['subject_code'].nunique()} subjects",
                    f"{n_sessions} sessions",
                    f"{kpis.iloc[0]['exam_session']} → {last['exam_session']}",
                ],
                "rings": [
                    {"label": "Pass rate", "value": pass_rate, "color": "#34C759"},
                    {"label": "First attempt", "value": first, "color": "#FF9500"},
                    {"label": "Attendance", "value": 1 - absence, "color": "#0A84FF"},
                ],
            },
            "kpis": [
                {
                    "label": "Students",
                    "value": f"{df['student_id'].nunique():,}",
                    "color": "#0A84FF",
                    "delta": student_delta,
                    "spark": kpis["students"].tolist(),
                    "note": "sitting per session",
                },
                {
                    "label": "Pass rate",
                    "value": f"{pass_rate:.1%}",
                    "color": "#34C759",
                    "delta": d("pass_rate"),
                    "spark": (kpis["pass_rate"] * 100).tolist(),
                    "note": "vs previous session",
                },
                {
                    "label": "First attempt",
                    "value": f"{first:.1%}",
                    "color": "#FF9500",
                    "delta": d("first_attempt_pass_rate"),
                    "spark": (kpis["first_attempt_pass_rate"] * 100).tolist(),
                    "note": "pass rate, attempt 1",
                },
                {
                    "label": "Absence rate",
                    "value": f"{absence:.1%}",
                    "color": "#BF5AF2",
                    "delta": d("absence_rate", up=False),
                    "spark": (kpis["absence_rate"] * 100).tolist(),
                    "note": "of registered attempts",
                },
                {
                    "label": "High risk",
                    "value": f"{high:,}",
                    "color": "#FF453A",
                    "delta": high_delta,
                    "bar": [
                        [int(counts.get("High", 0)), "#FF453A"],
                        [int(counts.get("Medium", 0)), "#FF9F0A"],
                        [int(counts.get("Low", 0)), "#30D158"],
                    ],
                    "note": "students needing support",
                },
            ],
            "trend": {
                "labels": kpis["exam_session"].tolist(),
                "pass": (kpis["pass_rate"] * 100).round(1).tolist(),
                "first": (kpis["first_attempt_pass_rate"] * 100).round(1).tolist(),
            },
            "insights": insights.key_insights(df),
            "grades": {"labels": grades.index.tolist(), "values": grades.tolist()},
            "programmes": {
                "labels": [p.replace(SHORT, "") for p in by_prog.index],
                "values": (by_prog * 100).round(1).tolist(),
            },
            "intakes": {
                "labels": by_intake.index.tolist(),
                "values": (by_intake * 100).round(1).tolist(),
            },
            "hardest": [
                {"code": r.subject_code, "name": r.subject_name, "value": r.difficulty_index}
                for r in summary.head(5).itertuples()
            ],
            "attention": [
                {
                    "name": r.student_name,
                    "sub": f"{r.student_id} · {r.intake}",
                    "score": r.risk_score,
                    "level": r.risk_level,
                }
                for r in risk.head(6).itertuples()
            ],
            "risk": {k: int(counts.get(k, 0)) for k in ("High", "Medium", "Low")},
        }
    )


def subjects(df: pd.DataFrame, summary: pd.DataFrame, pass_mark: float) -> dict:
    """Leaderboard rows plus per-subject detail (histogram, trend, first vs repeat)."""
    rows = [
        {
            "code": r.subject_code,
            "name": r.subject_name,
            "difficulty": r.difficulty_index,
            "pass": r.pass_rate,
            "first": r.first_attempt_pass_rate,
            "repeat": r.repeat_rate,
            "mean": r.mean_mark,
            "median": r.median_mark,
            "never": r.never_passed,
            "candidates": r.candidates,
            "attempts": r.attempts,
        }
        for r in summary.itertuples()
    ]
    detail = {}
    edges = list(range(0, 105, 5))
    for code, sub in df.groupby("subject_code"):
        counts, _ = np.histogram(sub["marks"].dropna(), bins=edges)
        trend = metrics.session_trend(sub)
        detail[code] = {
            "hist": counts.tolist(),
            "trend": {
                "labels": trend["exam_session"].tolist(),
                "pass": (trend["pass_rate"] * 100).round(1).tolist(),
            },
            "first": _pct(metrics.pass_rate(sub[sub["attempt_no"] == 1])),
            "repeat": _pct(metrics.pass_rate(sub[sub["attempt_no"] > 1])),
        }
    return clean({"rows": rows, "detail": detail, "pass_mark": pass_mark})


def repeats(df: pd.DataFrame, summary: pd.DataFrame) -> dict:
    """Repeat-attempt data: KPIs, distributions, funnels, ranking and never-passed list."""
    pairs = metrics.pair_table(df)
    passed = pairs[pairs["pass_attempt"].notna()]
    never = metrics.never_passed(df)

    def dist(data: pd.DataFrame) -> dict:
        return {str(int(k)): int(v) for k, v in metrics.attempts_to_pass_distribution(data).items()}

    def funnel(p: pd.DataFrame) -> dict:
        a = p["pass_attempt"]
        return {
            "attempted": len(p),
            "first": int((a == 1).sum()),
            "second": int((a == 2).sum()),
            "later": int((a >= 3).sum()),
            "outstanding": int(a.isna().sum()),
        }

    codes = summary["subject_code"].tolist()
    return clean(
        {
            "kpis": {
                "repeat_rate": metrics.repeat_rate(df),
                "avg_attempts": passed["pass_attempt"].mean() if len(passed) else None,
                "first_time": (passed["pass_attempt"] == 1).mean() if len(passed) else None,
                "never": len(never),
            },
            "codes": [
                {"code": r.subject_code, "name": r.subject_name} for r in summary.itertuples()
            ],
            "dist": {"all": dist(df), **{c: dist(df[df["subject_code"] == c]) for c in codes}},
            "funnel": {
                "all": funnel(pairs),
                **{c: funnel(pairs[pairs["subject_code"] == c]) for c in codes},
            },
            "ranking": [
                {
                    "code": r.subject_code,
                    "name": r.subject_name,
                    "repeat": r.repeat_rate,
                    "avg": r.mean_attempts_to_pass,
                    "never": r.never_passed,
                }
                for r in summary.sort_values("repeat_rate", ascending=False).itertuples()
            ],
            "never": [
                {
                    "id": r.student_id,
                    "name": r.student_name,
                    "code": r.subject_code,
                    "subject": r.subject_name,
                    "attempts": r.attempts,
                }
                for r in never.itertuples()
            ],
        }
    )


def profile(history: pd.DataFrame, risk_row: pd.Series | None) -> dict:
    """One student's profile: details, risk, history rows, outstanding subjects."""
    first = history.iloc[0]
    ordered = history.sort_values(["session_date", "subject_code"])
    passed = set(history.loc[history["result"] == "Pass", "subject_code"])
    remaining = (
        history[~history["subject_code"].isin(passed)]
        .groupby(["subject_code", "subject_name"])
        .agg(attempts=("attempt_no", "max"), best=("marks", "max"))
        .reset_index()
    )
    graded = history[history["result"].isin(["Pass", "Fail"])]
    return {
        "id": first["student_id"],
        "name": first["student_name"],
        "programme": first["programme"],
        "intake": first["intake"],
        "level": None if risk_row is None else risk_row["risk_level"],
        "score": None if risk_row is None else risk_row["risk_score"],
        "reasons": "" if risk_row is None else risk_row["reasons"],
        "passed": len(passed),
        "subjects": int(history["subject_code"].nunique()),
        "attempt_pass": _pct((graded["result"] == "Pass").mean()) if len(graded) else None,
        "history": [
            [
                r.exam_session,
                r.subject_code,
                r.subject_name,
                r.attempt_no,
                r.marks,
                r.grade,
                r.result,
            ]
            for r in ordered.itertuples()
        ],
        "remaining": [
            {"code": r.subject_code, "name": r.subject_name, "attempts": r.attempts, "best": r.best}
            for r in remaining.itertuples()
        ],
    }


def risk_page(df: pd.DataFrame, risk: pd.DataFrame) -> dict:
    """At-risk table rows, counts and every student's profile (for the in-page drawer)."""
    by_id = risk.set_index("student_id")
    profiles = {sid: profile(history, by_id.loc[sid]) for sid, history in df.groupby("student_id")}
    return clean(
        {
            "counts": {k: int(v) for k, v in risk["risk_level"].value_counts().items()},
            "rows": [
                {
                    "id": r.student_id,
                    "name": r.student_name,
                    "programme": r.programme,
                    "intake": r.intake,
                    "score": r.risk_score,
                    "level": r.risk_level,
                    "reasons": r.reasons,
                    "outstanding": r.outstanding_subjects,
                    "latest": r.latest_avg,
                }
                for r in risk.itertuples()
            ],
            "profiles": profiles,
            "pass_mark": None,
        }
    )


def student_page(df: pd.DataFrame, student_id: str, risk: pd.DataFrame, pass_mark: float) -> dict:
    """Profile for the Student Lookup page."""
    history = df[df["student_id"] == student_id]
    row = risk[risk["student_id"] == student_id]
    return clean(
        {"profile": profile(history, row.iloc[0] if len(row) else None), "pass_mark": pass_mark}
    )


def health(report, data: pd.DataFrame) -> dict:
    """Data-health page: KPIs, checks, per-file rows, issue details and a data preview."""
    cols = ["student_id", "student_name", "programme", "intake", "subject_code", "exam_session",
            "attempt_no", "marks", "grade", "result"]  # fmt: skip
    return clean(
        {
            "kpis": {
                "loaded": report.rows_loaded,
                "final": report.rows_final,
                "students": int(data["student_id"].nunique()),
                "files": len(report.rows_per_file),
            },
            "checks": [
                {
                    "ok": report.duplicates_removed == 0,
                    "text": f"Duplicate rows removed (kept highest mark): <b>{report.duplicates_removed}</b>",
                },
                {
                    "ok": report.invalid_marks == 0,
                    "text": f"Marks outside 0-100 (excluded): <b>{report.invalid_marks}</b>",
                },
                {
                    "ok": not report.name_conflicts,
                    "text": f"Student IDs with conflicting names: <b>{len(report.name_conflicts)}</b>",
                },
                {
                    "ok": report.rows_dropped_missing_required == 0,
                    "text": "Rows dropped for missing ID, subject or session: "
                    f"<b>{report.rows_dropped_missing_required}</b>",
                },
                {
                    "ok": None,
                    "text": f"Absent attempts: <b>{report.absent_count}</b> · Medical: <b>{report.medical_count}</b>",
                },
            ]
            + (
                [
                    {
                        "ok": None,
                        "text": "Wide-format files converted: " + ", ".join(report.wide_files),
                    }
                ]
                if report.wide_files
                else []
            ),
            "files": [{"file": f, "rows": n} for f, n in report.rows_per_file.items()],
            "name_conflicts": [
                {"id": c["student_id"], "names": " / ".join(c["names"]), "kept": c["kept"]}
                for c in report.name_conflicts
            ],
            "invalid": report.invalid_mark_rows,
            "duplicates": report.duplicate_keys,
            "columns": cols,
            "preview": data[cols].head(150).values.tolist(),
            "total_rows": len(data),
        }
    )
