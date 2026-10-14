"""Data-quality checks on the schedule under review: things that are probably
clerical errors or that make the other checks less reliable.
"""
from __future__ import annotations

from collections import defaultdict

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
            issues.append(Issue("warning", "dataquality.round-term", code, code,
                                f"{len(evs)} {td.term} teaching row(s) reference course round {ref}, "
                                f"expected a {' or '.join(sorted(allowed))} round. "
                                "Possibly a stale round; check with the scheduler.",
                                key=ref, evidence=[e.cite() for e in evs[:3]]))
        else:
            issues.append(Issue("info", "dataquality.round-term", code, code,
                                f"{len(evs)} exam row(s) reference course round {ref} "
                                "(plausible for re-exams of an older round).",
                                key=ref, evidence=[e.cite() for e in evs[:3]]))

    # Ordinary exams without an exam module.
    for x in td.exams():
        if x.kind == "ordinary" and not x.event.exam_modules and ctx.wants(x.course):
            issues.append(Issue("info", "dataquality.no-exam-module", x.course, x.course,
                                f"{x.course}: {x.event.activity} on {x.date} has no exam module "
                                "(Examinationsmodul) set.", key=str(x.date),
                                evidence=[x.event.cite()]))

    if ctx.review != "program":
        return issues

    # Export date ranges: re-exam period must be covered.
    cal = td.calendar
    last_exam = max((w.end for w in cal.exam_windows), default=None)
    if last_exam and not any(w.start > last_exam for w in cal.reexam_windows):
        issues.append(Issue("warning", "dataquality.no-late-reexams", td.term, None,
                            "No re-exam window after the last exam period was found. The export's "
                            "date range probably ends too early (it should include the August "
                            "re-exam period).", key="range"))
    ranges = {(ex.range_start, ex.range_end) for ex in td.exports}
    if len(ranges) > 1:
        issues.append(Issue("info", "dataquality.ranges-differ", td.term, None,
                            "Exports have different date ranges: "
                            + "; ".join(f"{ex.label} {ex.range_start}..{ex.range_end}" for ex in td.exports),
                            key="ranges"))
    if td.dropped_out_of_term:
        n = len(td.dropped_out_of_term)
        first = min(e.date for e in td.dropped_out_of_term)
        issues.append(Issue("info", "dataquality.out-of-term", td.term, None,
                            f"{n} row(s) from {first} onward fall after the term's last "
                            f"exam/re-exam day ({cal.end}) and were ignored (next term).",
                            key="out-of-term"))
    for ex in td.exports:
        if ex.program is None:
            issues.append(Issue("warning", "dataquality.unknown-export", ex.path, None,
                                f"Could not identify programme/year of {ex.path} from its header.",
                                key=ex.path))

    # Comments already entered in the remiss column.
    for e in td.events:
        if e.comment and any(ctx.wants(c) for c in e.codes):
            issues.append(Issue("info", "dataquality.remiss-comment", e.codes[0], e.codes[0],
                                f"Existing remiss comment on {e.cite()}: “{e.comment}”",
                                key=f"{e.start}", evidence=[e.cite()]))
    return issues
