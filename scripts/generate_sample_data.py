"""Generate synthetic, reproducible exam result files for ExamLens.

All data is fake. Output goes to ``data/sample/`` by default. Several files are deliberately
messy (different headers, text marks, duplicates, a wide-format marksheet) to exercise the
ingestion layer.

Usage:
    python scripts/generate_sample_data.py --seed 42 --students 600
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from faker import Faker

SESSIONS = ["2023-Dec", "2024-Jun", "2024-Dec", "2025-Jun", "2025-Dec", "2026-Jun"]
INTAKES = ["2023-Jan", "2023-Jul", "2024-Jan", "2024-Jul"]
INTAKE_START = {"2023-Jan": 0, "2023-Jul": 1, "2024-Jan": 2, "2024-Jul": 3}  # first session index
INTAKE_WEIGHTS = [0.30, 0.30, 0.25, 0.15]

PROGRAMMES = {
    "Diploma in Taxation": 0.40,
    "Diploma in Accounting": 0.35,
    "Diploma in Business Management": 0.25,
}

# (code, name, programme, level, extra difficulty in marks)
SUBJECTS = [
    ("TX101", "Principles of Taxation", "Diploma in Taxation", 1, 3),
    ("TX102", "Business Mathematics", "Diploma in Taxation", 1, 5),
    ("TX201", "Income Tax Law", "Diploma in Taxation", 2, 4),
    ("TX204", "Corporate Taxation", "Diploma in Taxation", 2, 17),
    ("TX301", "Tax Planning and Compliance", "Diploma in Taxation", 3, 6),
    ("AC101", "Financial Accounting I", "Diploma in Accounting", 1, 2),
    ("AC102", "Introduction to Economics", "Diploma in Accounting", 1, 4),
    ("AC201", "Management Accounting", "Diploma in Accounting", 2, 5),
    ("AC202", "Audit and Assurance", "Diploma in Accounting", 2, 15),
    ("AC301", "Strategic Financial Management", "Diploma in Accounting", 3, 7),
    ("BM101", "Principles of Management", "Diploma in Business Management", 1, 0),
    ("BM102", "Business Communication", "Diploma in Business Management", 1, 1),
    ("BM201", "Marketing Management", "Diploma in Business Management", 2, 3),
    ("BM202", "Business Statistics", "Diploma in Business Management", 2, 16),
    ("BM301", "Strategic Management", "Diploma in Business Management", 3, 5),
]
HARD_SUBJECTS = ["TX204", "AC202", "BM202"]

SL_FIRST = [
    "Nimal", "Kamal", "Sunil", "Chaminda", "Ruwan", "Dilshan", "Kasun", "Nuwan", "Tharindu",
    "Sanduni", "Nadeesha", "Kavindi", "Dinithi", "Ishara", "Hansika", "Amaya", "Thilini",
    "Pasindu", "Lahiru", "Madushan", "Shanika", "Gayani", "Buddhika", "Isuru", "Malsha",
]  # fmt: skip
SL_LAST = [
    "Perera", "Fernando", "Silva", "Jayawardena", "Wickramasinghe", "Gunasekara", "Bandara",
    "Dissanayake", "Rajapaksa", "Senanayake", "Karunaratne", "Herath", "Amarasinghe",
    "Weerasinghe", "Ratnayake", "Liyanage", "Samarasinghe", "Abeysekera", "De Mel", "Peiris",
]  # fmt: skip

PASS_MARK = 50
MAX_ATTEMPTS = 4
RESIT_BONUS = 12  # average extra marks on a repeat attempt (students revise before re-sitting)
FIXED_ZIP_TIME = (2020, 1, 1, 0, 0, 0)
FIXED_DATETIME = datetime(2020, 1, 1)


@dataclass
class Manifest:
    """Counts of the deliberately injected data issues, for ingestion tests."""

    files: dict[str, dict]

    def dump(self, path: Path) -> None:
        path.write_text(json.dumps(self.files, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def make_students(rng: np.random.Generator, fake: Faker, n: int) -> pd.DataFrame:
    """Create the student roster with ability, programme, intake and trend flags."""
    intakes = rng.choice(INTAKES, size=n, p=INTAKE_WEIGHTS)
    programmes = rng.choice(list(PROGRAMMES), size=n, p=list(PROGRAMMES.values()))
    abilities = rng.normal(0, 1, size=n)
    declining = rng.random(n) < 0.05
    names: list[str] = []
    for _ in range(n):
        if rng.random() < 0.5:
            names.append(f"{rng.choice(SL_FIRST)} {rng.choice(SL_LAST)}")
        else:
            names.append(f"{fake.first_name()} {fake.last_name()}")
    ids = [f"ST{intake[:4]}-{i + 1:04d}" for i, intake in enumerate(intakes)]
    return pd.DataFrame(
        {
            "student_id": ids,
            "student_name": names,
            "programme": programmes,
            "intake": intakes,
            "ability": abilities,
            "declining": declining,
        }
    )


def simulate_attempts(rng: np.random.Generator, students: pd.DataFrame) -> pd.DataFrame:
    """Simulate every student's attempts, including re-sits, as long-format rows."""
    by_programme: dict[str, list[tuple]] = {}
    for subject in SUBJECTS:
        by_programme.setdefault(subject[2], []).append(subject)

    rows: list[dict] = []
    for stu in students.itertuples(index=False):
        start = INTAKE_START[stu.intake]
        decline_rate = rng.uniform(5, 8) if stu.declining else 0.0
        for code, name, _prog, level, difficulty in sorted(
            by_programme[stu.programme], key=lambda s: s[3]
        ):
            session = start + (level - 1)
            attempt = 1
            while session < len(SESSIONS) and attempt <= MAX_ATTEMPTS:
                draw = rng.random()
                status = "Absent" if draw < 0.04 else "Medical" if draw < 0.045 else "Sat"
                marks = np.nan
                if status == "Sat":
                    mean = 66 + 9 * stu.ability - difficulty - decline_rate * (session - start)
                    mean += RESIT_BONUS if attempt > 1 else 0
                    marks = float(np.clip(round(rng.normal(mean, 7)), 0, 100))
                rows.append(
                    {
                        "student_id": stu.student_id,
                        "student_name": stu.student_name,
                        "programme": stu.programme,
                        "intake": stu.intake,
                        "level": f"Level {level}",
                        "subject_code": code,
                        "subject_name": name,
                        "exam_session": SESSIONS[session],
                        "session_idx": session,
                        "marks": marks,
                        "status": status,
                    }
                )
                if status == "Sat" and marks >= PASS_MARK:
                    break
                r = rng.random()
                if status != "Sat":
                    gap = 1 if r < 0.9 else 0
                else:
                    gap = 1 if r < 0.75 else 2 if r < 0.90 else 0
                if gap == 0:
                    break
                session += gap
                attempt += 1
    return pd.DataFrame(rows)


