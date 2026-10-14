"""Self-contained HTML report in the KTH graphical profile.

Everything is inline except the Figtree web font (Google Fonts), which
degrades to Helvetica/Arial when offline.

Sections: summary, issue table (filterable), exam calendar per term,
per-course week-by-week structure comparison.

Colour use follows a fixed role scheme: severity uses KTH functional colours
and always carries an icon + label; activity chips use the KTH palette in a
fixed order and always carry a text label, so colour is never the only cue.
"""
from __future__ import annotations

import html
from collections import Counter, defaultdict
from pathlib import Path

from ..checks.structure import abbrev, occasions, week_label
from ..model import SEVERITIES, severity_rank
from ..reviews.program import ReviewResult
from ..term import TermData

LOGO_SVG = (Path(__file__).parent / "assets" / "kth_logo.svg").read_text(encoding="utf-8").strip()

SEV_ICON = {"error": "✖", "warning": "▲", "review": "◆", "info": "●"}
SEV_LABEL = {"error": "Error", "warning": "Warning", "review": "Review", "info": "Info"}

# Activity -> categorical slot (fixed order; anything else is neutral).
ACT_SLOT = {"F": 1, "Ö": 2, "L": 3, "DL": 3, "S": 4, "Le": 5, "W": 5, "P": 6, "Red": 7,
            "TEN": 8, "KS": 8, "EX": 8}

