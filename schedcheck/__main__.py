"""Command-line interface: python3 -m schedcheck {program,course,dump} ..."""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

from .config import load_config
from .io.kursinfo import SyllabusSource
from .io.places import RoomSource, load_manual
from .io.studyplan import PlanSource
from .io.timeedit import read_folder
from .term import load_term


def _load(folder: str | None, program: str | None = None):
    """Read a folder of exports into TermData, optionally only one programme's."""
    if not folder:
        return None
    exports = read_folder(folder)
    if not exports:
        sys.exit(f"error: no .xlsx exports found in {folder}")
    if program:
        exports = [ex for ex in exports if ex.program == program]
        if not exports:
            return None
    return load_term(exports)


def _programs_in(folder: str) -> list[str]:
    return sorted({ex.program for ex in read_folder(folder) if ex.program})


def _rooms(args):
    if args.no_rooms or not args.old:
        return None
    return RoomSource(args.cache_dir, manual=load_manual(args.rooms))


def _write_outputs(res, args) -> None:
    from .report import comments, html, jsonout
    out = Path(args.out)
    paths = [jsonout.write(res, out), html.write(res, out), comments.write(res, out, args.lang)]
    print(jsonout.text_summary(res, show_info=args.verbose))
    print()
    for p in paths:
        print(f"wrote {p}")


def cmd_program(args) -> None:
    """One review per programme: each reads only its own programme's exports,
    so courses shared with other programmes don't leak into its comparison."""
    from .reviews.program import program_review
    programs = [args.program] if args.program else _programs_in(args.new)
    if not programs:
        sys.exit(f"error: no programme could be identified in the exports in {args.new}")
    source = None if args.no_plan else PlanSource(args.plan_source, args.cache_dir)
    syllabi = None if args.no_syllabus else SyllabusSource(args.cache_dir)
    rooms = _rooms(args)
    base_out = Path(args.out)
    for prog in programs:
        new = _load(args.new, prog)
        if new is None:
            sys.exit(f"error: no {prog} exports in {args.new}")
        old = _load(args.old, prog) if args.old else None
        if args.old and old is None:
            print(f"note: no {prog} exports in {args.old}; reviewing without a reference")
        cfg = load_config(prog, accepted_file=args.accepted)
        res = program_review(new, old, cfg, source, prog, syllabi, rooms)
        args.out = base_out / prog if len(programs) > 1 else base_out
        _write_outputs(res, args)
        print()
    args.out = base_out


def cmd_course(args) -> None:
    from .reviews.course import course_review
    new, old = _load(args.new), _load(args.old)
    cfg = load_config(None, accepted_file=args.accepted)
    syllabi = None if args.no_syllabus else SyllabusSource(args.cache_dir)
    res = course_review([c.upper() for c in args.codes], new, old, cfg, syllabi, _rooms(args))
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


def cmd_fetch(args) -> None:
    from .io import fetch
    cfg = fetch.load_config(args.config)
    try:
        labels = fetch.select_labels(cfg, args.programs)
    except ValueError as e:
        sys.exit(f"error: {e}")
    sets = []
    for spec, dest in ((args.new, args.new_dir), (args.old, args.old_dir)):
        if not spec:
            continue
        term, _, view = spec.partition(":")
        if not view:
            sys.exit(f"error: '{spec}': use TERM:VIEW, e.g. VT27:remiss")
        sets.append((term, view, dest or "{program}/{term}_{view}"))
    try:
        reqs = fetch.plan_requests(cfg, labels, sets)
    except ValueError as e:
        sys.exit(f"error: {e}")
    for r in reqs:
        print(f"{r['label']:8} {r['term']} {r['view']:7} -> {r['dest']}\n  {r['url']}")
    if args.print_only:
        return
    m = fetch.write_manifest(reqs, args.manifest)
    print(f"\nopening {len(reqs)} export(s) in your browser (log in to TimeEdit there if asked)…")
    fetch.open_in_browser([r["url"] for r in reqs], browser=args.browser)
    print(f"wrote {m}. When the downloads are done, run:\n"
          f"  python3 -m schedcheck collect --from <your download folder>")


