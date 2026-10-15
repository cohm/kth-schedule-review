"""Self-contained HTML report in the KTH graphical profile.

Everything is inline except the Figtree web font (Google Fonts), which
degrades to Helvetica/Arial when offline.

Bilingual: every text is in the page in Swedish and English (spans with
class l-sv / l-en; attributes in data-sv-* / data-en-*); a toggle switches
(default from --lang, the reader's choice is remembered).

Sections: summary, issue table (filterable), exam calendar per term,
room capacity overview, per-course structure comparison (with rooms).

Colour use follows a fixed role scheme: severity uses KTH functional colours
and always carries an icon + label; activity chips use the KTH palette in a
fixed order and always carry a text label, so colour is never the only cue.
"""
from __future__ import annotations

import difflib
import html
import re
from collections import Counter, defaultdict
from pathlib import Path

from ..checks.rooms import MODE_TEXT
from ..checks.structure import abbrev, occasions, week_label
from ..i18n import KIND, LANGS, SEVERITY, T, both, weekday
from ..io.timeedit import export_time_text
from ..model import SEVERITIES, severity_rank
from ..reviews.program import ReviewResult
from ..term import TermData
from .status import year_status

LOGO_SVG = (Path(__file__).parent / "assets" / "kth_logo.svg").read_text(encoding="utf-8").strip()

SEV_ICON = {"error": "✖", "warning": "▲", "review": "◆", "info": "●", "ok": "✔"}
SEV_LABEL = {k: v["en"] for k, v in SEVERITY.items()}

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
.seq { margin: 4px 0 8px; }
.seqrow { display: flex; flex-wrap: wrap; align-items: center; gap: 0; margin: 2px 0; }
.seqlbl { width: 3.5em; color: var(--text-secondary); font-weight: 600; font-size: 12px; }
.act.chg { outline: 2px solid var(--accent); outline-offset: -1px; }
details.weeks > summary { cursor: pointer; margin: 4px 0; }
a.cl { color: inherit; text-decoration: underline; text-decoration-color: color-mix(in srgb, var(--accent) 50%, transparent);
  text-underline-offset: 2px; }
a.cl:hover { color: var(--accent); text-decoration-color: var(--accent); }
a.cl .ext { font-size: .8em; margin-left: 1px; color: var(--accent); }
.chip a.cl { text-decoration: none; }
.status { background: var(--surface-1); border: 1px solid var(--border); border-left: 4px solid var(--accent);
  border-radius: 8px; padding: 10px 16px; margin: 12px 0; }
.status h3 { margin: 0 0 6px; }
.status ul { list-style: none; margin: 0; padding: 0; }
.status li { display: grid; grid-template-columns: 7.5em 15em 1fr; gap: 8px; padding: 3px 0;
  border-top: 1px solid var(--border); }
