"""Per-programme-year check status: what was checked and what came out,
stated explicitly also when nothing was found ("no clashes" is a result).
"""
from __future__ import annotations

from collections import Counter

from ..calendar import TERM_PERIODS
from ..model import severity_rank
from ..reviews.program import ReviewResult

OK = "ok"


def _worst(issues) -> str:
    sev = [i.severity for i in issues]
    return min(sev, key=severity_rank) if sev else OK


def _count_text(issues) -> str:
    c = Counter(i.severity for i in issues)
    return ", ".join(f"{c[s]} {s}" for s in ("error", "warning", "review", "info") if c[s])


def _raw_pairs(exams) -> Counter:
    """Gap in calendar days -> number of exam pairs (0, 1, 2 days), from the
    schedule itself rather than from issues (some pairs, e.g. unrelated
    electives on consecutive days, are deliberately not reported as issues)."""
    from itertools import combinations
    from ..checks.exams import same_sitting
    c: Counter = Counter()
    for a, b in combinations(exams, 2):
        if a.course == b.course or same_sitting(a, b):
            continue
        gap = abs((a.date - b.date).days)
        if gap <= 2:
            c[gap] += 1
    return c


def _spacing_line(label: str, exams: list, issues: list) -> dict:
    n = len({(x.course, x.event.start) for x in exams})
    noun = "exam" if n == 1 else "exams"
    if n < 2:
        return {"check": label, "status": OK, "text": f"{n} {noun}; nothing to compare."}
    c = _raw_pairs(exams)
    parts = [f"{c[0]} pair(s) on the same day" if c[0] else "none on the same day",
             f"{c[1]} pair(s) on consecutive days" if c[1] else "none on consecutive days"]
    if c[2]:
        parts.append(f"{c[2]} pair(s) two days apart")
    text = f"{n} {noun} checked: " + "; ".join(parts) + "."
    if issues:
        text += f" Reported: {_count_text(issues)}."
    elif c[0] or c[1]:
        text += " None reported (only pairs unlikely to be taken together)."
    return {"check": label, "status": _worst(issues), "text": text}


def year_status(res: ReviewResult, key) -> list[dict]:
    ctx = res.ctx
    prog, year = key
    scope = f"{prog}{year or ''}"
    mine = [i for i in res.issues if not i.accepted and i.scope == scope]
    lines: list[dict] = []

    # Coverage
    yp = ctx.plans.get(key)
    if ctx.review == "program":
        if yp is None or yp.plan is None:
            lines.append({"check": "Study-plan courses", "status": "warning",
                          "text": "No study plan available; coverage not checked."})
        else:
            periods = TERM_PERIODS[ctx.new.term[:2]]
            expected = yp.plan.expected(year, periods, yp.specialization)
            missing = [i for i in mine if i.check in ("coverage.missing-course", "coverage.group-empty")]
            n = len(expected)
            text = (f"All {n} courses in the {yp.cohort} study plan for {ctx.new.term} are scheduled."
                    if not missing else
                    f"{len(missing)} of {n} study-plan courses/groups not scheduled ({_count_text(missing)}).")
            lines.append({"check": "Study-plan courses", "status": _worst(missing), "text": text})

            ex = [i for i in mine if i.check in ("coverage.missing-exam", "coverage.missing-reexam")]
            text = ("Every course with an exam has an ordinary exam and a re-exam."
                    if not ex else f"{len(ex)} missing exam/re-exam ({_count_text(ex)}).")
            lines.append({"check": "Exams scheduled", "status": _worst(ex), "text": text})

    # Exam spacing within the year
    exams = ctx.new.exams(ctx.new.year_events.get(key, []))
    if ctx.courses:
        exams = [x for x in exams if x.course in ctx.courses]
    spacing = [i for i in mine if i.check == "exams.spacing"]
    ordinary = [x for x in exams if x.kind != "reexam"]
    reexams = [x for x in exams if x.kind == "reexam"]
    lines.append(_spacing_line("Exam spacing (ordinary exams and KS)", ordinary,
                               [i for i in spacing if "reexam" not in i.details.get("kinds", [])]))
    lines.append(_spacing_line("Re-exam spacing", reexams,
                               [i for i in spacing if "reexam" in i.details.get("kinds", [])]))

    # Re-exam paths from the year below
    prev = (prog, (year or 0) - 1)
    if year and year > 1 and prev in ctx.new.year_events:
        rp = [i for i in mine if i.check == "exams.reexam-path"]
        text = (f"No {scope} exams close in time to exams of year {year - 1} courses "
                "that students may be retaking." if not rp else
                f"{len(rp)} exam pair(s) close in time with year {year - 1} courses that {scope} "
                f"students may be retaking ({_count_text(rp)}).")
        lines.append({"check": f"Retaking year {year - 1} courses", "status": _worst(rp), "text": text})
    # Students of this year retaking it next year (shown from this year's side)
    nxt = (prog, (year or 0) + 1)
    if year and nxt in ctx.new.year_events:
        mine_codes = {c for e in ctx.new.year_events.get(key, []) for c in e.codes}
        rp = [i for i in res.issues if not i.accepted and i.check == "exams.reexam-path"
              and i.scope == f"{prog}{year + 1}"
              and set(i.details.get("courses", [])) & mine_codes]
        text = (f"No exams close in time for year {year + 1} students retaking {scope} courses."
                if not rp else
                f"{len(rp)} exam pair(s) close in time for year {year + 1} students retaking "
                f"{scope} courses ({_count_text(rp)}).")
        lines.append({"check": f"Retaken by year {year + 1}", "status": _worst(rp), "text": text})

    # Structure
    if ctx.old:
        codes = sorted({c for e in ctx.new.year_events.get(key, []) for c in e.codes if ctx.wants(c)})
        struct = [i for i in res.issues if not i.accepted and i.check.startswith("structure.")
                  and i.course in codes and i.severity != "info"]
        changed = sorted({i.course for i in struct})
        text = (f"{len(codes)} courses compared with {ctx.old.term}: all unchanged." if not changed else
                f"{len(codes)} courses compared with {ctx.old.term}: {len(changed)} with differences "
                f"to judge ({', '.join(changed)}).")
        lines.append({"check": f"Structure vs {ctx.old.term}", "status": _worst(struct), "text": text})
    return lines


def all_year_status(res: ReviewResult) -> dict[str, list[dict]]:
    return {f"{p}{y or ''}": year_status(res, (p, y)) for p, y in res.ctx.new.years()}
