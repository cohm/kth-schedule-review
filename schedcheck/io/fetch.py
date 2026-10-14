"""Fetching TimeEdit exports through the user's own browser.

TimeEdit's staff views need a KTH login, so this module never downloads
anything itself and never handles credentials: `fetch` builds the export
URLs and opens them in the default browser (where the user is logged in);
`collect` then picks the downloaded files up, identifies each one from its
header (programme year and date range) and files it.

Export URL pattern (KTH staff area, observed 2026-10):

    https://cloud.timeedit.net/kth/web/staff01/ri.xlsx
        ?h=t&sid=<view>&p=<YYYYMMDD>.x,<YYYYMMDD>.x&objects=<object id>&<layout params>

    sid      view: 9 = preliminary (remiss), 10 = published schedule
    p        date range (first day of term .. end of the August re-exams)
    objects  the programme year, e.g. CTFYS1 = 386379.16 (same in all views and terms)

Config (TOML, kept in the user's workspace):

    base  = "https://cloud.timeedit.net/kth/web/staff01/ri.xlsx"
    views = { remiss = 9, final = 10 }
    objects = { CTFYS1 = "386379.16", CTFYS2 = "386225.16" }

    [terms]
    VT26 = ["2026-01-13", "2026-08-23"]
    VT27 = ["2027-01-12", "2027-08-29"]
"""
from __future__ import annotations

import datetime as dt
import json
import shutil
import time
import tomllib
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode

from .timeedit import read_export

# Layout parameters as in TimeEdit's own export links; they do not change the
# exported data, but keeping them identical makes requests look like the UI's.
DEFAULT_PARAMS = {"ox": "0", "types": "0", "fe": "0", "mw": "300", "ps": "A4", "sp": "f",
                  "pl": "1", "fs": "9", "cl": "x89", "shf": "0", "wpp": "1"}
MANIFEST = ".schedcheck-fetch.json"


@dataclass
class FetchConfig:
    base: str
    views: dict[str, int]
    objects: dict[str, str]
    terms: dict[str, tuple[dt.date, dt.date]]
    params: dict[str, str]


def load_config(path: str | Path) -> FetchConfig:
    data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    terms = {t: (dt.date.fromisoformat(a), dt.date.fromisoformat(b))
             for t, (a, b) in data.get("terms", {}).items()}
    for key in ("base", "views", "objects"):
        if key not in data:
            raise ValueError(f"{path}: missing '{key}'")
    return FetchConfig(data["base"], dict(data["views"]), dict(data["objects"]), terms,
                       {**DEFAULT_PARAMS, **data.get("params", {})})


def export_url(cfg: FetchConfig, label: str, term: str, view: str) -> str:
    try:
        start, end = cfg.terms[term]
    except KeyError:
        raise ValueError(f"term {term} has no dates in the config [terms] table") from None
    if view not in cfg.views:
        raise ValueError(f"unknown view '{view}' (config has: {', '.join(cfg.views)})")
    if label not in cfg.objects:
        raise ValueError(f"no TimeEdit object for {label} (config has: {', '.join(cfg.objects)})")
    q = {"h": "t", "sid": str(cfg.views[view]), "p": f"{start:%Y%m%d}.x,{end:%Y%m%d}.x",
         "objects": cfg.objects[label], **cfg.params}
    return f"{cfg.base}?{urlencode(q, safe='.')}"


def plan_requests(cfg: FetchConfig, labels: list[str], sets: list[tuple[str, str, str]]) -> list[dict]:
    """sets: [(term, view, destination folder)] -> one request per label and set."""
    terms = [t for t, _, _ in sets]
    if len(set(terms)) != len(terms):
        raise ValueError("each term may be requested once: files are told apart by their date range")
    out = []
    for term, view, dest in sets:
        start, end = cfg.terms[term] if term in cfg.terms else (None, None)
        for label in labels:
            out.append({"label": label, "term": term, "view": view, "dest": str(dest),
                        "start": str(start), "end": str(end),
                        "url": export_url(cfg, label, term, view)})
    return out


def write_manifest(requests: list[dict], path: str | Path = MANIFEST) -> Path:
    p = Path(path)
    p.write_text(json.dumps({"requested_at": time.time(), "requests": requests},
                            ensure_ascii=False, indent=1), encoding="utf-8")
    return p


def open_in_browser(urls: list[str], pause: float = 1.5) -> None:
    for u in urls:
        webbrowser.open_new_tab(u)
        time.sleep(pause)  # be gentle with the server and the browser


@dataclass
class CollectResult:
    filed: list[tuple[Path, Path]]     # (source, destination)
    missing: list[dict]                # requests without a matching file
    ignored: list[tuple[Path, str]]    # (file, reason)


def collect(src: str | Path, manifest: str | Path = MANIFEST, copy: bool = False,
            since_slack: float = 60.0) -> CollectResult:
    """File downloaded exports that match the manifest, by programme year and
    date range read from each file's header. Only files modified after the
    fetch (minus a small slack) are considered."""
    m = json.loads(Path(manifest).read_text(encoding="utf-8"))
    since = m["requested_at"] - since_slack
    wanted = {(r["label"], r["start"], r["end"]): r for r in m["requests"]}
    filed, ignored, done = [], [], set()
    files = sorted((p for p in Path(src).expanduser().glob("*.xlsx")
                    if not p.name.startswith("~$") and p.stat().st_mtime >= since),
                   key=lambda p: p.stat().st_mtime, reverse=True)  # newest first
    for p in files:
        try:
            ex = read_export(p)
        except Exception as e:  # not a TimeEdit export
            ignored.append((p, f"unreadable: {e}"))
            continue
        key = (ex.label, str(ex.range_start), str(ex.range_end))
        r = wanted.get(key)
        if r is None:
            ignored.append((p, f"{ex.label} {ex.range_start}..{ex.range_end} was not requested"))
            continue
        if key in done:
            ignored.append((p, f"older duplicate of {ex.label} {r['term']}"))
            continue
        dest_dir = Path(r["dest"])
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{r['label']}_{r['term']}_{r['view']}.xlsx"
        (shutil.copy2 if copy else shutil.move)(str(p), str(dest))
        filed.append((p, dest))
        done.add(key)
    missing = [r for k, r in wanted.items() if k not in done]
    return CollectResult(filed, missing, ignored)
