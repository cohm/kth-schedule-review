"""Machine-readable output (issues.json), the interface for the agent layer."""
from __future__ import annotations

import datetime as dt
import json
from collections import Counter
from pathlib import Path

from ..reviews.program import ReviewResult
from .status import all_year_status

SCHEMA_VERSION = 1


def to_dict(res: ReviewResult) -> dict:
    ctx = res.ctx
    issues = res.sorted_issues()
    return {
        "schema": SCHEMA_VERSION,
        "generated": dt.datetime.now().isoformat(timespec="seconds"),
        "review": res.review,
        "title": res.title,
        "term": ctx.new.term,
        "reference_term": ctx.old.term if ctx.old else None,
        "exports": [{"path": ex.path, "label": ex.label, "range": [str(ex.range_start), str(ex.range_end)]}
                    for ex in ctx.new.exports],
        "reference_exports": [{"path": ex.path, "label": ex.label} for ex in (ctx.old.exports if ctx.old else [])],
        "calendar": {
            "periods": [[p, str(s), str(e)] for p, s, e in ctx.new.calendar.periods],
            "exam_windows": [[w.label, str(w.start), str(w.end)] for w in ctx.new.calendar.exam_windows],
            "reexam_windows": [[w.label, str(w.start), str(w.end)] for w in ctx.new.calendar.reexam_windows],
        },
        "notes": res.notes,
        "year_status": all_year_status(res),
        "summary": dict(Counter(i.severity for i in issues if not i.accepted)),
        "accepted_count": sum(1 for i in issues if i.accepted),
        "issues": [i.to_dict() for i in issues],
        "room_comparison": ctx.room_comparison,
    }


def write(res: ReviewResult, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / "issues.json"
    p.write_text(json.dumps(to_dict(res), ensure_ascii=False, indent=1), encoding="utf-8")
    return p


def text_summary(res: ReviewResult, show_info: bool = False) -> str:
    lines = [f"# {res.title}", ""]
    for n in res.notes:
        lines.append(f"note: {n}")
    issues = res.sorted_issues()
    c = Counter(i.severity for i in issues if not i.accepted)
    lines.append("")
    lines.append("summary: " + ", ".join(f"{k} {c.get(k, 0)}" for k in ("error", "warning", "review", "info"))
                 + f", accepted {sum(1 for i in issues if i.accepted)}")
    lines.append("")
    for i in issues:
        if i.severity == "info" and not show_info:
            continue
        acc = f" [accepted: {i.accepted}]" if i.accepted else ""
        lines.append(f"[{i.severity.upper():7}] {i.check:28} {i.scope:8} {i.message}{acc}")
    return "\n".join(lines)
