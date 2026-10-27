# 🎓 ExamLens

**Turn scattered exam result spreadsheets into clear academic insights: pass rates, subject difficulty, repeat attempts and at-risk students.**

![Python](https://img.shields.io/badge/python-3.11+-blue)
![Streamlit](https://img.shields.io/badge/built%20with-Streamlit-ff4b4b)
![License](https://img.shields.io/badge/license-MIT-green)
[![CI](https://github.com/imalk22/examlens/actions/workflows/ci.yml/badge.svg)](https://github.com/imalk22/examlens/actions/workflows/ci.yml)

**Live demo:** [examlens.streamlit.app](https://examlens.streamlit.app/) (click **Load sample data** to explore with synthetic data)

[![Open in Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://examlens.streamlit.app/)

![Overview page](docs/screenshots/overview.png)

## The problem

In many institutes, exam results live in many separate Excel files: one per subject, session or batch, each with its own headers. Answering a simple question like *"Which subject fails the most students?"* or *"Who has failed the same module twice?"* means hours of manual filtering. ExamLens answers it in seconds.

## Features

- **Upload & Data Health:** multi-file upload (`.xlsx`, `.xls`, `.csv`), automatic header mapping, wide-format marksheets, duplicate and invalid-mark detection, and a clear health report.
- **Overview:** KPI cards with change vs the previous session, pass-rate trend, grade distribution and auto-generated key insights.
- **Subject Analysis:** a difficulty leaderboard, mark histograms with the pass mark, trends and first-attempt vs repeat pass rates.
- **Repeat Attempts:** attempts-to-pass distributions, repeat rates, per-subject funnels and a "never passed" list.
- **At-Risk Students:** a transparent rule-based score with plain-English reasons, searchable and exportable to Excel.
- **Student Lookup:** fuzzy search, full exam history, what remains to pass, and a transcript download.
- **Certificates & Short Course:** print names, courses and dates (plus course subjects on the back for short courses) onto pre-printed certificates, laid out from Photoshop templates.
- **Live assumptions:** change the pass mark and risk weights in the sidebar and every page recomputes.

| Subjects | At-risk | Student profile |
|---|---|---|
| ![Subjects](docs/screenshots/subjects.png) | ![At-risk](docs/screenshots/at_risk.png) | ![Student](docs/screenshots/student.png) |

## Business questions it answers

- Which subjects have the lowest first-attempt pass rate?
- How many attempts do students need to pass each subject?
- Which students need academic intervention right now, and why?
- Is performance improving across sessions?

## Metric definitions

| Metric | Definition |
|---|---|
| **Pass rate** | Passes ÷ (Passes + Fails). Absentees are excluded and reported separately. |
| **First-attempt pass rate** | Pass rate counting only `attempt_no == 1`. |
| **Absence rate** | Absent ÷ total registered attempts. |
| **Average mark** | Mean of non-null marks. Median is shown alongside. |
| **Attempts to pass** | For students who eventually passed a subject: the `attempt_no` of the passing attempt. |
| **Never-passed count** | Students with ≥1 attempt and no pass in a subject. |
| **Repeat rate** | Share of (student, subject) pairs needing more than one attempt. |
| **Subject Difficulty Index (0–100)** | `0.5 × first_attempt_fail_rate + 0.3 × repeat_rate + 0.2 × (1 − mean_mark/100)`, scaled to 0–100. Higher = harder. |
| **Session trend** | Pass rate and mean mark per subject per session, ordered by session date. |
| **Cohort progress** | Per intake: % of students who have passed all subjects attempted so far. |

## How at-risk scoring works

No machine learning: every flag can be explained to a non-technical administrator. Each student earns points for the indicators below; the points are summed and mapped to a level.

| Indicator | Points |
|---|---|
| Failed the same subject 2+ times | 30 |
| Each subject currently not passed (max 3) | 10 each |
| Each absent attempt (max 3) | 8 each |
| Average dropped 10+ marks vs the previous session | 15 |
| Latest-session average below 45 | 15 |

**High** = 50+ points, **Medium** = 25–49, **Low** = below 25. All weights, thresholds and the pass mark can be changed in the sidebar's *Assumptions* panel (defaults live in [`config.py`](src/examlens/config.py)). Each flagged student gets a reasons string such as *"Failed TX204 twice · 2 subjects outstanding · Average dropped 14 marks since last session"*.

## Data privacy

This repository contains **no real student data**. Everything in `data/sample/` is synthetic and produced by [`scripts/generate_sample_data.py`](scripts/generate_sample_data.py) with a fixed seed. If you use real files locally, keep them in `data/private/`, which is git-ignored. The app holds uploaded data in memory only.

## Quick start

```bash
git clone https://github.com/imalk22/examlens.git
cd examlens
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
python scripts/generate_sample_data.py
streamlit run app.py
```

Run the checks with `ruff check . && ruff format --check . && pytest`.

## Project structure

```
app.py                 # home page
webui.py               # shared Streamlit helpers (state, sidebar, filters, components)
pages/                 # the six dashboard pages
src/examlens/          # pure Python logic, no Streamlit imports
  config.py            # pass mark, grade bands, risk weights
  schema.py            # canonical columns and validation
  ingestion.py         # read, map, clean, merge, de-duplicate
  metrics.py           # pass rates, difficulty, attempts, trends
  risk.py              # at-risk rules and scoring
  charts.py            # Plotly figures
  export.py            # Excel / CSV export
  insights.py          # key-insight sentences
scripts/generate_sample_data.py
data/sample/           # committed synthetic files
tests/                 # pytest suite
docs/DECISIONS.md      # recorded design decisions
```

## Tech stack

Python 3.11+, Streamlit, pandas, openpyxl, Plotly, Faker, pytest, ruff, GitHub Actions.

## Roadmap

- PDF report export
- Email digest of at-risk students
- Login with roles
- Connection to a database or LMS

## Author

**Imesh Samintha** · [LinkedIn](https://www.linkedin.com/) · [GitHub](https://github.com/imalk22)
