"""Check 3: exams of courses taken in parallel must not be too close.

Severity is derived from the gap in calendar days (same day / adjacent / two
days apart, see config thresholds) and then softened depending on how likely
it is that the same student sits both exams:

  * both mandatory in the same programme year .............. as is
  * both in the same master-eligibility group ............... as is
  * one mandatory, one elective ............................. one step softer
  * electives with the same subject prefix (SF/SF) .......... one step softer
  * other elective pairs .................................... two steps softer
  * re-exam paths (year N vs year N-1, re-exam vs re-exam) .. one step softer
  * a partial exam (KS) involved ............................ one step softer
"""
from __future__ import annotations

from itertools import combinations

from ..model import Issue
from ..term import Exam, course_prefix
from . import Context, YearPlan, register

LADDER = ("error", "warning", "info")


def soften(sev: str | None, steps: int) -> str | None:
    if sev is None:
        return None
    i = LADDER.index(sev) + steps
    return LADDER[i] if i < len(LADDER) else None


def base_severity(a: Exam, b: Exam, thresholds: dict[str, str]) -> tuple[str | None, str]:
    gap = abs((a.date - b.date).days)
    if gap == 0:
        overlap = a.event.start < b.event.end and b.event.start < a.event.end
        return thresholds["same_day"], ("overlapping" if overlap else "same day")
    if gap == 1:
        return thresholds["adjacent"], "consecutive days"
    if gap == 2:
        return thresholds["two_days"], "two days apart"
    return None, f"{gap} days apart"


def alternatives(yp: YearPlan | None, a: str, b: str) -> bool:
    """True if no student can take both a and b: they are options of the same
    pick-one group (e.g. alternative degree projects) and neither can be taken
    through any other group of the plan. (In CTMAT, SF1677/SF1678 form a
    pick-one group but are also electives elsewhere, so both can be taken.)"""
    if yp is None or yp.plan is None:
        return False
    groups = yp.plan.groups
    shared = [g for g in groups
              if (g.pick_n == 1 or (g.kind == "pickN" and (g.pick_n or 1) == 1))
              and a in g.options and b in g.options]
    if not shared:
        return False
    elsewhere = any((a in g.options or b in g.options) for g in groups if g not in shared)
    return not elsewhere


def same_sitting(a: Exam, b: Exam) -> bool:
    """Co-listed courses on one row (e.g. DD2421 + FDD3431) are one exam sitting."""
    return a.event.start == b.event.start and b.course in a.event.codes


def _category(yp: YearPlan | None, code: str) -> str:
    if yp is None or yp.plan is None:
        return "unknown"
    c = yp.plan.courses.get(code)
    return c.category if c else "unknown"


def _eligibility(ctx: Context, yp: YearPlan | None) -> dict[str, set[str]]:
    """Master code -> courses required for eligibility (plan data + config)."""
    groups: dict[str, set[str]] = {}
    if yp and yp.plan:
        for m, rec in yp.plan.eligibility_groups(yp.year).items():
            groups[m] = set(rec["required"])
    for g in ctx.config.eligibility_groups:
        groups[g.get("master", g.get("name", "?"))] = set(g.get("courses", []))
    return groups


def _pair_issue(ctx, a: Exam, b: Exam, sev: str, why: str, rel: str, scope: str, check: str,
                relation: str = ""):
    x, y = sorted([a, b], key=lambda e: (e.event.start, e.course))
    return Issue(
        sev, check, scope, x.course,
        f"{x.course} ({x.kind}, {x.event.start:%a %Y-%m-%d %H:%M}) and {y.course} "
        f"({y.kind}, {y.event.start:%a %Y-%m-%d %H:%M}): {why}. {rel}",
        key=f"{x.course}+{y.course}:{x.date}:{y.date}",
        evidence=[x.event.cite(), y.event.cite()],
        details={"courses": [x.course, y.course], "dates": [str(x.date), str(y.date)],
                 "times": [f"{x.event.start:%H:%M}-{x.event.end:%H:%M}", f"{y.event.start:%H:%M}-{y.event.end:%H:%M}"],
                 "kinds": [x.kind, y.kind], "gap_days": abs((x.date - y.date).days),
                 "why": why, "relation": relation},
    )


