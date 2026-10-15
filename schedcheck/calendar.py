"""Term calendar derived from an export's marker rows.

KTH exports contain rows without course codes that mark exam days
("Examinationsdag"), re-exam days ("Omexamination"), holidays etc. From these
we derive, without hard-coding any dates:

  * the ordinary exam windows (one per study period in the term),
  * the re-exam windows,
  * the study period each date belongs to,
  * a "teaching week" index per period that skips weeks without teaching
    (e.g. an Easter re-exam week), so that occasions can be compared across
    years even when Easter moves.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from .model import Export

EXAM_DAY_MARKERS = {"examinationsdag", "examination day"}
REEXAM_DAY_MARKERS = {"omexamination", "re-examination"}

TERM_PERIODS = {"VT": ("P3", "P4"), "HT": ("P1", "P2")}


@dataclass
class Window:
    start: dt.date
    end: dt.date
    kind: str            # "exam" or "reexam"
    label: str           # e.g. "P3 exams", "re-exams 2027-06-01..06-04"
    period: str = ""     # e.g. "P3" for an ordinary exam window

    def text(self, lang: str = "en") -> str:
        """The label in Swedish or English."""
        sv = lang == "sv"
        if self.kind == "exam" and self.period:
            return f"{self.period} {'tentaperiod' if sv else 'exams'}"
        what = ("tentor" if self.kind == "exam" else "omtentor") if sv else \
               ("exams" if self.kind == "exam" else "re-exams")
        return f"{what} {self.start:%m-%d}..{self.end:%m-%d}"

    def __contains__(self, d: dt.date) -> bool:
        return self.start <= d <= self.end


@dataclass
class TermCalendar:
    term: str                          # e.g. "VT27"
    start: dt.date
    end: dt.date                       # last day considered part of the term
    periods: list[tuple[str, dt.date, dt.date]] = field(default_factory=list)
    exam_windows: list[Window] = field(default_factory=list)
    reexam_windows: list[Window] = field(default_factory=list)
    skip_weeks: set[tuple[int, int]] = field(default_factory=set)  # ISO (year, week)

    def period_of(self, d: dt.date) -> str | None:
        for name, s, e in self.periods:
            if s <= d <= e:
                return name
        return None

    def window_of(self, d: dt.date) -> Window | None:
        for w in self.exam_windows + self.reexam_windows:
            if d in w:
                return w
        return None

    def teaching_week(self, d: dt.date) -> tuple[str, int] | None:
        """(period, 1-based week index within the period, skipping non-teaching weeks)."""
        p = self.period_of(d)
        if p is None:
            return None
        pstart = next(s for name, s, _ in self.periods if name == p)
        monday = pstart - dt.timedelta(days=pstart.weekday())
        idx, cur = 0, monday
        target = d - dt.timedelta(days=d.weekday())
        while cur <= target:
            if tuple(cur.isocalendar()[:2]) not in self.skip_weeks:
                idx += 1
            cur += dt.timedelta(days=7)
        return p, max(idx, 1)

    def in_term(self, d: dt.date) -> bool:
        return self.start <= d <= self.end


def term_name(d: dt.date) -> str:
    """Name of the term that starts around date d, e.g. 2027-01-12 -> 'VT27'."""
    return ("VT" if d.month < 7 else "HT") + f"{d.year % 100:02d}"


def _cluster(days: list[dt.date], max_gap: int = 4) -> list[tuple[dt.date, dt.date]]:
    out: list[list[dt.date]] = []
    for d in sorted(set(days)):
        if out and (d - out[-1][-1]).days <= max_gap:
            out[-1].append(d)
        else:
            out.append([d])
    return [(c[0], c[-1]) for c in out]


def build_calendar(exports: list[Export]) -> TermCalendar:
    """Build one calendar from the marker rows of all exports of a term."""
    markers = [e for ex in exports for e in ex.events if e.is_marker]
    exam_days = [e.date for e in markers if e.activity.casefold() in EXAM_DAY_MARKERS]
    reexam_days = [e.date for e in markers if e.activity.casefold() in REEXAM_DAY_MARKERS]

    starts = [ex.range_start for ex in exports if ex.range_start]
    all_dates = [e.date for ex in exports for e in ex.events]
    start = min(starts) if starts else min(all_dates)
    term = term_name(start)
    pnames = TERM_PERIODS[term[:2]]

    exam_w = _cluster(exam_days)
    # Re-exam windows can be split by a free day or two (e.g. an arrival
    # day in August); a week-long gap still separates distinct windows.
    reexam_w = _cluster(reexam_days, max_gap=6)
    # The term ends with its last exam or re-exam window; anything later
    # (e.g. next term's first week, present when an export range runs long)
    # is not part of this term.
    ends = [w[1] for w in exam_w + reexam_w]
    end = max(ends) if ends else max(all_dates)

    cal = TermCalendar(term=term, start=start, end=end)
    # Ordinary exam windows map, in order, to the term's study periods.
    # If there are more windows than periods (unusual), extra ones are labelled
    # generically and do not define periods.
    pstart = start
    for i, (s, e) in enumerate(exam_w):
        if i < len(pnames):
            cal.exam_windows.append(Window(s, e, "exam", f"{pnames[i]} exams", pnames[i]))
            cal.periods.append((pnames[i], pstart, e))
            # The next period starts on the Monday after the exam window.
            pstart = e + dt.timedelta(days=7 - e.weekday())
        else:
            cal.exam_windows.append(Window(s, e, "exam", f"exams {s:%m-%d}..{e:%m-%d}"))
    for s, e in reexam_w:
        cal.reexam_windows.append(Window(s, e, "reexam", f"re-exams {s:%m-%d}..{e:%m-%d}"))
        # A re-exam window inside the teaching part of the term (e.g. the
        # Easter week) is a week without regular teaching.
        if cal.periods and s < cal.periods[-1][2]:
            d = s
            while d <= e:
                cal.skip_weeks.add(tuple(d.isocalendar()[:2]))
                d += dt.timedelta(days=1)
    return cal
