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


def _week_order(k) -> tuple:
    """Sort key for week keys: by period, teaching weeks first, exam slot last."""
    if k is None:
        return (1, "", 0)
    return (0, k[0], 99 if k[1] == 0 else k[1])


@dataclass
class Changes:
    """How a course's occasions differ, per teaching week."""
    reordered: list[tuple]   # (week, old seq, new seq): same activities, other order
    moved: list[tuple]       # (from week, to week, [activities])
    added: list[tuple]       # (week, [activities])
    removed: list[tuple]     # (week, [activities])

    def empty(self) -> bool:
        return not (self.reordered or self.moved or self.added or self.removed)


def classify_changes(d: CourseDiff) -> Changes:
    """Split week-level differences into moves, within-week reorders, additions
    and removals. A session that disappears from one week and an identical
    activity that appears in another is a move (paired with the nearest week)."""
    wo, wn = week_sequences(d.old), week_sequences(d.new)
    keys = sorted(set(wo) | set(wn), key=_week_order)
    pos = {k: i for i, k in enumerate(keys)}
    reordered, delta = [], defaultdict(Counter)   # activity -> week -> +/-n
    for k in keys:
        a = [x.split("×")[0] for x in wo.get(k, [])]
        b = [x.split("×")[0] for x in wn.get(k, [])]
        if a == b:
            continue
        ca, cb = Counter(a), Counter(b)
        if ca == cb:
            reordered.append((k, a, b))
            continue
        for act, n in (cb - ca).items():
            delta[act][k] += n
        for act, n in (ca - cb).items():
            delta[act][k] -= n

    moved: dict[tuple, list[str]] = defaultdict(list)
    added: dict = defaultdict(list)
    removed: dict = defaultdict(list)
    for act, per_week in delta.items():
        gone = sorted((k for k, n in per_week.items() for _ in range(-n) if n < 0), key=_week_order)
        new = sorted((k for k, n in per_week.items() for _ in range(n) if n > 0), key=_week_order)
        for g in gone:
            if new:
                nearest = min(new, key=lambda k: abs(pos[k] - pos[g]))
                new.remove(nearest)
                moved[(g, nearest)].append(act)
            else:
                removed[g].append(act)
        for k in new:
            added[k].append(act)
    return Changes(
        reordered,
        [(f, t, acts) for (f, t), acts in sorted(moved.items(), key=lambda kv: _week_order(kv[0][0]))],
        sorted(added.items(), key=lambda kv: _week_order(kv[0])),
        sorted(removed.items(), key=lambda kv: _week_order(kv[0])),
    )


def describe_changes(c: Changes, limit: int = 6) -> list[str]:
    out = []
    for f, t, acts in c.moved:
        out.append(f"moved {week_label(f)} → {week_label(t)}: {' '.join(acts)}")
    for k, a, b in c.reordered:
        out.append(f"reordered within {week_label(k)}: {' '.join(a)} → {' '.join(b)}")
    for k, acts in c.added:
        out.append(f"added in {week_label(k)}: {' '.join(acts)}")
    for k, acts in c.removed:
        out.append(f"removed from {week_label(k)}: {' '.join(acts)}")
    if len(out) > limit:
        out = out[:limit] + [f"… and {len(out) - limit} more"]
    return out


def changes_dict(c: Changes) -> dict:
    return {
        "moved": [{"from": list(f) if f else None, "to": list(t) if t else None, "activities": acts}
                  for f, t, acts in c.moved],
        "reordered": [{"week": list(k) if k else None, "old": a, "new": b} for k, a, b in c.reordered],
        "added": [{"week": list(k) if k else None, "activities": acts} for k, acts in c.added],
        "removed": [{"week": list(k) if k else None, "activities": acts} for k, acts in c.removed],
    }


