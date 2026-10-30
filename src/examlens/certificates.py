"""Certificate printing: place name, course and date onto pre-printed certificate stock.

The layout comes from a Photoshop template (see ``scripts/psd_to_template.py``): page size and,
for each field, the anchor x, the baseline y, the font size, tracking and alignment. This module
turns records into a print-ready PDF that contains *only* the text, positioned to the hundredth
of a millimetre, with the certificate font embedded. No PDF library is needed: the writer below
emits a small, standards-compliant PDF 1.4 file with an embedded TrueType font.
"""

from __future__ import annotations

import json
import os
import re
import struct
import zlib
from dataclasses import asdict, dataclass, field, fields
from datetime import date
from html import escape
from pathlib import Path

import pandas as pd

PT_PER_MM = 72 / 25.4
FAUX_BOLD_ADVANCE_EM = 0.026  # Photoshop "Faux Bold": extra advance per letter, in em
FAUX_BOLD_STROKE_EM = 0.035  # and outline width (fitted to a Photoshop render), in em
SUPERSCRIPT_SIZE = 0.583  # Photoshop's default superscript size
SUPERSCRIPT_RISE = 0.333  # and position, as fractions of the font size
UNDERLINE_DROP_EM = 0.21  # Photoshop underline: centre below the baseline, in em
UNDERLINE_THICKNESS_EM = 0.07  # and thickness (both measured from a Photoshop render)
MIN_SHRINK = 0.6  # long names shrink to fit, but never below 60% of the design size
A4 = (210.0, 297.0)


# --------------------------------------------------------------------------------------------
# Template
# --------------------------------------------------------------------------------------------


@dataclass
class FieldSpec:
    """Where and how one line of text is printed."""

    x_mm: float
    baseline_mm: float
    size_pt: float
    tracking: float = 0.0  # 1/1000 em, as in Photoshop
    align: str = "center"
    caps: bool = True
    max_width_mm: float | None = None
    faux_bold: bool = False
    ordinal_gap: bool = False  # date: superscript ordinal with a space before it ("20 TH")

    def spacing_pt(self, size_pt: float) -> float:
        """Extra space after each character: tracking plus the faux-bold widening."""
        return (self.tracking / 1000 + (FAUX_BOLD_ADVANCE_EM if self.faux_bold else 0)) * size_pt


@dataclass
class DetailsSpec:
    """Back-page list: a title, then subject headings each followed by bulleted topics.

    Tracking and faux bold are shared by every line; the title is underlined,
    topics only when ``underline_topics`` is set. Vertical spacing follows the Photoshop template.
    """

    title_x_mm: float
    title_baseline_mm: float
    title_size_pt: float
    heading_x_mm: float
    first_heading_mm: float  # baseline of the first subject heading
    bullet_x_mm: float
    item_x_mm: float
    size_pt: float  # headings and topics
    line_mm: float  # between topics
    heading_gap_mm: float  # heading baseline to its first topic
    group_gap_mm: float  # last topic to the next heading
    bottom_mm: float  # lowest baseline that still fits on the page
    tracking: float = 0.0
    caps: bool = True  # headings and topics in capitals (False = exactly as typed)
    faux_bold: bool = False
    title: str = "Course subjects"
    title_caps: bool = True
    underline_topics: bool = False

    @classmethod
    def from_dict(cls, data: dict) -> DetailsSpec:
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in names})


@dataclass
class Template:
    """Certificate layout: page size, font and the three fields."""

    name: str
    width_mm: float
    height_mm: float
    font_name: str
    fields: dict[str, FieldSpec]
    details: DetailsSpec | None = None  # back page with a list of course subjects

    @classmethod
    def from_dict(cls, data: dict) -> Template:
        """Build from the JSON written by ``scripts/psd_to_template.py``."""
        page = data["page"]
        default_max = page["width_mm"] - 40
        fields = {
            key: FieldSpec(
                x_mm=float(f["x_mm"]),
                baseline_mm=float(f["baseline_mm"]),
                size_pt=float(f["size_pt"]),
                tracking=float(f.get("tracking", 0)),
                align=f.get("align", "center"),
                caps=bool(f.get("caps", True)),
                max_width_mm=float(f.get("max_width_mm", default_max)),
                faux_bold=bool(f.get("faux_bold", False)),
                ordinal_gap=bool(f.get("ordinal_gap", False)),
            )
            for key, f in data["fields"].items()
        }
        return cls(
            name=data.get("name", "Certificate"),
            width_mm=float(page["width_mm"]),
            height_mm=float(page["height_mm"]),
            font_name=data.get("font", {}).get("postscript_name", "BookmanOldStyle"),
            fields=fields,
            details=DetailsSpec.from_dict(data["details"]) if data.get("details") else None,
        )

    def to_dict(self) -> dict:
        """Inverse of :meth:`from_dict` (for downloading an adjusted layout)."""
        return {
            "name": self.name,
            "page": {"width_mm": self.width_mm, "height_mm": self.height_mm},
            "font": {"postscript_name": self.font_name},
            "fields": {
                key: {
                    "x_mm": f.x_mm,
                    "baseline_mm": f.baseline_mm,
                    "size_pt": f.size_pt,
                    "tracking": f.tracking,
                    "align": f.align,
                    "caps": f.caps,
                    "max_width_mm": f.max_width_mm,
                    "faux_bold": f.faux_bold,
                    "ordinal_gap": f.ordinal_gap,
                }
                for key, f in self.fields.items()
            },
            **({"details": asdict(self.details)} if self.details else {}),
        }


