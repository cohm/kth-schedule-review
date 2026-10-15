"""Programme review: all programme-year exports of a term vs. a reference term."""
from __future__ import annotations

from dataclasses import dataclass, field

from ..checks import Context, YearPlan, run_checks
from ..config import Config, apply_accepted
from ..i18n import T
from ..io.studyplan import PlanSource, PlanUnavailable, cohort_for
from ..model import Issue, severity_rank
from ..term import TermData


@dataclass
class ReviewResult:
    review: str
    title: str
    ctx: Context
    issues: list[Issue]
    notes: list[dict] = field(default_factory=list)   # {"sv", "en"} each

    def sorted_issues(self) -> list[Issue]:
        return sorted(self.issues, key=lambda i: (i.accepted is not None, severity_rank(i.severity),
                                                  i.scope, i.course or "", i.check))


def dedupe(issues: list[Issue]) -> list[Issue]:
    """Drop repeated issues (same check, scope, course and key)."""
    seen, out = set(), []
    for i in issues:
        k = (i.check, i.scope, i.course, i.key)
        if k in seen:
            continue
        seen.add(k)
        out.append(i)
    return out


def resolve_plans(td: TermData, source: PlanSource | None, program: str | None,
                  notes: list[str]) -> dict[tuple[str, int | None], YearPlan]:
    plans: dict[tuple[str, int | None], YearPlan] = {}
    for ex in td.exports:
        if ex.program is None or (program and ex.program != program):
            continue
        key = (ex.program, ex.year)
        if key in plans:
            continue
        if source is None or ex.year is None:
            plans[key] = YearPlan(ex.program, ex.year, ex.specialization, None, None,
                                  T("ingen källa för utbildningsplaner", "no study-plan source") if source is None
                                  else T("årskursen okänd", "programme year unknown"))
            continue
        cohort = cohort_for(td.term, ex.year)
        info = source.program_info(ex.program)
        try:
            plan = source.plan(ex.program, cohort)
        except PlanUnavailable as e:
            plans[key] = YearPlan(ex.program, ex.year, ex.specialization, cohort, None,
                                  T(f"hittades inte ({e})", str(e)))
            continue
        note = plan.year_confidence(ex.year)
        if info and not info.get("verified", False):
            notes.append(T(f"Utbildningsplanen för {ex.program} är inte markerad som verifierad i "
                           "ProgramVisualization; tolka resultaten om kurstäckning med försiktighet.",
                           f"Study plan data for {ex.program} is marked as not verified in "
                           "ProgramVisualization; treat coverage results with care."))
        if info and info.get("disabled"):
            notes.append(T(f"{ex.program} är inaktiverat i ProgramVisualization.",
                           f"{ex.program} is disabled in ProgramVisualization."))
        exact = note["en"] == "exact"
        plans[key] = YearPlan(ex.program, ex.year, ex.specialization, cohort, plan,
                              None if exact else note, approximated=note["en"].startswith("approximated"))
    return plans


def load_syllabi(ctx, syllabus_source, codes) -> None:
    """Fill ctx.syllabi for the given course codes (skipped without a source)."""
    if syllabus_source is None:
        return
    for code in sorted(codes):
        ctx.syllabi[code] = syllabus_source.get(code, ctx.new.term)
    ctx.syllabus_errors.update(syllabus_source.errors)


def program_review(new: TermData, old: TermData | None, config: Config,
                   source: PlanSource | None, program: str | None = None,
                   syllabus_source=None, room_source=None) -> ReviewResult:
    notes: list[str] = []
    plans = resolve_plans(new, source, program, notes)
    old_plans = resolve_plans(old, source, program, []) if old else {}
    if program:
        new.year_events = {k: v for k, v in new.year_events.items() if k[0] == program}
    ctx = Context("program", new, old, config, plans, old_plans, rooms=room_source)
    load_syllabi(ctx, syllabus_source, new.courses())
    issues = dedupe(run_checks(ctx))
    apply_accepted(issues, config.accepted)
    progs = sorted({k[0] for k in new.year_events})
    title = f"{', '.join(progs)} {new.term}" + (f" vs {old.term}" if old else "")
    for (p, y), yp in sorted(plans.items(), key=lambda kv: (kv[0][0], kv[0][1] or 0)):
        src = f" ({yp.plan.source})" if yp.plan else ""
        nt = yp.note or {}
        notes.append(T(f"{p}{y or ''}: utbildningsplan för kull {yp.cohort or '?'}"
                       + (f" — {nt['sv']}" if nt else "") + src,
                       f"{p}{y or ''}: study plan cohort {yp.cohort or '?'}"
                       + (f" — {nt['en']}" if nt else "") + src))
    unique = list({(n["sv"], n["en"]): n for n in notes}.values())
    return ReviewResult("program", title, ctx, issues, unique)
