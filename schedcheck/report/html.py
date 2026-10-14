"""Self-contained HTML report (no external resources).

Sections: summary, issue table (filterable), exam calendar per term,
per-course week-by-week structure comparison.

Colour use follows a fixed role scheme: severity uses status colours and
always carries an icon + label; activity chips use categorical slots in a
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

SEV_ICON = {"error": "✖", "warning": "▲", "review": "◆", "info": "●"}
SEV_LABEL = {"error": "Error", "warning": "Warning", "review": "Review", "info": "Info"}

# Activity -> categorical slot (fixed order; anything else is neutral).
ACT_SLOT = {"F": 1, "Ö": 2, "L": 3, "DL": 3, "S": 4, "Le": 5, "W": 5, "P": 6, "Red": 7,
            "TEN": 8, "KS": 8, "EX": 8}

CSS = """
:root {
  color-scheme: light;
  --surface-0: #f5f4f1; --surface-1: #fcfcfb; --surface-2: #f0efec; --border: #dddcd6;
  --text-primary: #0b0b0b; --text-secondary: #52514e; --text-muted: #77766f;
  --s1: #2a78d6; --s2: #eb6834; --s3: #1baf7a; --s4: #eda100; --s5: #e87ba4;
  --s6: #008300; --s7: #6250d6; --s8: #e34948;
  --critical: #d03b3b; --warning: #fab219; --serious: #ec835a; --review: #2a78d6; --muted: #9a998f;
  --hl: #fff4d6;
}
@media (prefers-color-scheme: dark) {
  :root:where(:not([data-theme="light"])) {
    color-scheme: dark;
    --surface-0: #121211; --surface-1: #1a1a19; --surface-2: #262624; --border: #383835;
    --text-primary: #f0efec; --text-secondary: #c3c2b7; --text-muted: #9a998f;
    --s1: #3987e5; --s2: #d95926; --s3: #199e70; --s4: #c98500; --s5: #d55181;
    --s6: #008300; --s7: #9085e9; --s8: #e66767; --review: #3987e5; --hl: #3a3320;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --surface-0: #121211; --surface-1: #1a1a19; --surface-2: #262624; --border: #383835;
  --text-primary: #f0efec; --text-secondary: #c3c2b7; --text-muted: #9a998f;
  --s1: #3987e5; --s2: #d95926; --s3: #199e70; --s4: #c98500; --s5: #d55181;
  --s6: #008300; --s7: #9085e9; --s8: #e66767; --review: #3987e5; --hl: #3a3320;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--surface-0); color: var(--text-primary);
  font: 14px/1.45 system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width: 1280px; margin: 0 auto; padding: 24px 16px 64px; }
h1 { font-size: 22px; margin: 0 0 4px; }
h2 { font-size: 17px; margin: 32px 0 8px; }
h3 { font-size: 15px; margin: 16px 0 6px; }
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
code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }
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
.themebtn { float: right; padding: 4px 10px; border: 1px solid var(--border); border-radius: 6px;
  background: var(--surface-1); color: var(--text-primary); cursor: pointer; }
@media (max-width: 640px) { td.msg { min-width: 240px; } .tile { min-width: 96px; } }
"""

JS = """
(function () {
  const rows = Array.from(document.querySelectorAll('#issues tbody tr'));
  const q = document.getElementById('q'), scope = document.getElementById('scope'),
        acc = document.getElementById('acc');
  const sev = Array.from(document.querySelectorAll('input[name=sev]'));
  function apply() {
    const on = new Set(sev.filter(s => s.checked).map(s => s.value));
    const text = q.value.trim().toLowerCase();
    let shown = 0;
    rows.forEach(r => {
      const ok = on.has(r.dataset.sev) && (!scope.value || r.dataset.scope === scope.value)
        && (acc.checked || r.dataset.acc !== '1')
        && (!text || r.textContent.toLowerCase().includes(text));
      r.classList.toggle('hidden', !ok); if (ok) shown++;
    });
    document.getElementById('shown').textContent = shown + ' shown';
  }
  [q, scope, acc, ...sev].forEach(el => el.addEventListener('input', apply));
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
        h.append(f'<tr><td class="y">{esc(prog)}{year or ""}</td>')
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
    scopes = sorted({i.scope for i in issues})

    out = ["<!doctype html><html lang='en'><head><meta charset='utf-8'>",
           "<meta name='viewport' content='width=device-width, initial-scale=1'>",
           f"<title>Schedule review {esc(res.title)}</title><style>{CSS}</style></head><body><main>",
           "<button class='themebtn' id='theme' type='button'>Toggle theme</button>",
           f"<h1>Schedule review: {esc(res.title)}</h1>"]
    src = ", ".join(sorted({ex.label for ex in ctx.new.exports}))
    sub = f"Under review: {esc(ctx.new.term)} ({esc(src)})"
    if ctx.old:
        sub += f" · reference: {esc(ctx.old.term)}"
    out.append(f"<p class='sub'>{sub}</p>")

    out.append("<div class='tiles'>")
    for s in SEVERITIES:
        out.append(f"<div class='tile'><div class='n'>{counts.get(s, 0)}</div><div class='l'>{sev_badge(s)}</div></div>")
    out.append(f"<div class='tile'><div class='n'>{n_acc}</div><div class='l'>Accepted</div></div></div>")
    if res.notes:
        out.append("<ul class='notes'>" + "".join(f"<li>{esc(n)}</li>" for n in res.notes) + "</ul>")
    cal = ctx.new.calendar
    out.append("<p class='sub'>Periods: " + "; ".join(f"{p} {s}–{e}" for p, s, e in cal.periods)
               + " · Exam windows: " + "; ".join(f"{w.start}–{w.end}" for w in cal.exam_windows)
               + " · Re-exam windows: " + "; ".join(f"{w.start}–{w.end}" for w in cal.reexam_windows) + "</p>")

    # Issues
    out.append("<h2>Issues</h2><div class='filters'>")
    for s in SEVERITIES:
        checked = "" if s == "info" else " checked"
        out.append(f"<label><input type='checkbox' name='sev' value='{s}'{checked}>{sev_badge(s)}</label>")
    out.append("<select id='scope' aria-label='Scope'><option value=''>All scopes</option>"
               + "".join(f"<option>{esc(s)}</option>" for s in scopes) + "</select>")
    out.append("<input id='q' type='search' placeholder='Filter text…' aria-label='Filter text'>")
    out.append("<label><input type='checkbox' id='acc'>show accepted</label><span id='shown' class='sub'></span></div>")
    out.append("<div class='tablewrap'><table id='issues'><thead><tr><th>Severity</th><th>Check</th>"
               "<th>Scope</th><th>Course</th><th>Finding</th></tr></thead><tbody>")
    for i in issues:
        ev = "".join(f"<div class='ev'>{esc(e)}</div>" for e in i.evidence[:4])
        acc = f"<div class='ev'>accepted: {esc(i.accepted)}</div>" if i.accepted else ""
        out.append(f"<tr data-sev='{i.severity}' data-scope='{esc(i.scope)}' data-acc='{1 if i.accepted else 0}'"
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
        out.append("<h2>Course structure, week by week</h2>")
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
            out.append(f"<details class='course'{' open' if n and ctx.review == 'course' else ''}>"
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

