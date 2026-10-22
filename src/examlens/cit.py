"""Parser for Chartered Institute of Taxation (CIT) result sheets.

These workbooks are wide marksheets with multi-row merged headers, one block of columns per
subject (marks, parts, council adjustments, status) and different layouts per level and batch.
:func:`parse_cit` turns one sheet into long format (one row per student and subject) so it can
flow through the normal cleaning pipeline and merge with every other file for the same student.
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

LEVEL_SUBJECTS: dict[str, list[tuple[str, str, str]]] = {
    # level: [(code, subject name, header regex)]; order matters (most specific first)
    "Application": [
        ("TX112", "Principles of Indirect Taxation", r"indirect|\bpit\b"),
        ("TX111", "Principles of Direct Taxation", r"direct|\bpdt\b"),
        ("BS111", "Fundamentals of Accounting", r"fundamental|\bfa\s+result"),
        ("BS112", "Business Environment for Taxation", r"environment|\bbe\s+result"),
    ],
    "Analyst 1": [
        ("TX212", "Indirect Taxation", r"indirect|\bit\s+result"),
        ("TX211", "Direct Taxation", r"direct|\bdt\s+result"),
        ("CP211", "Compliance Management", r"compl|\bcm\s+result"),
        ("BS211", "Accounting for Taxation", r"accounting|\bat\s+result"),
        ("BS212", "Business Law", r"business\s*l(aw|ow)|\bbl\s+result"),
    ],
    "Analyst 2": [
        ("TX222", "Practical Application of Value Added Tax", r"value\s*added|\bvat\b"),
        ("TX221", "Corporate Taxation", r"corporate\s*tax|corp\.?\s*tax"),
        ("CP221", "Conceptual Framework of Tax Adjudication", r"adjudication|\bta\s+marks"),
        ("BS222", "Corporate Law", r"corporate\s*law|\bcl\s+marks"),
        ("BS221", "Audit & Assurance for Taxation", r"audit|\baat\b"),
    ],
    "Advisory": [
        ("TX311", "International Taxation & Transfer Pricing", r"international|transfer|ittp"),
        ("CP311", "Contemporary Issues in Taxation", r"contemporary|\bci\b"),
        ("TX312", "Application of Tax Adjudication", r"adjudication|\bta\b"),
        ("CP312", "Compliance Risk Management & Validation", r"compliance\s*risk|crmv"),
        ("BS311", "Strategic Management & Entrepreneurship", r"strategic|\bsme\b"),
    ],
}
CODE_RE = re.compile(r"\b(TX|CP|BS)\s*(\d{3})\b", re.I)
STUDENT_RE = re.compile(r"^\d{4}/[A-Za-z0-9]{1,4}/\d{3,5}$")
ID_LIKE = re.compile(r"^\d{2,4}/[A-Za-z0-9]+/[A-Za-z0-9/]+$|^[A-Z]{3,5}\d{5,8}$")
SUMMARY_RE = re.compile(
    r"final\s*(total\s*)?marks|^average|overall\s*result|academic|determinant|"
    r"result\s*verification|council\s*final|total\s*mak",
    re.I,
)
SKIP_RE = re.compile(r"exempt|previous|skipp|^n/?a$|not\s*appl|withdraw|cancel", re.I)
ABSENT_RE = re.compile(r"^(ab|abs|absent)\.?$", re.I)
MEDICAL_RE = re.compile(r"^(mc|med|medical)$", re.I)
STATUS_WORDS = re.compile(
    r"^(pass|fail|ab|abs|absent|mc|medical|withheld|exempted|skipped|previously completed)\b", re.I
)
MONTHS = {
    m: i + 1
    for i, m in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
    )
}


def _cell(value: object) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return ""
    text = str(value).replace("−", "-").replace("–", "-")
    return re.sub(r"\s+", " ", text).strip()


def session_from_text(text: str) -> str | None:
    """Last 'Month YYYY' found in ``text`` as ``YYYY-Mon`` (e.g. 'Jan 2025' -> '2025-Jan')."""
    found = None
    for word, year in re.findall(r"([A-Za-z]{3,9})\.?\s*,?\s*(20\d{2})", text):
        month = MONTHS.get(word.lower()[:3])
        if month and (word.lower() in MONTHS or len(word) >= 3):
            found = f"{year}-{list(MONTHS)[month - 1].capitalize()}"
    return found


def detect_level(text: str) -> str | None:
    """Qualification level named in a title or filename."""
    low = text.lower()
    if "advisory" in low:
        return "Advisory"
    if re.search(r"analyst\s*(level)?\s*2", low):
        return "Analyst 2"
    if re.search(r"analyst\s*(level)?\s*1", low):
        return "Analyst 1"
    if "application" in low:
        return "Application"
    return None


def detect_intake(text: str) -> str:
    """Batch label such as '2025 B1' from a title like 'Analyst Level 1 (2025) B1 - English'."""
    m = re.search(r"(20\d{2})\s*\)?\s*(?:batch|b)\s*(\d)", text, re.I)
    return f"{m.group(1)} B{m.group(2)}" if m else ""


def match_subject(level: str, header: str) -> str | None:
    """Subject code a header text refers to, or ``None``."""
    allowed = {code for code, _, _ in LEVEL_SUBJECTS[level]}
    for prefix, num in CODE_RE.findall(header):
        code = f"{prefix.upper()}{num}"
        if code in allowed:
            return code
    for code, _, pattern in LEVEL_SUBJECTS[level]:
        if re.search(pattern, header, re.I):
            return code
    return None


def _numeric_ratio(values: list[str]) -> float:
    filled = [v for v in values if v]
    if not filled:
        return 0.0
    ok = 0
    for v in filled:
        try:
            float(v)
            ok += 1
        except ValueError:
            pass
    return ok / len(filled)


def _status_ratio(values: list[str]) -> float:
    filled = [v for v in values if v]
    return sum(bool(STATUS_WORDS.match(v)) for v in filled) / len(filled) if filled else 0.0


def _marks_score(header: str, numeric: float) -> float:
    score = 0.0
    if re.search(r"final\s*adjusted|final total", header):
        score += 10
    elif "total" in header and "marks" in header:
        score += 8
    elif "total" in header:
        score += 7
    elif re.search(r"\bmarks?\b", header):
        score += 6
    if re.search(r"part\s*-?\s*(\d|[a-d])|\(part", header):
        score -= 5
    if re.search(r"council|adjust|approved|review|evaluation|board", header) and not re.search(
        r"final\s*adjusted", header
    ):
        score -= 6
    if re.search(r"status|result", header) and "marks" not in header:
        score -= 3
    return score + numeric * 4


def parse_cit(grid: pd.DataFrame, filename: str) -> tuple[pd.DataFrame, dict] | None:
    """Parse one sheet. Returns ``(long_table, info)`` or ``None`` if it is not a CIT sheet."""
    grid = grid.dropna(how="all").dropna(axis=1, how="all")
    cells = [[_cell(v) for v in row] for row in grid.values.tolist()]
    if len(cells) < 4:
        return None
    ncols = len(cells[0])

    start = next(
        (
            i
            for i, row in enumerate(cells)
            if (ne := [c for c in row if c])
            and re.fullmatch(r"\d{1,3}", ne[0])
            and any(ID_LIKE.match(c) for c in ne[1:])
        ),
        None,
    )
    if start is None:
        return None
    header_rows = [r for r in range(start) if sum(bool(c) for c in cells[r]) >= 2]
    main = next(
        (
            r
            for r in header_rows
            if any(re.search(r"index|student\s*(reg\.?\s*)?no", c, re.I) for c in cells[r])
        ),
        None,
    )
    if main is None:
        return None

    title = " ".join(c for row in cells[: min(start, 4)] for c in row if c)
    level = detect_level(title + " " + filename) or detect_level(filename)
    if level is None:
        return None

    def find(pattern: str) -> int | None:
        for j, c in enumerate(cells[main]):
            if re.search(pattern, c, re.I):
                return j
        return None

    data_rows = [row for row in cells[start:] if any(ID_LIKE.match(c) for c in row if c)]
    id_col = find(r"student\s*(reg\.?\s*)?no")
    if id_col is None:
        best = max(range(ncols), key=lambda j: sum(bool(STUDENT_RE.match(r[j])) for r in data_rows))
        if sum(bool(STUDENT_RE.match(r[best])) for r in data_rows) >= max(1, len(data_rows) // 2):
            id_col = best
    idx_col = find(r"index")
    name_col = find(r"name")
    id_cols = [c for c in (id_col, idx_col, name_col) if c is not None]
    first_subject_col = max(id_cols) + 1 if id_cols else 0

    htext = [" ".join(cells[r][j] for r in header_rows if cells[r][j]) for j in range(ncols)]
    found: dict[str, int] = {}
    for j in range(first_subject_col, ncols):
        code = match_subject(level, htext[j])
        if code and code not in found:
            found[code] = j
    if not found:
        return None
    starts = sorted((col, code) for code, col in found.items())
    end = ncols
    for j in range(starts[-1][0] + 1, ncols):
        if SUMMARY_RE.search(cells[main][j]):
            end = j
            break
    spans = [
        (code, col, starts[i + 1][0] if i + 1 < len(starts) else end)
        for i, (col, code) in enumerate(starts)
    ]

    names = {code: name for code, name, _ in LEVEL_SUBJECTS[level]}
    columns: dict[str, tuple[int | None, int | None]] = {}
    for code, c0, c1 in spans:
        cols = range(c0, c1)
        values = {j: [r[j] for r in data_rows] for j in cols}
        candidates = [
            (j, _marks_score(htext[j].lower(), _numeric_ratio(values[j])))
            for j in cols
            if _numeric_ratio(values[j]) >= 0.3 or any(ABSENT_RE.match(v) for v in values[j])
        ]
        mcol = max(candidates, key=lambda x: x[1])[0] if candidates else None
        scols = [
            (
                j,
                _status_ratio(values[j])
                + (0.2 if re.search(r"status|result", htext[j], re.I) else 0),
            )
            for j in cols
            if j != mcol and _status_ratio(values[j]) >= 0.3
        ]
        scol = max(scols, key=lambda x: x[1])[0] if scols else None
        columns[code] = (mcol, scol)

    session = session_from_text(filename) or session_from_text(title) or "Unknown"
    intake = detect_intake(title)
    records: list[dict] = []
    skipped = 0
    index_only = 0
    for row in data_rows:
        student = (row[id_col] if id_col is not None else "").upper().replace(" ", "")
        index = row[idx_col] if idx_col is not None else ""
        if not student:
            student = index.upper().replace(" ", "")
            index_only += 1
        if not student:
            continue
        name = row[name_col] if name_col is not None else ""
        for code, (mcol, scol) in columns.items():
            marks = row[mcol] if mcol is not None else ""
            status = row[scol] if scol is not None else ""
            if SKIP_RE.search(marks) or SKIP_RE.search(status):
                skipped += 1
                continue
            state = ""
            if ABSENT_RE.match(marks) or ABSENT_RE.match(status):
                state, marks = "Absent", ""
            elif MEDICAL_RE.match(marks) or MEDICAL_RE.match(status):
                state, marks = "Medical", ""
            else:
                try:
                    float(marks)
                except ValueError:
                    marks = ""
            if not marks and not state:
                continue
            records.append(
                {
                    "Student ID": student,
                    "Student Name": name,
                    "Programme": "CIT Qualification",
                    "Level": level,
                    "Intake": intake,
                    "Subject Code": code,
                    "Subject Name": names[code],
                    "Exam Session": session,
                    "Marks": marks,
                    "Status": state,
                    "Official Result": status,
                }
            )
    if not records:
        return None
    info = {
        "level": level,
        "intake": intake,
        "session": session,
        "subjects": [c for c, _, _ in spans],
        "students": len({r["Student ID"] for r in records}),
        "skipped": skipped,
        "index_only": index_only,
        "columns": {
            code: (
                htext[m][:60] if m is not None else None,
                htext[s][:60] if s is not None else None,
            )
            for code, (m, s) in columns.items()
        },
    }
    return pd.DataFrame(records), info
