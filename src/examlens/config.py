"""Single source of truth for pass mark, grade bands and risk weights."""

PASS_MARK = 50

GRADE_BANDS = [  # (min_mark_inclusive, grade)
    (75, "A"),
    (65, "B"),
    (55, "C"),
    (50, "D"),
    (0, "F"),
]

RISK_WEIGHTS = {
    "repeat_fail_same_subject": 30,  # failed the same subject 2+ times
    "outstanding_fails": 10,  # per subject currently not passed (cap 3)
    "absences": 8,  # per absent attempt (cap 3)
    "declining_trend": 15,  # average mark dropped 10+ points vs. previous session
    "low_recent_average": 15,  # latest-session average < 45
}

RISK_LEVELS = {"High": 50, "Medium": 25, "Low": 0}  # score thresholds


def grade_for(marks: float) -> str:
    """Return the letter grade for a mark using ``GRADE_BANDS``."""
    for minimum, grade in GRADE_BANDS:
        if marks >= minimum:
            return grade
    return GRADE_BANDS[-1][1]
