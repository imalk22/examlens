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