CSS = """
/* KTH Graphical Profile (Grafisk manual v1.2, 2024), as defined in
   https://github.com/cohm/kth-doc-templates. The profile defines no dark
   theme; the dark tokens below keep the KTH hues, stepped for a dark surface. */
:root {
  color-scheme: light;
  --kth-blue: #004791; --kth-navy: #000061; --kth-skyblue: #6298D2; --kth-lightblue: #DEF0FF;
  --kth-sand: #EBE5E0; --kth-brokenblack: #212121; --kth-brokenwhite: #FCFCFC;
  --surface-0: var(--kth-brokenwhite); --surface-1: #FFFFFF; --surface-2: #F4F1EE;
  --border: #E6E6E6; --text-primary: var(--kth-brokenblack); --text-secondary: #323232;
  --text-muted: #5A5A5A; --accent: var(--kth-blue); --logo: var(--kth-navy);
  /* activity chips: KTH primary + functional palette */
  --s1: #004791; --s2: #E86A58; --s3: #4DA060; --s4: #FFBE00; --s5: #339C9C;
  --s6: #000061; --s7: #6298D2; --s8: #78001A;
  /* severities: brick / yellow / blue / gray, always with icon + label */
  --critical: #78001A; --warning: #A65900; --review: #004791; --muted: #A5A5A5;
  --hl: var(--kth-lightblue);
}
@media (prefers-color-scheme: dark) {
  :root:where(:not([data-theme="light"])) {
    color-scheme: dark;
    --surface-0: #12121A; --surface-1: #1B1B26; --surface-2: #262634; --border: #34344A;
    --text-primary: #FCFCFC; --text-secondary: #E6E6E6; --text-muted: #A5A5A5;
    --accent: #6298D2; --logo: #FFFFFF;
    --s1: #6298D2; --s2: #E86A58; --s3: #4DA060; --s4: #FFBE00; --s5: #339C9C;
    --s6: #C7EBBA; --s7: #DEF0FF; --s8: #FFCCC4;
    --critical: #E86A58; --warning: #FFBE00; --review: #6298D2; --hl: #1C2B4A;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --surface-0: #12121A; --surface-1: #1B1B26; --surface-2: #262634; --border: #34344A;
  --text-primary: #FCFCFC; --text-secondary: #E6E6E6; --text-muted: #A5A5A5;
  --accent: #6298D2; --logo: #FFFFFF;
  --s1: #6298D2; --s2: #E86A58; --s3: #4DA060; --s4: #FFBE00; --s5: #339C9C;
  --s6: #C7EBBA; --s7: #DEF0FF; --s8: #FFCCC4;
  --critical: #E86A58; --warning: #FFBE00; --review: #6298D2; --hl: #1C2B4A;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--surface-0); color: var(--text-primary);
  font: 14px/1.5 "Figtree", "Helvetica Neue", Helvetica, Arial, sans-serif; }
.kthhead { display: flex; align-items: center; gap: 16px; margin: 0 0 4px; }
.kthhead svg { height: 56px; width: auto; flex: none; color: var(--logo); }
main { max-width: 1280px; margin: 0 auto; padding: 24px 16px 64px; }
h1, h2, h3 { font-weight: 600; color: var(--accent); line-height: 1.2; }
h1 { font-size: 24px; margin: 0; padding-bottom: 6px; border-bottom: 2px solid var(--accent); flex: 1; }
h2 { font-size: 18px; margin: 32px 0 8px; padding-bottom: 3px;
  border-bottom: 1px solid color-mix(in srgb, var(--accent) 40%, transparent); }
h3 { font-size: 15px; margin: 16px 0 6px; }
h2 .sub { color: var(--text-secondary); font-weight: 500; }
.sub { color: var(--text-secondary); margin: 0 0 16px; }
.card { background: var(--surface-1); border: 1px solid var(--border); border-radius: 8px; padding: 12px 16px; }
.tiles { display: flex; gap: 12px; flex-wrap: wrap; margin: 12px 0; }
.tile { background: var(--surface-1); border: 1px solid var(--border); border-radius: 8px;
  padding: 10px 16px; min-width: 120px; }
.tile .n { font-size: 26px; font-weight: 600; }
.tile .l { color: var(--text-secondary); }
.sev { display: inline-flex; align-items: center; gap: 4px; font-weight: 600; white-space: nowrap; }
.sev .i { display: inline-block; width: 1.1em; text-align: center; }
.sev-error .i { color: var(--critical); } .sev-warning .i { color: var(--warning); }
.sev-review .i { color: var(--review); } .sev-info .i { color: var(--muted); }
.notes { color: var(--text-secondary); font-size: 13px; margin: 8px 0; padding-left: 18px; }
.filters { display: flex; gap: 12px; flex-wrap: wrap; align-items: center; margin: 8px 0 12px; }
.filters label { display: inline-flex; gap: 4px; align-items: center; }
.filters input[type=search], .filters select { padding: 4px 8px; border: 1px solid var(--border);
  border-radius: 6px; background: var(--surface-1); color: var(--text-primary); }
.tablewrap { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; background: var(--surface-1); }
th, td { text-align: left; vertical-align: top; padding: 6px 8px; border-bottom: 1px solid var(--border); }
th { font-weight: 600; color: var(--text-secondary); font-size: 12px; text-transform: uppercase; letter-spacing: .03em; }
td.msg { min-width: 360px; }
tr.accepted td { opacity: .55; }
.ev { color: var(--text-muted); font-size: 12px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
code { font-family: "SF Mono", ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }
.cal { overflow-x: auto; }
.cal table { width: auto; }
.cal th.win { text-align: center; border-left: 2px solid var(--border); }
.cal td { min-width: 92px; border-left: 1px solid var(--border); }
.cal td.y { font-weight: 600; white-space: nowrap; }
.chip { display: block; margin: 2px 0; padding: 2px 6px; border-radius: 4px; font-size: 12px;
  border: 1px solid var(--border); background: var(--surface-2); white-space: nowrap; }
.chip.ordinary { border-left: 4px solid var(--s1); }
.chip.reexam { border-left: 4px dashed var(--s2); }
.chip.partial { border-left: 4px dotted var(--s3); }
.chip.flag-error { outline: 2px solid var(--critical); }
.chip.flag-warning { outline: 2px solid var(--warning); }
.chip .fi { font-weight: 700; margin-right: 2px; }
.legend { display: flex; gap: 16px; flex-wrap: wrap; color: var(--text-secondary); font-size: 12px; margin: 6px 0; }
.legend .chip { display: inline-block; }
.legend > span { white-space: nowrap; }
details.course { background: var(--surface-1); border: 1px solid var(--border); border-radius: 8px;
  margin: 8px 0; padding: 6px 12px; }
details.course summary { cursor: pointer; font-weight: 600; }
details.course summary .cnt { font-weight: 400; color: var(--text-secondary); margin-left: 8px; }
.wk td { padding: 3px 8px; }
.wk tr.diff td { background: var(--hl); }
.wk td.w { white-space: nowrap; color: var(--text-secondary); }
.act { display: inline-block; min-width: 22px; text-align: center; padding: 1px 4px; margin: 1px;
  border-radius: 4px; font-size: 12px; font-weight: 600; color: var(--text-primary);
  background: var(--surface-2); border-bottom: 3px solid var(--muted); }
.a1 { border-bottom-color: var(--s1); } .a2 { border-bottom-color: var(--s2); }
.a3 { border-bottom-color: var(--s3); } .a4 { border-bottom-color: var(--s4); }
.a5 { border-bottom-color: var(--s5); } .a6 { border-bottom-color: var(--s6); }
.a7 { border-bottom-color: var(--s7); } .a8 { border-bottom-color: var(--s8); }
.hidden { display: none; }
.yearbar { position: sticky; top: 0; z-index: 5; background: var(--surface-0);
  padding: 8px 0; margin: 0 0 8px; border-bottom: 1px solid var(--border);
  display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
.yearbar .lbl { font-weight: 600; }
.seg { display: inline-flex; flex-wrap: wrap; max-width: 100%; border: 1px solid var(--border);
  border-radius: 8px; overflow: hidden; }
.seg input { position: absolute; opacity: 0; pointer-events: none; }
.seg label { padding: 5px 12px; cursor: pointer; background: var(--surface-1); border-left: 1px solid var(--border); }
.seg label:first-of-type { border-left: 0; }
.seg input:checked + label { background: var(--accent); color: var(--surface-1); font-weight: 600; }
.seg input:focus-visible + label { outline: 2px solid var(--review); outline-offset: -2px; }
.cal tr.sel td { background: var(--hl); }
.cal tr.sel td.y::before { content: "▶ "; }
.cal tr.dim td { opacity: .45; }
.themebtn { float: right; padding: 4px 10px; border: 1px solid var(--border); border-radius: 6px;
  background: var(--surface-1); color: var(--text-primary); cursor: pointer; }
h1 { overflow-wrap: anywhere; }
@media (max-width: 640px) {
  td.msg { min-width: 240px; } .tile { min-width: 0; flex: 1 1 28%; padding: 8px 10px; }
  .tile .n { font-size: 20px; } .themebtn { float: none; margin-bottom: 8px; }
  .yearbar .sub { display: none; }
}
"""

