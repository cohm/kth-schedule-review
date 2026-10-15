"""Per-programme-year check status: what was checked and what came out,
stated explicitly also when nothing was found ("no clashes" is a result).

Each line is {"check": {"sv", "en"}, "status": severity or "ok", "text": {"sv", "en"}}.
"""
from __future__ import annotations

from collections import Counter

from ..calendar import TERM_PERIODS
from ..i18n import SEVERITY, T, both
from ..model import severity_rank
from ..reviews.program import ReviewResult

OK = "ok"


def _worst(issues) -> str:
    sev = [i.severity for i in issues]
    return min(sev, key=severity_rank) if sev else OK


def _count_text(issues, lang: str) -> str:
    c = Counter(i.severity for i in issues)
    return ", ".join(f"{c[s]} {SEVERITY[s][lang].lower()}" for s in ("error", "warning", "review", "info") if c[s])


def _counts(issues) -> dict:
    return both(lambda lang: _count_text(issues, lang))


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


def _spacing_line(label: dict, exams: list, issues: list) -> dict:
    n = len({(x.course, x.event.start) for x in exams})
    if n < 2:
        return {"check": label, "status": OK,
                "text": T(f"{n} {'tentamen' if n == 1 else 'tentamina'}; inget att jämföra.",
                          f"{n} {'exam' if n == 1 else 'exams'}; nothing to compare.")}
    c = _raw_pairs(exams)
    cnt = _counts(issues)

    def text(lang):
        sv = lang == "sv"
        parts = [(f"{c[0]} par samma dag" if sv else f"{c[0]} pair(s) on the same day") if c[0]
                 else ("inga samma dag" if sv else "none on the same day"),
                 (f"{c[1]} par dagar i rad" if sv else f"{c[1]} pair(s) on consecutive days") if c[1]
                 else ("inga dagar i rad" if sv else "none on consecutive days")]
        if c[2]:
            parts.append(f"{c[2]} par med en dag emellan" if sv else f"{c[2]} pair(s) two days apart")
        t = (f"{n} tentamina kontrollerade: " if sv else f"{n} exams checked: ") + "; ".join(parts) + "."
        if issues:
            t += (f" Rapporterat: {cnt[lang]}." if sv else f" Reported: {cnt[lang]}.")
        elif c[0] or c[1]:
            t += (" Inget rapporterat (bara par som sällan läses tillsammans)." if sv else
                  " None reported (only pairs unlikely to be taken together).")
        return t
    return {"check": label, "status": _worst(issues), "text": both(text)}


