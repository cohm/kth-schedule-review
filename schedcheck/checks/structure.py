"""Check 2: each course's teaching structure compared with the reference term.

Rows are first collapsed into *occasions*: within one course, ISO week and
activity type, whole-class rows are one occasion each, while rows for
sub-groups ("grupp A", "grupp B-D", ...) running in parallel are merged; the
number of occasions is how many times the busiest group meets that week.

The ordered sequence of occasion activity types is then aligned between the
two terms with difflib, giving counts, insertions/deletions/reorderings and
week shifts.
"""
from __future__ import annotations

import difflib
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from ..model import Event, Issue
from ..term import REEXAM_ACTIVITY_PREFIXES, TermData
from . import Context, register

WHOLE_CLASS_MARKERS = ("helklass", "whole class")
WEEK_SHIFT_THRESHOLD = 2


@dataclass
class Occasion:
    course: str
    activity: str
    week: tuple[str, int] | None        # (period, teaching week)
    events: list[Event] = field(default_factory=list)
    parallel: int = 1                   # number of parallel sessions (group split)

    @property
    def first(self) -> Event:
        return self.events[0]

    def label(self) -> str:
        p = f" ×{self.parallel}" if self.parallel > 1 else ""
        w = week_label(self.week)
        return f"{w} {self.activity}{p}"


def week_label(week) -> str:
    if not week:
        return "?"
    return f"{week[0]} exams" if week[1] == 0 else f"{week[0]} w{week[1]}"


def _is_whole_class(e: Event) -> bool:
    return not e.groups or any(g.casefold().endswith(WHOLE_CLASS_MARKERS) for g in e.groups)


def occasions(td: TermData, code: str) -> list[Occasion]:
    evs = [e for e in td.course_events(code)
           if not e.activity.casefold().startswith(REEXAM_ACTIVITY_PREFIXES)
           and not (td.calendar.window_of(e.date) and td.calendar.window_of(e.date).kind == "reexam")]
    buckets: dict[tuple, list[Event]] = defaultdict(list)
    for e in evs:
        iso = tuple(e.date.isocalendar()[:2])
        buckets[(iso, e.activity)].append(e)

    def week_of(e: Event):
        # Occasions inside an exam window are placed in the period's exam
        # slot (week 0) rather than a teaching week.
        w = td.calendar.window_of(e.date)
        if w and w.kind == "exam":
            return (td.calendar.period_of(e.date), 0)
        return td.calendar.teaching_week(e.date)

    out: list[Occasion] = []
    for (iso, act), es in buckets.items():
        es.sort(key=lambda e: e.start)
        whole = [e for e in es if _is_whole_class(e)]
        split = [e for e in es if not _is_whole_class(e)]
        for e in whole:
            out.append(Occasion(code, act, week_of(e), [e]))
        if split:
            per_group: Counter = Counter(g for e in split for g in e.groups)
            n = max(per_group.values())
            # Distribute the split rows over n occasions in time order; each
            # occasion gets the rows covering one meeting of every group.
            chunks: list[list[Event]] = [[] for _ in range(n)]
            seen_count: Counter = Counter()
            for e in split:
                i = min(max(seen_count[g] for g in e.groups), n - 1)
                chunks[i].append(e)
                for g in e.groups:
                    seen_count[g] += 1
            for ch in chunks:
                if ch:
                    out.append(Occasion(code, act, week_of(ch[0]),
                                        ch, parallel=len(ch)))
    out.sort(key=lambda o: o.first.start)
    return out


@dataclass
class CourseDiff:
    code: str
    old: list[Occasion]
    new: list[Occasion]
    opcodes: list[tuple[str, int, int, int, int]]
    counts: dict[str, tuple[int, int]]   # activity -> (old, new)

    @property
    def changed(self) -> bool:
        return any(tag != "equal" for tag, *_ in self.opcodes)


