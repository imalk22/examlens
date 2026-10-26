import base64
import json
from datetime import date, datetime
from io import BytesIO

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import webui

from examlens import certificates as C
from examlens import config, printing
from examlens.ingestion import apply_results

webui.header(
    "Certificates",
    "Print names, courses and dates onto your pre-printed certificates, exactly where your "
    "Photoshop template places them.",
)

SETTINGS_FILE = webui.ROOT / "data" / "private" / "certificate_settings.json"  # git-ignored
TEMPLATE_FILE = webui.ASSETS / "certificate_template.json"


def load_settings() -> dict:
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_settings(values: dict) -> None:
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(values, indent=2), encoding="utf-8")


@st.cache_resource(show_spinner=False)
def system_font() -> C.TrueTypeFont | None:
    return C.find_font()


# Built-in defaults from the template (positions agreed for this certificate), overridden by
# anything saved on this PC.
TEMPLATE_DEFAULTS = json.loads(TEMPLATE_FILE.read_text(encoding="utf-8")).get("print_defaults", {})
settings: dict = st.session_state.setdefault(
    "cert_settings", {**TEMPLATE_DEFAULTS, **load_settings()}
)
template: C.Template = st.session_state.get("cert_template") or C.load_template(TEMPLATE_FILE)
font: C.TrueTypeFont | None = st.session_state.get("cert_font") or system_font()
default_course = settings.get("last_course", "Business Tax Associate (BTA)")

if font is None:
    st.error(
        "No certificate font found. Install **Bookman Old Style** (it ships with Windows and "
        "Microsoft Office) or upload a .ttf font under *Template & font* below."
    )

# --- who is it for ---------------------------------------------------------------------------
left, right = st.columns([5, 4], gap="large")
records: list[C.Record] = []
with left:
    mode = st.radio(
        "Who are the certificates for?",
        ["One person", "A list of names", "From exam results"],
        horizontal=True,
        key="cert_mode",
    )
    if mode == "One person":
        name = st.text_input("Name", placeholder="e.g. A.K Imesh Samintha", key="cert_name")
        c1, c2 = st.columns([3, 2])
        course = c1.text_input("Course / award", value=default_course, key="cert_course")
        awarded = c2.date_input("Date", value=date.today(), format="DD/MM/YYYY", key="cert_date")
        if name.strip():
            records = [C.Record(name, course, awarded)]

    elif mode == "A list of names":
        c1, c2 = st.columns([3, 2])
        course = c1.text_input(
            "Course / award for everyone", value=default_course, key="cert_list_course"
        )
        awarded = c2.date_input(
            "Date for everyone", value=date.today(), format="DD/MM/YYYY", key="cert_list_date"
        )
        upload = st.file_uploader(
            "Upload a list (Excel or CSV with a Name column; Course and Date columns are optional)",
            type=["xlsx", "xls", "csv"],
            key="cert_list_file",
        )
        if upload is not None:
            try:
                raw = (
                    pd.read_csv(upload)
                    if upload.name.lower().endswith(".csv")
                    else pd.read_excel(upload)
                )
                records = C.records_from_table(raw, course, awarded)
                st.caption(f"{len(records)} names read from {upload.name}.")
            except Exception:
                st.error("Could not read that file. Make sure it has a column of names.")
        else:
            st.caption(
                "Or type / paste names below (one per row). Course and date can be left blank."
            )
            table = st.data_editor(
                pd.DataFrame({"Name": [""] * 5, "Course": [""] * 5, "Date": [""] * 5}),
                num_rows="dynamic",
                width="stretch",
                hide_index=True,
                key="cert_list_table",
            )
            records = C.records_from_table(table, course, awarded)

    else:
        data = st.session_state.get("data")
        if data is None:
            st.info("Load your exam results on the **Upload & Data Health** page first.")
        else:
            data = apply_results(data, float(st.session_state.get("pass_mark", config.PASS_MARK)))
            levels = [lvl for lvl in sorted(data["level"].dropna().unique())]
            c1, c2 = st.columns([1, 1])
            level = c1.selectbox("Level completed", levels, key="cert_level")
            rule = c2.selectbox(
                "Who qualifies",
                ["Passed every subject of the level", "Nothing outstanding (counts exemptions)"],
                key="cert_rule",
                help="Exempted or previously-completed subjects are not exam attempts. The second "
                "option includes students who passed everything they sat at this level.",
            )
            done = C.level_completers(data, level, strict=rule.startswith("Passed"))
            sessions = sorted(done["completed_in"].unique()) if len(done) else []
            picked = st.multiselect(
                "Completed in session", sessions, default=sessions[-1:], key="cert_sessions"
            )
            if picked:
                done = done[done["completed_in"].isin(picked)]
            courses = settings.get("courses", {})
            c3, c4 = st.columns([3, 2])
            course = c3.text_input(
                "Course / award",
                value=courses.get(level, default_course),
                key=f"cert_course_{level}",
            )
            awarded = c4.date_input(
                "Date", value=date.today(), format="DD/MM/YYYY", key="cert_results_date"
            )
            if len(done):
                table = done[["student_name", "student_id", "completed_in", "subjects"]].copy()
                table.insert(0, "Print", True)
                edited = st.data_editor(
                    table,
                    hide_index=True,
                    width="stretch",
                    height=min(38 + 35 * len(table), 330),
                    disabled=["student_name", "student_id", "completed_in", "subjects"],
                    column_config={
                        "Print": st.column_config.CheckboxColumn("Print", width="small"),
                        "student_name": "Name",
                        "student_id": "Student No",
                        "completed_in": "Completed",
                        "subjects": "Passed",
                    },
                    key=f"cert_pick_{level}_{rule[:6]}",
                )
                chosen = edited[edited["Print"]]
                records = [C.Record(n, course, awarded) for n in chosen["student_name"]]
                st.caption(f"{len(chosen)} of {len(table)} students selected.")
                if course != courses.get(level):
                    settings.setdefault("courses", {})[level] = course
            else:
                st.warning(
                    "No students have completed this level with the current rule and sessions."
                )

