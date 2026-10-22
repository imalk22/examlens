"""Shared helpers for building small hand-made result DataFrames."""

from __future__ import annotations

import numpy as np
import pandas as pd

from examlens.ingestion import apply_results, parse_session
from examlens.schema import COLUMNS


def make_df(rows: list[tuple]) -> pd.DataFrame:
    """Build a canonical DataFrame from (student_id, subject, session, attempt, marks) tuples.

    ``marks`` may be a number, ``None`` (sat, no mark) or the strings ``"AB"`` / ``"MC"``.
    """
    records = []
    for sid, code, session, attempt, marks in rows:
        status = {"AB": "Absent", "MC": "Medical"}.get(marks, "Sat")
        label, date = parse_session(session)
        records.append(
            {
                "student_id": sid,
                "student_name": f"Name {sid}",
                "programme": "Prog",
                "intake": "2024-Jan",
                "level": "Level 1",
                "subject_code": code,
                "subject_name": f"Subject {code}",
                "exam_session": label,
                "session_date": date,
                "attempt_no": attempt,
                "marks": np.nan if isinstance(marks, str) or marks is None else float(marks),
                "status": status,
                "source_file": "test",
            }
        )
    df = pd.DataFrame(records)
    df["session_date"] = pd.to_datetime(df["session_date"])
    df = apply_results(df)
    return df[COLUMNS]
