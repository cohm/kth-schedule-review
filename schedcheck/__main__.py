"""Command-line interface: python3 -m schedcheck {program,course,fetch,collect,index,dump} ...

Language: --lang sv|en (before or after the subcommand), else the
environment variable SCHEDCHECK_LANG, else Swedish. It sets the CLI's
messages and help, the comment drafts and the report's initial language.
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from pathlib import Path

from .config import load_config
from .i18n import DEFAULT, LANGS, env_lang
from .io.kursinfo import SyllabusSource
from .io.places import RoomSource, load_manual
from .io.studyplan import PlanSource
from .io.timeedit import read_folder
from .term import load_term


LANG = DEFAULT


def t(sv: str, en: str) -> str:
    """The CLI's text in the selected language."""
    return sv if LANG == "sv" else en


def _err(e) -> str:
    text = getattr(e, "text", None)
    return text[LANG] if isinstance(text, dict) else str(e)


def _load(folder: str | None, program: str | None = None):
    """Read a folder of exports into TermData, optionally only one programme's."""
    if not folder:
        return None
    exports = read_folder(folder)
    if not exports:
        sys.exit(t(f"fel: inga .xlsx-exporter i {folder}", f"error: no .xlsx exports found in {folder}"))
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


def _link(td, args, view) -> None:
    """Add TimeEdit schedule links to the exports (needs --timeedit)."""
    if td is None or not args.timeedit:
        return
    from .io import fetch
    fetch.link_exports(td.exports, fetch.load_config(args.timeedit), view)


def _write_outputs(res, args) -> None:
    from .report import comments, html, jsonout
    out = Path(args.out)
    paths = [jsonout.write(res, out), html.write(res, out, LANG), comments.write(res, out, LANG)]
    print(jsonout.text_summary(res, show_info=args.verbose, lang=LANG))
    print()
    for p in paths:
        print(t(f"skrev {p}", f"wrote {p}"))


def cmd_program(args) -> None:
    """One review per programme: each reads only its own programme's exports,
    so courses shared with other programmes don't leak into its comparison."""
    from .reviews.program import program_review
    programs = [args.program] if args.program else _programs_in(args.new)
    if not programs:
        sys.exit(t(f"fel: inget program kunde identifieras i exporterna i {args.new}",
                   f"error: no programme could be identified in the exports in {args.new}"))
    source = None if args.no_plan else PlanSource(args.plan_source, args.cache_dir)
    syllabi = None if args.no_syllabus else SyllabusSource(args.cache_dir)
    rooms = _rooms(args)
    base_out = Path(args.out)
    for prog in programs:
        new = _load(args.new, prog)
        if new is None:
            sys.exit(t(f"fel: inga exporter för {prog} i {args.new}", f"error: no {prog} exports in {args.new}"))
        old = _load(args.old, prog) if args.old else None
        _link(new, args, args.new_view)
        _link(old, args, args.old_view)
        if args.old and old is None:
            print(t(f"obs: inga exporter för {prog} i {args.old}; granskar utan referens",
                    f"note: no {prog} exports in {args.old}; reviewing without a reference"))
        cfg = load_config(prog, accepted_file=args.accepted)
        res = program_review(new, old, cfg, source, prog, syllabi, rooms)
        args.out = base_out / prog if len(programs) > 1 else base_out
        _write_outputs(res, args)
        print()
    args.out = base_out


def cmd_course(args) -> None:
    from .reviews.course import course_review
    new, old = _load(args.new), _load(args.old)
    _link(new, args, args.new_view)
    _link(old, args, args.old_view)
    cfg = load_config(None, accepted_file=args.accepted)
    syllabi = None if args.no_syllabus else SyllabusSource(args.cache_dir)
    res = course_review([c.upper() for c in args.codes], new, old, cfg, syllabi, _rooms(args))
    _write_outputs(res, args)