def diff_course(old_td: TermData, new_td: TermData, code: str) -> CourseDiff:
    o, n = occasions(old_td, code), occasions(new_td, code)
    sm = difflib.SequenceMatcher(a=[x.activity for x in o], b=[x.activity for x in n], autojunk=False)
    co, cn = Counter(x.activity for x in o), Counter(x.activity for x in n)
    counts = {a: (co.get(a, 0), cn.get(a, 0)) for a in sorted(set(co) | set(cn))}
    return CourseDiff(code, o, n, sm.get_opcodes(), counts)


ABBREV = {"föreläsning": "F", "övning": "Ö", "laboration": "L", "datorlaboration": "DL",
          "seminarium": "S", "lektion": "Le", "tentamen": "TEN", "kontrollskrivning": "KS",
          "räknestuga": "R", "redovisning": "Red", "workshop": "W", "projektarbete": "P",
          "examination": "EX", "övrigt": "Övr", "information": "Info"}


def abbrev(activity: str) -> str:
    return ABBREV.get(activity.casefold(), activity)


def week_sequences(occ: list[Occasion]) -> dict[tuple[str, int] | None, list[str]]:
    out: dict = defaultdict(list)
    for o in occ:
        out[o.week].append(abbrev(o.activity) + (f"×{o.parallel}" if o.parallel > 1 else ""))
    return out


def _describe_ops(d: CourseDiff, limit: int = 6) -> list[str]:
    """Week-by-week description of differences: 'P4 w4: F Ö F → F F Ö'."""
    wo, wn = week_sequences(d.old), week_sequences(d.new)
    keys = sorted({k for k in wo} | {k for k in wn}, key=lambda k: (k is None, k or ("", 0)))
    out = []
    for k in keys:
        a = [x.split("×")[0] for x in wo.get(k, [])]
        b = [x.split("×")[0] for x in wn.get(k, [])]
        if a != b:
            wk = week_label(k)
            out.append(f"{wk}: {' '.join(a) or '–'} → {' '.join(b) or '–'}")
    if len(out) > limit:
        out = out[:limit] + [f"… {len(out) - limit} more weeks differ"]
    return out


