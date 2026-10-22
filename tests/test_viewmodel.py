"""Tests for examlens.viewmodel (JSON-ready dashboard data)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from examlens import metrics, risk, viewmodel
from examlens.ingestion import load_paths, sample_paths
from helpers import make_df

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "data" / "sample"


def dump(obj) -> str:
    return json.dumps(obj, allow_nan=False)  # raises on NaN or unsupported types


@pytest.fixture
def small():
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


def test_clean_converts_nan_and_numpy():
    import numpy as np

    out = viewmodel.clean({"a": np.float64("nan"), "b": np.int64(3), "c": [np.float32(1.5)]})
    assert out == {"a": None, "b": 3, "c": [1.5]}
    dump(out)


def test_profile_lists_outstanding_subjects(small):
    table = risk.compute_risk(small)
    prof = viewmodel.profile(
        small[small["student_id"] == "S3"], table.set_index("student_id").loc["S3"]
    )
    assert prof["remaining"][0]["code"] == "TX1"
    assert prof["passed"] == 0 and prof["subjects"] == 1
    assert prof["history"][0][4] == 30.0


def test_profile_of_student_who_passed_has_nothing_remaining(small):
    table = risk.compute_risk(small)
    prof = viewmodel.profile(
        small[small["student_id"] == "S1"], table.set_index("student_id").loc["S1"]
    )
    assert prof["remaining"] == [] and prof["passed"] == 1
    assert [h[3] for h in prof["history"]] == [1, 2]


def test_repeats_funnel_matches_hand_counts(small):
    summary = metrics.subject_summary(small)
    data = viewmodel.repeats(small, summary)
    assert data["funnel"]["TX1"] == {
        "attempted": 4,
        "first": 1,
        "second": 1,
        "later": 0,
        "outstanding": 2,
    }
    assert data["dist"]["TX1"] == {"1": 1, "2": 1}
    assert {r["id"] for r in data["never"]} == {"S3", "S4"}
    dump(data)


def test_subject_histogram_counts_every_mark(small):
    summary = metrics.subject_summary(small)
    data = viewmodel.subjects(small, summary, 50)
    assert sum(data["detail"]["TX1"]["hist"]) == small["marks"].notna().sum()
    dump(data)


def test_sample_view_models_are_json_safe():
    if not SAMPLE_DIR.exists():
        pytest.skip("sample data not generated")
    df, report = load_paths(sample_paths(SAMPLE_DIR))
    table = risk.compute_risk(df)
    summary = metrics.subject_summary(df)
    over = viewmodel.overview(df, table, summary, before_high=10)
    assert len(over["kpis"]) == 5
    assert over["risk"]["High"] + over["risk"]["Medium"] + over["risk"]["Low"] == len(table)
    dump(over)
    page = viewmodel.risk_page(df, table)
    assert len(page["rows"]) == len(page["profiles"]) == df["student_id"].nunique()
    dump(page)
    dump(viewmodel.health(report, df))
    dump(viewmodel.student_page(df, df["student_id"].iloc[0], table, 50))
