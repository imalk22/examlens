"""Pass rates, difficulty index, attempts-to-pass and trends.

Every function is pure: it takes the cleaned DataFrame (see ``schema.COLUMNS``) and returns
numbers or DataFrames. Definitions match the "Metric definitions" table in the README.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def graded(df: pd.DataFrame) -> pd.DataFrame:
    """Rows with a Pass or Fail result (absentees and invalid marks are excluded)."""
    return df[df["result"].isin(["Pass", "Fail"])]


def pass_rate(df: pd.DataFrame) -> float:
    """Passes / (Passes + Fails). NaN when there are no graded rows."""
    g = graded(df)
    return float((g["result"] == "Pass").mean()) if len(g) else float("nan")


def first_attempt_pass_rate(df: pd.DataFrame) -> float:
    """Pass rate counting only ``attempt_no == 1``."""
    return pass_rate(df[df["attempt_no"] == 1])


def absence_rate(df: pd.DataFrame) -> float:
    """Absent (including medical) rows / all registered attempts."""
    return float((df["result"] == "Absent").mean()) if len(df) else float("nan")


def mark_stats(df: pd.DataFrame) -> dict[str, float]:
    """Mean and median of non-null marks."""
    marks = df["marks"].dropna()
    if marks.empty:
        return {"mean": float("nan"), "median": float("nan")}
    return {"mean": float(marks.mean()), "median": float(marks.median())}


def pair_table(df: pd.DataFrame) -> pd.DataFrame:
    """One row per (student, subject): ``attempts`` and ``pass_attempt`` (NaN if never passed)."""
    keys = ["student_id", "subject_code"]
    pairs = df.groupby(keys).agg(attempts=("attempt_no", "max"))
    passed = df[df["result"] == "Pass"].groupby(keys)["attempt_no"].min().rename("pass_attempt")
    return pairs.join(passed).reset_index()


def repeat_rate(df: pd.DataFrame) -> float:
    """Share of (student, subject) pairs needing more than one attempt."""
    pairs = pair_table(df)
    return float((pairs["attempts"] > 1).mean()) if len(pairs) else float("nan")


def attempts_to_pass(df: pd.DataFrame) -> pd.DataFrame:
    """For each (student, subject) eventually passed: the attempt number of the first pass."""
    pairs = pair_table(df)
    return pairs[pairs["pass_attempt"].notna()][["student_id", "subject_code", "pass_attempt"]]


def attempts_to_pass_distribution(df: pd.DataFrame, subject_code: str | None = None) -> pd.Series:
    """Count of (student, subject) passes by the attempt number they passed on."""
    data = df if subject_code is None else df[df["subject_code"] == subject_code]
    counts = attempts_to_pass(data)["pass_attempt"].astype(int).value_counts().sort_index()
    counts.index.name = "attempts_to_pass"
    return counts


def never_passed(df: pd.DataFrame) -> pd.DataFrame:
    """Students with at least one attempt and no pass in a subject."""
    pairs = pair_table(df)
    out = pairs[pairs["pass_attempt"].isna()][["student_id", "subject_code", "attempts"]]
    names = df.drop_duplicates("student_id")[["student_id", "student_name"]]
    subjects = df.drop_duplicates("subject_code")[["subject_code", "subject_name"]]
    return out.merge(names, on="student_id").merge(subjects, on="subject_code")


def difficulty_index(
    first_attempt_fail_rate: float, repeat_rate_: float, mean_mark: float
) -> float:
    """Subject Difficulty Index on 0-100 (higher = harder).

    ``100 * (0.5 * first_attempt_fail_rate + 0.3 * repeat_rate + 0.2 * (1 - mean_mark / 100))``
    """
    return 100 * (0.5 * first_attempt_fail_rate + 0.3 * repeat_rate_ + 0.2 * (1 - mean_mark / 100))


def subject_summary(df: pd.DataFrame) -> pd.DataFrame:
    """One row per subject with all headline metrics, sorted hardest first."""
    rows = []
    for code, sub in df.groupby("subject_code"):
        stats = mark_stats(sub)
        far = first_attempt_pass_rate(sub)
        rep = repeat_rate(sub)
        atp = attempts_to_pass(sub)["pass_attempt"]
        rows.append(
            {
                "subject_code": code,
                "subject_name": sub["subject_name"].iloc[0],
                "candidates": sub["student_id"].nunique(),
                "attempts": len(sub),
                "pass_rate": pass_rate(sub),
                "first_attempt_pass_rate": far,
                "absence_rate": absence_rate(sub),
                "mean_mark": stats["mean"],
                "median_mark": stats["median"],
                "repeat_rate": rep,
                "never_passed": len(never_passed(sub)),
                "mean_attempts_to_pass": float(atp.mean()) if len(atp) else float("nan"),
                "difficulty_index": difficulty_index(1 - far, rep, stats["mean"]),
            }
        )
    cols = [
        "subject_code",
        "subject_name",
        "candidates",
        "attempts",
        "pass_rate",
        "first_attempt_pass_rate",
        "absence_rate",
        "mean_mark",
        "median_mark",
        "repeat_rate",
        "never_passed",
        "mean_attempts_to_pass",
        "difficulty_index",
    ]
    out = pd.DataFrame(rows, columns=cols)
    return out.sort_values("difficulty_index", ascending=False, ignore_index=True)


def subject_funnel(df: pd.DataFrame, subject_code: str) -> dict[str, int]:
    """Attempted -> passed first time -> passed second time -> passed later / outstanding."""
    pairs = pair_table(df[df["subject_code"] == subject_code])
    attempt = pairs["pass_attempt"]
    return {
        "attempted": len(pairs),
        "passed_first_time": int((attempt == 1).sum()),
        "passed_second_time": int((attempt == 2).sum()),
        "passed_later": int((attempt >= 3).sum()),
        "outstanding": int(attempt.isna().sum()),
    }


def session_trend(df: pd.DataFrame, by_subject: bool = False) -> pd.DataFrame:
    """Pass rate and mean mark per session (and per subject), ordered by ``session_date``."""
    keys = ["exam_session", "session_date"] + (["subject_code"] if by_subject else [])
    work = df.assign(
        _pass=(df["result"] == "Pass").astype(int), _fail=(df["result"] == "Fail").astype(int)
    )
    out = work.groupby(keys).agg(
        candidates=("student_id", "nunique"),
        passes=("_pass", "sum"),
        fails=("_fail", "sum"),
        mean_mark=("marks", "mean"),
    )
    out["pass_rate"] = out["passes"] / (out["passes"] + out["fails"]).replace(0, np.nan)
    sort = ["session_date"] + (["subject_code"] if by_subject else [])
    return out.reset_index().sort_values(sort, ignore_index=True)


def session_kpis(df: pd.DataFrame) -> pd.DataFrame:
    """Per session: students, pass rate, first-attempt pass rate and absence rate."""
    rows = []
    for (session, date), sub in df.groupby(["exam_session", "session_date"]):
        rows.append(
            {
                "exam_session": session,
                "session_date": date,
                "students": sub["student_id"].nunique(),
                "pass_rate": pass_rate(sub),
                "first_attempt_pass_rate": first_attempt_pass_rate(sub),
                "absence_rate": absence_rate(sub),
            }
        )
    return pd.DataFrame(rows).sort_values("session_date", ignore_index=True)


def cohort_progress(df: pd.DataFrame) -> pd.DataFrame:
    """Per intake: % of students who have passed every subject attempted so far."""
    pairs = pair_table(df)
    pairs["passed"] = pairs["pass_attempt"].notna()
    per_student = pairs.groupby("student_id")["passed"].all().rename("passed_all").reset_index()
    intakes = df.drop_duplicates("student_id")[["student_id", "intake"]]
    merged = per_student.merge(intakes, on="student_id")
    out = merged.groupby("intake").agg(
        students=("student_id", "size"), pct_passed_all=("passed_all", "mean")
    )
    out["pct_passed_all"] *= 100
    return out.reset_index()
