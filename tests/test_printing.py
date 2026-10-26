"""Tests for direct printing. Nothing is ever sent to a printer: Windows renders a print
*preview* (PreviewPrintController), which uses no paper."""

from __future__ import annotations

from datetime import date
from io import BytesIO
from pathlib import Path

import numpy as np
import pytest

from examlens import certificates as C
from examlens import printing as P

ROOT = Path(__file__).resolve().parent.parent


def test_unavailable_platform_gives_a_friendly_error(monkeypatch):
    monkeypatch.setattr(P, "available", lambda: False)
    assert P.list_printers() == []
    with pytest.raises(P.PrintError, match="Windows"):
        P.print_pages([b"png"], "Any printer", (210, 274.5))


def test_nothing_to_print_is_an_error(monkeypatch):
    monkeypatch.setattr(P, "available", lambda: True)
    with pytest.raises(P.PrintError, match="Nothing"):
        P.print_pages([], "Any printer", (210, 274.5))


def test_manual_tray_is_found_by_kind():
    printer = P.Printer(
        "X",
        sources=[{"name": "Auto", "kind": "AutomaticFeed"}, {"name": "手送纸盘", "kind": "Manual"}],
    )
    assert printer.manual_tray() == "手送纸盘"
    assert P.Printer("Y").manual_tray() is None


@pytest.fixture(scope="module")
def printer():
    if not P.available():
        pytest.skip("direct printing needs Windows")
    printers = P.list_printers()
    if not printers:
        pytest.skip("no printer installed")
    return printers[0]


def test_printers_are_listed_with_papers_and_default_first(printer):
    assert printer.name
    assert printer.papers and all({"name", "width", "height"} <= set(p) for p in printer.papers)


def test_print_preview_places_text_exactly_like_the_app(printer):
    from PIL import Image

    font = C.find_font()
    if font is None:
        pytest.skip("no certificate font")
    t = C.load_template(ROOT / "assets" / "certificate_template.json")
    layout = C.layout_record(
        t, C.Record("Ann Lee", "Business Tax Associate (BTA)", date(2025, 4, 20)), font
    )
    page = C.render_png(t, layout, font, dpi=150, transparent=False)
    result = P.print_pages([page], printer.name, (t.width_mm, t.height_mm), preview=True)
    assert result.pages == 1 and len(result.preview_pages) == 1
    assert result.paper == "Certificate"
    assert result.paper_mm[0] == pytest.approx(t.width_mm, abs=0.2)

    preview = Image.open(BytesIO(result.preview_pages[0])).convert("L")
    source = Image.open(BytesIO(page)).convert("L")
    px_preview = preview.size[0] / result.paper_mm[0]
    px_source = source.size[0] / t.width_mm
    for key, spec in t.fields.items():
        boxes = []
        for image, px in ((preview, px_preview), (source, px_source)):
            ink = np.array(image) < 128
            y0, y1 = round((spec.baseline_mm - 7) * px), round((spec.baseline_mm + 2) * px)
            ys, xs = np.nonzero(ink[y0:y1, : round(200 * px)])
            boxes.append((xs.min() / px, xs.max() / px, (ys.max() + y0) / px))
        got, want = boxes
        for a, b in zip(got, want, strict=True):
            assert a == pytest.approx(b, abs=0.5), key  # within half a millimetre


CANON_ERROR = """<tr><td><b>Printer:</b></td><td><img src="/sg_err.gif"></td>
<td><b>Maintenance errors have occurred.</b></td><td><a><img src="bh_updt.gif"></a></td></tr>
<tr><td><b>Scanner:</b></td><td><img src="/sg_ok.gif"></td><td><b>Ready to scan.</b></td></tr>"""


def test_status_page_error_is_detected():
    assert P.parse_status_page(CANON_ERROR) == ("Maintenance errors have occurred.", False)


def test_status_page_ready_is_ok():
    ready = CANON_ERROR.replace("sg_err", "sg_ok").replace(
        "Maintenance errors have occurred.", "Ready to print."
    )
    assert P.parse_status_page(ready) == ("Ready to print.", True)


def test_status_page_paper_jam_text_is_an_error_even_with_a_neutral_icon():
    jam = CANON_ERROR.replace("sg_err", "sg_ok").replace(
        "Maintenance errors have occurred.", "Paper jam."
    )
    assert P.parse_status_page(jam)[1] is False


def test_status_unknown_page_or_no_host():
    assert P.parse_status_page("<html>hello</html>") is None
    assert P.device_status("") is None