def sequence_hunks(d: CourseDiff, context: int = 2) -> list[dict]:
    """Differences between the old and new sequences of occasions, ignoring
    how they are spread over weeks. Each hunk has the changed stretch with a
    little context; changed parts are bracketed, '[–]' marks nothing there.
    'where' is the first and last week of the changed occasions (new term if
    any, else reference term)."""
    a = [abbrev(o.activity) for o in d.old]
    b = [abbrev(o.activity) for o in d.new]
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    hunks = []
    for group in sm.get_grouped_opcodes(context):
        # Bracket the whole changed stretch (first to last change in the
        # group) as one unit, so a swap reads "[Ö F] -> [F Ö]".
        ch = [op for op in group if op[0] != "equal"]
        i_lo, i_hi = ch[0][1], ch[-1][2]
        j_lo, j_hi = ch[0][3], ch[-1][4]
        i_start, j_start = group[0][1], group[0][3]
        i_end, j_end = group[-1][2], group[-1][4]
        old_parts = a[i_start:i_lo] + ["[" + (" ".join(a[i_lo:i_hi]) or "–") + "]"] + a[i_hi:i_end]
        new_parts = b[j_start:j_lo] + ["[" + (" ".join(b[j_lo:j_hi]) or "–") + "]"] + b[j_hi:j_end]
        changed_new, changed_old = d.new[j_lo:j_hi], d.old[i_lo:i_hi]
        occ = changed_new or changed_old
        weeks = [o.week for o in occ if o.week]
        hunks.append({
            "old": " ".join(old_parts), "new": " ".join(new_parts),
            "starts": group[0][1] == 0 and group[0][3] == 0,
            "ends": group[-1][2] == len(a) and group[-1][4] == len(b),
            "where": [list(weeks[0]), list(weeks[-1])] if weeks else None,
            "term": "new" if changed_new else "reference",
        })
    return hunks


def _where(w, label=None) -> str:
    label = label or week_label
    if not w:
        return "?"
    a, b = (tuple(x) for x in w)
    if a == b:
        return label(a)
    if a[0] == b[0] and a[1] and b[1]:
        return f"{label(a)}–w{b[1]}" if label is week_label else f"{label(a)}–{b[1]}"
    return f"{label(a)}–{label(b)}"


def describe_hunks(hunks: list[dict], limit: int = 4, label=None) -> list[str]:
    out = []
    for h in hunks[:limit]:
        pre = "" if h["starts"] else "… "
        post = "" if h["ends"] else " …"
        out.append(f"{_where(h['where'], label)}: {pre}{h['old']}{post} → {pre}{h['new']}{post}")
    if len(hunks) > limit:
        out.append(f"… and {len(hunks) - limit} more")
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
        hunks = sequence_hunks(d)
        details = {
            "counts": {a: list(v) for a, v in d.counts.items()},
            "old": [_occ_dict(x) for x in d.old],
            "new": [_occ_dict(x) for x in d.new],
            "sequence": hunks,
            "week_changes": changes_dict(classify_changes(d)),
            "reference_term": ctx.old.term,
        }
        # What matters to teachers is the number of occasions and their order
        # (e.g. F Ö F F Ö ...), not how that sequence is spread over weeks;
        # large shifts in time are reported separately (week-shift).
        count_changes = {a: v for a, v in d.counts.items() if v[0] != v[1]}
        desc = "; ".join(describe_hunks(hunks))
        if count_changes:
            txt = "; ".join(f"{a} {o}→{n}" for a, (o, n) in count_changes.items())
            issues.append(Issue("review", "structure.counts", code, code,
                                f"{code}: number of occasions changed ({ctx.old.term}→{ctx.new.term}): "
                                f"{txt}. Sequence: {desc}.",
                                key=",".join(f"{a}:{o}>{n}" for a, (o, n) in count_changes.items()),
                                details=details))
        elif hunks:
            issues.append(Issue("review", "structure.order", code, code,
                                f"{code}: same occasions in a different order: {desc}.",
                                key="order", details=details))

        # Without a study plan (course review) nothing else notices a lost exam.
        if ctx.review == "course":
            had = [x for x in ctx.old.exams(ctx.old.course_events(code)) if x.kind == "ordinary"]
            has = [x for x in ctx.new.exams(ctx.new.course_events(code)) if x.kind == "ordinary"]
            if not has:
                from .syllabus import exam_reasons
                reasons, ref = exam_reasons(ctx, code)
                if reasons:
                    issues.append(Issue("warning", "structure.exam-gone", code, code,
                                        f"{code} has no ordinary exam in an exam window in {ctx.new.term}, "
                                        f"but {'; '.join(reasons)}.",
                                        key=code, details=ref, evidence=[x.event.cite() for x in had[:2]]))

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
                                details={"reference_term": ctx.old.term}))

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
