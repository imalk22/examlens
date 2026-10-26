import base64
import json
from datetime import date, datetime
from io import BytesIO

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import webui

from examlens import certificates as C
from examlens import config
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


settings: dict = st.session_state.setdefault("cert_settings", load_settings())
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
                use_container_width=True,
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
                    use_container_width=True,
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
offset = (float(settings.get("offset_x", 0.0)), float(settings.get("offset_y", 0.0)))
layouts: list[C.Layout] = []
index = 0
stamp = datetime.now().strftime("%Y%m%d-%H%M")
with right:
    st.markdown("**Preview**")
    if font is not None and records:
        layouts = [C.layout_record(template, r, font) for r in records]
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
p1, p2, p3 = st.columns([3, 2, 2])
paper_label = p1.radio(
    "Paper size in the printer dialog",
    [
        f"Certificate size ({template.width_mm:.1f} × {template.height_mm:.1f} mm)",
        "A4 (certificate placed against the top-left guide)",
    ],
    key="cert_paper",
)
paper = "certificate" if paper_label.startswith("Certificate") else "a4"
off_x = p2.number_input(
    "Move right (mm)",
    -20.0,
    20.0,
    offset[0],
    0.1,
    format="%.1f",
    key="cert_off_x",
    help="Printer calibration: positive moves all text to the right, negative to the left.",
)
off_y = p3.number_input(
    "Move down (mm)",
    -20.0,
    20.0,
    offset[1],
    0.1,
    format="%.1f",
    key="cert_off_y",
    help="Printer calibration: positive moves all text down, negative moves it up.",
)
off_x, off_y = round(off_x, 1), round(off_y, 1)  # avoid float noise such as 2.8e-17
offset = (off_x, off_y)

PRINT_LIMIT = 60  # above this, printing images in the browser gets slow: use the PDF


def print_button(
    images: list[bytes], page_mm: tuple[float, float], label: str, primary: bool
) -> None:
    """A button that opens the browser's print window with these pages at their exact size."""
    w, h = page_mm
    pages = "".join(
        f'<img src="data:image/png;base64,{base64.b64encode(img).decode()}" alt="">'
        for img in images
    )
    doc = (
        "<!doctype html><html><head><meta charset='utf-8'><title>Certificates</title><style>"
        f"@page{{size:{w:.2f}mm {h:.2f}mm;margin:0}}"
        "html,body{margin:0;padding:0;background:transparent}"
        f"img{{display:block;width:{w:.2f}mm;height:{h:.2f}mm;break-after:page;page-break-after:always}}"
        "img:last-child{break-after:auto;page-break-after:auto}"
        "</style></head><body>" + pages + "</body></html>"
    )
    colour = (
        "color:#fff;background:linear-gradient(180deg,#3b9bff,#0a84ff);border:0;"
        "box-shadow:0 8px 18px rgba(10,132,255,.35)"
        if primary
        else "color:#0a84ff;background:#fff;border:1px solid rgba(60,60,67,.15)"
    )
    script = """
        <style>
          button{width:100%;font:600 14px -apple-system,BlinkMacSystemFont,'Segoe UI',Inter,sans-serif;
            border-radius:999px;padding:10px 14px;cursor:pointer;__COLOUR__;
            transition:transform .15s ease,box-shadow .2s ease}
          button:hover{transform:translateY(-1px)} button:active{transform:scale(.97)}
          button[disabled]{opacity:.6;cursor:progress}
        </style>
        <button id="b">__LABEL__</button>
        <script>
          const DOC = __DOC__;
          const LABEL = __LABEL_JS__;
          document.getElementById('b').onclick = () => {
            const btn = document.getElementById('b');
            btn.disabled = true;
            btn.textContent = 'Opening print window...';
            const frame = document.createElement('iframe');
            frame.style.cssText = 'position:fixed;right:0;bottom:0;width:0;height:0;border:0';
            frame.srcdoc = DOC;
            frame.onload = async () => {
              const imgs = [...frame.contentDocument.images];
              await Promise.all(imgs.map(i => (i.decode ? i.decode().catch(() => {}) : null)));
              frame.contentWindow.focus();
              frame.contentWindow.print();
              btn.disabled = false;
              btn.textContent = LABEL;
              setTimeout(() => frame.remove(), 60000);
            };
            document.body.appendChild(frame);
          };
        </script>
    """
    components.html(
        script.replace("__COLOUR__", colour)
        .replace("__LABEL_JS__", json.dumps(label))
        .replace("__LABEL__", label)
        .replace("__DOC__", json.dumps(doc)),
        height=50,
    )