def year_status(res: ReviewResult, key) -> list[dict]:
    ctx = res.ctx
    prog, year = key
    scope = f"{prog}{year or ''}"
    mine = [i for i in res.issues if not i.accepted and i.scope == scope]
    lines: list[dict] = []

    # Coverage
    yp = ctx.plans.get(key)
    if ctx.review == "program":
        label = T("Kurser i utbildningsplanen", "Study-plan courses")
        if yp is None or yp.plan is None:
            lines.append({"check": label, "status": "warning",
                          "text": T("Ingen utbildningsplan tillgänglig; kurstäckningen kontrollerades inte.",
                                    "No study plan available; coverage not checked.")})
        else:
            periods = TERM_PERIODS[ctx.new.term[:2]]
            expected = yp.plan.expected(year, periods, yp.specialization)
            missing = [i for i in mine if i.check in ("coverage.missing-course", "coverage.group-empty")]
            n, t, cnt = len(expected), ctx.new.term, _counts(missing)
            text = (T(f"Alla {n} kurser i utbildningsplanen för kull {yp.cohort} för {t} är schemalagda.",
                      f"All {n} courses in the {yp.cohort} study plan for {t} are scheduled.")
                    if not missing else
                    T(f"{len(missing)} av {n} kurser/kursgrupper i utbildningsplanen är inte schemalagda "
                      f"({cnt['sv']}).",
                      f"{len(missing)} of {n} study-plan courses/groups not scheduled ({cnt['en']})."))
            lines.append({"check": label, "status": _worst(missing), "text": text})

            ex = [i for i in mine if i.check in ("coverage.missing-exam", "coverage.missing-reexam")]
            cnt = _counts(ex)
            text = (T("Varje kurs med tentamen har en ordinarie tentamen och en omtentamen.",
                      "Every course with an exam has an ordinary exam and a re-exam.")
                    if not ex else
                    T(f"{len(ex)} saknad(e) tentamen/omtentamen ({cnt['sv']}).",
                      f"{len(ex)} missing exam/re-exam ({cnt['en']})."))
            lines.append({"check": T("Schemalagda tentamina", "Exams scheduled"),
                          "status": _worst(ex), "text": text})

    # Exam spacing within the year
    exams = ctx.new.exams(ctx.new.year_events.get(key, []))
    if ctx.courses:
        exams = [x for x in exams if x.course in ctx.courses]
    spacing = [i for i in mine if i.check == "exams.spacing"]
    ordinary = [x for x in exams if x.kind != "reexam"]
    reexams = [x for x in exams if x.kind == "reexam"]
    lines.append(_spacing_line(T("Avstånd mellan tentamina (ordinarie och KS)",
                                 "Exam spacing (ordinary exams and KS)"), ordinary,
                               [i for i in spacing if "reexam" not in i.details.get("kinds", [])]))
    lines.append(_spacing_line(T("Avstånd mellan omtentor", "Re-exam spacing"), reexams,
                               [i for i in spacing if "reexam" in i.details.get("kinds", [])]))

    # Teaching overlaps
    from ..checks.teaching import overlapping_pairs
    planned = set(yp.plan.courses) if yp and yp.plan else None
    raw = list(overlapping_pairs(ctx.new.year_events.get(key, []), planned))
    if ctx.courses:
        raw = [(a, b) for a, b in raw if set(a.codes + b.codes) & ctx.courses]
    tov = [i for i in mine if i.check == "teaching.overlap"]
    n_sessions = len({(e.start, e.row) for e in ctx.new.year_events.get(key, [])
                      if e.codes or e.other_codes})
    cnt = _counts(tov)
    if not raw:
        text = T(f"{n_sessions} tillfällen kontrollerade: inga tillfällen i olika kurser krockar.",
                 f"{n_sessions} sessions checked: no two sessions of different courses overlap.")
    else:
        text = T(f"{n_sessions} tillfällen kontrollerade: {len(raw)} par av tillfällen krockar"
                 + (f"; rapporterat för {len(tov)} kurspar ({cnt['sv']})." if tov else
                    "; inga mellan kurser som sannolikt läses samtidigt."),
                 f"{n_sessions} sessions checked: {len(raw)} overlapping session pair(s)"
                 + (f"; reported for {len(tov)} course pair(s) ({cnt['en']})." if tov else
                    "; none between courses likely to be taken together."))
    selfov = [i for i in mine if i.check == "teaching.self-overlap"]
    if selfov:
        k = sum(i.details["count"] for i in selfov)
        cs = ", ".join(sorted(i.course for i in selfov))
        text = T(text["sv"] + f" Inom en kurs: {k} par av tillfällen krockar i {cs}.",
                 text["en"] + f" Within a course: {k} overlapping session pair(s) in {cs}.")
    else:
        text = T(text["sv"] + " Ingen kurs krockar med sig själv.",
                 text["en"] + " No course overlaps with itself.")
    lines.append({"check": T("Krockar i undervisningen", "Teaching overlaps"),
                  "status": _worst(tov + selfov), "text": text})

    # Re-exam paths from the year below
    prev = (prog, (year or 0) - 1)
    if year and year > 1 and prev in ctx.new.year_events:
        rp = [i for i in mine if i.check == "exams.reexam-path"]
        cnt, y0 = _counts(rp), year - 1
        text = (T(f"Inga tentamina för {scope} ligger nära tentamina i kurser från årskurs {y0} "
                  "som studenter kan behöva tentera om.",
                  f"No {scope} exams close in time to exams of year {y0} courses "
                  "that students may be retaking.") if not rp else
                T(f"{len(rp)} par av tentamina ligger nära kurser från årskurs {y0} som studenter i {scope} "
                  f"kan behöva tentera om ({cnt['sv']}).",
                  f"{len(rp)} exam pair(s) close in time with year {y0} courses that {scope} "
                  f"students may be retaking ({cnt['en']})."))
        lines.append({"check": T(f"Omtentor från årskurs {y0}", f"Retaking year {y0} courses"),
                      "status": _worst(rp), "text": text})
    # Students of this year retaking it next year (shown from this year's side)
    nxt = (prog, (year or 0) + 1)
    if year and nxt in ctx.new.year_events:
        mine_codes = {c for e in ctx.new.year_events.get(key, []) for c in e.codes}
        rp = [i for i in res.issues if not i.accepted and i.check == "exams.reexam-path"
              and i.scope == f"{prog}{year + 1}"
              and set(i.details.get("courses", [])) & mine_codes]
        cnt, y1 = _counts(rp), year + 1
        text = (T(f"Inga tentamina ligger nära i tid för studenter i årskurs {y1} som tenterar om "
                  f"kurser från {scope}.",
                  f"No exams close in time for year {y1} students retaking {scope} courses.")
                if not rp else
                T(f"{len(rp)} par av tentamina ligger nära i tid för studenter i årskurs {y1} som tenterar "
                  f"om kurser från {scope} ({cnt['sv']}).",
                  f"{len(rp)} exam pair(s) close in time for year {y1} students retaking "
                  f"{scope} courses ({cnt['en']})."))
        lines.append({"check": T(f"Omtentor i årskurs {y1}", f"Retaken by year {y1}"),
                      "status": _worst(rp), "text": text})

    # Structure
    if ctx.old:
        ref = ctx.old.term
        codes = sorted({c for e in ctx.new.year_events.get(key, []) for c in e.codes if ctx.wants(c)})
        struct = [i for i in res.issues if not i.accepted and i.check.startswith("structure.")
                  and i.course in codes and i.severity != "info"]
        changed = sorted({i.course for i in struct})
        n, cs = len(codes), ", ".join(changed)
        text = (T(f"{n} {'kurs' if n == 1 else 'kurser'} jämförda med {ref}: antal och ordning av "
                  "tillfällen oförändrade.",
                  f"{n} course{'s' if n != 1 else ''} compared with {ref}: number and order of "
                  "occasions unchanged.")
                if not changed else
                T(f"{n} {'kurs' if n == 1 else 'kurser'} jämförda med {ref}: {len(changed)} med skillnader "
                  f"att bedöma ({cs}).",
                  f"{n} course{'s' if n != 1 else ''} compared with {ref}: {len(changed)} with differences "
                  f"to judge ({cs})."))
        lines.append({"check": T(f"Struktur jämfört med {ref}", f"Structure vs {ref}"),
                      "status": _worst(struct), "text": text})

        # Room capacity
        cmp = {c: ctx.room_comparison[c] for c in codes if c in ctx.room_comparison}
        if cmp:
            rooms = [i for i in res.issues if not i.accepted and i.check == "rooms.capacity"
                     and i.course in cmp and i.severity != "info"]
            n_occ = sum(len(v["pairs"]) for v in cmp.values())
            rs = ", ".join(sorted(i.course for i in rooms))
            text = T(f"{n_occ} tillfällen i {len(cmp)} kurser jämförda med {ref}: "
                     + ("inget tillfälle har minst 20 % färre platser." if not rooms else
                        f"{len(rooms)} kurs(er) med minst 20 % färre platser vid något tillfälle ({rs})."),
                     f"{n_occ} occasions in {len(cmp)} courses compared with {ref}: "
                     + ("no occasion has ≥20% fewer seats." if not rooms else
                        f"{len(rooms)} course(s) with ≥20% fewer seats on some occasion ({rs})."))
            lines.append({"check": T(f"Lokalplatser jämfört med {ref}", f"Room seats vs {ref}"),
                          "status": _worst(rooms), "text": text})
    return lines


def all_year_status(res: ReviewResult) -> dict[str, list[dict]]:
    return {f"{p}{y or ''}": year_status(res, (p, y)) for p, y in res.ctx.new.years()}
