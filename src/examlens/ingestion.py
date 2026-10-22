"""Read, map, clean, merge and de-duplicate raw exam result files.

The public entry points are :func:`load_paths` (read files from disk) and :func:`ingest`
(work on already-loaded DataFrames). Both return ``(clean_df, health_report)``.
"""

from __future__ import annotations

import calendar
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import IO

import numpy as np
import pandas as pd

from examlens import config
from examlens.schema import (
    COLUMN_ALIASES,
    COLUMNS,
    REQUIRED_COLUMNS,
    normalise_header,
)

ABSENT_TEXT = {"AB", "ABS", "ABSENT", "-", "--", "A"}
MEDICAL_TEXT = {"MC", "MED", "MEDICAL"}
WITHHELD_TEXT = {"WH", "WITHHELD", "W/H"}
SUBJECT_CODE_RE = re.compile(r"^[A-Za-z]{2,4}\s?\d{3}$")

_MONTHS: dict[str, int] = {}
for _i in range(1, 13):
    _MONTHS[calendar.month_abbr[_i].lower()] = _i
    _MONTHS[calendar.month_name[_i].lower()] = _i
_MONTHS["sept"] = 9


class IngestionError(Exception):
    """Raised when a file cannot be turned into the canonical schema."""


class MissingColumnsError(IngestionError):
    """Required columns could not be mapped; the UI should ask the user to map them."""

    def __init__(self, filename: str, missing: list[str], available: list[str]) -> None:
        super().__init__(
            f"{filename}: could not find column(s) {', '.join(missing)}. "
            f"Available columns: {', '.join(available)}"
        )
        self.filename = filename
        self.missing = missing
        self.available = available


@dataclass
class HealthReport:
    """Everything the Data Health page needs to describe an ingestion run."""

    rows_per_file: dict[str, int] = field(default_factory=dict)
    rows_loaded: int = 0
    rows_dropped_missing_required: int = 0
    duplicates_removed: int = 0
    duplicate_keys: list[dict] = field(default_factory=list)
    invalid_marks: int = 0
    invalid_mark_rows: list[dict] = field(default_factory=list)
    name_conflicts: list[dict] = field(default_factory=list)
    absent_count: int = 0
    medical_count: int = 0
    wide_files: list[str] = field(default_factory=list)
    missing_per_column: dict[str, int] = field(default_factory=dict)
    rows_final: int = 0

    def to_dict(self) -> dict:
        """Return the report as a plain dictionary."""
        return asdict(self)


def parse_session(value: object) -> tuple[str, pd.Timestamp]:
    """Normalise a session label to ``YYYY-Mon`` and return it with its first-of-month date.

    Accepts forms like ``2024-Jun``, ``Jun 2024``, ``2024 June`` and ``2024-06``. Unparseable
    values are returned unchanged with ``NaT``.
    """
    text = str(value).strip()
    year_match = re.search(r"(?<!\d)((?:19|20)\d{2})(?!\d)", text)
    if not year_match:
        return text, pd.NaT
    year = int(year_match.group(1))
    rest = text[: year_match.start()] + " " + text[year_match.end() :]
    month: int | None = None
    for word in re.findall(r"[A-Za-z]+", rest):
        if word.lower() in _MONTHS:
            month = _MONTHS[word.lower()]
            break
    if month is None:
        num = re.search(r"(?<!\d)(\d{1,2})(?!\d)", rest)
        if num and 1 <= int(num.group(1)) <= 12:
            month = int(num.group(1))
    if month is None:
        return text, pd.NaT
    return f"{year}-{calendar.month_abbr[month]}", pd.Timestamp(year=year, month=month, day=1)


def guess_session_from_filename(filename: str) -> str | None:
    """Return a normalised session label found in ``filename``, or ``None``."""
    stem = re.sub(r"[_\-.]+", " ", Path(filename).stem)
    label, date = parse_session(stem)
    return None if pd.isna(date) else label


