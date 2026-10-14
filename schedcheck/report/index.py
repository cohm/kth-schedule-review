"""Landing page listing several review reports (e.g. one per programme)."""
from __future__ import annotations

import json
from pathlib import Path

from .html import CSS, LOGO_SVG, esc, sev_badge
from ..model import SEVERITIES


def write_index(folder: str | Path, title: str = "Schedule reviews") -> Path:
    """Scan subfolders of `folder` for issues.json + *_review.html and write index.html."""
    folder = Path(folder)
    rows = []
    for sub in sorted(p for p in folder.iterdir() if p.is_dir()):
        js, pages = sub / "issues.json", sorted(sub.glob("*_review.html"))
        if not js.exists() or not pages:
            continue
        d = json.loads(js.read_text(encoding="utf-8"))
        s = d.get("summary", {})
        unverified = any("not verified" in n for n in d.get("notes", []))
        comments = sorted(sub.glob("*_kommentarer.html")) + sorted(sub.glob("*_comments.html"))
        rows.append(
            f"<tr><td><a class='cl' href='{esc(sub.name)}/{esc(pages[0].name)}'>{esc(d['title'])}</a>"
            + (" <span class='sub'>(study-plan data not verified)</span>" if unverified else "")
            + "</td>"
            + "".join(f"<td>{s.get(k, 0)}</td>" for k in SEVERITIES)
            + (f"<td><a class='cl' href='{esc(sub.name)}/{esc(comments[0].name)}'>comments</a></td>"
               if comments else "<td></td>")
            + f"<td class='sub'>{esc(d.get('generated', '')[:10])}</td></tr>")
    head = "".join(f"<th>{sev_badge(k)}</th>" for k in SEVERITIES)
    html = ("<!doctype html><html lang='en'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width, initial-scale=1'>"
            "<link rel='stylesheet' href='https://fonts.googleapis.com/css2?family=Figtree:wght@400;500;600;700&display=swap'>"
            f"<title>{esc(title)}</title><style>{CSS}</style></head><body><main>"
            f"<div class='kthhead'>{LOGO_SVG}<h1>{esc(title)}</h1></div>"
            "<p class='sub'>Automated checks of preliminary TimeEdit schedules against the study plans "
            "and last year's final schedule. Each report shows, per programme year, what was checked "
            "and what was found.</p>"
            f"<div class='tablewrap'><table><thead><tr><th>Review</th>{head}<th>Draft comments</th>"
            f"<th>Generated</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>"
            "<p class='sub'>Generated with <a class='cl' href='https://github.com/cohm/kth-schedule-review'>"
            "kth-schedule-review</a>.</p></main></body></html>")
    out = folder / "index.html"
    out.write_text(html, encoding="utf-8")
    return out

