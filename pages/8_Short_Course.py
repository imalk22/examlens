import base64
import json
from datetime import date, datetime
from io import BytesIO

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import webui

from examlens import certificates as C
from examlens import printing

webui.header(
    "Short Course",
    "Short-course certificates: name, course, date and subject on the front, and the course "
    "subjects on the back, exactly where your Photoshop templates place them.",
)

PRIVATE = webui.ROOT / "data" / "private"  # git-ignored
SETTINGS_FILE = PRIVATE / "short_course_settings.json"
DETAILS_FILE = PRIVATE / "short_course_details.json"  # back-page details saved per course
TEMPLATE_FILE = webui.ASSETS / "short_course_template.json"
DEFAULT_COURSE = "Certificate Course in UAE Taxation"
DEFAULT_SUBJECT = "Corporate Taxation"
DEFAULT_DETAILS = """Income Tax
- Introduction
- Source of income
- Tax
- Taxation

Value Added Tax
- Introduction
- Source of income
- Tax
- Taxation"""
CUSTOM = "custom"


def load_json(path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_json(path, values: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(values, indent=2), encoding="utf-8")


@st.cache_resource(show_spinner=False)
def system_font() -> C.TrueTypeFont | None:
    return C.find_font()


template = C.load_template(TEMPLATE_FILE)
TEMPLATE_DEFAULTS = json.loads(TEMPLATE_FILE.read_text(encoding="utf-8")).get("print_defaults", {})
settings: dict = st.session_state.setdefault(
    "sc_settings", {**TEMPLATE_DEFAULTS, **load_json(SETTINGS_FILE)}
)
presets: dict = st.session_state.setdefault("sc_presets", load_json(DETAILS_FILE))
font: C.TrueTypeFont | None = st.session_state.get("cert_font") or system_font()
page_mm = (template.width_mm, template.height_mm)

if font is None:
    st.error(
        "No certificate font found. Install **Bookman Old Style** (it ships with Windows and "
        "Microsoft Office) or upload a .ttf font on the **Certificates** page under "
        "*Template & font*."
    )

# --- front: who and what ---------------------------------------------------------------------
left, right = st.columns([5, 4], gap="large")
records: list[C.Record] = []
with left:
    mode = st.radio(
        "Who are the certificates for?",
        ["One person", "A list of names"],
        horizontal=True,
        key="sc_mode",
    )
    course = st.text_input(
        "Course", value=settings.get("last_course", DEFAULT_COURSE), key="sc_course"
    )
    preset = presets.get(course.strip(), {})
    c1, c2 = st.columns([3, 2])
    subject = c1.text_input(
        "Subject (last line on the front)",
        value=preset.get("subject", DEFAULT_SUBJECT),
        key=f"sc_subject_{course}",
        help="Leave empty to print only the name, course and date.",
    )
    awarded = c2.date_input("Date", value=date.today(), format="DD/MM/YYYY", key="sc_date")
    if mode == "One person":
        name = st.text_input("Name", placeholder="e.g. A.K Imesh Samintha", key="sc_name")
        if name.strip():
            records = [C.Record(name, course, awarded, subject)]
    else:
        upload = st.file_uploader(
            "Upload a list (Excel or CSV with a Name column; a Subject column is optional)",
            type=["xlsx", "xls", "csv"],
            key="sc_list_file",
        )
        if upload is not None:
            try:
                table = (
                    pd.read_csv(upload)
                    if upload.name.lower().endswith(".csv")
                    else pd.read_excel(upload)
                )
                st.caption(f"{len(table)} rows read from {upload.name}.")
            except Exception:
                table = pd.DataFrame()
                st.error("Could not read that file. Make sure it has a column of names.")
        else:
            st.caption("Or type / paste names below (one per row). Subject can be left blank.")
            table = st.data_editor(
                pd.DataFrame({"Name": [""] * 5, "Subject": [""] * 5}),
                num_rows="dynamic",
                width="stretch",
                hide_index=True,
                key="sc_list_table",
            )
        if len(table.columns):
            subject_col = next(
                (c for c in table.columns if str(c).strip().lower() == "subject"), None
            )
            for base in C.records_from_table(table, course, awarded):
                rec = C.Record(base.name, course, base.awarded, subject)
                if subject_col is not None:  # a per-person subject replaces the one above
                    match = table[table.iloc[:, 0].astype(str).str.strip() == base.name]
                    value = match[subject_col].iloc[0] if len(match) else None
                    if pd.notna(value) and str(value).strip():
                        rec.subject = str(value).strip()
                records.append(rec)

    # --- back: course subjects ------------------------------------------------------------------
    st.markdown("**Back page: course subjects**")
    title = st.text_input(
        "Heading", value=preset.get("title", template.details.title), key=f"sc_title_{course}"
    )
    details = st.text_area(
        "Subjects and topics",
        value=preset.get("details", DEFAULT_DETAILS),
        height=300,
        key=f"sc_details_{course}",
        help="Write each subject on its own line, and each topic under it starting with a dash "
        "( - ). Topics are printed with a bullet, like your template.",
    )
    groups = C.parse_details(details)
    entry = {"subject": subject, "title": title, "details": details}
    if course.strip() and preset != entry:
        if st.button("Save for this course", icon=":material/save:", key="sc_save_details"):
            presets[course.strip()] = entry
            save_json(DETAILS_FILE, presets)
            st.success(f"Saved. Typing *{course.strip()}* as the course brings these back.")
    elif preset:
        st.caption("Using the details saved for this course.")


# --- adjustments (read first so the preview shows the current values) --------------------------
def remembered(key: str, setting: str) -> float:
    """A move or size from the widget if touched, else the saved setting."""
    return round(float(st.session_state.get(key, settings.get(setting, 0.0))), 1)


front_off = (remembered("sc_off_x", "offset_x"), remembered("sc_off_y", "offset_y"))
back_off = (remembered("sc_back_x", "back_offset_x"), remembered("sc_back_y", "back_offset_y"))
text_scale = float(st.session_state.get("sc_scale", settings.get("text_scale", 100))) / 100
LINES = [("name", "Name"), ("course", "Course"), ("date", "Date"), ("subject", "Subject")]
saved_lines = settings.get("field_offsets", {})


def line_offset(key: str) -> tuple[float, float]:
    """Extra move for one front line (right, down): the widgets if touched, else saved."""
    sx, sy = saved_lines.get(key, (0.0, 0.0))
    return (
        round(float(st.session_state.get(f"sc_{key}_x", sx)), 1),
        round(float(st.session_state.get(f"sc_{key}_y", sy)), 1),
    )


line_moves = {key: line_offset(key) for key, _ in LINES}

with right:
    st.markdown("**Preview**")
    index = 0
    if len(records) > 1:
        index = st.selectbox(
            "Certificate",
            range(len(records)),
            format_func=lambda i: f"{i + 1}. {records[i].name}",
            label_visibility="collapsed",
            key="sc_preview_pick",
        )
    dark = webui.dark_mode()
    family = font.family_name if font else "Bookman Old Style"
    front_tab, back_tab = st.tabs(["Front", "Back"])
    with front_tab:
        front_layout = (
            C.layout_record(template, records[index], font, front_off, text_scale, line_moves)
            if font and records
            else C.Layout()
        )
        svg = C.preview_svg(template, front_layout, family, guides=not records, dark=dark)
        st.markdown(f'<div class="cert-preview">{svg}</div>', unsafe_allow_html=True)
        if not records:
            st.caption("Enter a name to see it on the certificate.")
    with back_tab:
        back_layout = (
            C.layout_details(template, groups, font, title, back_off, text_scale)
            if font
            else C.Layout()
        )
        svg = C.preview_svg(template, back_layout, family, dark=dark)
        st.markdown(f'<div class="cert-preview">{svg}</div>', unsafe_allow_html=True)
        if back_layout.overflow:
            st.warning(
                f"{back_layout.overflow} line(s) do not fit on the page. Remove some topics or "
                "lower the text size."
            )

# --- print -----------------------------------------------------------------------------------
st.markdown("### Print")


@st.cache_data(show_spinner=False, ttl=300)
def installed_printers() -> list[dict]:
    """Printers Windows knows about (refreshed every 5 minutes)."""
    try:
        return [vars(p) for p in printing.list_printers()]
    except printing.PrintError:
        return []


@st.cache_data(show_spinner=False, max_entries=256)
def front_png(
    record: tuple, adjust: tuple, guides: bool, transparent: bool, font_key: str
) -> bytes:
    """300 DPI front page (cached: images are large to draw)."""
    offset, scale, per_line = adjust
    per_line = {k: (x, y) for k, x, y in per_line}
    lay = C.layout_record(template, C.Record(*record), font, offset, scale, per_line)
    lines = C.alignment_guides(template, offset, per_line) if guides else None
    return C.render_png(template, lay, font, guides=lines, transparent=transparent)


@st.cache_data(show_spinner=False, max_entries=32)
def back_png(groups: tuple, heading: str, adjust: tuple, transparent: bool, font_key: str) -> bytes:
    """300 DPI back page."""
    offset, scale = adjust
    lay = C.layout_details(
        template, [(h, list(t)) for h, t in groups], font, heading, offset, scale
    )
    return C.render_png(template, lay, font, transparent=transparent)


def browser_print(images: list[bytes], label: str) -> None:
    """Fallback when direct printing is unavailable: the browser's print window, exact size."""
    w, h = page_mm
    pages = "".join(
        f'<img src="data:image/png;base64,{base64.b64encode(img).decode()}" alt="">'
        for img in images
    )
    doc = (
        "<!doctype html><html><head><meta charset='utf-8'><title> </title><style>"
        f"@page{{size:{w:.2f}mm {h:.2f}mm;margin:0}}html,body{{margin:0;padding:0}}"
        f"img{{display:block;width:{w:.2f}mm;height:{h:.2f}mm;break-after:page}}"
        "img:last-child{break-after:auto}</style></head><body>" + pages + "</body></html>"
    )
    components.html(
        """
        <style>button{width:100%;font:600 14px -apple-system,'Segoe UI',Inter,sans-serif;color:#fff;
          background:linear-gradient(180deg,#3b9bff,#0a84ff);border:0;border-radius:999px;padding:10px;cursor:pointer}</style>
        <button id="b">__LABEL__</button>
        <script>
          const DOC = __DOC__;
          document.getElementById('b').onclick = () => {
            const f = document.createElement('iframe');
            f.style.cssText = 'position:fixed;width:0;height:0;border:0';
            f.srcdoc = DOC;
            f.onload = async () => {
              await Promise.all([...f.contentDocument.images].map(i => i.decode().catch(() => {})));
              f.contentWindow.print();
              setTimeout(() => f.remove(), 60000);
            };
            document.body.appendChild(f);
          };
        </script>
        """.replace("__LABEL__", label).replace("__DOC__", json.dumps(doc)),
        height=50,
    )


direct = font is not None and printing.available()
printers = installed_printers() if direct else []
printer_name = paper_name = tray = None
copies = 1
if printers:
    names = [p["name"] for p in printers]
    q1, q2, q3, q4 = st.columns([3, 2.8, 2, 1])
    saved_printer = settings.get("printer")
    printer_name = q1.selectbox(
        "Printer",
        names,
        index=names.index(saved_printer) if saved_printer in names else 0,
        key="sc_printer",
    )
    pinfo = next(p for p in printers if p["name"] == printer_name)
    paper_options = [CUSTOM] + [p["name"] for p in pinfo["papers"]]
    saved_paper = settings.get("paper", "A4")
    paper_name = q2.selectbox(
        "Paper size",
        paper_options,
        index=paper_options.index(saved_paper) if saved_paper in paper_options else 0,
        format_func=lambda v: (
            f"Template size {page_mm[0]:.1f} × {page_mm[1]:.1f} mm" if v == CUSTOM else v
        ),
        key=f"sc_paper_{printer_name}",
    )
    trays = [s["name"] for s in pinfo["sources"]] or ["Default"]
    manual = next((s["name"] for s in pinfo["sources"] if s.get("kind") == "Manual"), None)
    saved_tray = settings.get("tray")
    tray_default = saved_tray if saved_tray in trays else (manual or trays[0])
    tray = q3.selectbox(
        "Paper tray",
        trays,
        index=trays.index(tray_default),
        key=f"sc_tray_{printer_name}",
        help="Use the manual / bypass tray for certificate stock.",
    )
    copies = int(q4.number_input("Copies", 1, 20, 1, key="sc_copies"))

o1, o2, o3, o4, o5, o6 = st.columns(6)
moves = {
    "offset_x": o1.number_input(
        "Front: right (mm)", -30.0, 30.0, front_off[0], 0.1, format="%.1f", key="sc_off_x"
    ),
    "offset_y": o2.number_input(
        "Front: down (mm)", -30.0, 30.0, front_off[1], 0.1, format="%.1f", key="sc_off_y"
    ),
    "back_offset_x": o3.number_input(
        "Back: right (mm)", -30.0, 30.0, back_off[0], 0.1, format="%.1f", key="sc_back_x"
    ),
    "back_offset_y": o4.number_input(
        "Back: down (mm)", -30.0, 30.0, back_off[1], 0.1, format="%.1f", key="sc_back_y"
    ),
}
moves = {k: round(v, 1) for k, v in moves.items()}
scale_pct = int(
    o5.number_input(
        "Text size (%)",
        50,
        150,
        int(round(text_scale * 100)),
        1,
        key="sc_scale",
        help="100% = the size in your Photoshop templates.",
    )
)
st.caption("Move one line of the front only (Down: minus moves it up), on top of the moves above:")
for col, (key, label) in zip(st.columns(len(LINES)), LINES, strict=True):
    with col:
        st.markdown(f"**{label}**")
        a, b = st.columns(2)
        down = a.number_input(
            "Down (mm)", -30.0, 30.0, line_moves[key][1], 0.1, format="%.1f", key=f"sc_{key}_y"
        )
        rgt = b.number_input(
            "Right (mm)", -30.0, 30.0, line_moves[key][0], 0.1, format="%.1f", key=f"sc_{key}_x"
        )
        line_moves[key] = (round(rgt, 1), round(down, 1))
current = {**moves, "text_scale": scale_pct}
saved_pairs = {
    k: tuple(round(float(v), 1) for v in saved_lines.get(k, (0.0, 0.0))) for k, _ in LINES
}
if line_moves != saved_pairs or any(
    round(float(settings.get(k, 0)), 1) != v for k, v in current.items()
):
    with o6:
        st.write("")
        if st.button("Save these settings", icon=":material/save:", key="sc_save_settings"):
            settings.update(current, field_offsets={k: list(v) for k, v in line_moves.items()})
            save_json(SETTINGS_FILE, settings)
            st.success("Saved. They will be used every time.")
front_off = (moves["offset_x"], moves["offset_y"])
back_off = (moves["back_offset_x"], moves["back_offset_y"])
text_scale = scale_pct / 100

stamp = datetime.now().strftime("%Y%m%d-%H%M")
if font is not None:
    font_key = font.source or font.family_name
    group_key = tuple((h, tuple(t)) for h, t in groups)
    sample = records[0] if records else C.Record("A.K Imesh Samintha", course, awarded, subject)
    count = len(records)

    def fronts(recs: list[C.Record], transparent: bool, guides: bool = False) -> list[bytes]:
        return [
            front_png(
                (r.name, r.course, r.awarded, r.subject),
                (front_off, text_scale, tuple((k, x, y) for k, (x, y) in line_moves.items())),
                guides,
                transparent,
                font_key,
            )
            for r in recs
        ]

    def back(transparent: bool) -> bytes:
        return back_png(group_key, title, (back_off, text_scale), transparent, font_key)

    if printers:

        def send(pages: list[bytes], job: str, preview: bool = False) -> printing.PrintResult:
            return printing.print_pages(
                pages,
                printer_name,
                page_mm,
                paper=None if paper_name == CUSTOM else paper_name,
                custom_paper_mm=page_mm,
                source=None if tray == "Default" else tray,
                copies=copies,
                title=job,
                preview=preview,
            )

        st.caption(
            "Print the fronts first. Then put the printed sheets back in the tray, turned over "
            "the way your printer needs, and print the backs."
        )
        a1, a2, a3 = st.columns(3)
        jobs = [
            (
                a1.button(
                    f"Print fronts ({count})",
                    type="primary",
                    icon=":material/print:",
                    disabled=not records,
                    width="stretch",
                ),
                lambda: fronts(records, False),
                "Short course certificates (front)",
            ),
            (
                a2.button(
                    f"Print backs ({count})",
                    type="primary",
                    icon=":material/flip:",
                    disabled=not records or not groups,
                    width="stretch",
                ),
                lambda: [back(False)] * count,
                "Short course certificates (back)",
            ),
            (
                a3.button(
                    "Print alignment test",
                    icon=":material/straighten:",
                    width="stretch",
                    help="Prints the sample front with guide lines on plain paper.",
                ),
                lambda: fronts([sample], False, guides=True),
                "Short course alignment test",
            ),
        ]
        show_preview = st.toggle("Show exactly what the printer receives", key="sc_printer_preview")
        for clicked, make, job in jobs:
            if not clicked:
                continue
            try:
                with st.spinner(f"Sending to {printer_name}..."):
                    result = send(make(), job)
                settings.update(
                    printer=printer_name, paper=paper_name, tray=tray, last_course=course
                )
                save_json(SETTINGS_FILE, settings)
                st.success(
                    f"Sent {result.pages} page{'s' if result.pages != 1 else ''} to "
                    f"**{printer_name}** ({result.paper}, tray {result.source}). If nothing comes "
                    "out, look at the printer's screen: it may be asking you to load paper."
                )
            except printing.PrintError as exc:
                st.error(f"Printing failed: {exc}")
        if show_preview:
            from PIL import Image

            try:
                with st.spinner("Asking the printer driver for a preview..."):
                    result = send(fronts([sample], False) + [back(False)], "Preview", preview=True)
                cols = st.columns(3)
                for col, data, side in zip(
                    cols, result.preview_pages, ("Front", "Back"), strict=False
                ):
                    image = Image.open(BytesIO(data)).convert("RGB")
                    image.thumbnail((700, 900))
                    col.image(
                        image,
                        caption=f"{side} as the driver renders it on {result.paper}",
                        width="stretch",
                    )
            except printing.PrintError as exc:
                st.error(f"Preview failed: {exc}")
    else:
        if direct:
            st.warning(
                "No printers found. Add a printer in Windows Settings, then reload this page."
            )
        else:
            st.info(
                "Direct printing works when ExamLens runs on your Windows PC. Here you can print "
                "through the browser (turn off *Headers and footers* in its print window) or "
                "save the PDFs below."
            )
        if records and count <= 60:
            b1, b2 = st.columns(2)
            with b1:
                browser_print(fronts(records, True), f"Print fronts ({count}) in the browser")
            with b2:
                browser_print([back(True)] * count, f"Print backs ({count}) in the browser")

    with st.expander("Save as a file instead (PDF / PNG)"):
        if records:
            front_pages = [
                C.layout_record(template, r, font, front_off, text_scale, line_moves)
                for r in records
            ]
            back_page = C.layout_details(template, groups, font, title, back_off, text_scale)
            d1, d2, d3, d4, d5 = st.columns(5)
            d1.download_button(
                f"Fronts PDF ({count})",
                C.build_pdf(front_pages, font, page_mm, title="Short course certificates (front)"),
                f"short_course_fronts_{stamp}.pdf",
                "application/pdf",
                icon=":material/picture_as_pdf:",
                width="stretch",
            )
            d2.download_button(
                "Backs PDF",
                C.build_pdf(
                    [back_page] * count, font, page_mm, title="Short course certificates (back)"
                ),
                f"short_course_backs_{stamp}.pdf",
                "application/pdf",
                icon=":material/picture_as_pdf:",
                width="stretch",
            )
            d3.download_button(
                "Both sides PDF",
                C.build_pdf(
                    [page for f in front_pages for page in (f, back_page)],
                    font,
                    page_mm,
                    title="Short course certificates",
                ),
                f"short_course_both_sides_{stamp}.pdf",
                "application/pdf",
                icon=":material/picture_as_pdf:",
                width="stretch",
                help="Front, back, front, back… for printers that print both sides (duplex).",
            )
            chosen = records[min(index, count - 1)]
            d4.download_button(
                "Front PNG",
                fronts([chosen], True)[0],
                f"short_course_{'_'.join(chosen.name.split())[:40] or 'front'}.png",
                "image/png",
                icon=":material/image:",
                width="stretch",
                help="The certificate shown in the preview, 300 DPI, transparent background.",
            )
            d5.download_button(
                "Back PNG",
                back(True),
                "short_course_back.png",
                "image/png",
                icon=":material/image:",
                width="stretch",
            )
        else:
            st.caption("Enter a name above to create the files.")
        st.caption(
            "If you print a file yourself, choose *Actual size* / 100% and margins *None*. Never "
            "*Fit to page*: it moves the text."
        )