def read_raw(source: str | Path | IO[bytes], filename: str | None = None) -> pd.DataFrame:
    """Read a ``.csv``, ``.xlsx`` or ``.xls`` file into a DataFrame of strings."""
    name = filename or str(source)
    suffix = Path(name).suffix.lower()
    try:
        if suffix == ".csv":
            return pd.read_csv(source, dtype=str)
        if suffix in {".xlsx", ".xls"}:
            return pd.read_excel(source, dtype=str)
    except Exception as exc:
        raise IngestionError(f"{Path(name).name}: could not be read ({exc})") from exc
    raise IngestionError(f"{Path(name).name}: unsupported file type '{suffix}'")


def _alias_lookup() -> dict[str, str]:
    lookup: dict[str, str] = {}
    for canonical, aliases in COLUMN_ALIASES.items():
        for alias in [normalise_header(canonical), *aliases]:
            lookup.setdefault(alias, canonical)
    return lookup


def map_columns(
    raw: pd.DataFrame, overrides: dict[str, str] | None = None
) -> tuple[pd.DataFrame, list[str]]:
    """Rename raw headers to canonical names.

    ``overrides`` maps canonical name -> source column and wins over automatic matching.
    Returns the renamed frame and the list of required canonical columns still unmapped
    (subject_code is not counted as missing for wide-format files).
    """
    lookup = _alias_lookup()
    chosen: dict[str, str] = {}
    for col in raw.columns:
        canonical = lookup.get(normalise_header(col))
        if canonical and canonical not in chosen:
            chosen[canonical] = col
    for canonical, source in (overrides or {}).items():
        if source in raw.columns:
            chosen[canonical] = source
    rename = {src: canon for canon, src in chosen.items()}
    mapped = raw[list(rename)].rename(columns=rename)
    leftovers = [c for c in raw.columns if c not in rename]
    mapped = pd.concat([mapped, raw[leftovers]], axis=1)
    missing = [c for c in REQUIRED_COLUMNS if c not in chosen]
    if "subject_code" in missing and _wide_columns(leftovers):
        missing.remove("subject_code")
        if "exam_session" in missing:  # wide files usually carry the session in the filename
            missing.remove("exam_session")
    return mapped, missing


def _wide_columns(columns: list[str]) -> list[str]:
    return [c for c in columns if SUBJECT_CODE_RE.match(str(c).strip())]


def _melt_wide(df: pd.DataFrame, session: str | None) -> pd.DataFrame:
    """Turn one-row-per-student / one-column-per-subject into long format."""
    code_cols = _wide_columns(list(df.columns))
    id_cols = [c for c in df.columns if c not in code_cols]
    long = df.melt(
        id_vars=id_cols, value_vars=code_cols, var_name="subject_code", value_name="marks"
    )
    long["subject_code"] = long["subject_code"].str.replace(r"\s+", "", regex=True)
    blank = long["marks"].isna() | (long["marks"].astype(str).str.strip() == "")
    long = long[~blank].copy()
    if session:
        long["exam_session"] = session
    return long


