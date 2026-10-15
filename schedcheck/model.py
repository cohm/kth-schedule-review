"""Normalised data model shared by readers, checks and reporters.

Readers turn source files (TimeEdit exports, study plans) into these objects;
checks only ever see these objects, never raw spreadsheet rows.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

# Severity levels, most severe first. "review" means "a human (or agent)
# should judge this" -- a difference that is not necessarily wrong.
SEVERITIES = ("error", "warning", "review", "info")


def severity_rank(sev: str) -> int:
    return SEVERITIES.index(sev)


def soften(sev: str, steps: int = 1) -> str:
    """Return a severity `steps` levels milder (clamped at 'info')."""
    return SEVERITIES[min(severity_rank(sev) + steps, len(SEVERITIES) - 1)]


@dataclass(frozen=True)
class CourseRef:
    """One course code on a schedule row, e.g. SF1674-12368 (VT27)."""
    code: str                    # base course code, e.g. "SF1674"
    round_id: str | None = None  # application/round code, e.g. "12368"
    round_term: str | None = None  # e.g. "VT27", "HT25"

    def __str__(self) -> str:
        if self.round_id:
            return f"{self.code}-{self.round_id} ({self.round_term})"
        return self.code


@dataclass(frozen=True)
class ProgramGroup:
    """One entry of the Program/grupp column, e.g. CTMAT2-3 or CLGYM3-MAFY."""
    program: str                 # e.g. "CTMAT"
    years: tuple[int, ...]       # e.g. (2, 3); empty if the export gives none
    specialization: str | None = None


@dataclass
class Event:
    """One row of a schedule export."""
    source: str                  # file name
    row: int                     # 1-based spreadsheet row number
    start: dt.datetime
    end: dt.datetime
    activity: str
    courses: list[CourseRef] = field(default_factory=list)
    other_codes: list[str] = field(default_factory=list)  # e.g. 8XCTFYS
    groups: list[str] = field(default_factory=list)
    room: str = ""
    info: str = ""
    staff: str = ""
    programs: list[ProgramGroup] = field(default_factory=list)
    exam_modules: list[str] = field(default_factory=list)  # e.g. ["TEN1"]
    comment: str = ""            # remiss comment column, if any

    @property
    def date(self) -> dt.date:
        return self.start.date()

    @property
    def codes(self) -> list[str]:
        return [c.code for c in self.courses]

    @property
    def is_marker(self) -> bool:
        """Calendar rows (exam days, holidays, ...) carry no course code."""
        return not self.courses and not self.other_codes

    def cite(self) -> str:
        """Short human-checkable reference to the source row."""
        t = f"{self.start:%Y-%m-%d %H:%M}-{self.end:%H:%M}"
        return f"{self.source}:{self.row} {t} {self.activity}"


@dataclass
class Export:
    """One schedule export file (typically one programme year, one term)."""
    path: str
    title: str
    program: str | None          # e.g. "CTFYS"
    year: int | None             # programme year, e.g. 2
    specialization: str | None
    range_start: dt.date | None
    range_end: dt.date | None
    events: list[Event]
    url: str = ""                # link to the schedule in TimeEdit, if known
    exported_at: dt.datetime | None = None   # when TimeEdit generated the file (tz-aware)
    exported_source: str = ""    # how that is known: metadata | file name | file date

    @property
    def label(self) -> str:
        spec = f"-{self.specialization}" if self.specialization else ""
        return f"{self.program}{self.year or ''}{spec}"


@dataclass
class Issue:
    severity: str                # one of SEVERITIES
    check: str                   # e.g. "coverage.missing-course"
    scope: str                   # e.g. "CTFYS2" or "SF1674" or "CTFYS"
    course: str | None
    message: str                 # English, human readable
    key: str = ""                # stable id within (check, course) for accept-lists
    evidence: list[str] = field(default_factory=list)  # Event.cite() strings
    details: dict = field(default_factory=dict)        # structured data for reports
    accepted: str | None = None  # note from accept-list, if accepted

    def to_dict(self) -> dict:
        return {
            "severity": self.severity, "check": self.check, "scope": self.scope,
            "course": self.course, "key": self.key, "message": self.message,
            "evidence": self.evidence, "details": self.details,
            "accepted": self.accepted,
        }