def cmd_collect(args) -> None:
    from .io import fetch
    res = fetch.collect(args.src, args.manifest, copy=args.copy)
    for src, dest in res.filed:
        print(f"filed   {src.name} -> {dest}")
    for p, why in res.ignored:
        print(f"ignored {p.name}: {why}")
    for r in res.missing:
        print(f"MISSING {r['label']} {r['term']} {r['view']} ({r['start']}..{r['end']})")
    if res.missing:
        sys.exit(1)


def cmd_index(args) -> None:
    from .report.index import write_index
    print(f"wrote {write_index(args.folder, args.title)}")


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
        p.add_argument("--no-syllabus", action="store_true",
                       help="don't fetch syllabus exam modules from the kth.se course pages")
        p.add_argument("--no-rooms", action="store_true",
                       help="don't compare room capacities (read from KTH Places)")
        p.add_argument("--rooms", help="TOML file with manual room capacities ([capacity] \"NAME\" = seats)")
        p.add_argument("--cache-dir", help="where to cache downloaded study plans, syllabus and room data")

    p = sub.add_parser("program", help="programme review (all years of a programme)")
    common(p)
    p.add_argument("--program", help="review only this programme (default: every programme in "
                                     "the exports, one review each, in OUT/<PROG>/ when several)")
    p.add_argument("--plan-source", help="ProgramVisualization clone or base URL "
                                         "(default: GitHub raw, main branch)")
    p.add_argument("--no-plan", action="store_true", help="skip study-plan based checks")
    p.set_defaults(func=cmd_program)

    p = sub.add_parser("course", help="course-level review of one or more courses")
    p.add_argument("codes", nargs="+", help="course codes, e.g. SF1674")
    common(p)
    p.set_defaults(func=cmd_course)

    p = sub.add_parser("fetch", help="open TimeEdit exports in your browser (you stay logged in there)")
    p.add_argument("--config", required=True, help="TOML with base URL, views, object ids and term dates")
    p.add_argument("--new", required=True, metavar="TERM:VIEW", help="e.g. VT27:remiss")
    p.add_argument("--old", metavar="TERM:VIEW", help="reference, e.g. VT26:final")
    p.add_argument("--new-dir", help="folder for the new exports; may contain {program}, {term}, "
                                     "{view} (default: {program}/{term}_{view})")
    p.add_argument("--old-dir", help="folder for the reference exports (same placeholders)")
    p.add_argument("--programs", nargs="*", help="programmes (CTMAT) or programme years (CTMAT2) "
                                                 "to fetch (default: all in the config)")
    p.add_argument("--manifest", default=".schedcheck-fetch.json", help="where to record the request")
    p.add_argument("--print-only", action="store_true", help="only print the URLs")
    p.add_argument("--browser", help="browser to use, e.g. 'Safari' or 'Google Chrome' "
                                     "(default: the system default browser)")
    p.set_defaults(func=cmd_fetch)

    p = sub.add_parser("collect", help="file downloaded exports requested by 'fetch'")
    p.add_argument("--from", dest="src", required=True, help="download folder")
    p.add_argument("--manifest", default=".schedcheck-fetch.json")
    p.add_argument("--copy", action="store_true", help="copy instead of move")
    p.set_defaults(func=cmd_collect)

    p = sub.add_parser("index", help="write an index.html linking the reports in a folder's subfolders")
    p.add_argument("folder")
    p.add_argument("--title", default="Schedule reviews")
    p.set_defaults(func=cmd_index)

    p = sub.add_parser("dump", help="print parsed events per course (debugging)")
    p.add_argument("folder")
    p.add_argument("--course", nargs="*", help="only these courses")
    p.set_defaults(func=cmd_dump)

    args = ap.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
