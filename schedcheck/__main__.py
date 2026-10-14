"""Command-line interface: python3 -m schedcheck {program,course,dump} ..."""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

from .config import load_config
from .io.studyplan import PlanSource
from .io.timeedit import read_folder
from .term import load_term


def _load(folder: str | None):
    if not folder:
        return None
    exports = read_folder(folder)
    if not exports:
        sys.exit(f"error: no .xlsx exports found in {folder}")
    return load_term(exports)


def _write_outputs(res, args) -> None:
    from .report import comments, html, jsonout
    out = Path(args.out)
    paths = [jsonout.write(res, out), html.write(res, out), comments.write(res, out, args.lang)]
    print(jsonout.text_summary(res, show_info=args.verbose))
    print()
    for p in paths:
        print(f"wrote {p}")


def cmd_program(args) -> None:
    from .reviews.program import program_review
    new, old = _load(args.new), _load(args.old)
    programs = sorted({ex.program for ex in new.exports if ex.program})
    program = args.program or (programs[0] if len(programs) == 1 else None)
    cfg = load_config(program, accepted_file=args.accepted)
    source = None if args.no_plan else PlanSource(args.plan_source, args.cache_dir)
    res = program_review(new, old, cfg, source, args.program)
    _write_outputs(res, args)


def cmd_course(args) -> None:
    from .reviews.course import course_review
    new, old = _load(args.new), _load(args.old)
    cfg = load_config(None, accepted_file=args.accepted)
    res = course_review([c.upper() for c in args.codes], new, old, cfg)
    _write_outputs(res, args)


def cmd_dump(args) -> None:
    td = _load(args.folder)
    cal = td.calendar
    print(f"term {cal.term}: {cal.start}..{cal.end}")
    for p, s, e in cal.periods:
        print(f"  period {p}: {s}..{e}")
    for w in cal.exam_windows + cal.reexam_windows:
        print(f"  {w.kind:7} {w.start}..{w.end}  {w.label}")
    for ex in td.exports:
        print(f"export {ex.path}: {ex.label} {ex.range_start}..{ex.range_end}, {len(ex.events)} rows")
    by_course = defaultdict(list)
    for e in td.events:
        for c in e.codes:
            by_course[c].append(e)
    for code in sorted(by_course):
        if args.course and code not in args.course:
            continue
        evs = by_course[code]
        print(f"\n{code} ({len(evs)} rows)")
        for e in evs:
            tw = cal.teaching_week(e.date)
            tws = f"{tw[0]}w{tw[1]:<2}" if tw else "     "
            print(f"  {e.start:%Y-%m-%d %a %H:%M}-{e.end:%H:%M} {tws} {e.activity:18} "
                  f"{', '.join(e.groups)[:40]:40} {', '.join(e.exam_modules)}")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="schedcheck", description="Review KTH TimeEdit schedule exports.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--new", required=True, help="folder with the exports under review")
        p.add_argument("--old", help="folder with reference exports (e.g. last year's final schedule)")
        p.add_argument("--out", default="reports", help="output folder (default: reports)")
        p.add_argument("--accepted", help="TOML file with accepted differences for this review")
        p.add_argument("--lang", choices=["sv", "en"], default="sv", help="language of comment drafts")
        p.add_argument("-v", "--verbose", action="store_true", help="also print info-level issues")

    p = sub.add_parser("program", help="programme review (all years of a programme)")
    common(p)
    p.add_argument("--program", help="programme code (default: read from the exports)")
    p.add_argument("--plan-source", help="ProgramVisualization clone or base URL "
                                         "(default: GitHub raw, main branch)")
    p.add_argument("--cache-dir", help="where to cache downloaded study plans")
    p.add_argument("--no-plan", action="store_true", help="skip study-plan based checks")
    p.set_defaults(func=cmd_program)

    p = sub.add_parser("course", help="course-level review of one or more courses")
    p.add_argument("codes", nargs="+", help="course codes, e.g. SF1674")
    common(p)
    p.set_defaults(func=cmd_course)

    p = sub.add_parser("dump", help="print parsed events per course (debugging)")
    p.add_argument("folder")
    p.add_argument("--course", nargs="*", help="only these courses")
    p.set_defaults(func=cmd_dump)

    args = ap.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