def load_template(path: str | Path) -> Template:
    """Read a template JSON file."""
    return Template.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


# --------------------------------------------------------------------------------------------
# Fonts
# --------------------------------------------------------------------------------------------


class FontError(Exception):
    """The font file is missing, unreadable or may not be embedded."""


class TrueTypeFont:
    """Just enough of a TrueType parser to measure and embed text (WinAnsi characters)."""

    def __init__(self, data: bytes, source: str = "") -> None:
        self.data = data
        self.source = source
        try:
            self._parse()
        except (struct.error, KeyError, IndexError) as exc:
            raise FontError(f"Not a usable TrueType font: {source or 'uploaded file'}") from exc

    @classmethod
    def from_path(cls, path: str | Path) -> TrueTypeFont:
        """Load a ``.ttf`` file."""
        return cls(Path(path).read_bytes(), str(path))

    def _table(self, tag: str) -> tuple[int, int]:
        return self.tables[tag]

    def _parse(self) -> None:
        data = self.data
        if data[:4] not in (b"\x00\x01\x00\x00", b"true"):
            raise FontError("Only TrueType outlines (.ttf) can be embedded")
        (num_tables,) = struct.unpack(">H", data[4:6])
        self.tables = {}
        for i in range(num_tables):
            tag, _, offset, length = struct.unpack(">4sIII", data[12 + 16 * i : 28 + 16 * i])
            self.tables[tag.decode("latin-1")] = (offset, length)

        head, _ = self._table("head")
        (self.units_per_em,) = struct.unpack(">H", data[head + 18 : head + 20])
        self.bbox = struct.unpack(">hhhh", data[head + 36 : head + 44])
        hhea, _ = self._table("hhea")
        self.ascent, self.descent = struct.unpack(">hh", data[hhea + 4 : hhea + 8])
        (num_hmetrics,) = struct.unpack(">H", data[hhea + 34 : hhea + 36])
        hmtx, _ = self._table("hmtx")
        self.advances = [
            struct.unpack(">H", data[hmtx + 4 * i : hmtx + 4 * i + 2])[0]
            for i in range(num_hmetrics)
        ]
        self.cap_height = self.ascent
        self.embeddable = True
        if "OS/2" in self.tables:
            os2, length = self._table("OS/2")
            (version,) = struct.unpack(">H", data[os2 : os2 + 2])
            (fs_type,) = struct.unpack(">H", data[os2 + 8 : os2 + 10])
            self.embeddable = not (fs_type & 0x0002)  # bit 1 = restricted licence
            if version >= 2 and length >= 90:
                (self.cap_height,) = struct.unpack(">h", data[os2 + 88 : os2 + 90])
        self.postscript_name = self._read_name(6) or Path(self.source).stem or "Font"
        self.family_name = self._read_name(1) or self.postscript_name
        self._cmap = self._read_cmap()
        space = self.glyph_width(" ")
        self.widths = []
        for code in range(32, 256):
            try:
                char = bytes([code]).decode("cp1252")
            except UnicodeDecodeError:
                self.widths.append(space)
                continue
            self.widths.append(self.glyph_width(char))

    def _read_name(self, name_id: int) -> str | None:
        if "name" not in self.tables:
            return None
        base, _ = self._table("name")
        _, count, string_offset = struct.unpack(">HHH", self.data[base : base + 6])
        for i in range(count):
            rec = base + 6 + 12 * i
            platform, encoding, _, nid, length, offset = struct.unpack(
                ">HHHHHH", self.data[rec : rec + 12]
            )
            if nid != name_id:
                continue
            raw = self.data[base + string_offset + offset : base + string_offset + offset + length]
            text = raw.decode("utf-16-be" if platform in (0, 3) else "latin-1", errors="ignore")
            if text:
                return text
        return None

    def _read_cmap(self) -> dict[int, int]:
        base, _ = self._table("cmap")
        _, count = struct.unpack(">HH", self.data[base : base + 4])
        sub = None
        for i in range(count):
            platform, encoding, offset = struct.unpack(
                ">HHI", self.data[base + 4 + 8 * i : base + 12 + 8 * i]
            )
            if platform == 3 and encoding in (1, 0) and sub is None:
                sub = base + offset
            elif platform == 0 and sub is None:
                sub = base + offset
        if sub is None or struct.unpack(">H", self.data[sub : sub + 2])[0] != 4:
            raise FontError("Font has no Unicode character map (format 4)")
        (seg_x2,) = struct.unpack(">H", self.data[sub + 6 : sub + 8])
        segs = seg_x2 // 2
        ends = struct.unpack(f">{segs}H", self.data[sub + 14 : sub + 14 + seg_x2])
        starts_at = sub + 16 + seg_x2
        starts = struct.unpack(f">{segs}H", self.data[starts_at : starts_at + seg_x2])
        deltas = struct.unpack(f">{segs}h", self.data[starts_at + seg_x2 : starts_at + 2 * seg_x2])
        ranges_at = starts_at + 2 * seg_x2
        ranges = struct.unpack(f">{segs}H", self.data[ranges_at : ranges_at + seg_x2])
        cmap: dict[int, int] = {}
        for code in range(32, 0x2200):  # Latin + punctuation is all a certificate needs
            for i in range(segs):
                if starts[i] <= code <= ends[i]:
                    if ranges[i] == 0:
                        gid = (code + deltas[i]) & 0xFFFF
                    else:
                        addr = ranges_at + 2 * i + ranges[i] + 2 * (code - starts[i])
                        (gid,) = struct.unpack(">H", self.data[addr : addr + 2])
                        gid = (gid + deltas[i]) & 0xFFFF if gid else 0
                    if gid:
                        cmap[code] = gid
                    break
        return cmap

    def glyph_width(self, char: str) -> float:
        """Advance width of one character in 1/1000 em."""
        gid = self._cmap.get(ord(char), 0)
        advance = self.advances[min(gid, len(self.advances) - 1)]
        return advance * 1000 / self.units_per_em

    def text_width_pt(self, text: str, size_pt: float, char_space_pt: float = 0.0) -> float:
        """Width of ``text`` set at ``size_pt``, with ``char_space_pt`` after every character."""
        units = sum(self.width_for_code(code) for code in encode(text))
        return units * size_pt / 1000 + char_space_pt * len(text)

    def width_for_code(self, code: int) -> float:
        """Advance width (1/1000 em) of a WinAnsi code."""
        return self.widths[code - 32] if 32 <= code <= 255 else self.widths[0]