def cmd_dump(args) -> None:
    td = _load(args.folder)
    cal = td.calendar
    print(f"{t('termin', 'term')} {cal.term}: {cal.start}..{cal.end}")
    for p, s, e in cal.periods:
        print(f"  {t('läsperiod', 'period')} {p}: {s}..{e}")
    for w in cal.exam_windows + cal.reexam_windows:
        print(f"  {w.kind:7} {w.start}..{w.end}  {w.text(LANG)}")
    for ex in td.exports:
        print(f"export {ex.path}: {ex.label} {ex.range_start}..{ex.range_end}, "
              f"{len(ex.events)} {t('rader', 'rows')}")
    by_course = defaultdict(list)
    for e in td.events:
        for c in e.codes:
            by_course[c].append(e)
    for code in sorted(by_course):
        if args.course and code not in args.course:
            continue
        evs = by_course[code]
        print(f"\n{code} ({len(evs)} {t('rader', 'rows')})")
        for e in evs:
            tw = cal.teaching_week(e.date)
            tws = f"{tw[0]}{t('v', 'w')}{tw[1]:<2}" if tw else "     "
            print(f"  {e.start:%Y-%m-%d %a %H:%M}-{e.end:%H:%M} {tws} {e.activity:18} "
                  f"{', '.join(e.groups)[:40]:40} {', '.join(e.exam_modules)}")


def cmd_fetch(args) -> None:
    from .io import fetch
    try:
        cfg = fetch.load_config(args.config)
        labels = fetch.select_labels(cfg, args.programs)
    except ValueError as e:
        sys.exit(t("fel: ", "error: ") + _err(e))
    sets = []
    for spec, dest in ((args.new, args.new_dir), (args.old, args.old_dir)):
        if not spec:
            continue
        term, _, view = spec.partition(":")
        if not view:
            sys.exit(t(f"fel: '{spec}': ange TERMIN:VY, t.ex. VT27:remiss",
                       f"error: '{spec}': use TERM:VIEW, e.g. VT27:remiss"))
        sets.append((term, view, dest or "{program}/{term}_{view}"))
    try:
        reqs = fetch.plan_requests(cfg, labels, sets)
    except ValueError as e:
        sys.exit(t("fel: ", "error: ") + _err(e))
    for r in reqs:
        print(f"{r['label']:8} {r['term']} {r['view']:7} -> {r['dest']}\n  {r['url']}")
    if args.print_only:
        return
    m = fetch.write_manifest(reqs, args.manifest)
    print(t(f"\nöppnar {len(reqs)} export(er) i webbläsaren (logga in i TimeEdit där om du ombeds)…",
            f"\nopening {len(reqs)} export(s) in your browser (log in to TimeEdit there if asked)…"))
    fetch.open_in_browser([r["url"] for r in reqs], browser=args.browser)
    print(t(f"skrev {m}. När nedladdningarna är klara, kör:\n"
            "  python3 -m schedcheck collect --from <din nedladdningsmapp>",
            f"wrote {m}. When the downloads are done, run:\n"
            "  python3 -m schedcheck collect --from <your download folder>"))


def cmd_collect(args) -> None:
    from .io import fetch
    res = fetch.collect(args.src, args.manifest, copy=args.copy)
    for src, dest in res.filed:
        print(f"{t('arkiverad', 'filed'):10} {src.name} -> {dest}")
    for p, why in res.ignored:
        print(f"{t('ignorerad', 'ignored'):10} {p.name}: {why[LANG]}")
    for r in res.missing:
        print(f"{t('SAKNAS', 'MISSING'):10} {r['label']} {r['term']} {r['view']} ({r['start']}..{r['end']})")
    if res.missing:
        sys.exit(1)


def cmd_index(args) -> None:
    from .report.index import write_index
    from .i18n import T
    title = (T(args.title, args.title_en or args.title) if args.title
             else T("Schemagranskningar", "Schedule reviews"))
    print(t("skrev ", "wrote ") + str(write_index(args.folder, title, LANG)))


