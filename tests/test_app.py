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


DATA_PAGES = [p for p in PAGES if "Certificates" not in p.name]  # certificates work without data


@pytest.mark.parametrize("page", DATA_PAGES, ids=lambda p: p.stem[:8])
def test_page_shows_prompt_without_data(page):
    at = run_page(page)
    assert not at.exception
    assert any("Load sample data" in b.label for b in at.button)


def test_certificates_single_person_produces_a_pdf():
    at = run_page(next(p for p in PAGES if "Certificates" in p.name))
    assert not at.exception
    at.text_input(key="cert_name").input("A.K Imesh Samintha").run()
    assert not at.exception
    labels = [b.label for b in at.get("download_button")]
    assert any("1 certificate" in str(label) for label in labels) or at.get("download_button")


def test_certificates_from_results_lists_qualifying_students(loaded):
    at = run_page(next(p for p in PAGES if "Certificates" in p.name), loaded)
    at.radio(key="cert_mode").set_value("From exam results").run()
    assert not at.exception
    assert any("students selected" in c.value for c in at.caption)


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.stem[:8])
def test_page_runs_with_data(page, loaded):
    at = run_page(page, loaded)
    assert not at.exception


def test_filter_changes_overview_numbers(loaded):
    overview = next(p for p in PAGES if "Overview" in p.name)
    at = run_page(overview, loaded)

    def canvas_html(app) -> str:
        return " ".join(e.proto.srcdoc for e in app.get("iframe"))

    before = canvas_html(at)
    assert "__EXAMLENS__" in before
    programme = next(m for m in at.multiselect if m.label == "Programme")
    programme.select(programme.options[0])
    assert before != canvas_html(at.run())


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


def test_certificates_printer_preview_toggle_does_not_crash():
    """Turning on the printer preview must render (it never sends anything to a printer)."""
    at = run_page(next(p for p in PAGES if "Certificates" in p.name))
    at.text_input(key="cert_name").input("Ann Lee").run()
    toggles = [t for t in at.toggle if t.key == "cert_printer_preview"]
    if not toggles:
        pytest.skip("no printer installed / not Windows")
    toggles[0].set_value(True).run(timeout=120)
    assert not at.exception