if font is not None:

    @st.cache_data(show_spinner=False, max_entries=256)
    def png_for(record: tuple, offset: tuple, paper: str, layout_json: str, guides: bool) -> bytes:
        """300 DPI transparent PNG of one certificate (cached: images are large to draw)."""
        rec = C.Record(*record)
        lay = C.layout_record(template, rec, font, offset)
        lines = C.alignment_guides(template, offset) if guides else None
        return C.render_png(template, lay, font, paper=paper, guides=lines)

    layout_json = json.dumps(template.to_dict(), sort_keys=True) + (font.source or "")
    page_mm = C.page_size(template, paper)
    sample = records[0] if records else C.Record("A.K Imesh Samintha", default_course, date.today())
    sample_key = (sample.name, sample.course, sample.awarded)

    if records:
        pdf, _ = C.render_certificates(template, records, font, paper, offset)
        count = f"{len(records)} certificate{'s' if len(records) > 1 else ''}"
        r1, r2, r3, r4 = st.columns([2, 1.5, 1.5, 1.2])
        with r1:
            if len(records) <= PRINT_LIMIT:
                with st.spinner("Preparing pages..."):
                    images = [
                        png_for((r.name, r.course, r.awarded), offset, paper, layout_json, False)
                        for r in records
                    ]
                print_button(images, page_mm, f"Print {count}", True)
            else:
                st.caption(
                    f"{len(records)} certificates: download the PDF and print it from your PDF viewer."
                )
        r2.download_button(
            f"Download PDF ({count})",
            pdf,
            f"certificates_{stamp}.pdf",
            "application/pdf",
            icon=":material/picture_as_pdf:",
            use_container_width=True,
            on_click=lambda: (
                settings.__setitem__("last_course", records[0].course),
                save_settings(settings),
            ),
        )
        pick = min(index, len(records) - 1)
        chosen_rec = records[pick]
        slug = "_".join(chosen_rec.name.split())[:40] or "certificate"
        r3.download_button(
            "Transparent PNG",
            png_for(
                (chosen_rec.name, chosen_rec.course, chosen_rec.awarded),
                offset,
                paper,
                layout_json,
                False,
            ),
            f"certificate_{slug}.png",
            "image/png",
            icon=":material/image:",
            use_container_width=True,
            help="The certificate shown in the preview as a 300 DPI PNG with a transparent "
            "background, so only the text prints.",
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
        r4.download_button(
            "Register (CSV)",
            register.to_csv(index=False).encode("utf-8-sig"),
            f"certificate_register_{stamp}.csv",
            "text/csv",
            icon=":material/list_alt:",
            use_container_width=True,
            help="A list of what was printed, for your records.",
        )
        size_text = "A4" if paper == "a4" else f"{page_mm[0]:.1f} × {page_mm[1]:.1f} mm (custom)"
        st.caption(
            f"In the print window: **Paper size** {size_text} · **Margins** None · "
            "**Scale** Default / 100 · **Background graphics** off. Never choose *Fit to page*."
        )

    a1, a2, a3, a4 = st.columns([2, 1.5, 1.5, 1.2])
    with a1:
        print_button(
            [png_for(sample_key, offset, paper, layout_json, True)],
            page_mm,
            "Print alignment test",
            not records,
        )
    a2.download_button(
        "Alignment test (PDF)",
        C.render_alignment_test(template, sample, font, paper, offset),
        "certificate_alignment_test.pdf",
        "application/pdf",
        icon=":material/straighten:",
        use_container_width=True,
        help="Print on plain paper and hold it against a real certificate to check the position.",
    )
    a3.download_button(
        "Alignment test (PNG)",
        png_for(sample_key, offset, paper, layout_json, True),
        "certificate_alignment_test.png",
        "image/png",
        icon=":material/straighten:",
        use_container_width=True,
    )
    if 1 < len(records) <= 40:
        import zipfile

        buffer = BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for n, r in enumerate(records, start=1):
                image = png_for((r.name, r.course, r.awarded), offset, paper, layout_json, False)
                archive.writestr(f"{n:03d}_{'_'.join(r.name.split())[:40]}.png", image)
        a4.download_button(
            "All PNGs (ZIP)",
            buffer.getvalue(),
            f"certificates_{stamp}_images.zip",
            "application/zip",
            icon=":material/folder_zip:",
            use_container_width=True,
        )

if (off_x, off_y) != (
    round(settings.get("offset_x", 0.0), 1),
    round(settings.get("offset_y", 0.0), 1),
):
    if st.button("Save calibration for this printer", icon=":material/save:"):
        settings.update(offset_x=off_x, offset_y=off_y)
        save_settings(settings)
        st.success("Saved. These offsets will be used every time.")

with st.expander("How to print perfectly (read once)"):
    st.markdown(
        f"""
1. **First time only: calibrate.** Click *Print alignment test*, print it on plain paper, then put
   it on top of a real certificate and hold both up to a window. The red lines are where each
   line of text sits. If everything is, say, 1.5 mm too high, set *Move down* to 1.5 and click
   *Save calibration*. Also measure the 50 mm ruler: if it isn't exactly 50 mm, the printer is
   scaling the page (see step 3).
2. **Load the certificate** the way your printer feeds paper (usually face-up in the manual /
   bypass tray, top edge first). Do one test sheet before a batch.
3. **Click Print.** The print window opens with a preview of every certificate. Check:
   *Destination* = your printer · *Paper size* = the size you picked above (for certificate
   size, create a custom paper size of {template.width_mm:.1f} × {template.height_mm:.1f} mm once
   in the printer settings) · *Margins* = None · *Scale* = Default or 100 · *Background
   graphics* off. Never choose *Fit to page* or *Fill page*: they stretch the text out of place.
   Avoid printing the PNG from Windows Photos for the same reason (its default is *Fill page*).
4. **Batches** print one certificate per page, in the order shown. Download the *Register* to
   keep a record of who was printed. For more than {PRINT_LIMIT} certificates use the PDF.
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
        use_container_width=True,
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
        use_container_width=True,
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