# --- preview ---------------------------------------------------------------------------------
offset = (
    round(float(st.session_state.get("cert_off_x", settings.get("offset_x", 0.0))), 1),
    round(float(st.session_state.get("cert_off_y", settings.get("offset_y", 0.0))), 1),
)
text_scale = float(st.session_state.get("cert_scale", settings.get("text_scale", 100))) / 100
LINES = [("name", "Name"), ("course", "Course"), ("date", "Date")]
saved_lines = settings.get("field_offsets", {})


def line_offset(key: str) -> tuple[float, float]:
    """Extra move for one line: from the widgets if touched, else the saved setting."""
    sx, sy = saved_lines.get(key, (0.0, 0.0))
    return (
        round(float(st.session_state.get(f"cert_{key}_x", sx)), 1),
        round(float(st.session_state.get(f"cert_{key}_y", sy)), 1),
    )


field_offsets = {key: line_offset(key) for key, _ in LINES}
layouts: list[C.Layout] = []
index = 0
stamp = datetime.now().strftime("%Y%m%d-%H%M")
with right:
    st.markdown("**Preview**")
    if font is not None and records:
        layouts = [
            C.layout_record(template, r, font, offset, text_scale, field_offsets) for r in records
        ]
        c1, c2 = st.columns([3, 2])
        index = (
            c1.selectbox(
                "Certificate",
                range(len(records)),
                format_func=lambda i: f"{i + 1}. {records[i].name}",
                label_visibility="collapsed",
                key="cert_preview_pick",
            )
            if len(records) > 1
            else 0
        )
        guides = c2.toggle("Guide lines", value=False, key="cert_guides")
        svg = C.preview_svg(
            template, layouts[index], font.family_name, guides=guides, dark=webui.dark_mode()
        )
        st.markdown(f'<div class="cert-preview">{svg}</div>', unsafe_allow_html=True)
        shrunk = [records[i].name for i, lay in enumerate(layouts) if "name" in lay.shrunk]
        if shrunk:
            st.caption(
                f"{len(shrunk)} long name(s) were reduced slightly to fit the line: "
                + ", ".join(shrunk[:5])
                + ("…" if len(shrunk) > 5 else "")
            )
    else:
        blank = C.Layout()
        st.markdown(
            f'<div class="cert-preview">{C.preview_svg(template, blank, "Bookman Old Style", guides=True, dark=webui.dark_mode())}</div>',
            unsafe_allow_html=True,
        )
        st.caption("Enter a name to see it on the certificate.")

# --- print -----------------------------------------------------------------------------------
st.markdown("### Print")

