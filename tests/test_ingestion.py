"""Tests for examlens.ingestion."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from examlens.ingestion import (
    IngestionError,
    MissingColumnsError,
    apply_results,
    guess_session_from_filename,
    ingest,
    load_paths,
    map_columns,
    parse_session,
    sample_paths,
)
from examlens.schema import COLUMNS, validate

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "data" / "sample"


def long_frame(rows: list[tuple]) -> pd.DataFrame:
    """Rows of (id, name, code, session, marks)."""
    return pd.DataFrame(rows, columns=["Student ID", "Name", "Subject Code", "Session", "Marks"])


# --- column mapping -------------------------------------------------------------------------


def test_map_columns_handles_variants_case_and_punctuation():
    raw = pd.DataFrame(columns=["reg.no", "FULL_NAME", "Module Code", "Sitting", "Score"])
    mapped, missing = map_columns(raw)
    assert missing == []
    assert {"student_id", "student_name", "subject_code", "exam_session", "marks"} <= set(
        mapped.columns
    )


def test_map_columns_reports_missing_required():
    raw = pd.DataFrame(columns=["Student ID", "Name", "Marks"])
    _, missing = map_columns(raw)
    assert missing == ["subject_code", "exam_session"]


def test_manual_override_resolves_missing_column():
    raw = pd.DataFrame(
        [["s1", "A B", "TX101", "2024-Jun", "60"]],
        columns=["Student ID", "Name", "Subject Code", "Period X", "Marks"],
    )
    frames = {"f.csv": raw}
    with pytest.raises(MissingColumnsError) as exc:
        ingest(frames)
    assert exc.value.missing == ["exam_session"]
    df, _ = ingest(frames, overrides={"f.csv": {"exam_session": "Period X"}})
    assert df.loc[0, "exam_session"] == "2024-Jun"


# --- sessions --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "label"),
    [
        ("2024-Jun", "2024-Jun"),
        ("June 2024", "2024-Jun"),
        ("2024 jun", "2024-Jun"),
        ("2024-06", "2024-Jun"),
        ("Sept 2025", "2025-Sep"),
    ],
)
def test_parse_session_normalises(text, label):
    parsed, date = parse_session(text)
    assert parsed == label
    assert date.year == int(label[:4])


def test_parse_session_unparseable_is_kept():
    label, date = parse_session("Semester One")
    assert label == "Semester One"
    assert pd.isna(date)


def test_guess_session_from_filename_ignores_marksheet_word():
    assert guess_session_from_filename("level1_marksheet_2025_dec.xlsx") == "2025-Dec"
    assert guess_session_from_filename("marksheet.xlsx") is None


# --- cleaning rules --------------------------------------------------------------------------


def test_text_marks_become_absent_and_medical():
    raw = long_frame(
        [
            (" st1 ", "Ann Lee", "tx101", "2024-Jun", "AB"),
            ("ST2", "Bob Ray", "TX101", "2024-Jun", "mc"),
            ("ST3", "Cy Poe", "TX101", "2024-Jun", "-"),
            ("ST4", "Di Fox", "TX101", "2024-Jun", "72"),
        ]
    )
    df, report = ingest({"f.csv": raw})
    by_id = df.set_index("student_id")
    assert by_id.loc["ST1", "status"] == "Absent"
    assert by_id.loc["ST2", "status"] == "Medical"
    assert by_id.loc["ST3", "status"] == "Absent"
    assert by_id.loc["ST4", "result"] == "Pass"
    assert by_id.loc["ST1", "result"] == "Absent"
    assert report.absent_count == 2
    assert report.medical_count == 1
    assert df["subject_code"].eq("TX101").all()


def test_out_of_range_marks_flagged_and_excluded():
    raw = long_frame(
        [
            ("ST1", "Ann Lee", "TX101", "2024-Jun", "150"),
            ("ST2", "Bob Ray", "TX101", "2024-Jun", "-5"),
            ("ST3", "Cy Poe", "TX101", "2024-Jun", "60"),
        ]
    )
    df, report = ingest({"f.csv": raw})
    assert report.invalid_marks == 2
    assert df["marks"].notna().sum() == 1
    assert df.loc[df["student_id"] == "ST1", "result"].isna().all()


def test_duplicates_keep_highest_mark_and_are_logged():
    raw = long_frame(
        [
            ("ST1", "Ann Lee", "TX101", "2024-Jun", "40"),
            ("ST1", "Ann Lee", "TX101", "2024-Jun", "58"),
            ("ST1", "Ann Lee", "TX101", "2024-Jun", "AB"),
        ]
    )
    df, report = ingest({"f.csv": raw})
    assert len(df) == 1
    assert df.loc[0, "marks"] == 58
    assert report.duplicates_removed == 2


def test_name_conflict_keeps_most_frequent_name():
    raw = long_frame(
        [
            ("ST1", "Ann Lee", "TX101", "2024-Jun", "60"),
            ("ST1", "Ann Lee", "TX102", "2024-Jun", "61"),
            ("ST1", "A. Lee", "TX103", "2024-Jun", "62"),
        ]
    )
    df, report = ingest({"f.csv": raw})
    assert df["student_name"].eq("Ann Lee").all()
    assert len(report.name_conflicts) == 1
    assert report.name_conflicts[0]["kept"] == "Ann Lee"


def test_attempt_no_derived_chronologically_per_student_subject():
    raw = long_frame(
        [
            ("ST1", "Ann Lee", "TX101", "2024-Dec", "55"),
            ("ST1", "Ann Lee", "TX101", "2024-Jun", "40"),
            ("ST1", "Ann Lee", "TX102", "2024-Dec", "70"),
        ]
    )
    df, _ = ingest({"f.csv": raw})
    tx101 = df[df["subject_code"] == "TX101"].sort_values("session_date")
    assert tx101["attempt_no"].tolist() == [1, 2]
    assert df.loc[df["subject_code"] == "TX102", "attempt_no"].iloc[0] == 1


def test_grade_and_result_recomputed_from_marks():
    raw = long_frame(
        [
            ("ST1", "A", "TX101", "2024-Jun", "49"),
            ("ST2", "B", "TX101", "2024-Jun", "50"),
            ("ST3", "C", "TX101", "2024-Jun", "75"),
        ]
    )
    df, _ = ingest({"f.csv": raw})
    by_id = df.set_index("student_id")
    assert by_id.loc["ST1", ["grade", "result"]].tolist() == ["F", "Fail"]
    assert by_id.loc["ST2", ["grade", "result"]].tolist() == ["D", "Pass"]
    assert by_id.loc["ST3", ["grade", "result"]].tolist() == ["A", "Pass"]


def test_apply_results_respects_custom_pass_mark():
    df, _ = ingest({"f.csv": long_frame([("ST1", "A", "TX101", "2024-Jun", "55")])})
    assert apply_results(df, pass_mark=60).loc[0, "result"] == "Fail"


def test_rows_missing_required_values_are_dropped():
    raw = long_frame(
        [
            ("ST1", "Ann Lee", "TX101", "2024-Jun", "60"),
            (None, "Ghost", "TX101", "2024-Jun", "60"),
        ]
    )
    df, report = ingest({"f.csv": raw})
    assert len(df) == 1
    assert report.rows_dropped_missing_required == 1


# --- wide format -----------------------------------------------------------------------------


def test_wide_format_is_melted_with_session_from_filename():
    wide = pd.DataFrame(
        {
            "Student ID": ["ST1", "ST2"],
            "Name": ["Ann Lee", "Bob Ray"],
            "TX101": ["60", "AB"],
            "TX102": [None, "45"],
        }
    )
    df, report = ingest({"level1_marksheet_2025_dec.xlsx": wide})
    assert len(df) == 3  # blank cell produces no row
    assert df["exam_session"].eq("2025-Dec").all()
    assert report.wide_files == ["level1_marksheet_2025_dec.xlsx"]
    assert df.set_index(["student_id", "subject_code"]).loc[("ST2", "TX101"), "status"] == "Absent"


def test_wide_format_without_session_raises():
    wide = pd.DataFrame({"Student ID": ["ST1"], "Name": ["A"], "TX101": ["60"], "TX102": ["61"]})
    with pytest.raises(IngestionError):
        ingest({"marksheet.xlsx": wide})
    df, _ = ingest({"marksheet.xlsx": wide}, wide_sessions={"marksheet.xlsx": "2025-Dec"})
    assert len(df) == 2


def test_unsupported_file_type_gives_friendly_error(tmp_path):
    bad = tmp_path / "notes.txt"
    bad.write_text("hello")
    with pytest.raises(IngestionError, match="unsupported"):
        load_paths([bad])


# --- sample data acceptance ------------------------------------------------------------------


@pytest.fixture(scope="module")
def sample_result():
    if not SAMPLE_DIR.exists():
        pytest.skip("sample data not generated")
    return load_paths(sample_paths(SAMPLE_DIR))


def test_sample_files_load_into_valid_schema(sample_result):
    df, _ = sample_result
    assert list(df.columns) == COLUMNS
    assert validate(df) == []
    assert df["exam_session"].nunique() == 6
    assert df["student_id"].nunique() == 600
    assert df["source_file"].nunique() == 7


def test_health_report_matches_injected_issues(sample_result):
    df, report = sample_result
    manifest = json.loads((SAMPLE_DIR / "MANIFEST.json").read_text())
    jun25 = manifest["results_2025_jun.csv"]
    assert report.duplicates_removed == jun25["duplicates"]
    assert report.invalid_marks == manifest["results_2024_dec.xlsx"]["invalid_marks"]
    assert len(report.name_conflicts) == jun25["name_conflicts"]
    expected_absent = jun25["ab_entries"] + manifest["level1_marksheet_2025_dec.xlsx"]["ab_entries"]
    assert (df[df["source_file"] == "results_2025_jun.csv"]["status"] == "Absent").sum() == (
        jun25["ab_entries"]
    )
    assert report.absent_count >= expected_absent
    assert report.wide_files == ["level1_marksheet_2025_dec.xlsx"]
    assert report.rows_final == report.rows_loaded - report.duplicates_removed


def test_sample_has_no_duplicate_keys_and_attempts_start_at_one(sample_result):
    df, _ = sample_result
    assert not df.duplicated(["student_id", "subject_code", "exam_session"]).any()
    assert df.groupby(["student_id", "subject_code"])["attempt_no"].min().eq(1).all()
