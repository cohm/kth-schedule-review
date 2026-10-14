"""Teaching overlaps: sessions of courses taken in parallel must not overlap in time.

Within each programme year, any two scheduled sessions (lectures, exercises,
labs, seminars, KS, ...) of different courses that overlap in time are a
clash for students taking both. Severity:

  base, by who is affected
    both whole-class ........................... error
    one session group-split (some students) .... warning
    both group-split (groups may be disjoint) .. info

  softened (in steps) by how likely students take both courses
    both mandatory / programme activity ........ 0
    both required for the same master .......... 0
    one mandatory, one elective ................ 1
    unknown to the study plan .................. 1
    electives, same subject prefix ............. 1
    other electives ............................ not reported (counted in the summary)

  optional-attendance activities (räknestuga, ...) one further step;
  elective pairs overlapping no more than in the reference term one further
  step (a known pattern rather than a new problem).

Overlaps are reported once per course pair, with all overlapping sessions.
Not clashes: one session listed under several codes (shared teaching) and
re-exams (those students are not taking the course this term).
"""
from __future__ import annotations

from collections import defaultdict

from ..model import Event, Issue
from ..term import REEXAM_ACTIVITY_PREFIXES, course_prefix
from . import Context, register
from .exams import LADDER, _category, _eligibility, soften

OPTIONAL_ACTIVITIES = ("räknestuga", "övrigt", "projektarbete", "eget arbete", "frivillig",
                       "öppet hus", "mässa")
WHOLE_CLASS_MARKERS = ("helklass", "whole class")


def _is_whole_class(e: Event) -> bool:
    return not e.groups or any(g.casefold().endswith(WHOLE_CLASS_MARKERS) for g in e.groups)


def _is_optional(e: Event) -> bool:
    return e.activity.casefold().startswith(OPTIONAL_ACTIVITIES)


def _units(e: Event, planned: set[str] | None = None) -> list[str]:
    """Course codes, or other codes (programme activities such as 8XCTFYS).

    When a row lists several codes and some are in the study plan, only those
    count: the others are alternative codes for the same teaching (e.g.
    DD232V next to DD2352, or a doctoral variant next to a course).
    """
    codes = e.codes or e.other_codes
    if planned and len(codes) > 1:
        known = [c for c in codes if c in planned]
        if known:
            return known
    return codes


def _shared(a: Event, b: Event) -> bool:
    """Same session listed separately under different codes."""
    return a is b or (a.start == b.start and a.end == b.end and a.room and a.room == b.room
                      and a.activity == b.activity)


def overlapping_pairs(events: list[Event], planned: set[str] | None = None):
    """Yield (a, b) for events overlapping in time, different units, not shared."""
    evs = sorted((e for e in events
                  if _units(e) and not e.activity.casefold().startswith(REEXAM_ACTIVITY_PREFIXES)),
                 key=lambda e: e.start)
    for i, a in enumerate(evs):
        for b in evs[i + 1:]:
            if b.start >= a.end:
                break
            if set(_units(a, planned)) & set(_units(b, planned)) or _shared(a, b):
                continue
            yield a, b


def pair_counts(events: list[Event], planned: set[str] | None = None) -> dict[tuple[str, str], int]:
    out: dict = defaultdict(int)
    for a, b in overlapping_pairs(events, planned):
        for ca in _units(a, planned):
            for cb in _units(b, planned):
                out[tuple(sorted((ca, cb)))] += 1
    return out


