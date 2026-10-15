"""Data-quality checks on the schedule under review: things that are probably
clerical errors or that make the other checks less reliable.
"""
from __future__ import annotations

import datetime as dt

from collections import defaultdict

from ..i18n import T, both
from ..model import Issue
from ..term import REEXAM_ACTIVITY_PREFIXES, is_exam_activity
from . import Context, register


def _allowed_round_terms(term: str) -> set[str]:
    """Round terms plausible for teaching in `term`.

    VT27 teaching may belong to a VT27 round or to a course round that
    started HT26; HT26 teaching to HT26 only.
    """
    yy = int(term[2:])
    if term.startswith("VT"):
        return {f"VT{yy:02d}", f"HT{yy - 1:02d}"}
    return {f"HT{yy:02d}"}


@register("dataquality", ("program", "course"), "Clerical problems in the export")
def check_dataquality(ctx: Context) -> list[Issue]:
    td = ctx.new
    issues: list[Issue] = []
    allowed = _allowed_round_terms(td.term)

    # Round codes from another term.
    odd: dict[tuple[str, str], list] = defaultdict(list)
    for e in td.events:
        is_re = e.activity.casefold().startswith(REEXAM_ACTIVITY_PREFIXES)
        for c in e.courses:
            if c.round_term and c.round_term not in allowed and ctx.wants(c.code):
                odd[(str(c), "reexam" if is_re or is_exam_activity(e.activity) else "teaching")].append(e)
    for (ref, kind), evs in sorted(odd.items()):
        code = ref.split("-")[0]
        if kind == "teaching":
            n = len(evs)
            issues.append(Issue("warning", "dataquality.round-term", code, code,
                                T(f"{n} undervisningsrad(er) {td.term} är kopplade till kurstillfälle {ref}, "
                                  f"väntat var ett tillfälle {' eller '.join(sorted(allowed))}. "
                                  "Troligen ett gammalt tillfälle.",
                                  f"{n} {td.term} teaching row(s) reference course round {ref}, "
                                  f"expected a {' or '.join(sorted(allowed))} round. "
                                  "Possibly a stale round; check with the scheduler."),
                                ask=T("Ska de kopplas till innevarande kurstillfälle?",
                                      "Should they be linked to the current course round?"),
                                key=ref, evidence=[e.cite() for e in evs[:3]]))
        else:
            issues.append(Issue("info", "dataquality.round-term", code, code,
                                T(f"{len(evs)} examinationsrad(er) är kopplade till kurstillfälle {ref} "
                                  "(rimligt för omtentor av ett äldre tillfälle).",
                                  f"{len(evs)} exam row(s) reference course round {ref} "
                                  "(plausible for re-exams of an older round)."),
                                key=ref, evidence=[e.cite() for e in evs[:3]]))

    # Ordinary exams without an exam module.
    for x in td.exams():
        if x.kind == "ordinary" and not x.event.exam_modules and ctx.wants(x.course):
            issues.append(Issue("info", "dataquality.no-exam-module", x.course, x.course,
                                T(f"{x.course}: {x.event.activity} {x.date} saknar examinationsmodul.",
                                  f"{x.course}: {x.event.activity} on {x.date} has no exam module "
                                  "(Examinationsmodul) set."), key=str(x.date),
                                evidence=[x.event.cite()]))

    if ctx.review != "program":
        return issues

    # Export date ranges: re-exam period must be covered.
    cal = td.calendar
    last_exam = max((w.end for w in cal.exam_windows), default=None)
    if last_exam and not any(w.start > last_exam for w in cal.reexam_windows):
        issues.append(Issue("warning", "dataquality.no-late-reexams", td.term, None,
                            T("Ingen omtentaperiod efter den sista tentamensperioden hittades. Exportens "
                              "datumintervall slutar troligen för tidigt (det ska omfatta omtentaperioden "
                              "i augusti).",
                              "No re-exam window after the last exam period was found. The export's "
                              "date range probably ends too early (it should include the August "
                              "re-exam period)."),
                            ask=T("Kontrollera datumintervallet och exportera igen.",
                                  "Check the date range and export again."), key="range"))
    ranges = {(ex.range_start, ex.range_end) for ex in td.exports}
    if len(ranges) > 1:
        rs = "; ".join(f"{ex.label} {ex.range_start}..{ex.range_end}" for ex in td.exports)
        issues.append(Issue("info", "dataquality.ranges-differ", td.term, None,
                            T(f"Exporterna har olika datumintervall: {rs}",
                              f"Exports have different date ranges: {rs}"), key="ranges"))
    # The remiss can change during the review period, so exports of one
    # review should be taken at the same time.
    times = [ex.exported_at for ex in td.exports if ex.exported_at]
    if times and max(times) - min(times) > dt.timedelta(hours=1):
        from ..io.timeedit import export_time_text
        lst = both(lambda lang: "; ".join(f"{ex.label} {export_time_text([ex], lang)}" for ex in td.exports))
        issues.append(Issue("info", "dataquality.export-times", td.term, None,
                            T(f"Exporterna togs vid olika tidpunkter ({lst['sv']}); schemat kan ha ändrats "
                              "däremellan. Exportera alla tillsammans om du är osäker.",
                              f"The exports were taken at different times ({lst['en']}); the schedule may "
                              "have changed in between. Re-export together if in doubt."), key="times"))
    if td.dropped_out_of_term:
        n = len(td.dropped_out_of_term)
        first = min(e.date for e in td.dropped_out_of_term)
        issues.append(Issue("info", "dataquality.out-of-term", td.term, None,
                            T(f"{n} rad(er) från {first} och framåt ligger efter terminens sista "
                              f"tentamens-/omtentamensdag ({cal.end}) och ignorerades (nästa termin).",
                              f"{n} row(s) from {first} onward fall after the term's last "
                              f"exam/re-exam day ({cal.end}) and were ignored (next term)."),
                            key="out-of-term"))
    for ex in td.exports:
        if ex.program is None:
            issues.append(Issue("warning", "dataquality.unknown-export", ex.path, None,
                                T(f"Kunde inte avgöra program/årskurs för {ex.path} från dess huvud.",
                                  f"Could not identify programme/year of {ex.path} from its header."),
                                key=ex.path))

    # Comments already entered in the remiss column.
    for e in td.events:
        if e.comment and any(ctx.wants(c) for c in e.codes):
            issues.append(Issue("info", "dataquality.remiss-comment", e.codes[0], e.codes[0],
                                T(f"Befintlig remisskommentar på {e.cite()}: ”{e.comment}”",
                                  f"Existing remiss comment on {e.cite()}: “{e.comment}”"),
                                key=f"{e.start}", evidence=[e.cite()]))
    return issues
