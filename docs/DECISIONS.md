# Decisions

Ambiguities in `PROJECT_SPEC.md` and the simplest reasonable choice made for each.

## Phase 1

- **Subjects per programme:** 15 subjects = 5 per programme (2 Ã— Level 1, 2 Ã— Level 2, 1 Ã— Level 3). Hard subjects: `TX204`, `AC202`, `BM202`.
- **Progression:** a student sits Level 1 subjects in their intake's first session, Level 2 in the next, Level 3 after that. Failed or absent subjects are re-sat 1-2 sessions later (some students give up, which produces "never passed" cases).
- **Extra sample file:** `results_2025_dec_level2_3.xlsx` carries the Level 2-3 rows of 2025-Dec, because `level1_marksheet_2025_dec.xlsx` (wide format) covers Level 1 only.
- **Injected data issues:** `data/sample/MANIFEST.json` records the deliberate issues (3 duplicates, 28 `AB` entries (counts are in the manifest), 1 name conflict, 1 invalid mark of 150) so Phase 2 tests can assert exact counts.
- **Reproducibility:** `.xlsx` output is byte-identical for a given seed. The generator fixes zip timestamps and workbook metadata after writing.
- **Extra files beyond Section 2/3:** `pyproject.toml` (ruff and pytest config), `.gitattributes` (LF line endings, `.xlsx` binary), `xlrd` in `requirements.txt` (required by pandas to read legacy `.xls`).

## Phase 2-4

- **Result values:** Medical attempts get `result = "Absent"`; withheld rows and out-of-range marks get an empty `result`, so they are excluded from pass/fail counts. Only `status == "Absent"` earns absence risk points (medical is excused).
- **Wide-format session:** taken from the filename, or asked for in the UI (`MissingSessionError`).
- **Streamlit helpers:** `webui.py` sits at the repo root (next to `app.py`) so `src/examlens/` stays free of Streamlit imports. It adds `src/` to `sys.path`, so `streamlit run app.py` works without `pip install -e .`.
- **Extra module:** `src/examlens/insights.py` holds the template-based Key insights text.
- **Pass mark / risk settings:** results are recomputed from `marks` on every page load using the sidebar's pass mark, so ingestion output stays untouched.
- **Leaderboard colouring:** uses Streamlit progress columns instead of pandas Styler gradients, which would need matplotlib (not in the approved dependency list).
- **Re-sit realism:** repeat attempts get a +12 mark bonus (`RESIT_BONUS`) so the pass-rate trend eases from ~87% to ~68% instead of collapsing, and about 9% of students land in High risk.

## Design refresh

