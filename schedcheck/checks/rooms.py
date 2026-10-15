"""Room capacity per occasion compared with the reference term.

Occasions are paired between the terms by the same sequence alignment as
the structure check (only occasions in unchanged stretches are paired). For
each occasion the seats of all rooms booked for it are summed, over all
parallel group sessions (a room booked for two sessions at the same time
counts once). The ratio new/old is graded:

    <= 0.9  lower (yellow)   <= 0.8  much lower (orange)   <= 0.6  far lower (red)
    >= 1.5  much higher (highlighted)

Exams are left out: their rooms are booked centrally, for many courses at
once. Rooms are looked up in KTH Places (io/places.py); occasions with a
room that cannot be found are not compared.
"""
from __future__ import annotations

from ..model import Issue
from ..term import is_exam_activity
from . import Context, register
from .structure import Occasion, abbrev, diff_course, occasions, week_label

LEVELS = ((0.6, "far-lower"), (0.8, "much-lower"), (0.9, "lower"))
INCREASE = 1.5
LEVEL_SEVERITY = {"far-lower": "warning", "much-lower": "review", "lower": "info", "higher": "info"}
LEVEL_TEXT = {"far-lower": "≥40% fewer", "much-lower": "≥20% fewer", "lower": "≥10% fewer",
              "higher": "≥50% more"}


def grade(old: int, new: int) -> str | None:
    if old <= 0:
        return None
    r = new / old
    for lim, name in LEVELS:
        if r <= lim:
            return name
    return "higher" if r >= INCREASE else None


def occasion_capacity(o: Occasion, rooms) -> dict:
    """Seats booked for an occasion: {seats, rooms, unknown, digital}."""
    seen: set[tuple] = set()
    seats, names, unknown, digital, physical, no_room = 0, [], [], False, False, False
    for e in o.events:
        for name in _split(e.room):
            info = rooms.lookup(name)
            if info.status == "digital":
                digital = True
                continue
            physical = True
            if (e.start, name) in seen:
                continue
            seen.add((e.start, name))
            if name not in names:
                names.append(name)
            if info.seats is None:
                unknown.append(name)
            else:
                seats += info.seats
        if not e.room.strip():
            no_room = True    # e.g. not yet assigned in a remiss
    return {"seats": None if unknown or no_room or not physical else seats, "rooms": names,
            "unknown": sorted(set(unknown)), "digital": digital and not physical, "no_room": no_room}


def _split(field: str) -> list[str]:
    from ..io.places import split_rooms
    return split_rooms(field)


def compare_course(ctx: Context, code: str) -> dict | None:
    """Paired occasions with seats in both terms, or None if not comparable."""
    d = diff_course(ctx.old, ctx.new, code)
    pairs = []
    for tag, i1, i2, j1, j2 in d.opcodes:
        if tag != "equal":
            continue
        for ia, ib in zip(range(i1, i2), range(j1, j2)):
            a, b = d.old[ia], d.new[ib]
            if is_exam_activity(a.activity):
                continue
            ca, cb = occasion_capacity(a, ctx.rooms), occasion_capacity(b, ctx.rooms)
            lvl = None
            if ca["seats"] is not None and cb["seats"] is not None:
                lvl = grade(ca["seats"], cb["seats"])
            mode = None
            if ca["digital"] != cb["digital"]:
                mode = "now digital" if cb["digital"] else "no longer digital"
            elif cb["no_room"] and ca["seats"] is not None:
                mode = "no room booked"     # e.g. not yet assigned in the remiss
            pairs.append({"activity": a.activity, "abbrev": abbrev(a.activity),
                          "old_index": ia, "new_index": ib,
                          "old_week": week_label(a.week), "new_week": week_label(b.week),
                          "old_date": f"{a.first.start:%Y-%m-%d %H:%M}",
                          "new_date": f"{b.first.start:%Y-%m-%d %H:%M}",
                          "old": ca, "new": cb, "level": lvl, "mode": mode,
                          "cite": b.first.cite()})
    if not pairs:
        return None
    return {"pairs": pairs, "reference_term": ctx.old.term}