FONT_DIRS = [
    Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Windows" / "Fonts",
    Path("/Library/Fonts"),
    Path.home() / "Library" / "Fonts",
    Path("/usr/share/fonts"),
    Path("/usr/local/share/fonts"),
    Path.home() / ".fonts",
    Path(__file__).resolve().parents[2] / "assets" / "fonts",  # bundled free fallback
]
FALLBACK_FONTS = [
    "BOOKOS.TTF",  # Bookman Old Style (Windows / Office)
    "ExamLensBonum-Regular.ttf",  # bundled: free Bookman clone (TeX Gyre Bonum, renamed)
    "TeXGyreBonum-Regular.ttf",  # free Bookman clone
    "texgyrebonum-regular.ttf",
    "georgia.ttf",
    "times.ttf",
    "DejaVuSerif.ttf",
    "LiberationSerif-Regular.ttf",
]


def find_font(extra_dirs: list[Path] | None = None) -> TrueTypeFont | None:
    """The certificate font if installed, otherwise the closest serif fallback."""
    dirs = [d for d in (extra_dirs or []) + FONT_DIRS if str(d) and d.exists()]
    for wanted in FALLBACK_FONTS:
        for folder in dirs:
            direct = folder / wanted
            matches = [direct] if direct.exists() else []
            if not matches and "windows" not in str(folder).lower():  # Windows folders are flat
                matches = [p for p in folder.rglob("*") if p.name.lower() == wanted.lower()][:1]
            for path in matches:
                try:
                    font = TrueTypeFont.from_path(path)
                except (OSError, FontError):
                    continue
                if font.embeddable:
                    return font
    return None


def encode(text: str) -> bytes:
    """Text as WinAnsi (cp1252) bytes; unsupported characters become '?'."""
    return text.encode("cp1252", errors="replace")


# --------------------------------------------------------------------------------------------
# Text and layout
# --------------------------------------------------------------------------------------------

ORDINAL = {1: "ST", 2: "ND", 3: "RD"}


def ordinal_suffix(day: int) -> str:
    """'ST', 'ND', 'RD' or 'TH' for a day of the month (11-13 are always 'TH')."""
    return "TH" if 10 <= day % 100 <= 20 else ORDINAL.get(day % 10, "TH")


def date_runs(value: date) -> list[tuple[str, bool]]:
    """Certificate date as text runs: ``[('20', False), ('TH', True), (' APRIL 2025', False)]``."""
    return [
        (str(value.day), False),
        (ordinal_suffix(value.day), True),
        (f" {value.strftime('%B').upper()} {value.year}", False),
    ]


@dataclass
class Record:
    """One certificate."""

    name: str
    course: str
    awarded: date
    subject: str = ""  # optional extra line (short courses: the specialisation)

    def runs(self, key: str, caps: bool) -> list[tuple[str, bool]]:
        if key == "date":
            return date_runs(self.awarded)
        text = " ".join(str(getattr(self, key, "")).split())
        return [(text.upper() if caps else text, False)]


@dataclass
class Placed:
    """A run of text ready to draw (all positions in mm from the top-left of the page)."""

    text: str
    x_mm: float
    baseline_mm: float
    size_pt: float
    char_space_pt: float
    field: str
    superscript: bool = False
    bold_pt: float = 0.0  # outline width that emulates faux bold (0 = plain fill)
    underline_mm: float = 0.0  # length of the underline (0 = none)


@dataclass
class Layout:
    """Everything on one certificate page."""

    runs: list[Placed] = field(default_factory=list)
    shrunk: dict[str, float] = field(default_factory=dict)  # field -> scale applied
    overflow: int = 0  # back page: lines that did not fit


