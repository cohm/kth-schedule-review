"""Check 1: every course in the study plan is in the schedule (and vice versa),
and courses with exams have an ordinary exam and a re-exam.
"""
from __future__ import annotations

from ..calendar import TERM_PERIODS
from ..i18n import T
from ..model import Issue
from ..term import REEXAM_ACTIVITY_PREFIXES
from . import Context, register
from .syllabus import exam_reasons, only_syllabus, reasons_text

CATEGORY = {"mandatory": T("obligatorisk", "mandatory"),
            "conditionallyElective": T("villkorligt valfri", "conditionally elective"),
            "recommended": T("rekommenderad", "recommended"),
            "electivePlaceholder": T("valfri", "elective")}

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
            note = yp.note or T("okänd orsak", "unknown reason")
            issues.append(Issue("warning", "coverage.no-plan", scope, None,
                                T(f"Ingen utbildningsplan tillgänglig för {scope}: {note['sv']}. "
                                  "Kurstäckningen kunde inte kontrolleras.",
                                  f"No study plan available for {scope}: {note['en']}. "
                                  "Coverage could not be checked."), key=scope))
            continue
        if yp.approximated and yp.note:
            issues.append(Issue("info", "coverage.plan-approximated", scope, None,
                                T(f"Utbildningsplanen för {scope} (kull {yp.cohort}) är {yp.note['sv']}.",
                                  f"Study plan for {scope} (cohort {yp.cohort}) is {yp.note['en']}."),
                                key=scope))

        expected = yp.plan.expected(year, periods, yp.specialization)
        exp_codes = {e.code for e in expected}

        # Option groups where one choice is enough (e.g. degree project).
        for g in yp.plan.groups_for(year, yp.specialization):
            if g.kind == "pickN" and g.options:
                if sum(g.period_credits.get(p, 0) or 0 for p in periods) <= 0:
                    continue
                if not set(g.options) & present:
                    opts = ", ".join(g.options)
                    issues.append(Issue("error", "coverage.group-empty", scope, None,
                                        T(f"Ingen av kurserna i '{g.name}' ({opts}) är schemalagd för {scope}.",
                                          f"None of the options in '{g.name}' ({opts}) is scheduled."),
                                        key=g.name))

        pick_groups = {o: g for g in yp.plan.groups_for(year, yp.specialization)
                       if g.kind == "pickN" for o in g.options}
        for e in expected:
            if e.code in present:
                continue
            sev = MISSING_SEVERITY.get(e.category, "warning")
            g = pick_groups.get(e.code)
            if g and set(g.options) & present:
                sev = "info"  # another option of a pick-one group is scheduled
            cat = CATEGORY.get(e.category, T(e.category, e.category))
            per = "/".join(e.periods) or ctx.new.term
            issues.append(Issue(sev, "coverage.missing-course", scope, e.code,
                                T(f"{e.code} {e.name} [{cat['sv']}]"
                                  + (f" (alternativ i '{e.group}')" if e.group else "")
                                  + f" ingår i utbildningsplanen för {scope} i {per} men finns inte i schemat.",
                                  f"{e.code} {e.name} [{cat['en']}]"
                                  + (f" (option in '{e.group}')" if e.group else "")
                                  + f" is in the study plan for {scope} in {per} but not in the schedule."),
                                ask=T("Ska den läggas in?", "Should it be added?"), key=e.code,
                                details={"name": e.name, "category": e.category,
                                         "periods": e.periods, "group": e.group}))

        # Scheduled but not in this year's plan (ignoring re-exam-only courses,
        # which are normally re-exams of earlier courses in the programme).
        for code in sorted(taught - exp_codes):
            if code in yp.plan.courses and yp.plan.courses[code].year not in (None, year):
                y = yp.plan.courses[code].year
                where = T(f"utbildningsplanen har den i årskurs {y}", f"the plan places it in year {y}")
            elif code in yp.plan.courses:
                where = T("utbildningsplanen ger inga poäng för den denna termin",
                          "the plan has no credits for it this term")
            else:
                where = T("den finns inte i utbildningsplanen", "it is not in the study plan")
            issues.append(Issue("info", "coverage.unplanned-course", scope, code,
                                T(f"{code} är schemalagd för {scope}, men {where['sv']}.",
                                  f"{code} is scheduled for {scope} but {where['en']}."), key=code))

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
            why = reasons_text(reasons)
            cx = [x for x in ctx.new.exams() if x.course == code]
            weak = only_syllabus(ref)
            note = (T(" (Bara kursplanen säger det; för en kurs utanför den obligatoriska planen kan "
                      f"tentamen vara schemalagd utan {scope} och då inte synas i denna export.)",
                      " (Only the syllabus says so; for a course outside the mandatory plan the exam may be "
                      f"scheduled without {scope} and not appear in this export.)") if weak else T("", ""))
            if not any(x.kind == "ordinary" for x in cx):
                issues.append(Issue("warning" if weak else "error", "coverage.missing-exam", scope, code,
                                    T(f"{code} har ingen ordinarie tentamen i tentamensperioden, men "
                                      f"{why['sv']}.{note['sv']}",
                                      f"{code} has no ordinary exam in an exam window, but {why['en']}.{note['en']}"),
                                    ask=T("Ska den läggas in?", "Should it be added?"),
                                    key=code, details=ref,
                                    evidence=[x.event.cite() for x in cx]))
            if not any(x.kind == "reexam" for x in cx):
                issues.append(Issue("info" if weak else "warning", "coverage.missing-reexam", scope, code,
                                    T(f"{code} har ingen omtentamen schemalagd denna termin, men "
                                      f"{why['sv']}.{note['sv']}",
                                      f"{code} has no re-exam scheduled this term, but {why['en']}.{note['en']}"),
                                    ask=T("Ska den läggas in?", "Should it be added?"),
                                    key=code, details=ref))
    return issues
