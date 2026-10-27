"""Tests for the short-course certificate: four front lines and the course-details back page."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from examlens import certificates as C
from test_certificates import FakeFont

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = C.load_template(ROOT / "assets" / "short_course_template.json")
RECORD = C.Record(
    "A.K Imesh Samintha",
    "Certificate Course in UAE Taxation",
    date(2026, 5, 20),
    "Corporate Taxation",
)
GROUPS = [("Income Tax", ["Introduction", "Source of income"]), ("Value Added Tax", ["Tax"])]


def test_template_has_four_front_lines_and_a_back_page():
    assert list(TEMPLATE.fields) == ["name", "course", "date", "subject"]
    assert TEMPLATE.fields["date"].ordinal_gap
    assert TEMPLATE.details is not None
    assert TEMPLATE.details.title == "Course subjects"
    again = C.Template.from_dict(TEMPLATE.to_dict())  # the back page survives a round trip
    assert again.details == TEMPLATE.details


def test_front_prints_the_subject_line_and_a_spaced_ordinal():
    lay = C.layout_record(TEMPLATE, RECORD, FakeFont())
    texts = [(r.field, r.text, r.superscript) for r in lay.runs]
    assert ("subject", "CORPORATE TAXATION", False) in texts
    assert ("date", " TH", True) in texts  # "20 TH MAY 2026", as in the Photoshop file


def test_blank_subject_is_left_out():
    rec = C.Record("A", "B", date(2026, 1, 1))
    assert "subject" not in {r.field for r in C.layout_record(TEMPLATE, rec, FakeFont()).runs}


def test_parse_details_reads_headings_and_bullets():
    text = "Income Tax\n- Introduction\n•  Source   of income\n\nValue Added Tax\n* Tax\n"
    assert C.parse_details(text) == GROUPS
    assert C.parse_details(C.details_text(GROUPS)) == GROUPS
    assert C.parse_details("- orphan topic") == [("", ["orphan topic"])]


def test_back_page_layout_follows_the_template():
    spec = TEMPLATE.details
    lay = C.layout_details(TEMPLATE, GROUPS, FakeFont())
    by = [(r.field, r.text) for r in lay.runs]
    assert by[0] == ("title", "COURSE SUBJECTS")  # title in capitals, the rest as typed
    assert by[1] == ("heading", "Income Tax")
    assert by[2:4] == [("bullet", "•"), ("topic", "Introduction")]
    heading, first, second = lay.runs[1], lay.runs[3], lay.runs[5]
    assert heading.baseline_mm == pytest.approx(spec.first_heading_mm)
    assert first.baseline_mm - heading.baseline_mm == pytest.approx(spec.heading_gap_mm)
    assert second.baseline_mm - first.baseline_mm == pytest.approx(spec.line_mm)
    next_heading = next(r for r in lay.runs if r.text == "Value Added Tax")
    assert next_heading.baseline_mm - second.baseline_mm == pytest.approx(spec.group_gap_mm)
    # only the title is underlined in this template; topics can be switched on
    assert {r.field for r in lay.runs if r.underline_mm} == {"title"}
    assert lay.overflow == 0


def test_topic_underline_is_a_template_option():
    data = TEMPLATE.to_dict()
    data["details"]["underline_topics"] = True
    lay = C.layout_details(C.Template.from_dict(data), GROUPS, FakeFont())
    assert {r.field for r in lay.runs if r.underline_mm} == {"title", "topic"}


def test_back_page_counts_lines_that_do_not_fit():
    many = [("Subject", [f"Topic {n}" for n in range(80)])]
    lay = C.layout_details(TEMPLATE, many, FakeFont())
    assert lay.overflow > 0
    assert max(r.baseline_mm for r in lay.runs) <= TEMPLATE.details.bottom_mm


def test_back_page_offset_and_title_override():
    lay = C.layout_details(TEMPLATE, GROUPS, FakeFont(), title="", offset_mm=(2.0, 3.0))
    plain = C.layout_details(TEMPLATE, GROUPS, FakeFont(), title="")
    assert lay.runs[0].field == "heading"
    assert lay.runs[0].x_mm - plain.runs[0].x_mm == pytest.approx(2.0)
    assert lay.runs[0].baseline_mm - plain.runs[0].baseline_mm == pytest.approx(3.0)


def test_underline_is_drawn_in_pdf_and_svg():
    lay = C.layout_details(TEMPLATE, GROUPS, FakeFont())
    pdf = C.build_pdf([lay], FakeFont(), (TEMPLATE.width_mm, TEMPLATE.height_mm))
    assert b" re f" in pdf  # filled underline rectangles
    svg = C.preview_svg(TEMPLATE, lay, "Fake")
    assert svg.count("<rect") > 3  # page + border rects + underlines


def test_templates_without_a_back_page_refuse_details():
    plain = C.load_template(ROOT / "assets" / "certificate_template.json")
    assert plain.details is None
    with pytest.raises(ValueError):
        C.layout_details(plain, GROUPS, FakeFont())


def test_line_spacing_changes_only_the_gap_between_topics():
    plain = C.layout_details(TEMPLATE, GROUPS, FakeFont())
    wide = C.layout_details(TEMPLATE, GROUPS, FakeFont(), line_spacing=1.5)
    topics = lambda lay: [r.baseline_mm for r in lay.runs if r.field == "topic"]  # noqa: E731
    gap = TEMPLATE.details.line_mm
    assert topics(wide)[1] - topics(wide)[0] == pytest.approx(gap * 1.5)
    assert topics(wide)[0] == pytest.approx(topics(plain)[0])  # heading to first topic unchanged