JS = """
(function () {
  const rows = Array.from(document.querySelectorAll('#issues tbody tr'));
  const q = document.getElementById('q'), acc = document.getElementById('acc');
  const sev = Array.from(document.querySelectorAll('input[name=sev]'));
  const years = Array.from(document.querySelectorAll('input[name=year]'));
  const ALL = '*';
  // Default: the first programme year; a choice made earlier is remembered.
  let year = years.length > 1 ? years[1].value : ALL;
  try { const saved = localStorage.getItem('schedcheck-year');
        if (saved && years.some(y => y.value === saved)) year = saved; } catch (e) {}
  years.forEach(y => { y.checked = y.value === year; });

  const inYear = el => year === ALL || el.dataset.years === ALL
    || el.dataset.years.split(' ').includes(year);

  function apply() {
    const on = new Set(sev.filter(s => s.checked).map(s => s.value));
    const text = q.value.trim().toLowerCase();
    let shown = 0;
    const counts = {error: 0, warning: 0, review: 0, info: 0}; let accepted = 0;
    rows.forEach(r => {
      const y = inYear(r);
      if (y) { if (r.dataset.acc === '1') accepted++; else counts[r.dataset.sev]++; }
      const ok = y && on.has(r.dataset.sev) && (acc.checked || r.dataset.acc !== '1')
        && (!text || r.textContent.toLowerCase().includes(text));
      r.classList.toggle('hidden', !ok); if (ok) shown++;
    });
    document.getElementById('shown').textContent = shown + ' shown';
    Object.entries(counts).forEach(([k, v]) => { document.getElementById('n-' + k).textContent = v; });
    document.getElementById('n-accepted').textContent = accepted;
    document.querySelectorAll('.cal tbody tr[data-year]').forEach(tr => {
      tr.classList.toggle('sel', year !== ALL && tr.dataset.year === year);
      tr.classList.toggle('dim', year !== ALL && tr.dataset.year !== year);
    });
    document.querySelectorAll('[data-course-years]').forEach(d => {
      const ys = d.dataset.courseYears;
      d.classList.toggle('hidden', !(year === ALL || ys === ALL || ys.split(' ').includes(year)));
    });
    document.querySelectorAll('.yearname').forEach(e => { e.textContent = year === ALL ? 'all years' : year; });
  }
  years.forEach(y => y.addEventListener('change', () => {
    year = y.value;
    try { localStorage.setItem('schedcheck-year', year); } catch (e) {}
    apply();
  }));
  [q, acc, ...sev].forEach(el => el.addEventListener('input', apply));
  apply();
  const btn = document.getElementById('theme');
  btn.addEventListener('click', () => {
    const r = document.documentElement;
    const dark = r.dataset.theme ? r.dataset.theme === 'dark'
      : matchMedia('(prefers-color-scheme: dark)').matches;
    r.dataset.theme = dark ? 'light' : 'dark';
  });
})();
"""


