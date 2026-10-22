"""Smoke tests: every page runs headlessly against the sample data without exceptions."""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from examlens import export, metrics, risk
from examlens.ingestion import load_paths, sample_paths

ROOT = Path(__file__).resolve().parent.parent
PAGES = sorted((ROOT / "pages").glob("*.py"))


@pytest.fixture(scope="module")
def loaded():
    if not (ROOT / "data" / "sample").exists():
        pytest.skip("sample data not generated")
    return load_paths(sample_paths(ROOT / "data" / "sample"))


def run_page(path: Path, loaded=None) -> AppTest:
    at = AppTest.from_file(str(path), default_timeout=60)
    if loaded is not None:
        at.session_state["data"], at.session_state["report"] = loaded
    return at.run()


def test_home_runs_empty_and_loaded(loaded):
    assert not run_page(ROOT / "pages" / "2_Overview.py").exception
    assert not run_page(ROOT / "pages" / "2_Overview.py", loaded).exception


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.stem[:8])
def test_page_shows_prompt_without_data(page):
    at = run_page(page)
    assert not at.exception
    assert any("Load sample data" in b.label for b in at.button)


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.stem[:8])
def test_page_runs_with_data(page, loaded):
    at = run_page(page, loaded)
    assert not at.exception


def test_filter_changes_overview_numbers(loaded):
    overview = next(p for p in PAGES if "Overview" in p.name)
    at = run_page(overview, loaded)

    def kpi_cards(app) -> str:
        return " ".join(m.value for m in app.markdown if 'class="kpi"' in m.value)

    before = kpi_cards(at)
    assert before
    programme = next(m for m in at.multiselect if m.label == "Programme")
    programme.select(programme.options[0])
    assert before != kpi_cards(at.run())


def test_exports_are_valid_excel(loaded):
    from io import BytesIO

    import pandas as pd

    df, _ = loaded
    table = risk.compute_risk(df)
    back = pd.read_excel(BytesIO(export.at_risk_workbook(table)))
    assert len(back) == len(table)
    assert "Reasons" in back.columns
    sid = df["student_id"].iloc[0]
    hist = df[df["student_id"] == sid]
    data = export.transcript_workbook({"Student ID": sid}, hist, metrics.never_passed(hist))
    assert set(pd.ExcelFile(BytesIO(data)).sheet_names) == {
        "Summary",
        "Exam history",
        "Outstanding",
    }