def layout_record(
    template: Template,
    record: Record,
    font: TrueTypeFont,
    offset_mm: tuple[float, float] = (0.0, 0.0),
    text_scale: float = 1.0,
    field_offsets: dict[str, tuple[float, float]] | None = None,
) -> Layout:
    """Position each field's runs: centring, tracking, superscripts and shrink-to-fit.

    ``offset_mm`` moves every line (right, down); ``text_scale`` resizes every line (1.0 = the
    template's size). Lines stay centred on their anchor and keep their baselines.
    ``field_offsets`` moves single lines, e.g. ``{"course": (0, 2)}`` = course 2 mm lower.
    """
    out = Layout()
    for key, spec in template.fields.items():
        fx, fy = (field_offsets or {}).get(key, (0.0, 0.0))
        dx, dy = offset_mm[0] + fx, offset_mm[1] + fy
        runs = [(t, sup) for t, sup in record.runs(key, spec.caps) if t]
        if spec.ordinal_gap:
            runs = [(f" {t}" if sup else t, sup) for t, sup in runs]
        if not runs:
            continue

        def measure(scale: float, runs=runs, spec=spec) -> float:
            total = 0.0
            for text, sup in runs:
                size = spec.size_pt * scale * (SUPERSCRIPT_SIZE if sup else 1)
                total += font.text_width_pt(text, size, spec.spacing_pt(size))
            last_size = spec.size_pt * scale * (SUPERSCRIPT_SIZE if runs[-1][1] else 1)
            # no tracking after the last letter (the faux-bold widening still applies)
            return total - spec.tracking / 1000 * last_size

        scale = text_scale
        width_pt = measure(scale)
        limit_pt = (spec.max_width_mm or template.width_mm) * PT_PER_MM
        if width_pt > limit_pt:
            scale = max(MIN_SHRINK * text_scale, scale * limit_pt / width_pt)
            width_pt = measure(scale)
            out.shrunk[key] = round(scale / text_scale, 3)
        width_mm = width_pt / PT_PER_MM
        x = spec.x_mm + dx
        if spec.align == "center":
            x -= width_mm / 2
        elif spec.align == "right":
            x -= width_mm
        size = spec.size_pt * scale
        bold_shift = FAUX_BOLD_STROKE_EM / 2 if spec.faux_bold else 0.0
        for text, sup in runs:
            run_size = size * (SUPERSCRIPT_SIZE if sup else 1)
            spacing = spec.spacing_pt(run_size)
            rise_mm = (size * SUPERSCRIPT_RISE / PT_PER_MM) if sup else 0.0
            out.runs.append(
                Placed(
                    text,
                    x + bold_shift * run_size / PT_PER_MM,  # outline grows both ways
                    spec.baseline_mm + dy - rise_mm,
                    run_size,
                    spacing,
                    key,
                    sup,
                    bold_pt=FAUX_BOLD_STROKE_EM * run_size if spec.faux_bold else 0.0,
                )
            )
            x += font.text_width_pt(text, run_size, spacing) / PT_PER_MM
    return out


BULLET_MARKS = "-*•–"


def parse_details(text: str) -> list[tuple[str, list[str]]]:
    """Course details typed as plain lines: a subject heading, then its topics.

    Topic lines start with ``-``, ``*`` or ``•``; any other line starts a new subject.
    """
    groups: list[tuple[str, list[str]]] = []
    for line in text.splitlines():
        line = " ".join(line.split())
        if not line:
            continue
        if line[0] in BULLET_MARKS:
            topic = line.lstrip(BULLET_MARKS + " ")
            if topic:
                if not groups:
                    groups.append(("", []))
                groups[-1][1].append(topic)
        else:
            groups.append((line, []))
    return groups


def details_text(groups: list[tuple[str, list[str]]]) -> str:
    """Inverse of :func:`parse_details`."""
    return "\n".join(
        "\n".join([heading] * bool(heading) + [f"- {t}" for t in topics])
        for heading, topics in groups
    )


