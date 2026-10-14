"""Optional configuration: shared per-programme files and per-review accept lists.

programs/<PROG>.toml (shipped with the repo, shared knowledge):

    [thresholds]
    # exams this many calendar days apart (0 = same day) get this severity
    same_day = "error"
    adjacent = "warning"
    two_days = "info"

    [[eligibility_group]]       # adds to / overrides the study-plan data
    master = "TMAKM"
    name = "Matematik"
    courses = ["SF1677", "SF1678"]
    verified = false

<workspace>/accepted.toml (per review round, not shared):

    [[accepted]]
    check = "structure.sequence"
    course = "DD1327"
    key = ""                    # optional; empty matches any key
    note = "New workshop format agreed with examiner"
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .model import Issue

REPO_PROGRAMS_DIR = Path(__file__).resolve().parent.parent / "programs"

DEFAULT_THRESHOLDS = {"same_day": "error", "adjacent": "warning", "two_days": "info"}


@dataclass
class Config:
    thresholds: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_THRESHOLDS))
    eligibility_groups: list[dict] = field(default_factory=list)
    accepted: list[dict] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)


def load_config(program: str | None, programs_dir: Path | None = None,
                accepted_file: str | Path | None = None) -> Config:
    cfg = Config()
    pdir = programs_dir or REPO_PROGRAMS_DIR
    if program:
        p = pdir / f"{program}.toml"
        if p.exists():
            data = tomllib.loads(p.read_text(encoding="utf-8"))
            cfg.thresholds.update(data.get("thresholds", {}))
            cfg.eligibility_groups.extend(data.get("eligibility_group", []))
            cfg.sources.append(str(p))
    if accepted_file:
        p = Path(accepted_file)
        if p.exists():
            data = tomllib.loads(p.read_text(encoding="utf-8"))
            cfg.accepted.extend(data.get("accepted", []))
            cfg.sources.append(str(p))
    return cfg


def apply_accepted(issues: list[Issue], accepted: list[dict]) -> None:
    for issue in issues:
        for a in accepted:
            if a.get("check") and a["check"] != issue.check:
                continue
            if a.get("course") and a["course"] != issue.course:
                continue
            if a.get("key") and a["key"] != issue.key:
                continue
            issue.accepted = a.get("note", "accepted")
            break
