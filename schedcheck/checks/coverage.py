"""Check 1: every course in the study plan is in the schedule (and vice versa),
and courses with exams have an ordinary exam and a re-exam.
"""
from __future__ import annotations

from ..calendar import TERM_PERIODS
from ..model import Issue
from ..term import REEXAM_ACTIVITY_PREFIXES
from . import Context, register
from .syllabus import exam_reasons, only_syllabus

MISSING_SEVERITY = {
    "mandatory": "error",
    "conditionallyElective": "warning",
    "recommended": "warning",
}


@register("coverage", ("program",), "Study-plan courses present in the schedule; exams present")
def check_coverage(ctx: Context) -> list[Issue]:
    issues: list[Issue] = []
    periods = TERM_PERIODS[ctx.new.term[:2]]

    for (prog, year), yp in sorted(ctx.plans.items(), key=lambda kv: (kv[0][0], kv[0][1] or 0)):
        scope = f"{prog}{year or ''}"
        year_events = ctx.new.year_events.get((prog, year), [])
        # Courses taught (not only re-examined) in this programme year's export.
        taught = {c for e in year_events for c in e.codes
                  if not e.activity.casefold().startswith(REEXAM_ACTIVITY_PREFIXES)}
        present = {c for e in year_events for c in e.codes}

        if yp.plan is None:
            issues.append(Issue("warning", "coverage.no-plan", scope, None,
                                f"No study plan available for {scope}: {yp.note}. "
                                "Coverage could not be checked.", key=scope))
            continue
        if "approximated" in yp.note:
            issues.append(Issue("info", "coverage.plan-approximated", scope, None,
                                f"Study plan for {scope} (cohort {yp.cohort}) is {yp.note}.",
                                key=scope))

        expected = yp.plan.expected(year, periods, yp.specialization)
        exp_codes = {e.code for e in expected}

        # Option groups where one choice is enough (e.g. degree project).
        for g in yp.plan.groups_for(year, yp.specialization):
            if g.kind == "pickN" and g.options:
                if sum(g.period_credits.get(p, 0) or 0 for p in periods) <= 0:
                    continue
                if not set(g.options) & present:
                    issues.append(Issue("error", "coverage.group-empty", scope, None,
                                        f"None of the options in '{g.name}' ({', '.join(g.options)}) "
                                        "is scheduled.", key=g.name))

        pick_groups = {o: g for g in yp.plan.groups_for(year, yp.specialization)
                       if g.kind == "pickN" for o in g.options}
        for e in expected:
            if e.code in present:
                continue
            sev = MISSING_SEVERITY.get(e.category, "warning")
            g = pick_groups.get(e.code)
            if g and set(g.options) & present:
                sev = "info"  # another option of a pick-one group is scheduled
            where = f" (option in '{e.group}')" if e.group else ""
            issues.append(Issue(sev, "coverage.missing-course", scope, e.code,
                                f"{e.code} {e.name} [{e.category}]{where} is in the study plan "
                                f"for {scope} in {'/'.join(e.periods) or ctx.new.term} "
                                "but not in the schedule.", key=e.code,
                                details={"name": e.name, "category": e.category,
                                         "periods": e.periods, "group": e.group}))

        # Scheduled but not in this year's plan (ignoring re-exam-only courses,
        # which are normally re-exams of earlier courses in the programme).
        for code in sorted(taught - exp_codes):
            if code in yp.plan.courses and yp.plan.courses[code].year not in (None, year):
                where = f"the plan places it in year {yp.plan.courses[code].year}"
            elif code in yp.plan.courses:
                where = "the plan has no credits for it this term"
            else:
                where = "it is not in the study plan"
            issues.append(Issue("info", "coverage.unplanned-course", scope, code,
                                f"{code} is scheduled for {scope} but {where}.", key=code))

        # Exam presence: an ordinary exam (in an exam window) and a later re-exam.
        # Expected if the study plan, last year's schedule or the current
        # syllabus says so (see checks/syllabus.py); all reasons are listed.
        plan_periods = {e.code: e.exam_periods for e in expected}
        planned = set(yp.plan.courses)

        def alias_only(code: str) -> bool:
            """Only ever listed together with a study-plan course (an alternative
            code for the same teaching, e.g. DD232V next to DD2352)."""
            evs = [e for e in year_events if code in e.codes]
            return code not in planned and bool(evs) and all(set(e.codes) & (planned - {code}) for e in evs)

        for code in sorted((exp_codes & present) | taught):
            if alias_only(code):
                continue
            reasons, ref = exam_reasons(ctx, code, plan_periods.get(code, ()))
            if not reasons:
                continue
            why = "; ".join(reasons)
            cx = [x for x in ctx.new.exams() if x.course == code]
            weak = only_syllabus(ref)
            note = (f" (Only the syllabus says so; for a course outside the mandatory plan the exam may be "
                    f"scheduled without {scope} and not appear in this export.)" if weak else "")
            if not any(x.kind == "ordinary" for x in cx):
                issues.append(Issue("warning" if weak else "error", "coverage.missing-exam", scope, code,
                                    f"{code} has no ordinary exam in an exam window, but {why}.{note}",
                                    key=code, details=ref,
                                    evidence=[x.event.cite() for x in cx]))
            if not any(x.kind == "reexam" for x in cx):
                issues.append(Issue("info" if weak else "warning", "coverage.missing-reexam", scope, code,
                                    f"{code} has no re-exam scheduled this term, but {why}.{note}",
                                    key=code, details=ref))
    return issues