def esc(x) -> str:
    return html.escape(str(x), quote=True)


def sev_badge(sev: str) -> str:
    return f'<span class="sev sev-{sev}"><span class="i" aria-hidden="true">{SEV_ICON[sev]}</span>{SEV_LABEL[sev]}</span>'


def act_chip(a: str, title: str = "") -> str:
    base = a.split("×")[0]
    slot = ACT_SLOT.get(base)
    cls = f"act a{slot}" if slot else "act"
    t = f' title="{esc(title)}"' if title else ""
    return f'<span class="{cls}"{t}>{esc(a)}</span>'


def year_label(key) -> str:
    prog, year = key
    return f"{prog}{year or ''}"


def course_years(res: ReviewResult, reference: bool = True) -> dict[str, set[str]]:
    """Course -> programme-year labels whose exports contain it (optionally
    also the reference term's exports, where a course may sit in another year)."""
    out: dict[str, set[str]] = defaultdict(set)
    for td in ((res.ctx.new, res.ctx.old) if reference else (res.ctx.new,)):
        if td is None:
            continue
        for key, evs in td.year_events.items():
            for e in evs:
                for c in e.codes:
                    out[c].add(year_label(key))
    return out


def issue_years(i, labels: set[str], cy: dict[str, set[str]], cy_new: dict[str, set[str]]) -> str:
    """Space-separated year labels an issue belongs to, or '*' for all.

    A year-scoped issue belongs to its year; a re-exam-path issue also to the
    year of the course being retaken, since it concerns that course's exam too.
    """
    if i.scope in labels:
        ys = {i.scope}
        if i.check == "exams.reexam-path":
            for c in i.details.get("courses", []):
                ys |= cy_new.get(c, set()) & labels
        return " ".join(sorted(ys))
    ys = set(cy.get(i.course, set())) if i.course else set()
    for c in i.details.get("courses", []) if isinstance(i.details, dict) else []:
        ys |= cy.get(c, set())
    ys &= labels
    return " ".join(sorted(ys)) if ys else "*"


def _exam_flags(res: ReviewResult) -> dict[tuple[str, str], str]:
    """(course, date) -> worst unaccepted severity among exam-pair issues."""
    flags: dict[tuple[str, str], str] = {}
    for i in res.issues:
        if i.accepted or not i.check.startswith("exams.") or "courses" not in i.details:
            continue
        for c, d in zip(i.details["courses"], i.details["dates"]):
            k = (c, d)
            if k not in flags or severity_rank(i.severity) < severity_rank(flags[k]):
                flags[k] = i.severity
    return flags


