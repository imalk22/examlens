"""Canonical column names and validation for the cleaned results dataset."""

from __future__ import annotations

import pandas as pd

COLUMNS: list[str] = [
    "student_id",
    "student_name",
    "programme",
    "intake",
    "level",
    "subject_code",
    "subject_name",
    "exam_session",
    "session_date",
    "attempt_no",
    "marks",
    "status",
    "grade",
    "result",
    "source_file",
]

REQUIRED_COLUMNS: list[str] = [
    "student_id",
    "student_name",
    "subject_code",
    "exam_session",
]

OPTIONAL_COLUMNS: list[str] = [c for c in COLUMNS if c not in REQUIRED_COLUMNS]

STATUS_VALUES: list[str] = ["Sat", "Absent", "Medical", "Withheld"]
RESULT_VALUES: list[str] = ["Pass", "Fail", "Absent"]

# Accepted header variants, matched after lower-casing and removing spaces, dots, underscores.
COLUMN_ALIASES: dict[str, list[str]] = {
    "student_id": ["studentid", "regno", "registrationnumber", "indexno", "studentno"],
    "student_name": ["name", "studentname", "fullname", "namewithinitials"],
    "subject_code": ["subjectcode", "modulecode", "coursecode", "papercode"],
    "subject_name": ["subject", "module", "modulename", "course", "paper"],
    "marks": ["marks", "mark", "score", "total", "finalmark", "totalmarks"],
    "exam_session": ["session", "examsession", "sitting", "examperiod", "semester"],
    "status": ["status", "attendance", "remarks"],
    "programme": ["programme", "program"],
    "intake": ["intake", "batch", "cohort"],
    "level": ["level"],
    "attempt_no": ["attemptno", "attempt"],
}


def normalise_header(name: object) -> str:
    """Lower-case a header and strip spaces, dots and underscores."""
    return "".join(ch for ch in str(name).lower() if ch not in " ._")


def validate(df: pd.DataFrame) -> list[str]:
    """Return a list of schema problems found in ``df`` (empty if valid)."""
    problems: list[str] = []
    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        problems.append(f"Missing columns: {', '.join(missing)}")
        return problems
    for col in REQUIRED_COLUMNS:
        if df[col].isna().any():
            problems.append(f"Null values in required column '{col}'")
    bad_marks = df["marks"].dropna()
    if ((bad_marks < 0) | (bad_marks > 100)).any():
        problems.append("Marks outside 0-100")
    if not df["status"].dropna().isin(STATUS_VALUES).all():
        problems.append("Unexpected status value")
    if not df["result"].dropna().isin(RESULT_VALUES).all():
        problems.append("Unexpected result value")
    return problems