- **iOS look:** styling lives in `assets/style.css` (system font stack with Inter fallback, grouped-grey background, white rounded cards, blue accent #007AFF). Charts share the same palette and font.
- **Navigation and icons:** `app.py` now uses `st.navigation` with Material Symbols icons, so page files dropped their emoji prefixes and pages no longer call `set_page_config`. `pages/home.py` is the new Home page.
- **No emoji:** risk levels and health checks use coloured pills and dots instead.

- **Apple redesign (round 2):** Settings-style sidebar with coloured icon tiles, Apple system colours throughout, borderless white cards on #F2F2F7, capsule buttons, segmented-control radios, Apple Health-style coloured KPI labels and chart palettes. SF Pro and SF Symbols are Apple-licensed, so the app uses the system font stack (SF Pro on Apple devices, Inter elsewhere) and thin-stroke Material Symbols.

- **Glass dashboard (round 3):** colour-mesh background with frosted-glass cards (blur, inner highlight, layered shadows, hover lift), KPI cards with sparklines, denser multi-column layouts, tabs as segmented controls. The separate Home page was removed: Overview is the default page and shows a welcome card until data is loaded.

- **Round 4 (dark, 3D, widgets):** dark mode is a sidebar toggle (`assets/dark.css` layered over `style.css`; canvas tables are colour-inverted in dark). A tiny script injected via `components.html` (same-origin iframe) adds mouse-driven 3D tilt, a specular highlight and count-up numbers; entrance animations, a top loading bar (keyed to `data-test-script-state`), activity rings, bar and people-list widgets are CSS/SVG. Subject and repeat tables are custom HTML tables for crisp styling; tables that need row selection stay `st.dataframe`.

- **Round 5 (rebuild):** pages are now drawn by a purpose-built front end (`assets/canvas.css` + `assets/canvas.js`) rendered through `components.html` and sized to its content, fed by JSON view models from `src/examlens/viewmodel.py` (pure Python, tested). Charts are hand-written SVG (area, bars, donut, scatter, rings, sparklines) with entrance animations and tooltips, so there is no chart-library dependency. Streamlit keeps navigation, filters, uploads, downloads and the student search. Per-student profiles for the At-Risk split view are embedded in the page (~0.5 MB) so selecting a row is instant. Avoid PowerShell `Set-Content -Encoding utf8` on CSS: it adds a BOM that breaks the first rule.

- **Messy workbooks:** `read_raw` now scans the first 40 rows of every sheet for the header row (known column names score highest), picks the best sheet, drops empty rows/columns, and detects the CSV delimiter from the data lines, so title rows, cover sheets and semicolon CSVs load without manual fixes.

- **CIT result sheets:** `src/examlens/cit.py` parses the institute's wide marksheets (Application, Analyst 1/2, Advisory). It finds the header block and student columns, maps subject headers (codes like TX 211 or names/abbreviations) to a per-level catalogue, picks the final marks column (Final adjusted > Total marks > Marks, ignoring parts and council columns) and the status column, drops Exempted / Previously Completed / Skipped cells (not attempts), reads the exam month from the filename and the batch from the title. Students are keyed by Student Reg No so every file for the same person merges into one profile with chronological attempt numbers; sheets that list only an index number use it as the ID with a placeholder name. A pass mark of 50 agrees with the official Pass/Fail status on 99.2% of 2,017 real rows. Tests use synthetic sheets only: real student data is never committed.

## Certificate printing

- **Text-only PDF onto pre-printed stock:** `src/examlens/certificates.py` writes a PDF the exact size of the certificate (209.97 x 274.49 mm, from the 2480 x 3242 px / 300 DPI PSD) containing only the name, course and date. No PDF library: a small PDF 1.4 writer embeds the TrueType font (WinAnsi), so there is no new dependency. `/PrintScaling /None` asks viewers to print at 100%.
- **Layout from Photoshop:** `scripts/psd_to_template.py` (optional `psd-tools`) reads each text layer's anchor, baseline, size (font size x transform scale), tracking, alignment, all-caps and faux-bold flags into `assets/certificate_template.json`. Layers map top-to-bottom to name, course, date.
- **Faux bold:** the PSD uses Photoshop's Faux Bold. It is emulated with text render mode 2 (fill + outline) plus extra advance; the amounts (0.026 em advance, 0.035 em outline) were fitted to the PSD render. Name and course match the Photoshop pixels to within 0.06 mm.
- **Date:** day + superscript ordinal (ST/ND/RD/TH, 58.3% size raised 33.3%) + month + year in caps. The PSD sample reads "2O TH" (letter O and a space); the app prints "20TH".
- **Font:** Bookman Old Style is licensed with Windows/Office, so it is never committed; it is loaded from the system font folder (fallbacks: TeX Gyre Bonum, Georgia, Times, DejaVu Serif) or uploaded in the app. Fonts flagged "restricted licence" are refused.
- **Calibration:** per-printer X/Y offsets are saved in `data/private/certificate_settings.json` (git-ignored). An alignment test page draws the certificate edge, each baseline and a 50 mm ruler for checking scale.
- **From results:** "Passed every subject of the level" uses the CIT catalogue (or the student's own programme's subjects for other data); "Nothing outstanding" also covers exempted students.
- **Direct printing (Windows):** browser printing adds its own header/footer (URL, date, page number) and a PDF-style dialog, so `src/examlens/printing.py` sends pages straight to a Windows printer through .NET `System.Drawing.Printing` via PowerShell (built into Windows, no new dependency). The app lists printers, paper sizes and trays (defaulting to the manual / bypass tray), sets a custom paper size equal to the certificate, zero margins, and draws each 300 DPI page at its exact physical size from the paper edge (subtracting the printer's hard margin, which print *preview* does not have). Pages sent to the printer have a white background: Windows printing ignores PNG transparency and turned it black. "Show exactly what the printer receives" renders the driver's own preview without printing; tests use that preview too, so no paper is used.
- **Transparent PNG downloads:** the hidden background is transparent *white* (never black), and letter pixels are pure black with partial opacity, so files look right in programs that ignore transparency and have no fringe on coloured paper.

## Deployment requirements

- Streamlit Community Cloud runs a newer Python than 3.11, and the old exact pins (Streamlit 1.39 needs Pillow < 11) had no wheels for it, so installation failed. `requirements.txt` now holds runtime packages only, with version ranges; Streamlit is held to the 1.66 line the app is tested on. Test and lint tools moved to `requirements-dev.txt`, which CI installs. Pandera was unused and dropped.
- Streamlit 1.66 removed `use_column_width`, so the certificate page uses `width="stretch"`.

## Short-course certificates

- A separate **Short Course** page (`pages/8_Short_Course.py`) uses its own template, `assets/short_course_template.json`, taken from `new certificate 2.psd` (front) and `new certificate 2 back.psd` (back). The original Certificates page is unchanged.
- Front: name, course, date and a fourth *subject* line. The date's superscript ordinal includes a space ("20 TH MAY 2026"), as in the PSD (`ordinal_gap`).
- Back: an underlined title, then subject headings, each followed by bulleted topics, typed as plain lines (`- topic`). Sizes, indents and line spacing come from the PSD. The gap between a heading and its first topic differs between the PSD's two groups (10.9 mm and 9.3 mm), so the average is used for every group. Topic underlines are a template option (`underline_topics`), off for this design.
- Back-page details can be saved per course on the PC (`data/private/short_course_details.json`, git-ignored).
- The back page has its own text size, separate from the front. Subject headings and topics print exactly as typed (`caps: false`), while the title stays in capitals (`title_caps`). Default front line moves: Name +1.0 mm, Course −0.9 mm, Date −0.1 mm, Subject −0.3 mm (down), text size 82% on both sides.
- Letter spacing (Photoshop tracking, 1/1000 em) can be changed separately for the front and the back; the template value (50) is the default.
