"""Tests for the CIT result-sheet parser, using small synthetic sheets (no real student data)."""

from __future__ import annotations

from io import BytesIO

import pandas as pd
import pytest

from examlens import metrics
from examlens.cit import detect_intake, detect_level, parse_cit, session_from_text
from examlens.ingestion import ingest, read_raw


def sheet(rows: list[list]) -> pd.DataFrame:
    width = max(len(r) for r in rows)
    return pd.DataFrame([r + [None] * (width - len(r)) for r in rows])


def coded_sheet() -> pd.DataFrame:
    """Layout like the 2025/26 sheets: code row, name row, Marks/Status sub-header."""
    return sheet(
        [
            [None, None, "CHARTERED INSTITUTE OF TAXATION"],
            [None, None, "Analyst Level 1 (2025) B1 - English"],
            [
                "Ref No",
                "Name in Full",
                "Student No",
                "Index Number",
                "TX 211",
                None,
                "TX 212",
                None,
                None,
                None,
            ],
            [
                None,
                None,
                None,
                None,
                "Direct Taxation",
                None,
                "Indirect Taxation",
                None,
                None,
                None,
            ],
            [
                None,
                None,
                None,
                None,
                "Marks",
                "Status",
                "Part 01",
                "Part 02",
                "Total Marks",
                "Status",
            ],
            [
                "1",
                "Ann Lee",
                "2025/03/0001",
                "2026/AN1/E1/001",
                "61",
                "Pass",
                "30",
                "20",
                "50",
                "Pass",
            ],
            [
                "2",
                "Bob Ray",
                "2025/03/0002",
                "2026/AN1/E1/002",
                "45",
                "Fail",
                "10",
                "20",
                "30",
                "Fail",
            ],
            [
                "3",
                "Cy Poe",
                "2025/03/0003",
                "2026/AN1/E1/003",
                "AB",
                "AB",
                "0",
                "0",
                "Previously Completed",
                "Previously Completed",
            ],
            [
                "4",
                "Di Fox",
                "2025/03/0004",
                "2026/AN1/E1/004",
                "Previously Completed",
                "Previously Completed",
                "55",
                "10",
                "65",
                "Pass",
            ],
            [None, "President", None, None, None],
        ]
    )


def named_sheet() -> pd.DataFrame:
    """Older layout: subject names only, with 'XX Result' status columns and a title row."""
    return sheet(
        [
            [None, None, None, "Analyst Level 1 (2024) B1-January 2025"],
            [
                "No.",
                "Student Reg No",
                "Index No",
                "Student Name",
                "Direct Taxation",
                "DT Result",
                "Indirect Taxation",
                "IT Result",
                "Final Marks",
                "Average Marks",
            ],
            [
                "1",
                "2025/03/0001",
                "25/A1/01/0378",
                "Ann Lee",
                "40",
                "Fail",
                "70",
                "Pass",
                "55",
                "55",
            ],
            ["2", "2025/03/0009", "25/A1/01/0379", "Eve Kim", "AB", "AB", "AB", "AB", "-", "-"],
        ]
    )


def index_only_sheet() -> pd.DataFrame:
    """Official sheet that lists index numbers but no names or student numbers."""
    return sheet(
        [
            ["ANALYST LEVEL 1 ( 2025 ) B 2 EXAMINATION"],
            ["Ref No", "Se No.", "Index Number", "TX 211", None, "TX 212", None],
            [None, None, None, "Marks", "Status", "Marks", "Status"],
            ["1", "1", "2025/AN1/E2/0001", "71", "Pass", "52", "Pass"],
            ["2", "2", "2025/AN1/E2/0002", "AB", "AB", "AB", "AB"],
        ]
    )


def test_detect_helpers():
    assert detect_level("ANALYST LEVEL 1 ( 2025 ) B 2") == "Analyst 1"
    assert detect_level("6. Results of Analyst Level 2 - Dec 2025") == "Analyst 2"
    assert detect_level("EXAMINATION RESULT SHEET FOR ADVISORY") == "Advisory"
    assert detect_intake("Application Level (2025) B1 - English") == "2025 B1"
    assert detect_intake("Analyst Level 1 (2025) Batch 3 Examination") == "2025 B3"
    # the exam month is the LAST month-year in a filename, not the batch year
    assert session_from_text("1. Application 2024  B1 - Jan 2025") == "2025-Jan"
    assert session_from_text("2. Results of Application Level - June 2026") == "2026-Jun"