def layout_details(
    template: Template,
    groups: list[tuple[str, list[str]]],
    font: TrueTypeFont,
    title: str | None = None,
    offset_mm: tuple[float, float] = (0.0, 0.0),
    text_scale: float = 1.0,
    line_spacing: float = 1.0,
) -> Layout:
    """The back page: underlined title, then each subject heading with its bulleted topics.

    ``text_scale`` resizes the text and the gaps below the title together, so lines never
    overlap. ``line_spacing`` scales the space between topic lines only (Photoshop's leading). Lines that would fall below the page's last baseline are counted in
    ``Layout.overflow`` and left out.
    """
    spec = template.details
    if spec is None:
        raise ValueError(f"The template '{template.name}' has no back page")
    out = Layout()
    dx, dy = offset_mm
    spacing = (
        spec.tracking / 1000 + (FAUX_BOLD_ADVANCE_EM if spec.faux_bold else 0)
    ) * spec.size_pt
    bold_em = FAUX_BOLD_STROKE_EM if spec.faux_bold else 0.0

    def put(text: str, x: float, y: float, size: float, key: str, underline: bool) -> None:
        if y > spec.bottom_mm:
            out.overflow += 1
            return
        if spec.title_caps if key == "title" else spec.caps:
            text = text.upper()
        space = spacing / spec.size_pt * size
        width = (font.text_width_pt(text, size, space) - spec.tracking / 1000 * size) / PT_PER_MM
        out.runs.append(
            Placed(
                text,
                x + dx + bold_em / 2 * size / PT_PER_MM,
                y + dy,
                size,
                space,
                key,
                bold_pt=bold_em * size,
                underline_mm=width if underline else 0.0,
            )
        )

    title = spec.title if title is None else title
    if title.strip():
        put(
            title,
            spec.title_x_mm,
            spec.title_baseline_mm,
            spec.title_size_pt * text_scale,
            "title",
            True,
        )
    size = spec.size_pt * text_scale
    top = spec.title_baseline_mm
    y = top + (spec.first_heading_mm - top) * text_scale
    for n, (heading, topics) in enumerate(groups):
        if n:
            y += spec.group_gap_mm * text_scale
        if heading:
            put(heading, spec.heading_x_mm, y, size, "heading", False)
            y += spec.heading_gap_mm * text_scale
        for i, topic in enumerate(topics):
            if i:
                y += spec.line_mm * text_scale * line_spacing
            put("•", spec.bullet_x_mm, y, size, "bullet", False)
            put(topic, spec.item_x_mm, y, size, "topic", spec.underline_topics)
    return out


# --------------------------------------------------------------------------------------------
# PDF
# --------------------------------------------------------------------------------------------


def underline_box(run: Placed) -> tuple[float, float]:
    """Top edge and thickness of a run's underline, in mm."""
    size_mm = run.size_pt / PT_PER_MM
    thick = UNDERLINE_THICKNESS_EM * size_mm
    return run.baseline_mm + UNDERLINE_DROP_EM * size_mm - thick / 2, thick


def _pdf_string(text: str) -> bytes:
    out = bytearray(b"(")
    for byte in encode(text):
        if byte in (0x28, 0x29, 0x5C):
            out += b"\\" + bytes([byte])
        elif byte < 32 or byte > 126:
            out += b"\\%03o" % byte
        else:
            out.append(byte)
    return bytes(out + b")")


def _num(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".") or "0"


@dataclass
class Guide:
    """Alignment-test drawing in mm from the top-left: a line, a rectangle or a small label."""

    kind: str  # "line" | "rect" | "label"
    x: float
    y: float
    x2: float = 0.0
    y2: float = 0.0
    text: str = ""


