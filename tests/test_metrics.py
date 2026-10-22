"""Tests for examlens.metrics. Expected values are worked out by hand in the comments."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from examlens import metrics
from examlens.ingestion import load_paths, sample_paths
from helpers import make_df

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "data" / "sample"


@pytest.fixture
def tx1():
    # S1: 40 Fail then 60 Pass | S2: 70 Pass | S3: 30 Fail | S4: absent
    return make_df(
        [
            ("S1", "TX1", "2024-Jun", 1, 40),
            ("S1", "TX1", "2024-Dec", 2, 60),
            ("S2", "TX1", "2024-Jun", 1, 70),
            ("S3", "TX1", "2024-Jun", 1, 30),
            ("S4", "TX1", "2024-Jun", 1, "AB"),
        ]
    )


def test_pass_rate_excludes_absentees(tx1):
    assert metrics.pass_rate(tx1) == pytest.approx(0.5)  # 2 passes / 4 graded


def test_first_attempt_pass_rate(tx1):
    assert metrics.first_attempt_pass_rate(tx1) == pytest.approx(1 / 3)  # S2 of S1, S2, S3


def test_absence_rate(tx1):
    assert metrics.absence_rate(tx1) == pytest.approx(0.2)  # 1 of 5 attempts


def test_mark_stats(tx1):
    stats = metrics.mark_stats(tx1)
    assert stats == {"mean": 50.0, "median": 50.0}  # (40+60+70+30)/4


def test_repeat_rate_and_attempts_to_pass(tx1):
    assert metrics.repeat_rate(tx1) == pytest.approx(0.25)  # only S1 needed 2 attempts
    dist = metrics.attempts_to_pass_distribution(tx1)
    assert dist.to_dict() == {1: 1, 2: 1}
    assert metrics.attempts_to_pass(tx1)["pass_attempt"].mean() == pytest.approx(1.5)


def test_never_passed_includes_absent_only_students(tx1):
    assert set(metrics.never_passed(tx1)["student_id"]) == {"S3", "S4"}


def test_difficulty_index_formula():
    # 0.5 * 2/3 + 0.3 * 0.25 + 0.2 * (1 - 0.5) = 0.50833 -> 50.83
    assert metrics.difficulty_index(2 / 3, 0.25, 50) == pytest.approx(50.8333, abs=1e-3)


def test_subject_summary_ranks_hardest_first(tx1):
    easy = make_df([(f"E{i}", "EZ1", "2024-Jun", 1, 90) for i in range(4)])
    combined = pd.concat([tx1, easy], ignore_index=True)
    summary = metrics.subject_summary(combined)
    assert summary["subject_code"].tolist() == ["TX1", "EZ1"]
    row = summary.iloc[0]
    assert row["difficulty_index"] == pytest.approx(50.8333, abs=1e-3)
    assert row["never_passed"] == 2
    assert row["candidates"] == 4


def test_subject_funnel(tx1):
    assert metrics.subject_funnel(tx1, "TX1") == {
        "attempted": 4,
        "passed_first_time": 1,
        "passed_second_time": 1,
        "passed_later": 0,
        "outstanding": 2,
    }


def test_session_trend_ordered_by_date_not_label():
    df = make_df(
        [
            ("S1", "TX1", "2024-Dec", 1, 80),
            ("S2", "TX1", "2024-Dec", 1, 40),
            ("S1", "TX2", "2024-Jun", 1, 60),
        ]
    )
    trend = metrics.session_trend(df)
    assert trend["exam_session"].tolist() == ["2024-Jun", "2024-Dec"]  # Dec sorts before Jun
    assert trend["pass_rate"].tolist() == [1.0, 0.5]
    assert trend["mean_mark"].tolist() == [60.0, 60.0]


def test_cohort_progress_percentage(tx1):
    progress = metrics.cohort_progress(tx1)
    # S1 and S2 passed everything attempted; S3 and S4 did not -> 50%
    assert progress.loc[0, "pct_passed_all"] == pytest.approx(50.0)
    assert progress.loc[0, "students"] == 4


def test_empty_frame_returns_nan_not_error():
    empty = make_df([("S1", "TX1", "2024-Jun", 1, "AB")])
    assert metrics.pass_rate(empty) != metrics.pass_rate(empty)  # NaN
    assert metrics.absence_rate(empty) == 1.0


def test_hard_subjects_top_the_sample_difficulty_ranking():
    if not SAMPLE_DIR.exists():
        pytest.skip("sample data not generated")
    df, _ = load_paths(sample_paths(SAMPLE_DIR))
    top3 = set(metrics.subject_summary(df)["subject_code"].head(3))
    assert top3 == {"TX204", "AC202", "BM202"}
