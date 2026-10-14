"""A term's worth of schedule data: exports + calendar + derived views.

Checks receive TermData objects (one for the schedule under review, one for
the reference schedule, typically last year's final schedule).
"""
from __future__ import annotations

import datetime as dt
import re
from collections import defaultdict
from dataclasses import dataclass, field

from .calendar import TermCalendar, build_calendar
from .model import Event, Export

# Activities that are examinations. Matched case-insensitively against the
# start of the activity name (so "Tentamen" also covers "Tentamen, digital").
EXAM_ACTIVITY_PREFIXES = ("tentamen", "omtenta", "kontrollskrivning", "examination",
                          "muntlig tentamen", "tenta", "ks ", "exam", "re-exam")
REEXAM_ACTIVITY_PREFIXES = ("omtenta", "omexamination", "re-exam")


def is_exam_activity(activity: str) -> bool:
    a = activity.casefold()
    return a.startswith(EXAM_ACTIVITY_PREFIXES) or a == "ks"


@dataclass
class Exam:
    course: str
    event: Event
    kind: str          # "ordinary" | "reexam" | "partial"
    window: str | None  # window label, if inside one

    @property
    def date(self) -> dt.date:
        return self.event.date


@dataclass
class TermData:
    exports: list[Export]
    calendar: TermCalendar
    events: list[Event]                         # in-term, de-duplicated, with course or activity codes
    dropped_out_of_term: list[Event] = field(default_factory=list)
    year_events: dict[tuple[str, int | None], list[Event]] = field(default_factory=dict)

    @property
    def term(self) -> str:
        return self.calendar.term

    def course_events(self, code: str) -> list[Event]:
        return [e for e in self.events if code in e.codes]

    def courses(self) -> set[str]:
        return {c for e in self.events for c in e.codes}

    def years(self) -> list[tuple[str, int | None]]:
        return sorted(self.year_events, key=lambda k: (k[0] or "", k[1] or 0))

    def exams(self, events: list[Event] | None = None) -> list[Exam]:
        out, seen = [], set()
        for e in (self.events if events is None else events):
            if not e.courses or not is_exam_activity(e.activity):
                continue
            win = self.calendar.window_of(e.date)
            a = e.activity.casefold()
            if a.startswith(REEXAM_ACTIVITY_PREFIXES) or (win and win.kind == "reexam"):
                kind = "reexam"
            elif win and win.kind == "exam":
                kind = "ordinary"
            else:
                kind = "partial"
            for c in e.codes:
                k = (c, e.start, e.end)
                if k in seen:
                    continue
                seen.add(k)
                out.append(Exam(c, e, kind, win.label if win else None))
        return sorted(out, key=lambda x: (x.event.start, x.course))


def _event_key(e: Event):
    return (e.start, e.end, e.activity.casefold(), tuple(sorted(e.codes)),
            tuple(sorted(e.groups)), e.room)


def load_term(exports: list[Export]) -> TermData:
    cal = build_calendar(exports)
    seen: dict = {}
    dropped = []
    year_events: dict[tuple[str, int | None], list[Event]] = defaultdict(list)
    for ex in exports:
        for e in ex.events:
            if e.is_marker:
                continue  # rows with neither course nor programme-activity code
            if not cal.in_term(e.date):
                dropped.append(e)
                continue
            year_events[(ex.program or "", ex.year)].append(e)
            seen.setdefault(_event_key(e), e)
    events = sorted(seen.values(), key=lambda e: (e.start, e.row))
    return TermData(exports, cal, events, dropped, dict(year_events))


def course_prefix(code: str) -> str:
    """Subject prefix used to guess related courses: 'SF1677' -> 'SF'."""
    m = re.match(r"F?([A-Z]{2})", code)
    return m.group(1) if m else code[:2]