def build_pdf(
    pages: list[Layout],
    font: TrueTypeFont,
    page_mm: tuple[float, float],
    guides: list[list[Guide]] | None = None,
    title: str = "Certificates",
) -> bytes:
    """Write a PDF with one page per layout, the font embedded, text only."""
    if not font.embeddable:
        raise FontError("This font's licence does not allow embedding in a PDF")
    width_pt, height_pt = page_mm[0] * PT_PER_MM, page_mm[1] * PT_PER_MM

    def y_pt(y_mm: float) -> float:
        return height_pt - y_mm * PT_PER_MM

    # Fixed object numbers: 1-3 font, then (content, page) per page, then pages, info, catalog.
    n_pages = len(pages)
    pages_id = 4 + 2 * n_pages
    objects: list[bytes] = []

    def add(obj: bytes) -> int:
        objects.append(obj)
        return len(objects)

    ps_name = re.sub(r"[^A-Za-z0-9\-]", "", font.postscript_name) or "CertificateFont"
    raw = font.data
    packed = zlib.compress(raw, 9)
    font_file = add(
        b"<< /Length %d /Length1 %d /Filter /FlateDecode >>\nstream\n" % (len(packed), len(raw))
        + packed
        + b"\nendstream"
    )
    k = 1000 / font.units_per_em
    bbox = " ".join(_num(v * k) for v in font.bbox)
    descriptor = add(
        (
            f"<< /Type /FontDescriptor /FontName /{ps_name} /Flags 34 /FontBBox [{bbox}] "
            f"/ItalicAngle 0 /Ascent {_num(font.ascent * k)} /Descent {_num(font.descent * k)} "
            f"/CapHeight {_num(font.cap_height * k)} /StemV 80 /FontFile2 {font_file} 0 R >>"
        ).encode()
    )
    widths = " ".join(_num(w) for w in font.widths)
    font_obj = add(
        (
            f"<< /Type /Font /Subtype /TrueType /BaseFont /{ps_name} /FirstChar 32 /LastChar 255 "
            f"/Widths [{widths}] /Encoding /WinAnsiEncoding /FontDescriptor {descriptor} 0 R >>"
        ).encode()
    )

    page_ids = []
    for index, layout in enumerate(pages):
        ops = [b"0 g 0 G 1 j"]
        for run in layout.runs:
            # Render mode 2 = fill + outline: an even outline is how faux bold is emulated.
            mode = b"2 Tr %s w" % _num(run.bold_pt).encode() if run.bold_pt else b"0 Tr"
            ops.append(
                b"BT %s /F1 %s Tf %s Tc 1 0 0 1 %s %s Tm %s Tj ET"
                % (
                    mode,
                    _num(run.size_pt).encode(),
                    _num(run.char_space_pt).encode(),
                    _num(run.x_mm * PT_PER_MM).encode(),
                    _num(y_pt(run.baseline_mm)).encode(),
                    _pdf_string(run.text),
                )
            )
            if run.underline_mm:
                top, thick = underline_box(run)
                ops.append(
                    b"%s %s %s %s re f"
                    % tuple(
                        _num(v).encode()
                        for v in (
                            run.x_mm * PT_PER_MM,
                            y_pt(top + thick),
                            run.underline_mm * PT_PER_MM,
                            thick * PT_PER_MM,
                        )
                    )
                )
        for guide in guides[index] if guides and index < len(guides) else []:
            if guide.kind == "line":
                ops.append(
                    b"0.25 w 0.85 0.1 0.1 RG %s %s m %s %s l S"
                    % tuple(
                        _num(v).encode()
                        for v in (
                            guide.x * PT_PER_MM,
                            y_pt(guide.y),
                            guide.x2 * PT_PER_MM,
                            y_pt(guide.y2),
                        )
                    )
                )
            elif guide.kind == "rect":
                ops.append(
                    b"0.4 w 0.2 0.4 0.9 RG %s %s %s %s re S"
                    % tuple(
                        _num(v).encode()
                        for v in (
                            guide.x * PT_PER_MM,
                            y_pt(guide.y2),
                            (guide.x2 - guide.x) * PT_PER_MM,
                            (guide.y2 - guide.y) * PT_PER_MM,
                        )
                    )
                )
            elif guide.kind == "label":
                ops.append(
                    b"0.5 g BT /F1 7 Tf 0 Tc 1 0 0 1 %s %s Tm %s Tj ET 0 g"
                    % (
                        _num(guide.x * PT_PER_MM).encode(),
                        _num(y_pt(guide.y)).encode(),
                        _pdf_string(guide.text),
                    )
                )
        stream = b"\n".join(ops)
        content = add(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
        page_ids.append(
            add(
                (
                    f"<< /Type /Page /Parent {pages_id} 0 R "
                    f"/MediaBox [0 0 {_num(width_pt)} {_num(height_pt)}] "
                    f"/Resources << /Font << /F1 {font_obj} 0 R >> >> /Contents {content} 0 R >>"
                ).encode()
            )
        )
    kids = " ".join(f"{p} 0 R" for p in page_ids)
    if add(f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode()) != pages_id:
        raise AssertionError("PDF object numbering is out of sync")
    info = add(
        b"<< /Title "
        + _pdf_string(title)
        + b" /Producer (ExamLens certificate printer) /Creator (ExamLens) >>"
    )
    # Print at 100%: ask viewers not to scale the page to the printer margins.
    catalog = add(
        f"<< /Type /Catalog /Pages {pages_id} 0 R "
        f"/ViewerPreferences << /PrintScaling /None /PickTrayByPDFSize true >> >>".encode()
    )

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<< /Size %d /Root %d 0 R /Info %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        catalog,
        info,
        xref,
    )
    return bytes(out)


def page_size(template: Template, paper: str) -> tuple[float, float]:
    """Physical page: the certificate itself, or A4 with the certificate at the top-left."""
    return A4 if paper == "a4" else (template.width_mm, template.height_mm)


def alignment_guides(
    template: Template,
    offset_mm: tuple[float, float],
    field_offsets: dict[str, tuple[float, float]] | None = None,
) -> list[Guide]:
    """Outline of the certificate edge, a baseline and centre tick for every field, a ruler."""
    dx, dy = offset_mm
    w, h = template.width_mm, template.height_mm
    guides = [Guide("rect", 0 + dx, 0 + dy, w + dx, h + dy)]
    for key, spec in template.fields.items():
        fx, fy = (field_offsets or {}).get(key, (0.0, 0.0))
        y = spec.baseline_mm + dy + fy
        x = spec.x_mm + dx + fx
        guides += [
            Guide("line", x - 60, y, x + 60, y),
            Guide("line", x, y - 6, x, y + 2),
            Guide("label", x + 62, y, text=f"{key} baseline"),
        ]
    for mm in range(0, 51, 10):  # 50 mm ruler at the bottom-left to check printer scaling
        guides.append(Guide("line", 10 + mm + dx, h - 12 + dy, 10 + mm + dx, h - 15 + dy))
    guides += [
        Guide("line", 10 + dx, h - 12 + dy, 60 + dx, h - 12 + dy),
        Guide("label", 62 + dx, h - 12 + dy, text="50 mm: measure this to check 100% scale"),
    ]
    return guides


def render_certificates(
    template: Template,
    records: list[Record],
    font: TrueTypeFont,
    paper: str = "certificate",
    offset_mm: tuple[float, float] = (0.0, 0.0),
    text_scale: float = 1.0,
    field_offsets: dict[str, tuple[float, float]] | None = None,
) -> tuple[bytes, list[Layout]]:
    """PDF bytes for a batch of certificates, plus the layouts (for warnings and previews)."""
    layouts = [
        layout_record(template, r, font, offset_mm, text_scale, field_offsets) for r in records
    ]
    pdf = build_pdf(
        layouts, font, page_size(template, paper), title=f"{template.name} certificates"
    )
    return pdf, layouts