def mark_text(row: pd.Series, absent: str = "AB", medical: str = "MC") -> object:
    """Marks cell as a number, or text for absent/medical rows."""
    if row["status"] == "Absent":
        return absent
    if row["status"] == "Medical":
        return medical
    return row["marks"]


def write_xlsx(df: pd.DataFrame, path: Path) -> None:
    """Write an .xlsx with fixed metadata and zip timestamps so output is byte-reproducible."""
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)
        props = writer.book.properties
        props.created = FIXED_DATETIME
        props.modified = FIXED_DATETIME
        props.creator = "examlens-generator"
        props.lastModifiedBy = "examlens-generator"
    tmp = path.with_suffix(".tmp")
    with zipfile.ZipFile(path) as src, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            info = zipfile.ZipInfo(item.filename, FIXED_ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = item.external_attr
            content = src.read(item.filename)
            if item.filename == "docProps/core.xml":  # openpyxl stamps "modified" on save
                content = re.sub(
                    rb"(<dcterms:modified[^>]*>)[^<]*", rb"\g<1>2020-01-01T00:00:00Z", content
                )
            dst.writestr(info, content)
    shutil.move(tmp, path)


def clean_frame(rows: pd.DataFrame) -> pd.DataFrame:
    """Clean long format with friendly Title Case headers."""
    return pd.DataFrame(
        {
            "Student ID": rows["student_id"],
            "Student Name": rows["student_name"],
            "Programme": rows["programme"],
            "Intake": rows["intake"],
            "Level": rows["level"],
            "Subject Code": rows["subject_code"],
            "Subject Name": rows["subject_name"],
            "Exam Session": rows["exam_session"],
            "Marks": rows["marks"],
            "Status": rows["status"],
        }
    )


def alt_header_frame(rows: pd.DataFrame) -> pd.DataFrame:
    """Same data with a different header vocabulary (Reg No / Module Code / Score)."""
    return pd.DataFrame(
        {
            "Reg No": rows["student_id"],
            "Name": rows["student_name"],
            "Programme": rows["programme"],
            "Intake": rows["intake"],
            "Level": rows["level"],
            "Module Code": rows["subject_code"],
            "Module": rows["subject_name"],
            "Sitting": rows["exam_session"],
            "Score": rows["marks"],
            "Remarks": rows["status"].replace({"Sat": ""}),
        }
    )


def wide_frame(rows: pd.DataFrame) -> pd.DataFrame:
    """One row per student, one column per Level 1 subject code; no session column."""
    level1 = [s[0] for s in SUBJECTS if s[3] == 1]
    records: dict[str, dict] = {}
    for _, row in rows.iterrows():
        rec = records.setdefault(
            row["student_id"],
            {
                "Student ID": row["student_id"],
                "Name": row["student_name"],
                "Programme": row["programme"],
                "Intake": row["intake"],
                **{code: np.nan for code in level1},
            },
        )
        rec[row["subject_code"]] = mark_text(row)
    return pd.DataFrame(list(records.values())).sort_values("Student ID").reset_index(drop=True)


def generate(seed: int, n_students: int, out_dir: Path) -> dict:
    """Generate all sample files and return the manifest dict."""
    rng = np.random.default_rng(seed)
    Faker.seed(seed)
    fake = Faker()

    students = make_students(rng, fake, n_students)
    data = simulate_attempts(rng, students)
    data = data.sort_values(["session_idx", "student_id", "subject_code"]).reset_index(drop=True)

    out_dir.mkdir(parents=True, exist_ok=True)
    for old in list(out_dir.glob("*.xlsx")) + list(out_dir.glob("*.csv")):
        old.unlink()
    manifest = Manifest(files={})

    def session_rows(name: str, level1_only: bool | None = None) -> pd.DataFrame:
        sel = data["exam_session"] == name
        if level1_only is True:
            sel &= data["level"] == "Level 1"
        elif level1_only is False:
            sel &= data["level"] != "Level 1"
        return data[sel].copy()

    # Clean long-format files.
    for fname, session in [
        ("results_2023_dec.xlsx", "2023-Dec"),
        ("results_2024_jun.xlsx", "2024-Jun"),
        ("results_2026_jun.xlsx", "2026-Jun"),
    ]:
        rows = session_rows(session)
        write_xlsx(clean_frame(rows), out_dir / fname)
        manifest.files[fname] = {"format": "long", "session": session, "rows": len(rows)}

    # Different headers; one invalid mark injected.
    rows = session_rows("2024-Dec")
    frame = alt_header_frame(rows)
    sat_idx = frame.index[rows["status"].to_numpy() == "Sat"]
    frame.loc[sat_idx[0], "Score"] = 150.0
    write_xlsx(frame, out_dir / "results_2024_dec.xlsx")
    manifest.files["results_2024_dec.xlsx"] = {
        "format": "long",
        "session": "2024-Dec",
        "rows": len(frame),
        "invalid_marks": 1,
        "header_style": "Reg No / Module Code / Score",
    }

    # CSV with AB / MC text marks, duplicate rows and one name conflict.
    rows = session_rows("2025-Jun")
    frame = clean_frame(rows).drop(columns=["Status"])
    frame["Marks"] = rows.apply(mark_text, axis=1)
    sat_idx = frame.index[rows["status"].to_numpy() == "Sat"]
    dup_rows = frame.loc[sat_idx[[5, 40, 90]]].copy()
    dup_rows["Marks"] = dup_rows["Marks"].astype(float).sub(6).clip(lower=0)  # lower mark dupes
    conflict_idx = sat_idx[150]
    original = frame.loc[conflict_idx, "Student Name"]
    first, *rest = original.split()
    frame.loc[conflict_idx, "Student Name"] = f"{first[0]}. {' '.join(rest)}".strip()
    frame = pd.concat([frame, dup_rows], ignore_index=True)
    frame.to_csv(out_dir / "results_2025_jun.csv", index=False, lineterminator="\n")
    manifest.files["results_2025_jun.csv"] = {
        "format": "long",
        "session": "2025-Jun",
        "rows": len(frame),
        "duplicates": len(dup_rows),
        "ab_entries": int((rows["status"] == "Absent").sum()),
        "mc_entries": int((rows["status"] == "Medical").sum()),
        "name_conflicts": 1,
    }

    # 2025-Dec: Level 1 as a wide marksheet, Levels 2-3 as a clean long file.
    rows = session_rows("2025-Dec", level1_only=True)
    frame = wide_frame(rows)
    write_xlsx(frame, out_dir / "level1_marksheet_2025_dec.xlsx")
    manifest.files["level1_marksheet_2025_dec.xlsx"] = {
        "format": "wide",
        "session": "2025-Dec (not in file; ask user)",
        "rows": len(frame),
        "long_rows_after_melt": len(rows),
        "ab_entries": int((rows["status"] == "Absent").sum()),
    }
    rows = session_rows("2025-Dec", level1_only=False)
    write_xlsx(clean_frame(rows), out_dir / "results_2025_dec_level2_3.xlsx")
    manifest.files["results_2025_dec_level2_3.xlsx"] = {
        "format": "long",
        "session": "2025-Dec",
        "rows": len(rows),
    }

    manifest.dump(out_dir / "MANIFEST.json")

    print(f"Seed {seed}: wrote {len(manifest.files)} files to {out_dir}")
    for fname, info in sorted(manifest.files.items()):
        print(f"  {fname:<36} {info['rows']:>5} rows  ({info['format']})")
    print(
        f"Summary: {len(data)} attempt rows, {data['student_id'].nunique()} students, "
        f"{data['subject_code'].nunique()} subjects, {data['exam_session'].nunique()} sessions"
    )
    return manifest.files


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--students", type=int, default=600)
    parser.add_argument("--out", type=Path, default=Path("data/sample"))
    args = parser.parse_args()
    generate(args.seed, args.students, args.out)


if __name__ == "__main__":
    main()
