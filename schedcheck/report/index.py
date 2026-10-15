"""Landing page listing several review reports (e.g. one per programme).
Bilingual like the reports (sv/en toggle, default from --lang)."""
from __future__ import annotations

import json
from pathlib import Path

from . import html as H
from .html import CSS, JS, LOGO_SVG, battr, bi, esc, sev_badge
from ..i18n import LANGS, T
from ..model import SEVERITIES


def write_index(folder: str | Path, title: str | dict = T("Schemagranskningar", "Schedule reviews"),
                lang: str = "sv") -> Path:
    """Scan subfolders of `folder` for issues.json + *_review.html and write index.html."""
    H._LANG = lang if lang in LANGS else "sv"
    title = title if isinstance(title, dict) else T(title, title)
    folder = Path(folder)
    rows = []
    for sub in sorted(p for p in folder.iterdir() if p.is_dir()):
        js, pages = sub / "issues.json", sorted(sub.glob("*_review.html"))
        if not js.exists() or not pages:
            continue
        d = json.loads(js.read_text(encoding="utf-8"))
        s = d.get("summary", {})
        notes = d.get("notes", [])
        unverified = any("not verified" in (n.get("en", "") if isinstance(n, dict) else n) for n in notes)
        comments = sorted(sub.glob("*_kommentarer.html")) + sorted(sub.glob("*_comments.html"))
        rows.append(
            f"<tr><td><a class='cl' href='{esc(sub.name)}/{esc(pages[0].name)}'>{esc(d['title'])}</a>"
            + (f" <span class='sub'>({bi(T('utbildningsplanens data inte verifierad', 'study-plan data not verified'))})</span>"
               if unverified else "")
            + "</td>"
            + "".join(f"<td>{s.get(k, 0)}</td>" for k in SEVERITIES)
            + "<td>" + " ".join(
                f"<a class='cl' href='{esc(sub.name)}/{esc(c.name)}'>"
                f"{'svenska' if c.name.endswith('_kommentarer.html') else 'English'}</a>" for c in comments)
            + "</td>"
            + f"<td class='sub'>{esc(d.get('generated', '')[:10])}</td></tr>")
    head = "".join(f"<th>{sev_badge(k)}</th>" for k in SEVERITIES)
    intro = T("Automatiska kontroller av preliminära TimeEdit-scheman mot utbildningsplanerna och förra årets "
              "slutliga schema. Varje rapport visar, per årskurs, vad som kontrollerades och vad som hittades.",
              "Automated checks of preliminary TimeEdit schedules against the study plans and last year's "
              "final schedule. Each report shows, per programme year, what was checked and what was found.")
    page = (f"<!doctype html><html lang='{H._LANG}' data-lang='{H._LANG}'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width, initial-scale=1'>"
            "<link rel='stylesheet' href='https://fonts.googleapis.com/css2?family=Figtree:wght@400;500;600;700&display=swap'>"
            f"<title>{esc(title[H._LANG])}</title><style>{CSS}</style></head><body><main>"
            "<div class='topbtns'><button class='themebtn' id='lang' type='button'>English</button>"
            f"<button class='themebtn' id='theme' type='button'>{bi(T('Byt tema', 'Toggle theme'))}</button></div>"
            f"<div class='kthhead'>{LOGO_SVG}<h1>{bi(title)}</h1></div>"
            f"<p class='sub'>{bi(intro)}</p>"
            f"<div class='tablewrap'><table><thead><tr><th>{bi(T('Granskning', 'Review'))}</th>{head}"
            f"<th>{bi(T('Kommentarsutkast', 'Draft comments'))}</th>"
            f"<th>{bi(T('Skapad', 'Generated'))}</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>"
            f"<p class='sub'>{bi(T('Skapad med', 'Generated with'))} "
            "<a class='cl' href='https://github.com/cohm/kth-schedule-review'>kth-schedule-review</a>.</p>"
            f"<script>{JS}</script></main></body></html>")
    out = folder / "index.html"
    out.write_text(page, encoding="utf-8")
    return out
