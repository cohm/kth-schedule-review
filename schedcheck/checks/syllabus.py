"""Exam expectations combining three sources, and syllabus module checks.

Why a course should have an ordinary exam this term (any of):
  * the study plan puts an exam in one of the term's periods,
  * it had an ordinary exam in the reference term (last year),
  * its current syllabus (valid for this term, from the course page) has a
    written exam module (TEN…) and a course round ends within this term.
Findings list every reason that applies, so the reader can weigh them.
"""
from __future__ import annotations

import re

from ..model import Issue
from . import Context, register


def expand_modules(mods) -> set[str]:
    """'TEN1-2' -> {'TEN1', 'TEN2'}; other codes unchanged."""
    out = set()
    for m in mods:
        r = re.fullmatch(r"([A-ZÅÄÖ]+)(\d+)-(\d+)", m)
        if r:
            out |= {f"{r.group(1)}{i}" for i in range(int(r.group(2)), int(r.group(3)) + 1)}
        else:
            out.add(m)
    return out


def round_ends_in_term(syl, ctx: Context) -> bool | None:
    """True/False if the syllabus data has rounds; None if it says nothing."""
    if not syl or not syl.rounds:
        return None
    s, e = ctx.new.calendar.start, ctx.new.calendar.end
    return any(r.get("end") and s.isoformat() <= r["end"] <= e.isoformat() for r in syl.rounds)


def round_starts_in_term(syl, ctx: Context) -> bool:
    if not syl or not syl.rounds:
        return False
    s, e = ctx.new.calendar.start, ctx.new.calendar.end
    return any(r.get("start") and s.isoformat() <= r["start"] <= e.isoformat() for r in syl.rounds)


def only_syllabus(details: dict) -> bool:
    return not details.get("plan_exam_periods") and not details.get("reference_ordinary")


def exam_reasons(ctx: Context, code: str, plan_exam_periods=()) -> tuple[list[str], dict]:
    """English reasons an ordinary exam is expected, and details for reports."""
    reasons, details = [], {}
    if plan_exam_periods:
        reasons.append(f"the study plan has an exam in {'/'.join(plan_exam_periods)}")
        details["plan_exam_periods"] = list(plan_exam_periods)
    if ctx.old:
        old_ex = [x for x in ctx.old.exams() if x.course == code]
        ordinary = [x for x in old_ex if x.kind == "ordinary"]
        details["reference_term"] = ctx.old.term
        details["reference_ordinary"] = [f"{x.event.start:%Y-%m-%d %H:%M} {x.event.activity}"
                                         + (f" ({', '.join(x.event.exam_modules)})" if x.event.exam_modules else "")
                                         for x in ordinary]
        details["reference_reexam"] = [f"{x.event.start:%Y-%m-%d %H:%M} {x.event.activity}"
                                       for x in old_ex if x.kind == "reexam"]
        if ordinary:
            reasons.append(f"it had an ordinary exam in {ctx.old.term} ({ordinary[0].date})")
    syl = ctx.syllabi.get(code)
    if syl and syl.written:
        ends = round_ends_in_term(syl, ctx)
        details["syllabus_valid_from"] = syl.valid_from
        details["syllabus_written"] = [m.label() for m in syl.written]
        details["syllabus_round_ends_in_term"] = ends
        if ends is not False:
            reasons.append(f"its syllabus (valid from {syl.valid_from}) has "
                           + ", ".join(m.label() for m in syl.written))
    return reasons, details


@register("syllabus", ("program", "course"), "Scheduled exam modules against the current syllabus")
def check_syllabus(ctx: Context) -> list[Issue]:
    issues: list[Issue] = []
    for code in sorted(c for c in ctx.new.courses() if ctx.wants(c)):
        syl = ctx.syllabi.get(code)
        if not syl or not syl.modules:
            continue
        exams = [x for x in ctx.new.exams(ctx.new.course_events(code)) if x.course == code]
        syl_codes = {m.code for m in syl.modules}
        written = {m.code for m in syl.written}
        # Modules on ordinary exams / KS that the current syllabus doesn't have.
        # A row shared by several courses may carry any of their modules; a
        # code on the row from an older round may follow an older syllabus.
        prev_ht = f"HT{int(ctx.new.term[2:]) - 1:02d}" if ctx.new.term.startswith("VT") else None

        def old_round_on(row) -> bool:
            return any(c.code == code and c.round_term and c.round_term not in (ctx.new.term, prev_ht)
                       for c in row.courses)

        for x in exams:
            if x.kind == "reexam" or old_round_on(x.event):
                continue  # re-exams and old rounds may follow an older syllabus
            allowed = set(syl_codes)
            for other in x.event.codes:
                o = ctx.syllabi.get(other)
                if other != code and o:
                    allowed |= {m.code for m in o.modules}
            unknown = sorted(expand_modules(x.event.exam_modules) - allowed)
            if unknown:
                issues.append(Issue(
                    "warning", "syllabus.unknown-module", code, code,
                    f"{code}: {x.event.activity} on {x.date} is registered as {', '.join(unknown)}, which the "
                    f"current syllabus (valid from {syl.valid_from}) does not have; its exam modules are "
                    + ", ".join(m.label() for m in syl.modules) + ".",
                    key=f"{x.date}:{','.join(unknown)}", evidence=[x.event.cite()],
                    details={"scheduled": unknown, "syllabus_valid_from": syl.valid_from,
                             "syllabus_modules": [m.label() for m in syl.modules]}))
        # Written modules no scheduled ordinary exam mentions.
        ordinary = [x for x in exams if x.kind == "ordinary"]
        listed = set().union(*(expand_modules(x.event.exam_modules) for x in ordinary)) if ordinary else set()
        if ordinary and listed and round_starts_in_term(syl, ctx):
            # (A course running over two terms may examine some modules in the other one.)
            missing = sorted(written - listed)
            if missing:
                issues.append(Issue(
                    "review", "syllabus.module-not-scheduled", code, code,
                    f"{code}: the syllabus (valid from {syl.valid_from}) has "
                    + ", ".join(m.label() for m in syl.written if m.code in missing)
                    + f", but no scheduled ordinary exam lists it (scheduled: {', '.join(sorted(listed))}).",
                    key=",".join(missing), evidence=[x.event.cite() for x in ordinary[:2]],
                    details={"missing": missing, "scheduled": sorted(listed),
                             "syllabus_valid_from": syl.valid_from}))
    if ctx.syllabus_errors and ctx.review in ("program", "course"):
        codes = sorted(c for c in ctx.syllabus_errors if ctx.wants(c))
        if codes:
            issues.append(Issue("info", "syllabus.unavailable", ctx.new.term, None,
                                f"No syllabus data could be fetched for {len(codes)} course(s): "
                                f"{', '.join(codes)}. Exam-module checks skipped for them.",
                                key="unavailable", details={"courses": codes}))
    return issues