def render_alignment_test(
    template: Template,
    sample: Record,
    font: TrueTypeFont,
    paper: str = "certificate",
    offset_mm: tuple[float, float] = (0.0, 0.0),
    text_scale: float = 1.0,
    field_offsets: dict[str, tuple[float, float]] | None = None,
) -> bytes:
    """One page with sample text plus guides, for checking alignment on plain paper."""
    layout = layout_record(template, sample, font, offset_mm, text_scale, field_offsets)
    return build_pdf(
        [layout],
        font,
        page_size(template, paper),
        guides=[alignment_guides(template, offset_mm, field_offsets)],
        title="Certificate alignment test",
    )


def render_png(
    template: Template,
    layout: Layout,
    font: TrueTypeFont,
    dpi: int = 300,
    paper: str = "certificate",
    guides: list[Guide] | None = None,
    transparent: bool = True,
) -> bytes:
    """The same page as the PDF, as a PNG image at ``dpi`` (positions identical to the PDF).

    ``transparent``: only the letters are visible, so nothing but the text prints on the
    certificate. Empty pixels are transparent *white* (programs that ignore transparency, such
    as Windows printing, show white = no ink), while every letter pixel, including the
    anti-aliased edges, is pure black with partial opacity (no light fringe on coloured paper).
    """
    from io import BytesIO

    from PIL import Image, ImageDraw, ImageFont

    px = dpi / 25.4  # pixels per mm
    width_mm, height_mm = page_size(template, paper)
    size = (round(width_mm * px), round(height_mm * px))
    ink = Image.new("L", size, 0)  # letter coverage: 0 = paper, 255 = solid ink
    draw = ImageDraw.Draw(ink)
    fonts: dict[float, ImageFont.FreeTypeFont] = {}
    for run in layout.runs:
        size_px = run.size_pt / 72 * dpi
        if size_px not in fonts:
            fonts[size_px] = ImageFont.truetype(BytesIO(font.data), size=size_px)
        face = fonts[size_px]
        # PDF outline of width w grows each side by w/2; Pillow's stroke_width is per side.
        stroke = max(0, round(run.bold_pt / 72 * dpi / 2))
        x, y = run.x_mm * px, run.baseline_mm * px
        for char, code in zip(run.text, encode(run.text), strict=True):
            draw.text(
                (x, y), char, font=face, fill=255, anchor="ls", stroke_width=stroke, stroke_fill=255
            )
            x += (font.width_for_code(code) * run.size_pt / 1000 + run.char_space_pt) / 72 * dpi
        if run.underline_mm:
            top, thick = underline_box(run)
            draw.rectangle(
                [
                    run.x_mm * px,
                    top * px,
                    (run.x_mm + run.underline_mm) * px,
                    (top + thick) * px - 1,
                ],
                fill=255,
            )

    if transparent:
        rgb = ink.point(lambda v: 0 if v else 255)  # black under letters, white elsewhere
        image = Image.merge("RGBA", (rgb, rgb, rgb, ink))
    else:
        image = Image.new("RGBA", size, (255, 255, 255, 255))
        image.paste((0, 0, 0, 255), mask=ink)

    if guides:
        overlay = Image.new("RGBA", size, (0, 0, 0, 0))
        g = ImageDraw.Draw(overlay)
        for guide in guides:
            if guide.kind == "line":
                g.line(
                    [(guide.x * px, guide.y * px), (guide.x2 * px, guide.y2 * px)],
                    fill=(217, 38, 38, 255),
                    width=max(1, dpi // 150),
                )
            elif guide.kind == "rect":
                g.rectangle(
                    [guide.x * px, guide.y * px, guide.x2 * px - 1, guide.y2 * px - 1],
                    outline=(51, 102, 230, 255),
                    width=max(1, dpi // 100),
                )
            elif guide.kind == "label":
                label = ImageFont.truetype(BytesIO(font.data), size=7 / 72 * dpi)
                g.text(
                    (guide.x * px, guide.y * px),
                    guide.text,
                    font=label,
                    fill=(128, 128, 128, 255),
                    anchor="ls",
                )
        image.alpha_composite(overlay)
    if not transparent:
        image = image.convert("RGB")
    out = BytesIO()
    image.save(out, format="PNG", dpi=(dpi, dpi))  # DPI is stored so printing at 100% is exact
    return out.getvalue()


# --------------------------------------------------------------------------------------------
# Preview
# --------------------------------------------------------------------------------------------


def preview_svg(
    template: Template,
    layout: Layout,
    font_family: str,
    guides: bool = False,
    dark: bool = False,
) -> str:
    """SVG preview of one certificate (mm coordinates, so it is to scale)."""
    w, h = template.width_mm, template.height_mm
    paper, ink, faint = (
        ("#1e1e24", "#f5f5f7", "#3a3a44") if dark else ("#fffdf7", "#1a1a1a", "#e8e1cf")
    )
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:.2f} {h:.2f}" '
        f'style="width:100%;height:auto;display:block">',
        f'<rect x="0" y="0" width="{w:.2f}" height="{h:.2f}" rx="1.5" fill="{paper}"/>',
        f'<rect x="8" y="8" width="{w - 16:.2f}" height="{h - 16:.2f}" fill="none" '
        f'stroke="{faint}" stroke-width="1.2"/>',
        f'<rect x="11" y="11" width="{w - 22:.2f}" height="{h - 22:.2f}" fill="none" '
        f'stroke="{faint}" stroke-width="0.3"/>',
    ]
    if guides:
        for key, spec in template.fields.items():
            parts.append(
                f'<line x1="15" x2="{w - 15:.2f}" y1="{spec.baseline_mm:.2f}" y2="{spec.baseline_mm:.2f}" '
                f'stroke="#ff453a" stroke-width="0.15" stroke-dasharray="1 1"/>'
                f'<text x="16" y="{spec.baseline_mm - 1:.2f}" font-size="2.2" fill="#ff453a" '
                f'font-family="sans-serif">{escape(key)}</text>'
            )
        parts.append(
            f'<line x1="{w / 2:.2f}" x2="{w / 2:.2f}" y1="15" y2="{h - 15:.2f}" stroke="#0a84ff" '
            f'stroke-width="0.15" stroke-dasharray="1 1"/>'
        )
    for run in layout.runs:
        size_mm = run.size_pt / PT_PER_MM
        spacing_mm = run.char_space_pt / PT_PER_MM
        bold = (
            f'stroke="{ink}" stroke-width="{run.bold_pt / PT_PER_MM:.3f}" stroke-linejoin="round" '
            if run.bold_pt
            else ""
        )
        parts.append(
            f'<text x="{run.x_mm:.3f}" y="{run.baseline_mm:.3f}" font-size="{size_mm:.3f}" '
            f'letter-spacing="{spacing_mm:.3f}" fill="{ink}" {bold}'
            # inline style, so page-wide font rules cannot override the certificate font
            f"style=\"font-family:'{escape(font_family)}','Bookman Old Style','URW Bookman',serif\" "
            f'xml:space="preserve">{escape(run.text)}</text>'
        )
        if run.underline_mm:
            top, thick = underline_box(run)
            parts.append(
                f'<rect x="{run.x_mm:.3f}" y="{top:.3f}" width="{run.underline_mm:.3f}" '
                f'height="{thick:.3f}" fill="{ink}"/>'
            )
    parts.append("</svg>")
    return "".join(parts)