def exam_calendar(td: TermData, flags: dict | None = None, courses: set[str] | None = None) -> str:
    flags = flags or {}
    cal = td.calendar
    rows = td.years()
    # date -> {(prog, year): [Exam]}
    grid: dict = defaultdict(lambda: defaultdict(list))
    for key in rows:
        for x in td.exams(td.year_events.get(key, [])):
            if courses and x.course not in courses:
                continue
            grid[x.date][key].append(x)
    if not grid:
        return '<p class="sub">No exams found.</p>'
    dates = sorted(grid)

    def group_of(d):
        w = cal.window_of(d)
        return w.label if w else "during teaching"

    groups: list[tuple[str, list]] = []
    for d in dates:
        g = group_of(d)
        if groups and groups[-1][0] == g:
            groups[-1][1].append(d)
        else:
            groups.append((g, [d]))

    h = ['<div class="cal tablewrap"><table><thead><tr><th></th>']
    for g, ds in groups:
        h.append(f'<th class="win" colspan="{len(ds)}">{esc(g)}</th>')
    h.append("</tr><tr><th></th>")
    for g, ds in groups:
        for d in ds:
            h.append(f"<th>{d:%a %d %b}</th>")
    h.append("</tr></thead><tbody>")
    for key in rows:
        prog, year = key
        h.append(f'<tr data-year="{esc(year_label(key))}"><td class="y">{esc(prog)}{year or ""}</td>')
        for g, ds in groups:
            for d in ds:
                cell = []
                for x in sorted(grid[d].get(key, []), key=lambda x: x.event.start):
                    f = flags.get((x.course, str(d)))
                    fcls = f" flag-{f}" if f in ("error", "warning") else ""
                    icon = f'<span class="fi" aria-label="{f}">{SEV_ICON[f]}</span>' if f in ("error", "warning") else ""
                    title = f"{x.course} {x.kind} {x.event.start:%H:%M}-{x.event.end:%H:%M} {x.event.activity}"
                    cell.append(f'<span class="chip {x.kind}{fcls}" title="{esc(title)}">{icon}'
                                f'{esc(x.course)} <span class="ev">{x.event.start:%H}</span></span>')
                h.append(f"<td>{''.join(cell)}</td>")
        h.append("</tr>")
    h.append("</tbody></table></div>")
    return "".join(h)


def week_table(res: ReviewResult, code: str) -> str:
    ctx = res.ctx
    new_occ = occasions(ctx.new, code)
    old_occ = occasions(ctx.old, code) if ctx.old else []
    wo, wn = defaultdict(list), defaultdict(list)
    for o in old_occ:
        wo[o.week].append(o)
    for o in new_occ:
        wn[o.week].append(o)
    keys = sorted(set(wo) | set(wn), key=lambda k: (k is None, k[0] if k else "", (k[1] if k else 0) or 99))

    def cell(occs):
        return "".join(act_chip(abbrev(o.activity) + (f"×{o.parallel}" if o.parallel > 1 else ""),
                                f"{o.first.start:%a %Y-%m-%d %H:%M} {o.activity}"
                                + (f" ({o.parallel} parallel groups)" if o.parallel > 1 else ""))
                       for o in occs)

    old_t = ctx.old.term if ctx.old else "—"
    h = [f'<div class="tablewrap"><table class="wk"><thead><tr><th>Week</th><th>{esc(old_t)}</th>'
         f'<th>{esc(ctx.new.term)}</th></tr></thead><tbody>']
    for k in keys:
        a = [abbrev(o.activity) for o in wo.get(k, [])]
        b = [abbrev(o.activity) for o in wn.get(k, [])]
        cls = ' class="diff"' if a != b else ""
        h.append(f'<tr{cls}><td class="w">{esc(week_label(k))}</td><td>{cell(wo.get(k, []))}</td>'
                 f'<td>{cell(wn.get(k, []))}</td></tr>')
    h.append("</tbody></table></div>")
    return "".join(h)