@register("structure", ("program", "course"), "Teaching structure compared with the reference term")
def check_structure(ctx: Context) -> list[Issue]:
    if ctx.old is None:
        return []
    issues: list[Issue] = []
    new_courses = {c for c in ctx.new.courses() if ctx.wants(c)}
    old_courses = {c for c in ctx.old.courses() if ctx.wants(c)}

    def taught(td: TermData, code: str) -> bool:
        return bool(occasions(td, code))

    for code in sorted(new_courses | old_courses):
        in_new, in_old = taught(ctx.new, code), taught(ctx.old, code)
        if in_old and not in_new:
            issues.append(Issue("review", "structure.course-gone", code, code,
                                f"{code} had teaching in {ctx.old.term} but none in {ctx.new.term}.",
                                key=code))
            continue
        if in_new and not in_old:
            issues.append(Issue("review", "structure.course-new", code, code,
                                f"{code} has teaching in {ctx.new.term} but had none in {ctx.old.term}.",
                                key=code))
            continue
        if not in_new:
            continue

        d = diff_course(ctx.old, ctx.new, code)
        details = {
            "counts": {a: list(v) for a, v in d.counts.items()},
            "old": [_occ_dict(x) for x in d.old],
            "new": [_occ_dict(x) for x in d.new],
            "opcodes": [list(op) for op in d.opcodes],
            "weeks": _describe_ops(d, limit=100),
            "reference_term": ctx.old.term,
        }
        count_changes = {a: v for a, v in d.counts.items() if v[0] != v[1]}
        if count_changes:
            txt = "; ".join(f"{a} {o}→{n}" for a, (o, n) in count_changes.items())
            issues.append(Issue("review", "structure.counts", code, code,
                                f"{code}: number of occasions changed ({ctx.old.term}→{ctx.new.term}): {txt}.",
                                key=",".join(f"{a}:{o}>{n}" for a, (o, n) in count_changes.items()),
                                details=details))
        elif d.changed:
            issues.append(Issue("review", "structure.order", code, code,
                                f"{code}: same occasions, different order. "
                                + "; ".join(_describe_ops(d)) + ".",
                                key="order", details=details))
        if count_changes and d.changed:
            # Attach the sequence diff to the counts issue for context.
            issues[-1].message += " By week: " + "; ".join(_describe_ops(d)) + "."

        # Without a study plan (course review) nothing else notices a lost exam.
        if ctx.review == "course":
            had = [x for x in ctx.old.exams(ctx.old.course_events(code)) if x.kind == "ordinary"]
            has = [x for x in ctx.new.exams(ctx.new.course_events(code)) if x.kind == "ordinary"]
            if had and not has:
                issues.append(Issue("warning", "structure.exam-gone", code, code,
                                    f"{code} had an ordinary exam in {ctx.old.term} "
                                    f"({had[0].date}) but has none in an exam window in {ctx.new.term}.",
                                    key=code, evidence=[x.event.cite() for x in had[:2]]))

        # Week shifts within aligned stretches.
        shifts = []
        for tag, i1, i2, j1, j2 in d.opcodes:
            if tag != "equal":
                continue
            for a, b in zip(d.old[i1:i2], d.new[j1:j2]):
                if a.week and b.week and a.week[0] == b.week[0] and (a.week[1] == 0) == (b.week[1] == 0):
                    delta = b.week[1] - a.week[1]
                    if abs(delta) >= WEEK_SHIFT_THRESHOLD:
                        shifts.append((a, b, delta))
                elif a.week and b.week and a.week != b.week:
                    shifts.append((a, b, None))
        if shifts:
            desc = "; ".join(
                f"{a.activity} {week_label(a.week)}→{week_label(b.week)}" for a, b, _ in shifts[:6])
            more = f" (+{len(shifts) - 6} more)" if len(shifts) > 6 else ""
            issues.append(Issue("review", "structure.week-shift", code, code,
                                f"{code}: {len(shifts)} occasion(s) moved ≥{WEEK_SHIFT_THRESHOLD} teaching "
                                f"weeks: {desc}{more}.", key=f"shifts:{len(shifts)}",
                                evidence=[b.first.cite() for _, b, _ in shifts[:6]],
                                details={"weeks": details["weeks"], "reference_term": ctx.old.term}))

        # Parallel-group changes (e.g. exercises split into fewer groups).
        par_old = Counter()
        par_new = Counter()
        for x in d.old:
            par_old[x.activity] = max(par_old[x.activity], x.parallel)
        for x in d.new:
            par_new[x.activity] = max(par_new[x.activity], x.parallel)
        par_changes = {a: (par_old[a], par_new[a]) for a in set(par_old) & set(par_new)
                       if par_old[a] != par_new[a]}
        if par_changes:
            txt = "; ".join(f"{a} {o}→{n}" for a, (o, n) in sorted(par_changes.items()))
            issues.append(Issue("info", "structure.parallel-groups", code, code,
                                f"{code}: max number of parallel group sessions changed: {txt}.",
                                key=txt))

        # Exam modules on ordinary exams.
        mods_old = {m for x in ctx.old.exams(ctx.old.course_events(code)) if x.kind == "ordinary"
                    for m in x.event.exam_modules}
        mods_new = {m for x in ctx.new.exams(ctx.new.course_events(code)) if x.kind == "ordinary"
                    for m in x.event.exam_modules}
        if mods_old and mods_new and mods_old != mods_new:
            issues.append(Issue("review", "structure.exam-modules", code, code,
                                f"{code}: exam modules on ordinary exams changed: "
                                f"{', '.join(sorted(mods_old))} → {', '.join(sorted(mods_new))}.",
                                key=f"{','.join(sorted(mods_old))}>{','.join(sorted(mods_new))}",
                                details={"old": sorted(mods_old), "new": sorted(mods_new)}))
    return issues


def _occ_dict(o: Occasion) -> dict:
    return {
        "activity": o.activity, "week": list(o.week) if o.week else None,
        "date": o.first.start.strftime("%Y-%m-%d %H:%M"), "parallel": o.parallel,
        "groups": sorted({g for e in o.events for g in e.groups}),
        "cite": o.first.cite(),
    }