def test_coded_layout_is_parsed_per_subject():
    table, info = parse_cit(coded_sheet(), "5. Results - March 2026.xlsx")
    assert info["level"] == "Analyst 1" and info["intake"] == "2025 B1"
    assert info["session"] == "2026-Mar"
    got = table.set_index(["Student ID", "Subject Code"])
    assert got.loc[("2025/03/0001", "TX211"), "Marks"] == "61"
    # multi-part subject: the Total Marks column wins over the parts
    assert got.loc[("2025/03/0001", "TX212"), "Marks"] == "50"
    assert got.loc[("2025/03/0003", "TX211"), "Status"] == "Absent"
    assert info["skipped"] == 2  # 'Previously Completed' cells are not attempts
    assert ("2025/03/0003", "TX212") not in got.index
    assert ("2025/03/0004", "TX211") not in got.index


def test_name_only_layout_maps_names_to_codes():
    table, info = parse_cit(named_sheet(), "Analyst 1 2024 B1 - Jan 2025.xlsx")
    assert set(table["Subject Code"]) == {"TX211", "TX212"}
    assert set(table["Subject Name"]) == {"Direct Taxation", "Indirect Taxation"}
    absent = table[table["Student ID"] == "2025/03/0009"]
    assert (absent["Status"] == "Absent").all()


def test_non_cit_sheet_returns_none():
    plain = sheet(
        [
            ["Student ID", "Name", "Subject Code", "Session", "Marks"],
            ["S1", "Ann", "TX1", "2024-Jun", "60"],
        ]
    )
    assert parse_cit(plain, "plain.xlsx") is None


def workbook(sheets: dict[str, pd.DataFrame]) -> BytesIO:
    buffer = BytesIO()
    with pd.ExcelWriter(buffer) as writer:
        for name, grid in sheets.items():
            grid.to_excel(writer, sheet_name=name, index=False, header=False)
    buffer.seek(0)
    return buffer


def test_same_student_across_files_becomes_one_profile_with_attempts():
    jan = read_raw(workbook({"Sheet1": named_sheet()}), "4. Analyst 1 2024 B1 - Jan 2025.xlsx")
    mar = read_raw(workbook({"Sheet1": coded_sheet()}), "4. Results of Analyst 1 - March 2026.xlsx")
    df, report = ingest(
        {
            "4. Analyst 1 2024 B1 - Jan 2025.xlsx": jan,
            "4. Results of Analyst 1 - March 2026.xlsx": mar,
        }
    )
    ann = df[df["student_id"] == "2025/03/0001"].sort_values("session_date")
    assert ann["student_name"].eq("Ann Lee").all()
    tx211 = ann[ann["subject_code"] == "TX211"]
    assert tx211["exam_session"].tolist() == ["2025-Jan", "2026-Mar"]
    assert tx211["attempt_no"].tolist() == [1, 2]  # failed in Jan, passed in March
    assert tx211["result"].tolist() == ["Fail", "Pass"]
    assert report.skipped_rows == 2 and len(report.notes) == 2
    assert metrics.repeat_rate(df) > 0


def test_index_only_sheet_uses_index_as_id_and_placeholder_name():
    table = read_raw(workbook({"Sheet": index_only_sheet()}), "3. Results - Dec 2025.xlsx")
    df, report = ingest({"3. Results - Dec 2025.xlsx": table})
    assert set(df["student_id"]) == {"2025/AN1/E2/0001", "2025/AN1/E2/0002"}
    assert (df["student_name"] == df["student_id"]).all()
    assert "identified by index number only" in report.notes[0]


def test_real_name_replaces_placeholder_when_another_file_has_it():
    named = pd.DataFrame(
        {
            "Student ID": ["S1", "S1"],
            "Student Name": [None, "Ann Lee"],
            "Subject Code": ["TX1", "TX2"],
            "Session": ["2024-Jun", "2024-Jun"],
            "Marks": ["60", "70"],
        }
    )
    df, report = ingest({"f.csv": named})
    assert df["student_name"].eq("Ann Lee").all()
    assert report.name_conflicts == []


@pytest.mark.parametrize("marks", ["50", "51"])
def test_pass_mark_of_fifty_is_inclusive(marks):
    grid = coded_sheet()
    grid.iloc[5, 4] = marks
    table, _ = parse_cit(grid, "x - Jan 2026.xlsx")
    df, _ = ingest({"x.xlsx": table})
    row = df[(df["student_id"] == "2025/03/0001") & (df["subject_code"] == "TX211")]
    assert row["result"].iloc[0] == "Pass"