def render(res: ReviewResult) -> str:
    ctx = res.ctx
    issues = res.sorted_issues()
    counts = Counter(i.severity for i in issues if not i.accepted)
    n_acc = sum(1 for i in issues if i.accepted)
    flags = _exam_flags(res)
    labels = [year_label(k) for k in ctx.new.years()]
    label_set = set(labels)
    cy = course_years(res)
    cy_new = course_years(res, reference=False)

    out = ["<!doctype html><html lang='en'><head><meta charset='utf-8'>",
           "<meta name='viewport' content='width=device-width, initial-scale=1'>",
           # Figtree (KTH profile font); falls back to Helvetica/Arial offline.
           "<link rel='preconnect' href='https://fonts.googleapis.com'>",
           "<link rel='preconnect' href='https://fonts.gstatic.com' crossorigin>",
           "<link rel='stylesheet' href='https://fonts.googleapis.com/css2?family=Figtree:wght@400;500;600;700&display=swap'>",
           f"<title>Schedule review {esc(res.title)}</title><style>{CSS}</style></head><body><main>",
           "<button class='themebtn' id='theme' type='button'>Toggle theme</button>",
           f"<div class='kthhead'>{LOGO_SVG}<h1>Schedule review: {esc(res.title)}</h1></div>"]
    src = ", ".join(sorted({ex.label for ex in ctx.new.exports}))
    sub = f"Under review: {esc(ctx.new.term)} ({esc(src)})"
    if ctx.old:
        sub += f" · reference: {esc(ctx.old.term)}"
    out.append(f"<p class='sub'>{sub}</p>")

    if len(labels) > 1:
        opts = [("*", "All years")] + [(lb, lb) for lb in labels]
        seg = "".join(f"<input type='radio' name='year' id='yr-{i}' value='{esc(v)}'>"
                      f"<label for='yr-{i}'>{esc(t)}</label>" for i, (v, t) in enumerate(opts))
        out.append(f"<div class='yearbar'><span class='lbl'>Programme year</span>"
                   f"<div class='seg' role='radiogroup' aria-label='Programme year'>{seg}</div>"
                   "<span class='sub'>Issues and course structure follow the selection; "
                   "the exam calendars show all years with the selected one highlighted.</span></div>")
    out.append("<div class='tiles'>")
    for s in SEVERITIES:
        out.append(f"<div class='tile'><div class='n' id='n-{s}'>{counts.get(s, 0)}</div>"
                   f"<div class='l'>{sev_badge(s)}</div></div>")
    out.append(f"<div class='tile'><div class='n' id='n-accepted'>{n_acc}</div><div class='l'>Accepted</div></div></div>")
    if res.notes:
        out.append("<ul class='notes'>" + "".join(f"<li>{esc(n)}</li>" for n in res.notes) + "</ul>")
    cal = ctx.new.calendar
    out.append("<p class='sub'>Periods: " + "; ".join(f"{p} {s}–{e}" for p, s, e in cal.periods)
               + " · Exam windows: " + "; ".join(f"{w.start}–{w.end}" for w in cal.exam_windows)
               + " · Re-exam windows: " + "; ".join(f"{w.start}–{w.end}" for w in cal.reexam_windows) + "</p>")

    # Issues
    out.append("<h2>Issues <span class='sub yearname'></span></h2><div class='filters'>")
    for s in SEVERITIES:
        checked = "" if s == "info" else " checked"
        out.append(f"<label><input type='checkbox' name='sev' value='{s}'{checked}>{sev_badge(s)}</label>")
    out.append("<input id='q' type='search' placeholder='Filter text…' aria-label='Filter text'>")
    out.append("<label><input type='checkbox' id='acc'>show accepted</label><span id='shown' class='sub'></span></div>")
    out.append("<div class='tablewrap'><table id='issues'><thead><tr><th>Severity</th><th>Check</th>"
               "<th>Scope</th><th>Course</th><th>Finding</th></tr></thead><tbody>")
    for i in issues:
        ev = "".join(f"<div class='ev'>{esc(e)}</div>" for e in i.evidence[:4])
        acc = f"<div class='ev'>accepted: {esc(i.accepted)}</div>" if i.accepted else ""
        out.append(f"<tr data-sev='{i.severity}' data-years='{esc(issue_years(i, label_set, cy, cy_new))}' "
                   f"data-acc='{1 if i.accepted else 0}'"
                   f"{' class=accepted' if i.accepted else ''}><td>{sev_badge(i.severity)}</td>"
                   f"<td><code>{esc(i.check)}</code></td><td>{esc(i.scope)}</td><td>{esc(i.course or '')}</td>"
                   f"<td class='msg'>{esc(i.message)}{ev}{acc}</td></tr>")
    out.append("</tbody></table></div>")

    # Exam calendars
    legend = ("<div class='legend'><span><span class='chip ordinary'>ordinary</span></span>"
              "<span><span class='chip reexam'>re-exam</span></span>"
              "<span><span class='chip partial'>partial/KS</span></span>"
              f"<span><span class='chip flag-error'><span class='fi'>{SEV_ICON['error']}</span>error</span></span>"
              f"<span><span class='chip flag-warning'><span class='fi'>{SEV_ICON['warning']}</span>warning</span></span>"
              "<span>hour of start shown after the code; hover for details</span></div>")
    out.append(f"<h2>Exams {esc(ctx.new.term)}</h2>{legend}")
    shown = None
    if ctx.courses:
        # Course review: the course's own exams plus those it was compared with.
        shown = set(ctx.courses) | {c for i in issues if i.check.startswith("exams.")
                                    for c in i.details.get("courses", [])}
    out.append(exam_calendar(ctx.new, flags, shown))
    if ctx.old:
        out.append(f"<details><summary><h3 style='display:inline'>Exams {esc(ctx.old.term)} (reference)</h3></summary>")
        out.append(exam_calendar(ctx.old, None, ctx.courses))
        out.append("</details>")

    # Course structure
    if ctx.old:
        out.append("<h2>Course structure, week by week <span class='sub yearname'></span></h2>")
        out.append("<p class='sub'>Occasions per teaching week (weeks without regular teaching, e.g. an "
                   "Easter re-exam week, are skipped; ‘exams’ is the period's exam window). "
                   "Highlighted rows differ. ×n = n parallel group sessions.</p>")
        legend = "".join(f"<span>{act_chip(a)} {esc(n)}</span>" for a, n in
                         [("F", "Föreläsning"), ("Ö", "Övning"), ("L", "Laboration"), ("DL", "Datorlab"),
                          ("S", "Seminarium"), ("Le", "Lektion"), ("W", "Workshop"), ("P", "Projekt"),
                          ("Red", "Redovisning"), ("TEN", "Tentamen"), ("KS", "Kontrollskrivning")])
        out.append(f"<div class='legend'>{legend}</div>")
        per_course = defaultdict(list)
        for i in issues:
            if i.check.startswith("structure.") and i.course and not i.accepted:
                per_course[i.course].append(i)
        codes = sorted({c for c in ctx.new.courses() | ctx.old.courses() if ctx.wants(c)})
        for code in sorted(codes, key=lambda c: (c not in per_course, c)):
            if not occasions(ctx.new, code) and not occasions(ctx.old, code):
                continue
            n = len(per_course.get(code, []))
            cnt = f"<span class='cnt'>{n} finding(s)</span>" if n else "<span class='cnt'>unchanged</span>"
            yrs = " ".join(sorted(cy.get(code, set()) & label_set)) or "*"
            out.append(f"<details class='course' data-course-years='{esc(yrs)}'"
                       f"{' open' if n and ctx.review == 'course' else ''}>"
                       f"<summary>{esc(code)}{cnt}</summary>")
            for i in per_course.get(code, []):
                out.append(f"<p>{sev_badge(i.severity)} {esc(i.message)}</p>")
            out.append(week_table(res, code))
            out.append("</details>")

    out.append(f"<script>{JS}</script></main></body></html>")
    return "".join(out)


def write(res: ReviewResult, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = res.title.split(" vs ")[0].replace(", ", "_").replace(" ", "_")
    p = out_dir / f"{stem}_review.html"
    p.write_text(render(res), encoding="utf-8")
    return p