def _pre_lang(argv) -> str:
    """The language for help texts, known before argparse runs."""
    argv = list(sys.argv[1:] if argv is None else argv)
    for i, a in enumerate(argv):
        if a == "--lang" and i + 1 < len(argv) and argv[i + 1] in LANGS:
            return argv[i + 1]
        if a.startswith("--lang=") and a[7:] in LANGS:
            return a[7:]
    return env_lang()


def main(argv=None) -> None:
    global LANG
    LANG = _pre_lang(argv)
    lang_help = t("språk: sv (standard) eller en; även SCHEDCHECK_LANG",
                  "language: sv (default) or en; also SCHEDCHECK_LANG")
    ap = argparse.ArgumentParser(prog="schedcheck", description=t(
        "Granska scheman exporterade ur KTH:s TimeEdit.", "Review KTH TimeEdit schedule exports."))
    ap.add_argument("--lang", choices=LANGS, default=None, help=lang_help)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def lang_opt(p):
        p.add_argument("--lang", choices=LANGS, default=argparse.SUPPRESS, help=lang_help)

    def common(p):
        p.add_argument("--new", required=True, help=t("mapp med exporterna som granskas",
                                                      "folder with the exports under review"))
        p.add_argument("--old", help=t("mapp med referensexporter (t.ex. förra årets slutliga schema)",
                                       "folder with reference exports (e.g. last year's final schedule)"))
        p.add_argument("--out", default="reports", help=t("mapp för resultatet (standard: reports)",
                                                          "output folder (default: reports)"))
        p.add_argument("--accepted", help=t("TOML-fil med accepterade skillnader för granskningen",
                                            "TOML file with accepted differences for this review"))
        lang_opt(p)
        p.add_argument("-v", "--verbose", action="store_true",
                       help=t("skriv även ut fynd på info-nivå", "also print info-level issues"))
        p.add_argument("--no-syllabus", action="store_true",
                       help=t("hämta inte kursplanernas examinationsmoduler från kth.se",
                              "don't fetch syllabus exam modules from the kth.se course pages"))
        p.add_argument("--no-rooms", action="store_true",
                       help=t("jämför inte lokalernas antal platser (från KTH Places)",
                              "don't compare room capacities (read from KTH Places)"))
        p.add_argument("--rooms", help=t('TOML-fil med antal platser för lokaler ([capacity] "NAMN" = platser)',
                                         'TOML file with manual room capacities ([capacity] "NAME" = seats)'))
        p.add_argument("--cache-dir", help=t("var hämtade utbildningsplaner, kursplaner och lokaldata sparas",
                                             "where to cache downloaded study plans, syllabus and room data"))
        p.add_argument("--timeedit", metavar="CONFIG",
                       help=t("TimeEdit-konfiguration (som för 'fetch'), för länkar till varje årskurs schema",
                              "TimeEdit config (as for 'fetch'), to link each programme year to its schedule"))
        p.add_argument("--new-view", help=t("TimeEdit-vy för --new-exporterna, t.ex. remiss "
                                            "(standard: från filnamnen som 'collect' ger)",
                                            "TimeEdit view of the --new exports, e.g. remiss "
                                            "(default: from file names as written by 'collect')"))
        p.add_argument("--old-view", help=t("TimeEdit-vy för --old-exporterna, t.ex. final",
                                            "TimeEdit view of the --old exports, e.g. final"))

    p = sub.add_parser("program", help=t("programgranskning (alla årskurser i ett program)",
                                         "programme review (all years of a programme)"))
    common(p)
    p.add_argument("--program", help=t("granska bara detta program (standard: varje program i exporterna, "
                                       "en granskning var, i OUT/<PROG>/ om de är flera)",
                                       "review only this programme (default: every programme in "
                                       "the exports, one review each, in OUT/<PROG>/ when several)"))
    p.add_argument("--plan-source", help=t("klon av ProgramVisualization eller bas-URL "
                                           "(standard: GitHub raw, main-grenen)",
                                           "ProgramVisualization clone or base URL "
                                           "(default: GitHub raw, main branch)"))
    p.add_argument("--no-plan", action="store_true", help=t("hoppa över kontroller mot utbildningsplanen",
                                                            "skip study-plan based checks"))
    p.set_defaults(func=cmd_program)

    p = sub.add_parser("course", help=t("kursgranskning av en eller flera kurser",
                                        "course-level review of one or more courses"))
    p.add_argument("codes", nargs="+", help=t("kurskoder, t.ex. SF1674", "course codes, e.g. SF1674"))
    common(p)
    p.set_defaults(func=cmd_course)

    p = sub.add_parser("fetch", help=t("öppna TimeEdit-exporter i webbläsaren (du är inloggad där)",
                                       "open TimeEdit exports in your browser (you stay logged in there)"))
    lang_opt(p)
    p.add_argument("--config", required=True, help=t("TOML med bas-URL, vyer, objekt-id:n och terminsdatum",
                                                     "TOML with base URL, views, object ids and term dates"))
    p.add_argument("--new", required=True, metavar="TERM:VIEW", help=t("t.ex. VT27:remiss", "e.g. VT27:remiss"))
    p.add_argument("--old", metavar="TERM:VIEW", help=t("referens, t.ex. VT26:final", "reference, e.g. VT26:final"))
    p.add_argument("--new-dir", help=t("mapp för de nya exporterna; får innehålla {program}, {term}, {view} "
                                       "(standard: {program}/{term}_{view})",
                                       "folder for the new exports; may contain {program}, {term}, "
                                       "{view} (default: {program}/{term}_{view})"))
    p.add_argument("--old-dir", help=t("mapp för referensexporterna (samma platshållare)",
                                       "folder for the reference exports (same placeholders)"))
    p.add_argument("--programs", nargs="*", help=t("program (CTMAT) eller årskurser (CTMAT2) att hämta "
                                                   "(standard: alla i konfigurationen)",
                                                   "programmes (CTMAT) or programme years (CTMAT2) "
                                                   "to fetch (default: all in the config)"))
    p.add_argument("--manifest", default=".schedcheck-fetch.json",
                   help=t("var begäran sparas", "where to record the request"))
    p.add_argument("--print-only", action="store_true", help=t("skriv bara ut länkarna", "only print the URLs"))
    p.add_argument("--browser", help=t("webbläsare, t.ex. 'Safari' eller 'Google Chrome' (standard: systemets)",
                                       "browser to use, e.g. 'Safari' or 'Google Chrome' "
                                       "(default: the system default browser)"))
    p.set_defaults(func=cmd_fetch)

    p = sub.add_parser("collect", help=t("arkivera exporter som laddats ned via 'fetch'",
                                         "file downloaded exports requested by 'fetch'"))
    lang_opt(p)
    p.add_argument("--from", dest="src", required=True, help=t("nedladdningsmapp", "download folder"))
    p.add_argument("--manifest", default=".schedcheck-fetch.json")
    p.add_argument("--copy", action="store_true", help=t("kopiera i stället för att flytta", "copy instead of move"))
    p.set_defaults(func=cmd_collect)

    p = sub.add_parser("index", help=t("skriv en index.html som länkar till rapporterna i en mapps undermappar",
                                       "write an index.html linking the reports in a folder's subfolders"))
    lang_opt(p)
    p.add_argument("folder")
    p.add_argument("--title", help=t("sidans rubrik (svenska)", "page title (Swedish)"))
    p.add_argument("--title-en", help=t("sidans rubrik på engelska (standard: som --title)",
                                        "page title in English (default: as --title)"))
    p.set_defaults(func=cmd_index)

    p = sub.add_parser("dump", help=t("skriv ut tolkade rader per kurs (felsökning)",
                                      "print parsed events per course (debugging)"))
    lang_opt(p)
    p.add_argument("folder")
    p.add_argument("--course", nargs="*", help=t("bara dessa kurser", "only these courses"))
    p.set_defaults(func=cmd_dump)

    args = ap.parse_args(argv)
    LANG = args.lang or env_lang()
    args.lang = LANG
    args.func(args)


if __name__ == "__main__":
    main()
