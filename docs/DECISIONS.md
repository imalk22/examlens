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