# --------------------------------------------------------------------------------------------
# Who qualifies (from the results data)
# --------------------------------------------------------------------------------------------


def level_completers(df: pd.DataFrame, level: str, strict: bool = True) -> pd.DataFrame:
    """Students who have completed a level.

    ``strict``: passed every subject of the level (the CIT catalogue when known, otherwise every
    subject seen at that level). Otherwise: passed everything they attempted at the level with
    nothing outstanding, which also covers students exempted from some subjects.
    """
    from examlens.cit import LEVEL_SUBJECTS

    rows = df[df["level"] == level]
    if rows.empty:
        return pd.DataFrame(columns=["student_id", "student_name", "completed_in", "subjects"])
    catalogue = {code for code, _, _ in LEVEL_SUBJECTS.get(level, [])}
    by_programme = rows.groupby(rows["programme"].fillna(""))["subject_code"].agg(set).to_dict()
    out = []
    for sid, grp in rows.groupby("student_id"):
        required = catalogue or by_programme.get(
            grp["programme"].fillna("").iloc[0], set(grp["subject_code"])
        )
        passed = set(grp.loc[grp["result"] == "Pass", "subject_code"])
        attempted = set(grp["subject_code"])
        done = required <= passed if strict else (bool(passed) and attempted <= passed)
        if not done:
            continue
        last = grp[grp["result"] == "Pass"].sort_values("session_date").iloc[-1]
        out.append(
            {
                "student_id": sid,
                "student_name": grp["student_name"].iloc[0],
                "completed_in": last["exam_session"],
                "completed_date": last["session_date"],
                "subjects": len(passed),
            }
        )
    result = pd.DataFrame(out)
    if result.empty:
        return pd.DataFrame(columns=["student_id", "student_name", "completed_in", "subjects"])
    return result.sort_values(["completed_date", "student_name"], ascending=[False, True])


def records_from_table(
    table: pd.DataFrame, default_course: str, default_date: date
) -> list[Record]:
    """Records from a pasted / uploaded table with name (and optionally course, date) columns."""
    cols = {re.sub(r"[^a-z]", "", str(c).lower()): c for c in table.columns}
    name_col = next(
        (cols[k] for k in ("name", "studentname", "fullname", "nameinfull") if k in cols), None
    )
    if name_col is None:
        name_col = table.columns[0]
    course_col = next(
        (cols[k] for k in ("course", "programme", "qualification", "award") if k in cols), None
    )
    date_col = next(
        (cols[k] for k in ("date", "awarded", "awarddate", "dateofaward") if k in cols), None
    )
    records = []
    for _, row in table.iterrows():
        name = str(row[name_col]).strip() if pd.notna(row[name_col]) else ""
        if not name:
            continue
        course = str(row[course_col]).strip() if course_col and pd.notna(row[course_col]) else ""
        when = default_date
        if date_col and pd.notna(row[date_col]):
            parsed = pd.to_datetime(row[date_col], errors="coerce", dayfirst=True)
            if pd.notna(parsed):
                when = parsed.date()
        records.append(Record(name, course or default_course, when))
    return records