CUSTOM = "custom"
PRINT_LIMIT = 60  # browser printing (non-Windows fallback) gets slow above this
cert_mm = (template.width_mm, template.height_mm)


@st.cache_data(show_spinner=False, ttl=300)
def installed_printers() -> list[dict]:
    """Printers Windows knows about (refreshed every 5 minutes)."""
    try:
        return [vars(p) for p in printing.list_printers()]
    except printing.PrintError:
        return []


@st.cache_data(show_spinner=False, max_entries=256)
def png_for(
    record: tuple, offset: tuple, paper: str, layout_json: str, guides: bool, transparent: bool
) -> bytes:
    """300 DPI PNG of one certificate (cached: images are large to draw)."""
    per_line = {k: (x, y) for k, x, y in offset[3]}
    lay = C.layout_record(template, C.Record(*record), font, offset[:2], offset[2], per_line)
    lines = C.alignment_guides(template, offset[:2], per_line) if guides else None
    return C.render_png(template, lay, font, paper=paper, guides=lines, transparent=transparent)


def print_button(images: list[bytes], page_mm: tuple[float, float], label: str) -> None:
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
        key="cert_printer",
    )
    pinfo = next(p for p in printers if p["name"] == printer_name)
    paper_options = [CUSTOM] + [p["name"] for p in pinfo["papers"]]

    def paper_label(value: str) -> str:
        if value == CUSTOM:
            return f"Certificate {cert_mm[0]:.1f} × {cert_mm[1]:.1f} mm (exact size)"
        return value

    saved_paper = settings.get("paper", CUSTOM)
    paper_name = q2.selectbox(
        "Paper size",
        paper_options,
        index=paper_options.index(saved_paper) if saved_paper in paper_options else 0,
        format_func=paper_label,
        key=f"cert_paper_{printer_name}",
        help="The certificate size is sent to the printer as a custom size. If your printer "
        "only takes standard sizes, pick A4 and feed the certificate against the top-left guide.",
    )
    trays = [s["name"] for s in pinfo["sources"]] or ["Default"]
    manual = next((s["name"] for s in pinfo["sources"] if s.get("kind") == "Manual"), None)
    saved_tray = settings.get("tray")
    tray_default = saved_tray if saved_tray in trays else (manual or trays[0])
    tray = q3.selectbox(
        "Paper tray",
        trays,
        index=trays.index(tray_default),
        key=f"cert_tray_{printer_name}",
        help="Use the manual / bypass tray for certificate stock.",
    )
    copies = int(q4.number_input("Copies", 1, 20, 1, key="cert_copies"))

    @st.cache_data(show_spinner=False, ttl=20)
    def printer_says(host: str) -> tuple[str, bool, str] | None:
        """The printer's own status (cached briefly so the page stays fast)."""
        status = printing.device_status(host)
        return (status.text, status.ok, status.url) if status else None

    said = printer_says(pinfo.get("host", ""))
    if said and not said[1]:
        st.warning(
            f"**The printer reports a problem:** {said[0]} It will accept jobs but not print "
            "them until this is cleared. Check the printer's touch screen (paper jam, open door, "
            f"toner, or a service code), or open its [status page]({said[2]}).",
        )
    elif said:
        st.caption(f"Printer status: {said[0]}")

o1, o2, o4, o3 = st.columns([2, 2, 2, 2])
off_x = o1.number_input(
    "Move right (mm)",
    -30.0,
    30.0,
    offset[0],
    0.1,
    format="%.1f",
    key="cert_off_x",
    help="Printer calibration: positive moves all text right, negative moves it left.",
)
off_y = o2.number_input(
    "Move down (mm)",
    -30.0,
    30.0,
    offset[1],
    0.1,
    format="%.1f",
    key="cert_off_y",
    help="Printer calibration: positive moves all text down, negative moves it up.",
)
scale_pct = o4.number_input(
    "Text size (%)",
    50,
    150,
    int(round(text_scale * 100)),
    1,
    key="cert_scale",
    help="100% = the size in your Photoshop template. Lines stay centred where they are.",
)
st.caption("Move one line only (on top of the moves above):")
line_cols = st.columns(len(LINES))
for col, (key, label) in zip(line_cols, LINES, strict=True):
    with col:
        st.markdown(f"**{label}**")
        a, b = st.columns(2)
        down = a.number_input(
            "Down (mm)", -30.0, 30.0, field_offsets[key][1], 0.1, format="%.1f", key=f"cert_{key}_y"
        )
        rgt = b.number_input(
            "Right (mm)",
            -30.0,
            30.0,
            field_offsets[key][0],
            0.1,
            format="%.1f",
            key=f"cert_{key}_x",
        )
        field_offsets[key] = (round(rgt, 1), round(down, 1))

