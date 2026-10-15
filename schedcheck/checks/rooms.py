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

from ..i18n import T, both
from ..model import Issue
from ..term import is_exam_activity
from . import Context, register
from .structure import Occasion, abbrev, diff_course, occasions, week_label

LEVELS = ((0.6, "far-lower"), (0.8, "much-lower"), (0.9, "lower"))
INCREASE = 1.5
LEVEL_SEVERITY = {"far-lower": "warning", "much-lower": "review", "lower": "info", "higher": "info"}
LEVEL_TEXT = {"far-lower": T("minst 40 % färre", "≥40% fewer"), "much-lower": T("minst 20 % färre", "≥20% fewer"),
              "lower": T("minst 10 % färre", "≥10% fewer"), "higher": T("minst 50 % fler", "≥50% more")}
# Pair "mode" codes (details) -> text.
MODE_TEXT = {"now digital": T("nu digitalt", "now digital"),
             "no longer digital": T("inte längre digitalt", "no longer digital"),
             "no room booked": T("ingen lokal bokad", "no room booked")}


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
        ref = ctx.old.term

        def summary(lang):
            sv = lang == "sv"
            parts = [f"{n} {'med' if sv else 'with'} {LEVEL_TEXT[lv][lang]} {'platser' if sv else 'seats'}"
                     for lv, n in counts.items() if n]
            if no_room:
                parts.append(f"{len(no_room)} utan bokad lokal (hade lokal {ref})" if sv else
                             f"{len(no_room)} with no room booked (had rooms in {ref})")
            if modes:
                parts.append(f"{len(modes)} som bytt mellan digitalt och på campus" if sv else
                             f"{len(modes)} changed between digital and on campus")
            return ", ".join(parts)
        ex = sorted((p for p in flagged if p["level"] and p["level"] != "higher"),
                    key=lambda p: p["new"]["seats"] / p["old"]["seats"])[:4]
        ex_txt = "; ".join(f"{p['abbrev']} {p['new_date'][:10]}: {'+'.join(p['old']['rooms'])} "
                           f"{p['old']['seats']} → {'+'.join(p['new']['rooms'])} {p['new']['seats']}"
                           for p in ex)
        sm = both(summary)
        issues.append(Issue(worst, "rooms.capacity", code, code,
                            T(f"{code}: lokalernas platser jämfört med {ref} per tillfälle: {sm['sv']}"
                              + (f". Störst minskning: {ex_txt}." if ex_txt else "."),
                              f"{code}: room seats compared with {ref} per occasion: {sm['en']}"
                              + (f". Largest reductions: {ex_txt}." if ex_txt else ".")),
                            ask=T("Räcker platserna?", "Are there enough seats?"),
                            key="capacity", evidence=[p["cite"] for p in ex],
                            details={"counts": counts, "reference_term": ctx.old.term,
                                     "digital_changes": len(modes), "no_room": len(no_room),
                                     "largest": [{"activity": p["abbrev"], "date": p["new_date"],
                                                  "old_rooms": p["old"]["rooms"], "old_seats": p["old"]["seats"],
                                                  "new_rooms": p["new"]["rooms"], "new_seats": p["new"]["seats"]}
                                                 for p in ex]}))
    if unknown:
        why = {"unknown": T("som inte finns i KTH Places", "not found in KTH Places"),
               "no-seats": T("utan antal platser i KTH Places", "without a seat count in KTH Places"),
               "ambiguous": T("som matchar flera lokaler med olika antal platser i KTH Places",
                              "matching several rooms with different seat counts in KTH Places")}
        by_status: dict[str, list[str]] = {}
        for r in sorted(unknown):
            by_status.setdefault(ctx.rooms.lookup(r).status, []).append(r)

        def parts(lang):
            more = "till" if lang == "sv" else "more"
            return "; ".join(f"{len(rs)} {'lokal(er)' if lang == 'sv' else 'room(s)'} "
                             f"{why.get(st, T(st, st))[lang]} ({', '.join(rs[:12])}"
                             + (f" +{len(rs) - 12} {more})" if len(rs) > 12 else ")")
                             for st, rs in sorted(by_status.items()))
        ps = both(parts)
        issues.append(Issue("info", "rooms.unknown", ctx.new.term, None,
                            T(f"Platserna jämfördes inte för tillfällen i {ps['sv']}. Antal platser kan "
                              "anges i en lokalfil (--rooms).",
                              f"Room capacity not compared for occasions in {ps['en']}. Capacities can be "
                              "added in a rooms file (--rooms)."),
                            key="unknown", details={"rooms": {r: sorted(c) for r, c in unknown.items()}}))
    if getattr(ctx.rooms, "errors", None):
        errs = "; ".join(ctx.rooms.errors[:3])
        issues.append(Issue("info", "rooms.unavailable", ctx.new.term, None,
                            T(f"Viss data från KTH Places kunde inte läsas: {errs}",
                              f"Some KTH Places data could not be read: {errs}"),
                            key="errors"))
    return issues