@register("teaching", ("program", "course"), "Overlapping sessions of courses taken in parallel")
def check_teaching(ctx: Context) -> list[Issue]:
    issues: list[Issue] = []
    for key in sorted(ctx.new.year_events, key=lambda k: (k[0], k[1] or 0)):
        prog, year = key
        scope = f"{prog}{year or ''}"
        yp = ctx.plans.get(key)
        elig = _eligibility(ctx, yp)
        planned = set(yp.plan.courses) if yp and yp.plan else None
        old_yp = ctx.old_plans.get(key)
        old_planned = set(old_yp.plan.courses) if old_yp and old_yp.plan else None
        old_counts = pair_counts(ctx.old.year_events.get(key, []), old_planned) if ctx.old else {}

        def cat(code):
            if not code[:2].isalpha():
                # Activity codes: 8X<PROG> is this programme's own activity
                # (e.g. term-start information) and counts as mandatory; other
                # ones (e.g. shared degree-project slots for many programmes)
                # are treated like courses outside the study plan.
                return "programme" if code[2:] == prog else "unknown"
            return _category(yp, code)

        # Collect overlapping sessions per course pair, with the worst base severity.
        pairs: dict[tuple[str, str], list[tuple[Event, Event, str]]] = defaultdict(list)
        for a, b in overlapping_pairs(ctx.new.year_events.get(key, []), planned):
            wa, wb = _is_whole_class(a), _is_whole_class(b)
            base = "error" if wa and wb else ("warning" if wa or wb else "info")
            if _is_optional(a) or _is_optional(b):
                base = soften(base, 1)
            if base is None:
                continue
            for ca in _units(a, planned):
                for cb in _units(b, planned):
                    if not (ctx.wants(ca) or ctx.wants(cb)):
                        continue
                    (x, ex), (y, ey) = sorted([(ca, a), (cb, b)], key=lambda t: t[0])
                    pairs[(x, y)].append((ex, ey, base))

        for (x, y), sessions in sorted(pairs.items()):
            cx, cy = cat(x), cat(y)
            mand = {"mandatory", "programme"}
            shared = [m for m, cs in elig.items() if x in cs and y in cs]
            if cx in mand and cy in mand:
                steps, rel, relation = 0, "Both are mandatory for this programme year.", "mandatory"
            elif shared:
                steps, rel, relation = 0, (f"Both are required for eligibility to "
                                           f"{', '.join(sorted(shared))}."), "eligibility:" + ",".join(sorted(shared))
            elif cx in mand or cy in mand:
                steps, rel, relation = 1, "One mandatory course and one elective.", "mandatory+elective"
            elif "unknown" in (cx, cy):
                steps, rel, relation = 1, "At least one course is not in the study plan for this year.", "unplanned"
            elif course_prefix(x) == course_prefix(y):
                steps, rel, relation = 1, (f"Electives in the same subject ({course_prefix(x)}), "
                                           "plausibly taken together."), "same-subject"
            else:
                continue  # unrelated electives: only counted in the status summary
            worst = min((s for _, _, s in sessions), key=LADDER.index)
            n_old = old_counts.get((x, y), 0)
            # Elective pairs that overlapped at least as much last year are a
            # known pattern, not a new problem: one step softer.
            if steps > 0 and n_old >= len(sessions):
                steps += 1
            sev = soften(worst, steps)
            if sev is None:
                continue
            hist = (f" The same pair overlapped {n_old} time(s) in {ctx.old.term}." if n_old
                    else (f" No overlap in {ctx.old.term}." if ctx.old else ""))
            listed = "; ".join(f"{ea.start:%a %Y-%m-%d %H:%M}-{max(ea.end, eb.end):%H:%M} "
                               f"{ea.activity} / {eb.activity}" for ea, eb, _ in sessions[:4])
            more = f" (+{len(sessions) - 4} more)" if len(sessions) > 4 else ""
            issues.append(Issue(
                sev, "teaching.overlap", scope, x,
                f"{x} and {y}: {len(sessions)} overlapping session(s): {listed}{more}. {rel}{hist}",
                key=f"{x}+{y}",
                evidence=[e.cite() for ea, eb, _ in sessions[:3] for e in (ea, eb)],
                details={"courses": [x, y], "count": len(sessions), "relation": relation,
                         "reference_count": n_old,
                         "reference_term": ctx.old.term if ctx.old else None,
                         "sessions": [{"date": f"{ea.start:%Y-%m-%d}",
                                       "times": [f"{ea.start:%H:%M}-{ea.end:%H:%M}",
                                                 f"{eb.start:%H:%M}-{eb.end:%H:%M}"],
                                       "activities": [ea.activity, eb.activity],
                                       "whole_class": [_is_whole_class(ea), _is_whole_class(eb)]}
                                      for ea, eb, _ in sessions]},
            ))
    return issues