off_x, off_y = round(off_x, 1), round(off_y, 1)  # avoid float noise such as 2.8e-17
offset = (off_x, off_y)
text_scale = scale_pct / 100
adjust = (off_x, off_y, text_scale, tuple((k, x, y) for k, (x, y) in field_offsets.items()))
saved_pairs = {
    k: tuple(round(float(v), 1) for v in saved_lines.get(k, (0.0, 0.0))) for k, _ in LINES
}
if (off_x, off_y, scale_pct, field_offsets) != (
    round(settings.get("offset_x", 0.0), 1),
    round(settings.get("offset_y", 0.0), 1),
    int(settings.get("text_scale", 100)),
    saved_pairs,
):
    with o3:
        st.write("")
        if st.button("Save these settings", icon=":material/save:"):
            settings.update(
                offset_x=off_x,
                offset_y=off_y,
                text_scale=scale_pct,
                field_offsets={k: list(v) for k, v in field_offsets.items()},
            )
            save_settings(settings)
            st.success("Saved. They will be used every time.")

stamp = datetime.now().strftime("%Y%m%d-%H%M")
if font is not None:
    layout_json = json.dumps(template.to_dict(), sort_keys=True) + (font.source or "")
    sample = records[0] if records else C.Record("A.K Imesh Samintha", default_course, date.today())
    sample_key = (sample.name, sample.course, sample.awarded)
    count = f"{len(records)} certificate{'s' if len(records) != 1 else ''}"

    if printers:
        # Pages for the printer have a WHITE background: Windows printing ignores transparency.
        def pages_for(recs: list[C.Record], guides: bool = False) -> list[bytes]:
            return [
                png_for(
                    (r.name, r.course, r.awarded), adjust, "certificate", layout_json, guides, False
                )
                for r in recs
            ]

        def send(pages: list[bytes], title: str, preview: bool = False) -> printing.PrintResult:
            return printing.print_pages(
                pages,
                printer_name,
                cert_mm,
                paper=None if paper_name == CUSTOM else paper_name,
                custom_paper_mm=cert_mm,
                source=None if tray == "Default" else tray,
                copies=copies,
                title=title,
                preview=preview,
            )

        if records:
            st.markdown(
                f"**{count}** → {printer_name} · {paper_label(paper_name)} · tray {tray} · "
                f"{copies} cop{'y' if copies == 1 else 'ies'} each · only the name, course and date are printed"
            )
        a1, a2, a3 = st.columns([2, 2, 2.4])
        print_now = a1.button(
            f"Print {count}" if records else "Print",
            type="primary",
            icon=":material/print:",
            disabled=not records,
            width="stretch",
        )
        print_test = a2.button(
            "Print alignment test",
            icon=":material/straighten:",
            width="stretch",
            help="Prints the sample text with guide lines on plain paper, for calibration.",
        )
        show_preview = a3.toggle(
            "Show exactly what the printer receives", key="cert_printer_preview"
        )

        for clicked, recs, guides, title in (
            (print_now, records, False, "Certificates"),
            (print_test, [sample], True, "Certificate alignment test"),
        ):
            if not clicked:
                continue
            try:
                with st.spinner(
                    f"Sending {len(recs)} page{'s' if len(recs) != 1 else ''} to {printer_name}..."
                ):
                    result = send(pages_for(recs, guides), title)
                settings.update(printer=printer_name, paper=paper_name, tray=tray)
                if not guides and records:
                    settings["last_course"] = records[0].course
                save_settings(settings)
                st.success(
                    f"Sent {result.pages} page{'s' if result.pages != 1 else ''} to **{printer_name}** "
                    f"({result.paper}, tray {result.source}). Only the name, course and date are "
                    "printed. If nothing comes out, look at the printer's screen: it may be asking "
                    "you to load paper or confirm the paper size for the manual tray."
                )
            except printing.PrintError as exc:
                st.error(f"Printing failed: {exc}")

        if show_preview:
            preview_recs = records[:3] if records else [sample]
            try:
                with st.spinner("Asking the printer driver for a preview..."):
                    result = send(pages_for(preview_recs), "Preview", preview=True)
                cols = st.columns(3)  # thumbnail size, like a print dialog
                for n, (col, data) in enumerate(
                    zip(cols, result.preview_pages, strict=False), start=1
                ):
                    from PIL import Image

                    image = Image.open(BytesIO(data)).convert("RGB")
                    image.thumbnail((700, 900))
                    col.image(
                        image,
                        caption=f"Page {n} as the driver renders it on {result.paper} "
                        f"({result.paper_mm[0]:.1f} × {result.paper_mm[1]:.1f} mm)",
                        width="stretch",
                    )
                if len(records) > 3:
                    st.caption(f"Showing the first 3 of {len(records)} pages.")
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
                "save the PDF below."
            )
        if records and len(records) <= PRINT_LIMIT:
            images = [
                png_for(
                    (r.name, r.course, r.awarded), adjust, "certificate", layout_json, False, True
                )
                for r in records
            ]
            print_button(images, cert_mm, f"Print {count} in the browser")

    with st.expander("Save as a file instead (PDF / PNG)"):
        paper_label_dl = st.radio(
            "Page size of the files",
            [
                f"Certificate size ({cert_mm[0]:.1f} × {cert_mm[1]:.1f} mm)",
                "A4 (certificate at the top-left)",
            ],
            horizontal=True,
            key="cert_paper",
        )
        paper = "certificate" if paper_label_dl.startswith("Certificate") else "a4"
        d1, d2, d3, d4 = st.columns(4)
        if records:
            pdf, _ = C.render_certificates(
                template, records, font, paper, offset, text_scale, field_offsets
            )
            d1.download_button(
                f"PDF ({count})",
                pdf,
                f"certificates_{stamp}.pdf",
                "application/pdf",
                icon=":material/picture_as_pdf:",
                width="stretch",
            )
            pick = min(index, len(records) - 1)
            chosen = records[pick]
            d2.download_button(
                "Transparent PNG",
                png_for(
                    (chosen.name, chosen.course, chosen.awarded),
                    adjust,
                    paper,
                    layout_json,
                    False,
                    True,
                ),
                f"certificate_{'_'.join(chosen.name.split())[:40] or 'certificate'}.png",
                "image/png",
                icon=":material/image:",
                width="stretch",
                help="The certificate shown in the preview, 300 DPI, transparent background.",
            )
            if 1 < len(records) <= 40:
                import zipfile

                buffer = BytesIO()
                with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
                    for n, r in enumerate(records, start=1):
                        archive.writestr(
                            f"{n:03d}_{'_'.join(r.name.split())[:40]}.png",
                            png_for(
                                (r.name, r.course, r.awarded),
                                adjust,
                                paper,
                                layout_json,
                                False,
                                True,
                            ),
                        )
                d3.download_button(
                    "All PNGs (ZIP)",
                    buffer.getvalue(),
                    f"certificates_{stamp}_images.zip",
                    "application/zip",
                    icon=":material/folder_zip:",
                    width="stretch",
                )
            register = pd.DataFrame(
                {
                    "No": range(1, len(records) + 1),
                    "Name": [r.name for r in records],
                    "Course": [r.course for r in records],
                    "Date": [r.awarded.isoformat() for r in records],
                    "Printed": datetime.now().isoformat(timespec="minutes"),
                }
            )
            d4.download_button(
                "Register (CSV)",
                register.to_csv(index=False).encode("utf-8-sig"),
                f"certificate_register_{stamp}.csv",
                "text/csv",
                icon=":material/list_alt:",
                width="stretch",
                help="A list of who was printed, for your records.",
            )
        e1, e2, _, _ = st.columns(4)
        e1.download_button(
            "Alignment test (PDF)",
            C.render_alignment_test(
                template, sample, font, paper, offset, text_scale, field_offsets
            ),
            "certificate_alignment_test.pdf",
            "application/pdf",
            icon=":material/straighten:",
            width="stretch",
        )
        e2.download_button(
            "Alignment test (PNG)",
            png_for(sample_key, adjust, paper, layout_json, True, True),
            "certificate_alignment_test.png",
            "image/png",
            icon=":material/straighten:",
            width="stretch",
        )
        st.caption(
            "If you print a file yourself, choose *Actual size* / 100% and margins *None*. Never "
            "*Fit to page* or *Fill page* (Windows Photos' default): they move the text."
        )