.status li:first-child { border-top: 0; }
.status .chk { color: var(--text-secondary); font-weight: 500; }
.sev-ok .i { color: #4DA060; }
@media (max-width: 640px) { .status li { grid-template-columns: 1fr; gap: 0; } }
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
/* Room capacity vs reference: sequential yellow -> coral -> brick for fewer
   seats (always with a ↓ and the numbers in the tooltip/table), a thick
   border and ↑ for many more seats. */
:root { --cap1: #FFBE00; --cap2: #E86A58; --cap3: #78001A; --cap3-text: #FFFFFF; }
.act.cap-lower { background: color-mix(in srgb, var(--cap1) 55%, var(--surface-1)); }
.act.cap-much-lower { background: color-mix(in srgb, var(--cap2) 70%, var(--surface-1)); }
.act.cap-far-lower { background: var(--cap3); color: var(--cap3-text); }
.act.cap-higher { box-shadow: inset 0 0 0 2px var(--text-secondary); }
.capn { display: inline-block; min-width: 2.2em; padding: 0 6px; border-radius: 4px; text-align: center; font-weight: 600; }
.capn.cap-lower { background: color-mix(in srgb, var(--cap1) 55%, var(--surface-1)); }
.capn.cap-much-lower { background: color-mix(in srgb, var(--cap2) 70%, var(--surface-1)); }
.capn.cap-far-lower { background: var(--cap3); color: var(--cap3-text); }
.capn.cap-higher { box-shadow: inset 0 0 0 2px var(--text-secondary); }
.capn.cap-nr { box-shadow: inset 0 0 0 2px var(--warning); }
.act.cap-nr { box-shadow: inset 0 0 0 2px var(--warning); }
.act { position: relative; }
.act.cap-lower::after, .act.cap-much-lower::after, .act.cap-far-lower::after,
.act.cap-higher::after, .act.cap-nr::after { position: absolute; top: 0; right: 1px;
  font-size: 8px; line-height: 1; font-weight: 700; pointer-events: none; }
.act.cap-lower::after, .act.cap-much-lower::after, .act.cap-far-lower::after { content: "↓"; }
.act.cap-higher::after { content: "↑"; }
.act.cap-nr::after { content: "?"; }
.capn.zero { color: var(--text-muted); font-weight: 400; }
table.rooms td.n, table.rooms th.n { text-align: right; white-space: nowrap; }
/* Language: both texts are in the page; the other one is hidden. */
:root[data-lang="sv"] .l-en, :root[data-lang="en"] .l-sv { display: none !important; }
.topbtns { float: right; display: flex; gap: 6px; }
.topbtns .themebtn { float: none; }
@media (max-width: 640px) {
  .topbtns { float: none; margin-bottom: 8px; }
  td.msg { min-width: 240px; } .tile { min-width: 0; flex: 1 1 28%; padding: 8px 10px; }
  .tile .n { font-size: 20px; } .themebtn { float: none; margin-bottom: 8px; }
  .yearbar .sub { display: none; }
}
"""

JS = """
(function () {
  const root = document.documentElement;
  const rows = Array.from(document.querySelectorAll('#issues tbody tr'));
  const q = document.getElementById('q'), acc = document.getElementById('acc');
  const sev = Array.from(document.querySelectorAll('input[name=sev]'));
  const years = Array.from(document.querySelectorAll('input[name=year]'));
  const ALL = '*';
  // Language: the page default (from --lang), or the reader's earlier choice.
  let lang = root.dataset.lang;
  try { const s = localStorage.getItem('schedcheck-lang'); if (s === 'sv' || s === 'en') lang = s; } catch (e) {}
  // Default year: the first programme year; a choice made earlier is remembered.
  let year = years.length > 1 ? years[1].value : ALL;
  try { const saved = localStorage.getItem('schedcheck-year');
        if (saved && years.some(y => y.value === saved)) year = saved; } catch (e) {}
  years.forEach(y => { y.checked = y.value === year; });

  const inYear = el => year === ALL || el.dataset.years === ALL
    || el.dataset.years.split(' ').includes(year);

  function apply() {
    if (!q) return;
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
    document.getElementById('shown').textContent = shown + (lang === 'sv' ? ' visas' : ' shown');
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
    document.querySelectorAll('.yearname').forEach(e => {
      e.textContent = year === ALL ? (lang === 'sv' ? 'alla årskurser' : 'all years') : year; });
  }
  function setLang(l) {
    lang = l; root.dataset.lang = l; root.lang = l;
    ['title', 'placeholder', 'aria-label'].forEach(a => {
      const key = s => s + a.replace(/(^|-)([a-z])/g, (m, d, c) => c.toUpperCase());
      document.querySelectorAll('[data-en-' + a + ']').forEach(e => e.setAttribute(a, e.dataset[key(l)]));
    });
    const lb = document.getElementById('lang');
    if (lb) lb.textContent = l === 'sv' ? 'English' : 'Svenska';
    apply();
  }
  years.forEach(y => y.addEventListener('change', () => {
    year = y.value;
    try { localStorage.setItem('schedcheck-year', year); } catch (e) {}
    apply();
  }));
  [q, acc, ...sev].filter(Boolean).forEach(el => el.addEventListener('input', apply));
  const lb = document.getElementById('lang');
  if (lb) lb.addEventListener('click', () => {
    const l = lang === 'sv' ? 'en' : 'sv';
    try { localStorage.setItem('schedcheck-lang', l); } catch (e) {}
    setLang(l);
  });
  setLang(lang);
  const btn = document.getElementById('theme');
  if (btn) btn.addEventListener('click', () => {
    const dark = root.dataset.theme ? root.dataset.theme === 'dark'
      : matchMedia('(prefers-color-scheme: dark)').matches;
    root.dataset.theme = dark ? 'light' : 'dark';
  });
})();
"""

# Language the page opens in (set by render(); the reader can switch).
_LANG = "sv"


def esc(x) -> str:
    return html.escape(str(x), quote=True)


def bi(t, fmt=esc) -> str:
    """Both language versions of a text; CSS shows the selected one."""
    if not isinstance(t, dict):
        return fmt(t)
    if t["sv"] == t["en"]:
        return fmt(t["sv"])
    return (f"<span class='l-sv' lang='sv'>{fmt(t['sv'])}</span>"
            f"<span class='l-en' lang='en'>{fmt(t['en'])}</span>")


def battr(name: str, t) -> str:
    """An attribute (title, placeholder, ...) in both languages; the page
    script sets the attribute itself to the selected one on load and on
    every switch. Placeholders and labels also get the initial value (they
    matter without the script); tooltips don't, to keep the page small."""
    if not isinstance(t, dict) or t["sv"] == t["en"]:
        return f" {name}='{esc(pick_(t))}'"
    first = f" {name}='{esc(t[_LANG])}'" if name != "title" else ""
    return f"{first} data-sv-{name}='{esc(t['sv'])}' data-en-{name}='{esc(t['en'])}'"


def pick_(t) -> str:
    return t["sv"] if isinstance(t, dict) else t


COURSE_URL = "https://www.kth.se/student/kurser/kurs/{code}"

# Course names for tooltips, from the study plans of the review being
# rendered (set by render(); empty for course reviews without a plan).
_NAMES: dict[str, str] = {}


def course_title(code: str) -> str:
    name = _NAMES.get(code)
    return f"{code} {name}" if name else code


# Course codes, but not term/cohort names such as HT2025 or VT2027.
_CODE_RE = re.compile(r"\b(?!(?:HT|VT)\d{4}\b)(F?[A-Z]{2}\d{3}[0-9A-Z])\b")


def course_link(code: str, arrow: bool = True) -> str:
    """A course code linking to its KTH course page (new tab)."""
    a = "<span class='ext' aria-hidden='true'>↗</span>" if arrow else ""
    # Language-neutral tooltip: it appears on every course code in the page.
    return (f"<a class='cl' href='{COURSE_URL.format(code=esc(code))}' target='_blank' rel='noopener' "
            f"title='{esc(course_title(code))} · kth.se'>{esc(code)}{a}</a>")


def linkify(text: str) -> str:
    """Escape text and turn course codes in it into links (no arrow, to keep prose readable)."""
    return _CODE_RE.sub(lambda m: course_link(m.group(1), arrow=False), esc(text))


def sev_badge(sev: str, lang: str | None = None) -> str:
    """Severity icon + label; both languages unless `lang` is given."""
    label = esc(SEVERITY[sev][lang]) if lang else bi(SEVERITY[sev])
    return f'<span class="sev sev-{sev}"><span class="i" aria-hidden="true">{SEV_ICON[sev]}</span>{label}</span>'


def act_chip(a: str, title=None, extra: str = "") -> str:
    base = a.split("×")[0]
    slot = ACT_SLOT.get(base)
    cls = (f"act a{slot}" if slot else "act") + extra
    t = battr("title", title) if title else ""
    return f'<span class="{cls}"{t}>{esc(a)}</span>'


def schedule_link(ex, text=None) -> str:
    """An export's label, linked to its schedule in TimeEdit when known."""
    body = bi(text) if text else esc(ex.label)
    if not ex.url:
        return body
    return (f"<a class='cl' href='{esc(ex.url)}' target='_blank' rel='noopener'"
            f"{battr('title', T(f'{ex.label} – schema i TimeEdit (KTH-inloggning)', f'{ex.label} – schedule in TimeEdit (KTH login)'))}>"
            f"{body}<span class='ext' aria-hidden='true'>↗</span></a>")


def schedule_links(td) -> str:
    seen, out = set(), []
    for ex in sorted(td.exports, key=lambda e: e.label):
        if ex.label not in seen:
            seen.add(ex.label)
            out.append(schedule_link(ex))
    return ", ".join(out)


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


MONTHS = {"sv": ["jan", "feb", "mar", "apr", "maj", "jun", "jul", "aug", "sep", "okt", "nov", "dec"],
          "en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]}


def day_label(d) -> dict:
    return both(lambda lang: f"{weekday(d, lang)} {d.day} {MONTHS[lang][d.month - 1]}")


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
        return f'<p class="sub">{bi(T("Inga tentamina hittades.", "No exams found."))}</p>'
    dates = sorted(grid)

    def group_of(d):
        w = cal.window_of(d)
        return both(w.text) if w else T("under undervisningen", "during teaching")

    groups: list[tuple[dict, list]] = []
    for d in dates:
        g = group_of(d)
        if groups and groups[-1][0] == g:
            groups[-1][1].append(d)
        else:
            groups.append((g, [d]))

    h = ['<div class="cal tablewrap"><table><thead><tr><th></th>']
    for g, ds in groups:
        h.append(f'<th class="win" colspan="{len(ds)}">{bi(g)}</th>')
    h.append("</tr><tr><th></th>")
    for g, ds in groups:
        for d in ds:
            h.append(f"<th>{bi(day_label(d))}</th>")
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
                    title = both(lambda lang: f"{course_title(x.course)}\n{x.event.activity} ({KIND[x.kind][lang]}) "
                                              f"{weekday(x.date, lang)} {x.event.start:%Y-%m-%d %H:%M}-{x.event.end:%H:%M}")
                    cell.append(f'<span class="chip {x.kind}{fcls}"{battr("title", title)}>{icon}'
                                f'{course_link(x.course)} <span class="ev">{x.event.start:%H}</span></span>')
                h.append(f"<td>{''.join(cell)}</td>")
        h.append("</tr>")
    h.append("</tbody></table></div>")
    return "".join(h)


CAP_ARROW = {"lower": "↓", "much-lower": "↓", "far-lower": "↓", "higher": "↑"}


def _seats_txt(c: dict, lang: str) -> str:
    sv = lang == "sv"
    if c.get("digital"):
        return "digitalt" if sv else "digital"
    if c.get("no_room"):
        return "ingen lokal bokad" if sv else "no room booked"
    rooms = "+".join(c["rooms"]) or "–"
    if c["seats"] is not None:
        return f"{rooms} ({c['seats']} {'platser' if sv else 'seats'})"
    return f"{rooms} ({'okänt antal platser' if sv else 'seats unknown'})"


def _change_txt(p: dict, lang: str) -> str:
    o, n = p["old"]["seats"], p["new"]["seats"]
    if p["mode"]:
        return MODE_TEXT.get(p["mode"], T(p["mode"], p["mode"]))[lang]
    if o and n is not None:
        if n == o:
            return "samma" if lang == "sv" else "same"
        pct = f"{(n - o) / o:+.0%}".replace("-", "−")
        return pct.replace("%", " %") if lang == "sv" else pct
    return ""


def room_table(res: ReviewResult, code: str) -> str:
    """The paired occasions whose rooms differ from the reference term."""
    cmp = res.ctx.room_comparison.get(code)
    if not cmp:
        return ""
    ref = cmp["reference_term"]
    rows = [p for p in cmp["pairs"] if p["level"] or p["mode"] or p["old"]["rooms"] != p["new"]["rooms"]]
    flagged = sum(1 for p in cmp["pairs"] if p["level"])
    n = len(cmp["pairs"])
    head = T(f"Lokaler: {n} tillfälle(n) jämförda med {ref}, {len(rows)} i andra lokaler, "
             f"{flagged} med en markerad ändring av antalet platser",
             f"Rooms: {n} occasion(s) compared with {ref}, {len(rows)} in other rooms, "
             f"{flagged} with a marked change in seats")
    if not rows:
        return f"<p class='sub'>{bi(head)}.</p>"
    h = [f"<details class='weeks'><summary class='sub'>{bi(head)}</summary><div class='tablewrap'>"
         f"<table class='wk rooms'><thead><tr><th>{bi(T('Tillfälle', 'Occasion'))}</th><th>{esc(ref)}</th>"
         f"<th>{esc(res.ctx.new.term)}</th><th class='n'>{bi(T('Ändring', 'Change'))}</th></tr></thead><tbody>"]
    for p in rows:
        lvl = p["level"]
        ch = both(lambda lang: _change_txt(p, lang))
        badge = f"<span class='capn cap-{lvl}'>{CAP_ARROW[lvl]} {bi(ch)}</span>" if lvl else bi(ch)
        h.append(f"<tr><td class='w'>{act_chip(p['abbrev'])} {esc(p['new_date'])}</td>"
                 f"<td>{bi(both(lambda lang: _seats_txt(p['old'], lang)))}</td>"
                 f"<td>{bi(both(lambda lang: _seats_txt(p['new'], lang)))}</td>"
                 f"<td class='n'>{badge}</td></tr>")
    h.append("</tbody></table></div></details>")
    return "".join(h)


def week_table(res: ReviewResult, code: str) -> str:
    ctx = res.ctx
    new_occ = occasions(ctx.new, code)
    old_occ = occasions(ctx.old, code) if ctx.old else []
    cmp = ctx.room_comparison.get(code) or {"pairs": []}
    by_new = {p["new_index"]: p for p in cmp["pairs"]}
    by_old = {p["old_index"]: p for p in cmp["pairs"]}

    def chip(o, extra="", pair=None, side="new"):
        def title(lang):
            sv = lang == "sv"
            par = ((f" ({o.parallel} parallella grupper)" if sv else f" ({o.parallel} parallel groups)")
                   if o.parallel > 1 else "")
            t = (f"{course_title(code)}\n{o.activity}{par} {weekday(o.first.start.date(), lang)} "
                 f"{o.first.start:%Y-%m-%d %H:%M} ({week_label(o.week, lang)})")
            if pair:
                t += f"\n{'Lokaler' if sv else 'Rooms'}: {_seats_txt(pair[side], lang)}"
                if side == "new":
                    t += f"\n{cmp['reference_term']}: {_seats_txt(pair['old'], lang)}"
                    if _change_txt(pair, lang):
                        t += f" → {_change_txt(pair, lang)}"
            return t
        label = abbrev(o.activity) + (f"×{o.parallel}" if o.parallel > 1 else "")
        if pair and side == "new":
            # Marked by class only: the arrow is drawn as an overlay
            # (CSS ::after) so chips keep their width and the two
            # terms' sequences stay aligned.
            if pair["level"]:
                extra += f" cap-{pair['level']}"
            elif pair["mode"] == "no room booked":
                extra += " cap-nr"
        return act_chip(label, both(title), extra)

    # Sequence view: the order of occasions is what matters most; the
    # changed stretches (as in the findings) are outlined.
    sm = difflib.SequenceMatcher(a=[abbrev(o.activity) for o in old_occ],
                                 b=[abbrev(o.activity) for o in new_occ], autojunk=False)
    # Outline the same stretches the findings bracket: first to last change
    # within each group (see checks.structure.sequence_hunks).
    chg_old, chg_new = set(), set()
    for group in sm.get_grouped_opcodes(2):
        ch = [op for op in group if op[0] != "equal"]
        chg_old.update(range(ch[0][1], ch[-1][2]))
        chg_new.update(range(ch[0][3], ch[-1][4]))
    old_t = ctx.old.term if ctx.old else "—"
    seq = ("<div class='seq'><div class='seqrow'><span class='seqlbl'>" + esc(old_t) + "</span>"
           + "".join(chip(o, " chg" if i in chg_old else "", by_old.get(i), "old") for i, o in enumerate(old_occ))
           + "</div><div class='seqrow'><span class='seqlbl'>" + esc(ctx.new.term) + "</span>"
           + "".join(chip(o, " chg" if i in chg_new else "", by_new.get(i)) for i, o in enumerate(new_occ))
           + "</div></div>")

    wo, wn = defaultdict(list), defaultdict(list)
    for o in old_occ:
        wo[o.week].append(o)
    for o in new_occ:
        wn[o.week].append(o)
    keys = sorted(set(wo) | set(wn), key=lambda k: (k is None, k[0] if k else "", (k[1] if k else 0) or 99))
    h = [f"<p class='sub'>{bi(T(f'Tillfällen i ordning (inramat: skiljer sig från {old_t}):', f'Sequence of occasions (outlined: differs from {old_t}):'))}</p>{seq}",
         f"<details class='weeks'><summary class='sub'>{bi(T('Vecka för vecka', 'Week by week'))}</summary>",
         f'<div class="tablewrap"><table class="wk"><thead><tr><th>{bi(T("Vecka", "Week"))}</th><th>{esc(old_t)}</th>'
         f'<th>{esc(ctx.new.term)}</th></tr></thead><tbody>']
    for k in keys:
        a = [abbrev(o.activity) for o in wo.get(k, [])]
        b = [abbrev(o.activity) for o in wn.get(k, [])]
        cls = ' class="diff"' if a != b else ""
        h.append(f'<tr{cls}><td class="w">{bi(both(lambda lang: week_label(k, lang)))}</td>'
                 f'<td>{"".join(chip(o) for o in wo.get(k, []))}</td>'
                 f'<td>{"".join(chip(o) for o in wn.get(k, []))}</td></tr>')
    h.append("</tbody></table></div></details>")
    h.append(room_table(res, code))
    return "".join(h)


ROOM_LEVELS = [("far-lower", T("minst 40 % färre", "≥40% fewer")), ("much-lower", T("minst 20 % färre", "≥20% fewer")),
               ("lower", T("minst 10 % färre", "≥10% fewer")), ("higher", T("minst 50 % fler", "≥50% more"))]


def room_overview(res: ReviewResult, cy: dict, label_set: set) -> str:
    ctx = res.ctx
    if not ctx.room_comparison:
        return ""
    ref, new = ctx.old.term, ctx.new.term
    legend = ("".join(f"<span><span class='capn cap-{lv}'>{CAP_ARROW[lv]}</span> "
                      f"{bi(T(t['sv'] + ' platser', t['en'] + ' seats'))}</span>" for lv, t in ROOM_LEVELS)
              + f"<span><span class='capn cap-nr'>?</span> {bi(T('ingen lokal bokad', 'no room booked'))}</span>")
    places = ("<a class='cl' href='https://www.kth.se/places' target='_blank' rel='noopener'>KTH Places</a>")
    intro = T(f"Bokade platser per tillfälle jämfört med {ref}: tillfällena paras ihop där sekvensen är "
              "oförändrad (se Kursstruktur), och platserna i alla lokaler för ett tillfälle summeras över dess "
              "parallella grupptillfällen. Antalet platser kommer från KTH Places. Tentamina ingår inte. "
              "Markeringarna finns också på tillfällena i varje kurs sekvens.",
              f"Seats booked per occasion compared with {ref}: occasions are paired where the sequence is "
              "unchanged (see Course structure), and the seats of all rooms of an occasion are summed over its "
              "parallel group sessions. Seat counts are from KTH Places. Exams are not included. The marks "
              "also appear on the occasions in each course's sequence.")
    h = [f"<h2 id='rooms'>{bi(T('Lokalernas kapacitet', 'Room capacity'))} <span class='sub yearname'></span></h2>",
         f"<p class='sub'>{bi(intro, lambda x: esc(x).replace('KTH Places', places))}</p>",
         f"<div class='legend'>{legend}</div>",
         f"<div class='tablewrap'><table class='rooms'><thead><tr><th>{bi(T('Kurs', 'Course'))}</th>"
         f"<th class='n'>{bi(T('Jämförda', 'Compared'))}</th>"
         + "".join(f"<th class='n'>{CAP_ARROW[lv]} {bi(t)}</th>" for lv, t in ROOM_LEVELS)
         + f"<th class='n'>{bi(T('Ingen lokal bokad', 'No room booked'))}</th>"
         f"<th class='n'>{bi(T('Ej jämförda', 'Not compared'))}</th></tr></thead><tbody>"]
    order = {lv: i for i, (lv, _) in enumerate(ROOM_LEVELS)}

    def weight(item):
        _, cmp = item
        c = [sum(1 for p in cmp["pairs"] if p["level"] == lv) for lv, _ in ROOM_LEVELS]
        return tuple(-x for x in c)

    for code, cmp in sorted(ctx.room_comparison.items(), key=lambda kv: (weight(kv), kv[0])):
        pairs = cmp["pairs"]
        cnt = {lv: sum(1 for p in pairs if p["level"] == lv) for lv in order}
        nr = sum(1 for p in pairs if p["mode"] == "no room booked")
        why: Counter = Counter()
        for p in pairs:
            if p["mode"] == "no room booked":
                continue
            for side, term in (("old", ref), ("new", new)):
                c = p[side]
                if c["seats"] is None:
                    key = ("digital" if c["digital"] else "no_room" if c["no_room"] else "unknown")
                    why[(term, key, ", ".join(c["unknown"]))] += 1
                    break
        nc = sum(why.values())
        reason = {"digital": T("digitalt", "digital"), "no_room": T("ingen lokal", "no room"),
                  "unknown": T("okänt antal platser i", "seats unknown for")}
        tip = both(lambda lang: "\n".join(
            f"{n} × {term}: {reason[k][lang]}" + (f" {rooms}" if k == "unknown" else "")
            for (term, k, rooms), n in why.most_common()))
        nr_cell = f"<span class='capn cap-nr'>{nr}</span>" if nr else ""
        yrs = " ".join(sorted(cy.get(code, set()) & label_set)) or "*"
        cells = "".join(f"<td class='n'><span class='capn {('cap-' + lv) if cnt[lv] else 'zero'}'>"
                        f"{cnt[lv]}</span></td>" for lv in order)
        h.append(f"<tr data-course-years='{esc(yrs)}'><td>{course_link(code)} "
                 f"<span class='sub'>{esc(_NAMES.get(code, ''))}</span></td>"
                 f"<td class='n'>{len(pairs)}</td>{cells}"
                 f"<td class='n'>{nr_cell}</td>"
                 f"<td class='n'{battr('title', tip) if nc else ''}>{nc or ''}</td></tr>")
    h.append("</tbody></table></div>")
    return "".join(h)


ACTIVITY_LEGEND = [("F", T("Föreläsning", "Föreläsning (lecture)")), ("Ö", T("Övning", "Övning (exercise)")),
                   ("L", T("Laboration", "Laboration (lab)")), ("DL", T("Datorlaboration", "Datorlaboration (computer lab)")),
                   ("S", T("Seminarium", "Seminarium (seminar)")), ("Le", T("Lektion", "Lektion (lesson)")),
                   ("W", T("Workshop", "Workshop")), ("P", T("Projekt", "Projekt (project)")),
                   ("Red", T("Redovisning", "Redovisning (presentation)")), ("TEN", T("Tentamen", "Tentamen (exam)")),
                   ("KS", T("Kontrollskrivning", "Kontrollskrivning (partial exam)"))]


def render(res: ReviewResult, lang: str = "sv") -> str:
    global _LANG
    _LANG = lang if lang in LANGS else "sv"
    ctx = res.ctx
    _NAMES.clear()
    for yp in list(ctx.old_plans.values()) + list(ctx.plans.values()):
        if yp.plan:
            _NAMES.update({c: pc.name for c, pc in yp.plan.courses.items() if pc.name})
    issues = res.sorted_issues()
    counts = Counter(i.severity for i in issues if not i.accepted)
    n_acc = sum(1 for i in issues if i.accepted)
    flags = _exam_flags(res)
    labels = [year_label(k) for k in ctx.new.years()]
    label_set = set(labels)
    cy = course_years(res)
    cy_new = course_years(res, reference=False)
    title = T(f"Schemagranskning: {res.title}", f"Schedule review: {res.title}")

    out = [f"<!doctype html><html lang='{_LANG}' data-lang='{_LANG}'><head><meta charset='utf-8'>",
           "<meta name='viewport' content='width=device-width, initial-scale=1'>",
           # Figtree (KTH profile font); falls back to Helvetica/Arial offline.
           "<link rel='preconnect' href='https://fonts.googleapis.com'>",
           "<link rel='preconnect' href='https://fonts.gstatic.com' crossorigin>",
           "<link rel='stylesheet' href='https://fonts.googleapis.com/css2?family=Figtree:wght@400;500;600;700&display=swap'>",
           f"<title>{esc(title[_LANG])}</title><style>{CSS}</style></head><body><main>",
           "<div class='topbtns'><button class='themebtn' id='lang' type='button' lang='en'>English</button>"
           f"<button class='themebtn' id='theme' type='button'>{bi(T('Byt tema', 'Toggle theme'))}</button></div>",
           f"<div class='kthhead'>{LOGO_SVG}<h1>{bi(title)}</h1></div>"]

    def exported(td):
        t = both(lambda lang: export_time_text(td.exports, lang))
        if not t["en"]:
            return ""
        return bi(T(f", exporterat ur TimeEdit <strong>{esc(t['sv'])}</strong>",
                    f", exported from TimeEdit <strong>{esc(t['en'])}</strong>"), lambda x: x)
    sub = f"{bi(T('Granskas', 'Under review'))}: {esc(ctx.new.term)} ({schedule_links(ctx.new)}){exported(ctx.new)}"
    if ctx.old:
        sub += f"<br>{bi(T('Referens', 'Reference'))}: {esc(ctx.old.term)} ({schedule_links(ctx.old)}){exported(ctx.old)}"
    out.append(f"<p class='sub'>{sub}</p>")

    if len(labels) > 1:
        opts = [("*", T("Alla årskurser", "All years"))] + [(lb, lb) for lb in labels]
        seg = "".join(f"<input type='radio' name='year' id='yr-{i}' value='{esc(v)}'>"
                      f"<label for='yr-{i}'>{bi(t)}</label>" for i, (v, t) in enumerate(opts))
        out.append(f"<div class='yearbar'><span class='lbl'>{bi(T('Årskurs', 'Programme year'))}</span>"
                   f"<div class='seg' role='radiogroup'{battr('aria-label', T('Årskurs', 'Programme year'))}>{seg}</div>"
                   "<span class='sub'>" + bi(T("Fynd och kursstruktur följer valet; tentamenskalendrarna visar "
                                               "alla årskurser med den valda markerad.",
                                               "Issues and course structure follow the selection; the exam "
                                               "calendars show all years with the selected one highlighted."))
                   + "</span></div>")
    out.append("<div class='tiles'>")
    for s in SEVERITIES:
        out.append(f"<div class='tile'><div class='n' id='n-{s}'>{counts.get(s, 0)}</div>"
                   f"<div class='l'>{sev_badge(s)}</div></div>")
    out.append(f"<div class='tile'><div class='n' id='n-accepted'>{n_acc}</div>"
               f"<div class='l'>{bi(T('Accepterade', 'Accepted'))}</div></div></div>")
    for key in ctx.new.years():
        lb = year_label(key)
        items = "".join(f"<li>{sev_badge(l['status'])}<span class='chk'>{bi(l['check'])}</span>"
                        f"<span>{bi(l['text'], linkify)}</span></li>" for l in year_status(res, key))
        links = []
        for td in (ctx.new, ctx.old):
            ex = next((e for e in (td.exports if td else []) if e.label == lb), None)
            if ex:
                w = both(lambda lang: export_time_text([ex], lang))
                txt = T(f"schema {td.term}" + (f" (exporterat {w['sv']})" if w["sv"] else ""),
                        f"{td.term} schedule" + (f" (exported {w['en']})" if w["en"] else ""))
                links.append(schedule_link(ex, txt) if ex.url else bi(txt))
        links_html = f" <span class='sub'>· {' · '.join(links)}</span>" if links else ""
        out.append(f"<section class='status' data-course-years='{esc(lb)}'>"
                   f"<h3>{bi(T('Detta kontrollerades', 'What was checked'))}: {esc(lb)}{links_html}</h3>"
                   f"<ul>{items}</ul></section>")
    if res.notes:
        out.append("<ul class='notes'>" + "".join(f"<li>{bi(n)}</li>" for n in res.notes) + "</ul>")
    cal = ctx.new.calendar
    ps = "; ".join(f"{p} {s}–{e}" for p, s, e in cal.periods)
    ew = "; ".join(f"{w.start}–{w.end}" for w in cal.exam_windows)
    rw = "; ".join(f"{w.start}–{w.end}" for w in cal.reexam_windows)
    out.append("<p class='sub'>" + bi(T(f"Läsperioder: {ps} · Tentamensperioder: {ew} · Omtentaperioder: {rw}",
                                        f"Periods: {ps} · Exam windows: {ew} · Re-exam windows: {rw}")) + "</p>")

    # Issues
    out.append(f"<h2>{bi(T('Fynd', 'Issues'))} <span class='sub yearname'></span></h2><div class='filters'>")
    for s in SEVERITIES:
        checked = "" if s == "info" else " checked"
        out.append(f"<label><input type='checkbox' name='sev' value='{s}'{checked}>{sev_badge(s)}</label>")
    ft = T("Filtrera text…", "Filter text…")
    out.append(f"<input id='q' type='search'{battr('placeholder', ft)}{battr('aria-label', ft)}>")
    out.append(f"<label><input type='checkbox' id='acc'>{bi(T('visa accepterade', 'show accepted'))}</label>"
               "<span id='shown' class='sub'></span></div>")
    out.append("<div class='tablewrap'><table id='issues'><thead><tr>"
               + "".join(f"<th>{bi(t)}</th>" for t in (T("Allvarlighet", "Severity"), T("Kontroll", "Check"),
                                                        T("Omfattning", "Scope"), T("Kurs", "Course"),
                                                        T("Fynd", "Finding")))
               + "</tr></thead><tbody>")
    for i in issues:
        ev = "".join(f"<div class='ev'>{esc(e)}</div>" for e in i.evidence[:4])
        acc = (f"<div class='ev'>{bi(T('accepterat', 'accepted'))}: {esc(i.accepted)}</div>"
               if i.accepted else "")
        out.append(f"<tr data-sev='{i.severity}' data-years='{esc(issue_years(i, label_set, cy, cy_new))}' "
                   f"data-acc='{1 if i.accepted else 0}'"
                   f"{' class=accepted' if i.accepted else ''}><td>{sev_badge(i.severity)}</td>"
                   f"<td><code>{esc(i.check)}</code></td><td>{esc(i.scope)}</td>"
                   f"<td>{course_link(i.course) if i.course and _CODE_RE.fullmatch(i.course) else esc(i.course or '')}</td>"
                   f"<td class='msg'>{bi(i.message, linkify)}{ev}{acc}</td></tr>")
    out.append("</tbody></table></div>")

    # Exam calendars
    legend = ("<div class='legend'>"
              f"<span><span class='chip ordinary'>{bi(T('ordinarie', 'ordinary'))}</span></span>"
              f"<span><span class='chip reexam'>{bi(T('omtentamen', 're-exam'))}</span></span>"
              f"<span><span class='chip partial'>{bi(T('delexamination/KS', 'partial/KS'))}</span></span>"
              f"<span><span class='chip flag-error'><span class='fi'>{SEV_ICON['error']}</span>{bi(T('fel', 'error'))}</span></span>"
              f"<span><span class='chip flag-warning'><span class='fi'>{SEV_ICON['warning']}</span>{bi(T('varning', 'warning'))}</span></span>"
              f"<span>{bi(T('starttimme efter koden; håll muspekaren över för detaljer', 'hour of start shown after the code; hover for details'))}</span></div>")
    out.append(f"<h2>{bi(T('Tentamina', 'Exams'))} {esc(ctx.new.term)}</h2>{legend}")
    shown = None
    if ctx.courses:
        # Course review: the course's own exams plus those it was compared with.
        shown = set(ctx.courses) | {c for i in issues if i.check.startswith("exams.")
                                    for c in i.details.get("courses", [])}
    out.append(exam_calendar(ctx.new, flags, shown))
    if ctx.old:
        out.append(f"<details><summary><h3 style='display:inline'>{bi(T('Tentamina', 'Exams'))} {esc(ctx.old.term)} "
                   f"({bi(T('referens', 'reference'))})</h3></summary>")
        out.append(exam_calendar(ctx.old, None, ctx.courses))
        out.append("</details>")

    out.append(room_overview(res, cy, label_set))

    # Course structure
    if ctx.old:
        out.append(f"<h2 id='structure'>{bi(T('Kursstruktur', 'Course structure'))} <span class='sub yearname'></span></h2>")
        out.append("<p class='sub'>" + bi(T(
            "Per kurs visas tillfällena i ordning för båda terminerna; det som räknas är antalet tillfällen och "
            "deras ordning, inte hur de fördelas över veckor. Inramat: de avsnitt som skiljer sig. ”Vecka för "
            "vecka” visar samma tillfällen per undervisningsvecka (veckor utan ordinarie undervisning, t.ex. en "
            "omtentavecka vid påsk, hoppas över; ”tentaperiod” är läsperiodens tentamensperiod). ×n = n "
            "parallella grupptillfällen.",
            "Per course, the sequence of occasions in both terms; what counts is the number of occasions and "
            "their order, not how they fall in weeks. Outlined: the stretches that differ. ‘Week by week’ shows "
            "the same occasions per teaching week (weeks without regular teaching, e.g. an Easter re-exam week, "
            "are skipped; ‘exams’ is the period's exam window). ×n = n parallel group sessions.")) + "</p>")
        legend = "".join(f"<span>{act_chip(a)} {bi(n)}</span>" for a, n in ACTIVITY_LEGEND)
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
            cnt = (f"<span class='cnt'>{bi(T(f'{n} fynd', f'{n} finding(s)'))}</span>" if n
                   else f"<span class='cnt'>{bi(T('oförändrad', 'unchanged'))}</span>")
            yrs = " ".join(sorted(cy.get(code, set()) & label_set)) or "*"
            out.append(f"<details class='course' data-course-years='{esc(yrs)}'"
                       f"{' open' if n and ctx.review == 'course' else ''}>"
                       f"<summary>{esc(course_title(code))}{cnt}</summary>"
                       f"<p class='sub'>{course_link(code)} {bi(T('kurssida på kth.se', 'course page on kth.se'))}</p>")
            for i in per_course.get(code, []):
                out.append(f"<p>{sev_badge(i.severity)} {bi(i.message, linkify)}</p>")
            out.append(week_table(res, code))
            out.append("</details>")

    out.append(f"<script>{JS}</script></main></body></html>")
    return "".join(out)


def write(res: ReviewResult, out_dir: Path, lang: str = "sv") -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = res.title.split(" vs ")[0].replace(", ", "_").replace(" ", "_")
    p = out_dir / f"{stem}_review.html"
    p.write_text(render(res, lang), encoding="utf-8")
    return p
