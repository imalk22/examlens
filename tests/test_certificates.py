"""Tests for certificate layout and the PDF writer."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from examlens import certificates as C
from helpers import make_df

ROOT = Path(__file__).resolve().parent.parent


class FakeFont(C.TrueTypeFont):
    """Every character 500/1000 em wide, so expected positions can be worked out by hand."""

    def __init__(self) -> None:  # no font file needed
        self.data = b"\x00\x01\x00\x00fake-font-bytes"
        self.source = "fake"
        self.units_per_em = 1000
        self.bbox = (-100, -200, 1000, 900)
        self.ascent, self.descent, self.cap_height = 800, -200, 700
        self.embeddable = True
        self.postscript_name = self.family_name = "Fake"
        self.widths = [500.0] * 224


def template(**field_overrides) -> C.Template:
    spec = {
        "x_mm": 100.0,
        "baseline_mm": 100.0,
        "size_pt": 10.0,
        "tracking": 0,
        "align": "center",
        "caps": True,
    }
    spec.update(field_overrides)
    return C.Template.from_dict(
        {"name": "T", "page": {"width_mm": 200, "height_mm": 250}, "fields": {"name": spec}}
    )


@pytest.mark.parametrize(
    ("day", "suffix"),
    [
        (1, "ST"),
        (2, "ND"),
        (3, "RD"),
        (4, "TH"),
        (11, "TH"),
        (12, "TH"),
        (13, "TH"),
        (21, "ST"),
        (22, "ND"),
        (23, "RD"),
        (31, "ST"),
    ],
)
def test_ordinal_suffix(day, suffix):
    assert C.ordinal_suffix(day) == suffix


def test_date_runs_have_superscript_ordinal():
    assert C.date_runs(date(2025, 4, 20)) == [("20", False), ("TH", True), (" APRIL 2025", False)]


def test_centred_text_is_centred_on_the_anchor():
    # "ABCD" = 4 x 500/1000 em x 10 pt = 20 pt wide = 7.056 mm, centred on x=100 mm
    layout = C.layout_record(template(), C.Record("abcd", "", date(2025, 1, 1)), FakeFont())
    run = layout.runs[0]
    assert run.text == "ABCD"  # all caps
    assert run.x_mm == pytest.approx(100 - 20 / C.PT_PER_MM / 2, abs=1e-6)
    assert run.baseline_mm == 100


def test_tracking_widens_but_not_after_the_last_letter():
    # tracking 100 = 0.1 em = 1 pt after each of the first three letters: 23 pt wide
    layout = C.layout_record(
        template(tracking=100), C.Record("abcd", "", date(2025, 1, 1)), FakeFont()
    )
    assert layout.runs[0].x_mm == pytest.approx(100 - 23 / C.PT_PER_MM / 2, abs=1e-6)
    assert layout.runs[0].char_space_pt == pytest.approx(1.0)


def test_left_and_right_alignment():
    left = C.layout_record(template(align="left"), C.Record("ab", "", date(2025, 1, 1)), FakeFont())
    right = C.layout_record(
        template(align="right"), C.Record("ab", "", date(2025, 1, 1)), FakeFont()
    )
    assert left.runs[0].x_mm == pytest.approx(100)
    assert right.runs[0].x_mm == pytest.approx(100 - 10 / C.PT_PER_MM)


def test_long_names_shrink_to_fit_the_maximum_width():
    long_name = "x" * 200  # 1000 pt wide at full size, far wider than 50 mm
    layout = C.layout_record(
        template(max_width_mm=50), C.Record(long_name, "", date(2025, 1, 1)), FakeFont()
    )
    assert layout.shrunk["name"] == C.MIN_SHRINK  # never smaller than the floor
    short = C.layout_record(
        template(max_width_mm=50), C.Record("ab", "", date(2025, 1, 1)), FakeFont()
    )
    assert short.shrunk == {}


def test_calibration_offset_moves_everything():
    base = C.layout_record(template(), C.Record("ab", "", date(2025, 1, 1)), FakeFont())
    moved = C.layout_record(
        template(), C.Record("ab", "", date(2025, 1, 1)), FakeFont(), offset_mm=(1.5, -2)
    )
    assert moved.runs[0].x_mm - base.runs[0].x_mm == pytest.approx(1.5)
    assert moved.runs[0].baseline_mm - base.runs[0].baseline_mm == pytest.approx(-2)


def test_superscript_is_smaller_and_raised():
    spec = {"x_mm": 100.0, "baseline_mm": 140.0, "size_pt": 10.0}
    t = C.Template.from_dict(
        {"page": {"width_mm": 200, "height_mm": 250}, "fields": {"date": spec}}
    )
    runs = C.layout_record(t, C.Record("", "", date(2025, 4, 20)), FakeFont()).runs
    sup = next(r for r in runs if r.superscript)
    assert sup.text == "TH"
    assert sup.size_pt == pytest.approx(10 * C.SUPERSCRIPT_SIZE)
    assert sup.baseline_mm < 140
    assert runs[0].x_mm < sup.x_mm < runs[2].x_mm


def pdf_check(pdf: bytes) -> str:
    """Basic structural checks; returns the PDF as text for content assertions."""
    text = pdf.decode("latin-1")
    assert text.startswith("%PDF-1.4") and text.rstrip().endswith("%%EOF")
    start = int(re.search(r"startxref\s+(\d+)", text).group(1))
    assert text[start:].startswith("xref")
    # every xref offset must point at "N 0 obj"
    entries = re.findall(r"(\d{10}) 00000 n", text[start:])
    for number, offset in enumerate(entries, start=1):
        assert text[int(offset) :].startswith(f"{number} 0 obj")
    return text


def test_pdf_has_one_page_per_certificate_and_exact_size():
    t = template()
    records = [
        C.Record("Ann Lee", "BTA", date(2025, 4, 20)),
        C.Record("Bob (Jr)", "BTA", date(2025, 4, 20)),
    ]
    pdf, layouts = C.render_certificates(t, records, FakeFont())
    text = pdf_check(pdf)
    assert "/Count 2" in text
    assert text.count("/Type /Page ") == 2
    width, height = 200 * C.PT_PER_MM, 250 * C.PT_PER_MM
    assert f"/MediaBox [0 0 {C._num(width)} {C._num(height)}]" in text
    assert "/FontFile2" in text and "/PrintScaling /None" in text
    assert "(ANN LEE)" in text and "(BOB \\(JR\\))" in text  # parentheses escaped
    assert len(layouts) == 2


def test_a4_paper_keeps_the_certificate_at_the_top_left():
    pdf, _ = C.render_certificates(
        template(), [C.Record("A", "B", date(2025, 1, 1))], FakeFont(), paper="a4"
    )
    text = pdf_check(pdf)
    assert f"/MediaBox [0 0 {C._num(210 * C.PT_PER_MM)} {C._num(297 * C.PT_PER_MM)}]" in text
    # same distance from the TOP of the page as on certificate-size paper
    y = float(
        re.search(r"Tm \(A\)", text)
        and re.search(r"1 0 0 1 [\d.]+ ([\d.]+) Tm \(A\)", text).group(1)
    )
    assert 297 * C.PT_PER_MM - y == pytest.approx(100 * C.PT_PER_MM, abs=0.01)


def test_alignment_test_page_draws_guides():
    pdf = C.render_alignment_test(
        template(), C.Record("Sample", "Course", date(2025, 1, 1)), FakeFont()
    )
    text = pdf_check(pdf)
    assert " re S" in text and " l S" in text and "50 mm" in text


def test_restricted_fonts_are_refused():
    font = FakeFont()
    font.embeddable = False
    with pytest.raises(C.FontError):
        C.render_certificates(template(), [C.Record("A", "B", date(2025, 1, 1))], font)


def test_repo_template_matches_the_photoshop_layout():
    t = C.load_template(ROOT / "assets" / "certificate_template.json")
    assert (t.width_mm, t.height_mm) == pytest.approx((209.97, 274.49))
    assert set(t.fields) == {"name", "course", "date"}
    assert (
        t.fields["name"].baseline_mm < t.fields["course"].baseline_mm < t.fields["date"].baseline_mm
    )
    assert all(f.faux_bold and f.caps for f in t.fields.values())


def test_real_font_measures_and_embeds():
    font = C.find_font()
    if font is None:
        pytest.skip("no serif TrueType font installed")
    assert font.text_width_pt("MMMM", 10) > font.text_width_pt("iiii", 10) > 0
    t = C.load_template(ROOT / "assets" / "certificate_template.json")
    pdf, _ = C.render_certificates(
        t, [C.Record("Ann Lee", "Business Tax Associate (BTA)", date(2025, 4, 20))], font
    )
    pdf_check(pdf)


def test_records_from_table_maps_columns_and_dates():
    table = pd.DataFrame(
        {
            "Full Name": ["Ann Lee", "", "Bob Ray"],
            "Course": ["BTA", "", None],
            "Date": ["20/04/2025", "", "bad"],
        }
    )
    records = C.records_from_table(table, "Default course", date(2026, 1, 1))
    assert [r.name for r in records] == ["Ann Lee", "Bob Ray"]  # blank rows skipped
    assert records[0].course == "BTA" and records[0].awarded == date(2025, 4, 20)
    assert records[1].course == "Default course" and records[1].awarded == date(2026, 1, 1)


def test_level_completers_strict_and_lenient():
    df = make_df(
        [
            ("S1", "A1", "2024-Jun", 1, 60),
            ("S1", "A2", "2024-Jun", 1, 70),  # passed both
            ("S2", "A1", "2024-Jun", 1, 60),  # passed the only one attempted
            ("S3", "A1", "2024-Jun", 1, 40),
            ("S3", "A2", "2024-Jun", 1, 70),  # one outstanding
        ]
    )
    df["level"] = "Level X"
    strict = C.level_completers(df, "Level X", strict=True)
    lenient = C.level_completers(df, "Level X", strict=False)
    assert set(strict["student_id"]) == {"S1"}
    assert set(lenient["student_id"]) == {"S1", "S2"}
    assert C.level_completers(df, "Nope").empty


def test_png_matches_the_page_size_and_puts_ink_on_the_baseline():
    from io import BytesIO

    from PIL import Image

    font = C.find_font()
    if font is None:
        pytest.skip("no serif TrueType font installed")
    t = C.load_template(ROOT / "assets" / "certificate_template.json")
    layout = C.layout_record(t, C.Record("Ann Lee", "Course", date(2025, 4, 20)), font)
    image = Image.open(BytesIO(C.render_png(t, layout, font, dpi=100)))
    assert image.size == (round(t.width_mm * 100 / 25.4), round(t.height_mm * 100 / 25.4))
    assert round(image.info["dpi"][0]) == 100  # stored so it prints at 100%
    pixels = image.convert("L").load()
    y = round(t.fields["name"].baseline_mm * 100 / 25.4) - 3  # just above the name's baseline
    x0 = round((t.fields["name"].x_mm - 15) * 100 / 25.4)
    assert any(pixels[x, y] < 128 for x in range(x0, x0 + round(30 * 100 / 25.4)))
    guided = Image.open(
        BytesIO(C.render_png(t, layout, font, dpi=100, guides=C.alignment_guides(t, (0, 0))))
    )
    assert guided.convert("RGB").getpixel((0, guided.height // 2))[2] > 150  # blue page outline


def test_png_background_is_transparent_and_letters_are_opaque_black():
    from io import BytesIO

    from PIL import Image

    font = C.find_font()
    if font is None:
        pytest.skip("no serif TrueType font installed")
    t = C.load_template(ROOT / "assets" / "certificate_template.json")
    layout = C.layout_record(t, C.Record("Ann Lee", "Course", date(2025, 4, 20)), font)
    image = Image.open(BytesIO(C.render_png(t, layout, font, dpi=100)))
    assert image.mode == "RGBA"
    assert image.getpixel((5, 5))[3] == 0  # empty paper is fully transparent
    alpha = image.getchannel("A")
    assert alpha.getextrema() == (0, 255)
    # every visible pixel is black: no white halo around anti-aliased edges
    visible = [px for px in image.getdata() if px[3] > 0]
    assert visible and all(px[:3] == (0, 0, 0) for px in visible)
    assert image.getpixel((5, 5))[:3] == (255, 255, 255)  # hidden background is white, not black
    opaque = Image.open(BytesIO(C.render_png(t, layout, font, dpi=100, transparent=False)))
    assert opaque.mode == "RGB" and opaque.getpixel((5, 5)) == (255, 255, 255)


def test_text_scale_shrinks_every_line_but_keeps_centre_and_baseline():
    base = C.layout_record(template(), C.Record("abcd", "", date(2025, 1, 1)), FakeFont())
    small = C.layout_record(
        template(), C.Record("abcd", "", date(2025, 1, 1)), FakeFont(), text_scale=0.9
    )
    assert small.runs[0].size_pt == pytest.approx(base.runs[0].size_pt * 0.9)
    assert small.runs[0].baseline_mm == base.runs[0].baseline_mm
    # 20 pt wide -> 18 pt wide, still centred on x = 100 mm
    assert small.runs[0].x_mm == pytest.approx(100 - 18 / C.PT_PER_MM / 2, abs=1e-6)
    assert small.shrunk == {}


def test_moving_text_down_12_mm():
    base = C.layout_record(template(), C.Record("abcd", "", date(2025, 1, 1)), FakeFont())
    down = C.layout_record(
        template(), C.Record("abcd", "", date(2025, 1, 1)), FakeFont(), offset_mm=(0, 12)
    )
    assert down.runs[0].baseline_mm - base.runs[0].baseline_mm == pytest.approx(12)