with st.expander("How to print perfectly (read once)"):
    st.markdown(
        f"""
1. **First time only: calibrate.** Put plain paper in the tray and click *Print alignment test*.
   Lay the sheet on a real certificate and hold both up to a window: the red lines are where each
   line of text sits. If everything is, say, 1.5 mm too high, set *Move down* to 1.5 and click
   *Save calibration*. Measure the 50 mm ruler too: it should be exactly 50 mm.
2. **Load the certificates** in the tray you chose (usually the manual / bypass tray), the way
   your printer feeds paper. Do one sheet first before a batch.
3. **Click Print.** ExamLens sends the pages straight to the printer: no print window, no
   browser headers or footers, nothing but the name, course and date. Turn on *Show exactly what
   the printer receives* first if you want to double-check.
4. **Paper size:** *Certificate {cert_mm[0]:.1f} × {cert_mm[1]:.1f} mm* sends the exact size. If the
   printer rejects it, choose *A4* and feed the certificate against the top-left guide: the text
   is measured from the top-left corner either way.
5. **Batches** print one certificate per page, in the order shown. Keep the *Register* (under
   *Save as a file instead*) as a record of who was printed.
        """
    )

# --- template & font -------------------------------------------------------------------------
with st.expander("Template & font (advanced)"):
    st.caption(
        f"Template: **{template.name}** · page {template.width_mm:.2f} × {template.height_mm:.2f} mm · "
        f"font: **{font.family_name if font else 'none'}**"
        + (f" ({font.source})" if font and font.source else "")
    )
    rows = pd.DataFrame(
        [
            {
                "field": key,
                "x_mm": f.x_mm,
                "baseline_mm": f.baseline_mm,
                "size_pt": f.size_pt,
                "tracking": f.tracking,
                "max_width_mm": f.max_width_mm,
            }
            for key, f in template.fields.items()
        ]
    )
    edited = st.data_editor(
        rows,
        hide_index=True,
        disabled=["field"],
        width="stretch",
        key="cert_tpl_editor",
        column_config={
            "x_mm": st.column_config.NumberColumn("Centre x (mm)", format="%.2f", step=0.1),
            "baseline_mm": st.column_config.NumberColumn(
                "Baseline y (mm)", format="%.2f", step=0.1
            ),
            "size_pt": st.column_config.NumberColumn("Size (pt)", format="%.2f", step=0.1),
            "tracking": st.column_config.NumberColumn("Tracking", step=5),
            "max_width_mm": st.column_config.NumberColumn("Max width (mm)", format="%.0f", step=1),
        },
    )
    if not edited.equals(rows):
        for row in edited.itertuples():
            spec = template.fields[row.field]
            spec.x_mm, spec.baseline_mm, spec.size_pt = row.x_mm, row.baseline_mm, row.size_pt
            spec.tracking, spec.max_width_mm = row.tracking, row.max_width_mm
        st.session_state["cert_template"] = template
        st.rerun()
    t1, t2, t3 = st.columns(3)
    t1.download_button(
        "Download template (JSON)",
        json.dumps(template.to_dict(), indent=2),
        "certificate_template.json",
        "application/json",
        width="stretch",
    )
    new_tpl = t2.file_uploader("Use another template (JSON)", type=["json"], key="cert_tpl_upload")
    if new_tpl is not None:
        try:
            st.session_state["cert_template"] = C.Template.from_dict(json.loads(new_tpl.getvalue()))
        except (ValueError, KeyError):
            st.error("That is not a certificate template file.")
    new_font = t3.file_uploader("Use another font (.ttf)", type=["ttf"], key="cert_font_upload")
    if new_font is not None:
        try:
            uploaded = C.TrueTypeFont(new_font.getvalue(), new_font.name)
            if not uploaded.embeddable:
                st.error("This font's licence does not allow embedding it in a PDF.")
            else:
                st.session_state["cert_font"] = uploaded
        except C.FontError as exc:
            st.error(str(exc))
    if st.session_state.get("cert_template") is not None and st.button(
        "Reset to the original template"
    ):
        st.session_state.pop("cert_template", None)
        st.rerun()
    st.caption(
        "Made a new certificate design? Run `python scripts/psd_to_template.py your.psd` "
        "(needs `pip install psd-tools`) and upload the JSON it writes."
    )