@register("exams", ("program", "course"), "Exam spacing within and across programme years")
def check_exams(ctx: Context) -> list[Issue]:
    th = ctx.config.thresholds
    issues: list[Issue] = []
    seen_sittings: set = set()

    def new_pair(scope, a: Exam, b: Exam) -> bool:
        """Report each pair of exam sittings once, even if co-listed courses
        (e.g. DD2421 + FDD3431 on one row) would make several course pairs."""
        k = (scope, frozenset([(a.event.start, frozenset(a.event.codes)),
                               (b.event.start, frozenset(b.event.codes))]))
        if k in seen_sittings:
            return False
        seen_sittings.add(k)
        return True
    years = sorted(ctx.new.year_events, key=lambda k: (k[0], k[1] or 0))

    def year_exams(key) -> list[Exam]:
        return ctx.new.exams(ctx.new.year_events.get(key, []))

    for key in years:
        prog, year = key
        scope = f"{prog}{year or ''}"
        yp = ctx.plans.get(key)
        elig = _eligibility(ctx, yp)
        exams = year_exams(key)

        for a, b in combinations(exams, 2):
            if a.course == b.course or same_sitting(a, b):
                continue
            if not (ctx.wants(a.course) or ctx.wants(b.course)):
                continue
            # Re-exams are compared with re-exams; ordinary/partial with each other.
            if (a.kind == "reexam") != (b.kind == "reexam"):
                continue
            if alternatives(yp, a.course, b.course):
                continue  # pick-one alternatives: nobody takes both
            sev, why = base_severity(a, b, th)
            if sev is None:
                continue
            ca, cb = _category(yp, a.course), _category(yp, b.course)
            mand_a, mand_b = ca == "mandatory", cb == "mandatory"
            shared = [m for m, cs in elig.items() if a.course in cs and b.course in cs]
            if mand_a and mand_b:
                steps, rel, relation = 0, "Both are mandatory for this programme year.", "mandatory"
            elif shared:
                steps, rel, relation = 0, f"Both are required for eligibility to {', '.join(sorted(shared))}.", "eligibility:" + ",".join(sorted(shared))
            elif mand_a or mand_b:
                steps, rel, relation = 1, "One mandatory course and one elective.", "mandatory+elective"
            elif "unknown" in (ca, cb):
                steps, rel, relation = 1, "At least one course is not in the study plan for this year.", "unplanned"
            elif course_prefix(a.course) == course_prefix(b.course):
                steps, rel, relation = 1, (f"Electives in the same subject ({course_prefix(a.course)}), "
                                           "plausibly taken together."), "same-subject"
            else:
                steps, rel, relation = 2, "Electives; only a problem for students taking both.", "electives"
            if a.kind == "reexam":
                steps += 1
                rel += " Re-exams (affects students retaking both)."
            if "partial" in (a.kind, b.kind):
                steps += 1
                rel += " Includes a partial exam/KS."
            sev = soften(sev, steps)
            if sev and new_pair(scope, a, b):
                issues.append(_pair_issue(ctx, a, b, sev, why, rel, scope, "exams.spacing",
                                          relation + (":reexam" if a.kind == "reexam" else "")))

        # Re-exam paths: students in year N retaking courses from year N-1.
        prev = (prog, (year or 0) - 1)
        if year and prev in ctx.new.year_events:
            prev_plan = ctx.plans.get(prev)
            for a in exams:
                if a.kind == "partial":
                    continue
                for b in year_exams(prev):
                    if b.kind == "partial" or a.course == b.course or same_sitting(a, b):
                        continue
                    if not (ctx.wants(a.course) or ctx.wants(b.course)):
                        continue
                    if _category(prev_plan, b.course) not in ("mandatory", "unknown"):
                        continue
                    if _category(yp, a.course) not in ("mandatory",) and yp and yp.plan:
                        continue
                    sev, why = base_severity(a, b, th)
                    sev = soften(sev, 1)
                    if sev and new_pair(scope, a, b):
                        rel = (f"Affects {scope} students retaking {b.course} "
                               f"from year {year - 1}.")
                        issues.append(_pair_issue(ctx, a, b, sev, why, rel, scope,
                                                  "exams.reexam-path", f"retake:{b.course}:{year - 1}"))

    # Context: where in the exam window each ordinary exam sits vs. last year.
    if ctx.old:
        for code in sorted({x.course for x in ctx.new.exams() if x.kind == "ordinary"}):
            if not ctx.wants(code):
                continue
            new = [x for x in ctx.new.exams() if x.course == code and x.kind == "ordinary"]
            old = [x for x in ctx.old.exams() if x.course == code and x.kind == "ordinary"]
            if not old:
                continue
            pos_new = [_window_pos(ctx.new, x) for x in new]
            pos_old = [_window_pos(ctx.old, x) for x in old]
            if pos_new != pos_old:
                issues.append(Issue(
                    "info", "exams.moved", code, code,
                    f"{code}: ordinary exam position in the exam window changed: "
                    f"{ctx.old.term} {', '.join(pos_old)} → {ctx.new.term} {', '.join(pos_new)}.",
                    key=f"{pos_old}>{pos_new}",
                    evidence=[x.event.cite() for x in new]))
    return issues


def _window_pos(td, x: Exam) -> str:
    w = next((w for w in td.calendar.exam_windows if x.date in w), None)
    if not w:
        return f"{x.date} (outside window)"
    # Count working days from the window start.
    d, n = w.start, 0
    while d < x.date:
        if d.weekday() < 5:
            n += 1
        d = d.fromordinal(d.toordinal() + 1)
    return f"{w.label.split()[0]} day {n + 1} ({x.event.start:%a %H:%M})"
