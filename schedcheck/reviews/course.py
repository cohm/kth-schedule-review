"""Course review: one or more courses, new term vs. reference term.

Uses whatever exports contain the course (programme exports or a course
export); no study plan is needed.
"""
from __future__ import annotations

from ..checks import Context, run_checks
from ..config import Config, apply_accepted
from ..term import TermData
from .program import ReviewResult, dedupe, load_syllabi


def course_review(codes: list[str], new: TermData, old: TermData | None,
                  config: Config, syllabus_source=None, room_source=None) -> ReviewResult:
    ctx = Context("course", new, old, config, courses=set(codes), rooms=room_source)
    load_syllabi(ctx, syllabus_source, codes)
    issues = dedupe(run_checks(ctx))
    apply_accepted(issues, config.accepted)
    notes = []
    for c in codes:
        if not new.course_events(c):
            notes.append(f"{c} does not occur in the {new.term} exports.")
        if old and not old.course_events(c):
            notes.append(f"{c} does not occur in the {old.term} exports.")
    title = f"{', '.join(codes)} {new.term}" + (f" vs {old.term}" if old else "")
    return ReviewResult("course", title, ctx, issues, notes)