@register("rooms", ("program", "course"), "Room capacity per occasion compared with the reference term")
def check_rooms(ctx: Context) -> list[Issue]:
    if ctx.old is None or ctx.rooms is None:
        return []
    issues: list[Issue] = []
    unknown: dict[str, set[str]] = {}
    codes = sorted(c for c in ctx.new.courses() & ctx.old.courses() if ctx.wants(c))
    for code in codes:
        if not occasions(ctx.new, code) or not occasions(ctx.old, code):
            continue
        cmp = compare_course(ctx, code)
        if cmp is None:
            continue
        ctx.room_comparison[code] = cmp
        for p in cmp["pairs"]:
            for side in ("old", "new"):
                for r in p[side]["unknown"]:
                    unknown.setdefault(r, set()).add(code)
        flagged = [p for p in cmp["pairs"] if p["level"] or p["mode"]]
        if not flagged:
            continue
        no_room = [p for p in flagged if p["mode"] == "no room booked"]
        modes = [p for p in flagged if p["mode"] and p not in no_room]
        worst = min([LEVEL_SEVERITY[p["level"]] for p in flagged if p["level"]]
                    + (["review"] if no_room else []),
                    key=("warning", "review", "info").index, default="info")
        counts = {lv: sum(1 for p in flagged if p["level"] == lv) for lv in LEVEL_TEXT}
        summary = ", ".join(f"{n} with {LEVEL_TEXT[lv]} seats" for lv, n in counts.items() if n)
        if no_room:
            summary += (", " if summary else "") + (f"{len(no_room)} with no room booked "
                                                    f"(had rooms in {ctx.old.term})")
        if modes:
            summary += (", " if summary else "") + f"{len(modes)} changed between digital and on campus"
        ex = sorted((p for p in flagged if p["level"] and p["level"] != "higher"),
                    key=lambda p: p["new"]["seats"] / p["old"]["seats"])[:4]
        ex_txt = "; ".join(f"{p['abbrev']} {p['new_date'][:10]}: {'+'.join(p['old']['rooms'])} "
                           f"{p['old']['seats']} → {'+'.join(p['new']['rooms'])} {p['new']['seats']}"
                           for p in ex)
        issues.append(Issue(worst, "rooms.capacity", code, code,
                            f"{code}: room seats compared with {ctx.old.term} per occasion: {summary}"
                            + (f". Largest reductions: {ex_txt}." if ex_txt else "."),
                            key="capacity", evidence=[p["cite"] for p in ex],
                            details={"counts": counts, "reference_term": ctx.old.term,
                                     "digital_changes": len(modes), "no_room": len(no_room),
                                     "largest": [{"activity": p["abbrev"], "date": p["new_date"],
                                                  "old_rooms": p["old"]["rooms"], "old_seats": p["old"]["seats"],
                                                  "new_rooms": p["new"]["rooms"], "new_seats": p["new"]["seats"]}
                                                 for p in ex]}))
    if unknown:
        why = {"unknown": "not found in KTH Places", "no-seats": "without a seat count in KTH Places",
               "ambiguous": "matching several rooms with different seat counts in KTH Places"}
        by_status: dict[str, list[str]] = {}
        for r in sorted(unknown):
            by_status.setdefault(ctx.rooms.lookup(r).status, []).append(r)
        parts = [f"{len(rs)} room(s) {why.get(st, st)} ({', '.join(rs[:12])}"
                 + (f" +{len(rs) - 12} more)" if len(rs) > 12 else ")")
                 for st, rs in sorted(by_status.items())]
        issues.append(Issue("info", "rooms.unknown", ctx.new.term, None,
                            "Room capacity not compared for occasions in " + "; ".join(parts)
                            + ". Capacities can be added in a rooms file (--rooms).",
                            key="unknown", details={"rooms": {r: sorted(c) for r, c in unknown.items()}}))
    if getattr(ctx.rooms, "errors", None):
        issues.append(Issue("info", "rooms.unavailable", ctx.new.term, None,
                            "Some KTH Places data could not be read: " + "; ".join(ctx.rooms.errors[:3]),
                            key="errors"))
    return issues
