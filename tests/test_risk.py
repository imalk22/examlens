"""Tests for examlens.risk. Scores are worked out by hand from the default weights."""

from __future__ import annotations

from examlens import risk
from helpers import make_df


def one(df, sid):
    table = risk.compute_risk(df)
    return table[table["student_id"] == sid].iloc[0]


def test_single_attempt_student_is_low_with_no_reasons():
    row = one(make_df([("S1", "TX1", "2024-Jun", 1, 70)]), "S1")
    assert row["risk_score"] == 0
    assert row["risk_level"] == "Low"
    assert row["reasons"] == ""


def test_absent_in_every_attempt():
    df = make_df([("S1", "TX1", "2024-Jun", 1, "AB"), ("S1", "TX1", "2024-Dec", 2, "AB")])
    row = one(df, "S1")
    # 1 outstanding subject (10) + 2 absences (16) = 26 -> Medium; no marks so no trend flags
    assert row["risk_score"] == 26
    assert row["risk_level"] == "Medium"
    assert row["outstanding_subjects"] == 1
    assert row["latest_avg"] != row["latest_avg"]  # NaN


def test_failed_twice_then_passed_counts_repeat_but_not_outstanding():
    df = make_df(
        [
            ("S1", "TX1", "2024-Jun", 1, 40),
            ("S1", "TX1", "2024-Dec", 2, 45),
            ("S1", "TX1", "2025-Jun", 3, 60),
        ]
    )
    row = one(df, "S1")
    assert row["outstanding_subjects"] == 0
    assert row["risk_score"] == 30  # repeat-fail only; average rose 45 -> 60
    assert row["reasons"] == "Failed TX1 twice"
    assert row["risk_level"] == "Medium"


def test_declining_trend_flag_and_wording():
    df = make_df(
        [
            ("S1", "TX1", "2024-Jun", 1, 80),
            ("S1", "TX2", "2024-Jun", 1, 70),  # avg 75
            ("S1", "TX3", "2024-Dec", 1, 60),
            ("S1", "TX4", "2024-Dec", 1, 56),  # avg 58 -> dropped 17
        ]
    )
    row = one(df, "S1")
    assert row["risk_score"] == 15
    assert row["reasons"] == "Average dropped 17 marks since last session"


def test_outstanding_cap_and_low_average():
    df = make_df([("S1", f"TX{i}", "2024-Jun", 1, 30) for i in range(5)])
    row = one(df, "S1")
    # 5 outstanding capped at 3 -> 30; latest avg 30 < 45 -> 15
    assert row["risk_score"] == 45
    assert row["outstanding_subjects"] == 5
    assert "5 subjects outstanding" in row["reasons"]


def test_custom_weights_change_score_and_level_boundary():
    df = make_df([("S1", f"TX{i}", "2024-Jun", 1, 30) for i in range(5)])
    weights = {
        "repeat_fail_same_subject": 30,
        "outstanding_fails": 20,
        "absences": 8,
        "declining_trend": 15,
        "low_recent_average": 15,
    }
    table = risk.compute_risk(df, weights=weights)
    assert table.loc[0, "risk_score"] == 75  # 3 * 20 + 15
    assert table.loc[0, "risk_level"] == "High"


def test_level_thresholds_are_inclusive():
    assert risk.risk_level(50) == "High"
    assert risk.risk_level(49) == "Medium"
    assert risk.risk_level(25) == "Medium"
    assert risk.risk_level(24) == "Low"


def test_table_sorted_highest_risk_first():
    df = make_df(
        [("S1", "TX1", "2024-Jun", 1, 90)] + [("S2", f"TX{i}", "2024-Jun", 1, 20) for i in range(4)]
    )
    table = risk.compute_risk(df)
    assert table["student_id"].tolist() == ["S2", "S1"]