def _parse_marks(
    marks: pd.Series, status: pd.Series | None
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Split raw marks/status into numeric marks, normalised status and an out-of-range flag."""
    text = marks.astype("string").str.strip()
    upper = text.str.upper()
    numeric = pd.to_numeric(text, errors="coerce")

    if status is None:
        status_text = pd.Series("", index=marks.index)
    else:
        status_text = status.astype("string").str.strip().str.upper().fillna("")

    out = pd.Series("Sat", index=marks.index, dtype=object)
    out[status_text.isin(WITHHELD_TEXT) | status_text.str.startswith("WITH")] = "Withheld"
    out[status_text.isin(MEDICAL_TEXT) | status_text.str.startswith("MEDIC")] = "Medical"
    out[status_text.isin(ABSENT_TEXT) | status_text.str.startswith("ABSENT")] = "Absent"
    out[upper.isin(WITHHELD_TEXT)] = "Withheld"
    out[upper.isin(MEDICAL_TEXT)] = "Medical"
    out[upper.isin(ABSENT_TEXT)] = "Absent"

    invalid = numeric.notna() & ((numeric < 0) | (numeric > 100))
    numeric = numeric.mask(invalid | (out != "Sat"))
    return numeric.astype(float), out, invalid


def apply_results(df: pd.DataFrame, pass_mark: float = config.PASS_MARK) -> pd.DataFrame:
    """Recompute ``grade`` and ``result`` from ``marks`` (used by ingest and live re-scoring)."""
    out = df.copy()
    marks = out["marks"]
    out["grade"] = marks.map(lambda m: config.grade_for(m) if pd.notna(m) else np.nan)
    result = pd.Series(np.nan, index=out.index, dtype=object)
    result[marks.notna() & (marks >= pass_mark)] = "Pass"
    result[marks.notna() & (marks < pass_mark)] = "Fail"
    result[out["status"].isin(["Absent", "Medical"])] = "Absent"
    out["result"] = result
    return out


def _resolve_names(df: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    """Give each student_id its most frequent name (longest wins ties) and log conflicts."""
    conflicts: list[dict] = []
    chosen: dict[str, str] = {}
    for sid, names in df.groupby("student_id")["student_name"]:
        counts = Counter(names)
        if len(counts) > 1:
            best = max(counts, key=lambda n: (counts[n], len(n), n))
            conflicts.append({"student_id": sid, "names": sorted(counts), "kept": best})
            chosen[sid] = best
    if chosen:
        df = df.copy()
        df["student_name"] = df["student_id"].map(chosen).fillna(df["student_name"])
    return df, conflicts


def _derive_attempts(df: pd.DataFrame) -> pd.Series:
    """Rank sessions chronologically per (student, subject): 1, 2, 3..."""
    order = df.assign(_label=df["exam_session"]).sort_values(
        ["student_id", "subject_code", "session_date", "_label"], na_position="last"
    )
    return order.groupby(["student_id", "subject_code"]).cumcount().add(1).reindex(df.index)


def _fill_from_code(df: pd.DataFrame, column: str) -> pd.Series:
    """Fill blanks in ``column`` with the most common value for the same subject_code."""
    if column not in df.columns:
        df[column] = np.nan
    modes = (
        df.dropna(subset=[column]).groupby("subject_code")[column].agg(lambda s: s.mode().iloc[0])
    )
    return df[column].where(df[column].notna(), df["subject_code"].map(modes))


def ingest(
    frames: dict[str, pd.DataFrame],
    overrides: dict[str, dict[str, str]] | None = None,
    wide_sessions: dict[str, str] | None = None,
    pass_mark: float = config.PASS_MARK,
) -> tuple[pd.DataFrame, HealthReport]:
    """Clean and merge raw frames (keyed by filename) into the canonical dataset.

    ``overrides`` is ``{filename: {canonical: source_column}}`` for manual column mapping.
    ``wide_sessions`` is ``{filename: session}`` for wide-format files; if absent the session
    is guessed from the filename. Raises :class:`MissingColumnsError` when a required column
    cannot be mapped and :class:`IngestionError` for a wide file with no known session.
    """
    report = HealthReport()
    parts: list[pd.DataFrame] = []

    for filename, raw in frames.items():
        report.rows_per_file[filename] = len(raw)
        mapped, missing = map_columns(raw, (overrides or {}).get(filename))
        if missing:
            raise MissingColumnsError(filename, missing, [str(c) for c in raw.columns])
        if "subject_code" not in mapped.columns:
            session = (wide_sessions or {}).get(filename) or guess_session_from_filename(filename)
            if "exam_session" not in mapped.columns and not session:
                raise IngestionError(
                    f"{filename}: wide-format file needs an exam session (none found in the name)"
                )
            mapped = _melt_wide(mapped, session)
            report.wide_files.append(filename)
        mapped = mapped.copy()
        mapped["source_file"] = filename
        parts.append(mapped)

    if not parts:
        raise IngestionError("No files to load")
    df = pd.concat(parts, ignore_index=True)
    report.rows_loaded = len(df)

    for col in COLUMNS:
        if col not in df.columns:
            df[col] = np.nan

    # Text normalisation.
    for col in ["student_id", "student_name", "subject_code", "exam_session"]:
        df[col] = df[col].astype(object).str.strip().replace("", pd.NA)
    df["student_id"] = df["student_id"].str.upper()
    df["subject_code"] = df["subject_code"].str.upper().str.replace(r"\s+", "", regex=True)
    df["student_name"] = df["student_name"].str.replace(r"\s+", " ", regex=True)
    for col in ["programme", "intake", "level", "subject_name"]:
        df[col] = df[col].astype(object).str.strip().replace("", pd.NA)

    required_blank = df[REQUIRED_COLUMNS].isna().any(axis=1)
    report.rows_dropped_missing_required = int(required_blank.sum())
    df = df[~required_blank].copy()

    # Marks / status.
    marks, status, invalid = _parse_marks(
        df["marks"], df["status"] if df["status"].notna().any() else None
    )
    df["marks"], df["status"] = marks, status
    report.invalid_marks = int(invalid.sum())
    report.invalid_mark_rows = [
        {
            "source_file": r.source_file,
            "student_id": r.student_id,
            "subject_code": r.subject_code,
            "exam_session": r.exam_session,
        }
        for r in df[invalid].itertuples()
    ]

    # Sessions.
    parsed = df["exam_session"].map(parse_session)
    df["exam_session"] = parsed.map(lambda p: p[0])
    df["session_date"] = pd.to_datetime(parsed.map(lambda p: p[1]))

    # Names.
    df, report.name_conflicts = _resolve_names(df)

    # Duplicates: keep the highest mark per student + subject + session.
    keys = ["student_id", "subject_code", "exam_session"]
    ranked = df.assign(_m=df["marks"].fillna(-1)).sort_values("_m", ascending=False, kind="stable")
    dup_mask = ranked.duplicated(keys, keep="first")
    report.duplicates_removed = int(dup_mask.sum())
    report.duplicate_keys = ranked.loc[dup_mask, keys].to_dict("records")
    df = ranked[~dup_mask].drop(columns="_m")

    # Fill descriptive columns from other rows of the same subject.
    df["subject_name"] = _fill_from_code(df, "subject_name").fillna(df["subject_code"])
    df["level"] = _fill_from_code(df, "level")

    # Attempts.
    df = df.sort_values(["session_date", "student_id", "subject_code"]).reset_index(drop=True)
    given = pd.to_numeric(df["attempt_no"], errors="coerce")
    df["attempt_no"] = given.fillna(_derive_attempts(df)).astype(int)

    df = apply_results(df, pass_mark)
    df = df[COLUMNS].copy()

    report.absent_count = int((df["status"] == "Absent").sum())
    report.medical_count = int((df["status"] == "Medical").sum())
    report.missing_per_column = {c: int(n) for c, n in df.isna().sum().items() if n}
    report.rows_final = len(df)
    return df, report


def load_paths(
    paths: list[str | Path],
    overrides: dict[str, dict[str, str]] | None = None,
    wide_sessions: dict[str, str] | None = None,
    pass_mark: float = config.PASS_MARK,
) -> tuple[pd.DataFrame, HealthReport]:
    """Read files from disk and run :func:`ingest` on them (keyed by filename)."""
    frames = {Path(p).name: read_raw(p) for p in paths}
    return ingest(frames, overrides, wide_sessions, pass_mark)


def sample_paths(directory: str | Path = "data/sample") -> list[Path]:
    """Return the ``.xlsx``/``.xls``/``.csv`` files in ``directory`` in a stable order."""
    return sorted(
        p for p in Path(directory).iterdir() if p.suffix.lower() in {".xlsx", ".xls", ".csv"}
    )
