"""Fetching TimeEdit exports through the user's own browser.

TimeEdit's staff views need a KTH login, so this module never downloads
anything itself and never handles credentials: `fetch` builds the export
URLs and opens them in the default (or a chosen) browser, where the user is
logged in;
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
import math
import re
import shutil
import subprocess
import sys
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


def select_labels(cfg: FetchConfig, wanted: list[str] | None) -> list[str]:
    """Programme years to fetch: exact labels (CTMAT2) or programme codes (CTMAT
    = all its years in the config). None/empty means everything in the config."""
    if not wanted:
        return list(cfg.objects)
    out = []
    for w in wanted:
        hits = [lb for lb in cfg.objects if lb == w or lb.rstrip("0123456789") == w]
        if not hits:
            raise ValueError(f"'{w}' matches nothing in the config (has: {', '.join(cfg.objects)})")
        out += [h for h in hits if h not in out]
    return out


def program_of(label: str) -> str:
    return label.rstrip("0123456789")


def plan_requests(cfg: FetchConfig, labels: list[str], sets: list[tuple[str, str, str]]) -> list[dict]:
    """sets: [(term, view, destination folder)] -> one request per label and set.
    The destination may contain {program}, {term} and {view} placeholders."""
    terms = [t for t, _, _ in sets]
    if len(set(terms)) != len(terms):
        raise ValueError("each term may be requested once: files are told apart by their date range")
    out = []
    for term, view, dest in sets:
        start, end = cfg.terms[term] if term in cfg.terms else (None, None)
        for label in labels:
            folder = str(dest).format(program=program_of(label), term=term, view=view)
            out.append({"label": label, "term": term, "view": view, "dest": folder,
                        "start": str(start), "end": str(end),
                        "url": export_url(cfg, label, term, view)})
    return out


def write_manifest(requests: list[dict], path: str | Path = MANIFEST) -> Path:
    p = Path(path)
    p.write_text(json.dumps({"requested_at": time.time(), "requests": requests},
                            ensure_ascii=False, indent=1), encoding="utf-8")
    return p


def open_in_browser(urls: list[str], pause: float = 1.5, browser: str | None = None) -> None:
    """Open URLs in the default browser, or in a named one (e.g. "Safari",
    "Google Chrome", "Firefox"). The user must be logged in to TimeEdit there."""
    for u in urls:
        if browser and sys.platform == "darwin":
            subprocess.run(["open", "-a", browser, u], check=True)
        elif browser:
            webbrowser.get(browser).open_new_tab(u)
        else:
            webbrowser.open_new_tab(u)
        time.sleep(pause)  # be gentle with the server and the browser


# -- links to the schedules themselves ------------------------------------------
#
# TimeEdit's schedule pages have URLs like .../staff01/ri<scrambled query>.html,
# where the query is the same as for an export, scrambled by TimeEdit's own
# (reversible) obfuscation: common substrings shortened, characters substituted,
# positions swapped in a fixed pattern. Verified 2026-10 against links copied
# from TimeEdit (tests/test_fetch.py has them).

_TE_TABLE = [("h=t&sid=", "6="), ("objects=", "1="), ("sid=", "2="), ("&ox=0&types=0&fe=0", "3=3"),
             ("&types=0&fe=0", "5=5"), ("&h=t&p=", "4=")]
_TE_PAIRS = [("=", "Q"), ("&", "Z"), (",", "X"), (".", "Y"), (" ", "V"), ("-", "W")]
_TE_PATTERN = [4, 22, 5, 37, 26, 17, 33, 15, 39, 11, 45, 20, 2, 40, 19, 36, 28, 38, 30, 41, 44, 42, 7, 24,
               14, 27, 35, 25, 12, 1, 43, 23, 6, 16, 3, 9, 47, 46, 48, 50, 21, 10, 49, 32, 18, 31, 29, 34, 13, 8]


def _te_char(c: str, inverse: bool = False) -> str:
    for a, b in _TE_PAIRS:
        if c == a:
            return b
        if c == b:
            return a
    o = ord(c)
    if 97 <= o <= 122:                   # a-z rotated by 9
        return chr(97 + (o - 97 + (17 if inverse else 9)) % 26)
    if 49 <= o <= 57:                    # 1-9 rotated by 4 (0 unchanged)
        return chr(49 + (o - 49 + (5 if inverse else 4)) % 9)
    return c


def _te_swaps(n: int) -> list[tuple[int, int]]:
    k = len(_TE_PATTERN)
    return [(_TE_PATTERN[i] + step * k, _TE_PATTERN[i - 1] + step * k)
            for step in range(math.ceil(n / k)) for i in range(1, k, 2)]


def _te_apply(s: str, swaps) -> str:
    c = list(s)
    for a, b in swaps:
        if a < len(c) and b < len(c):
            c[a], c[b] = c[b], c[a]
    return "".join(c)


def te_scramble(query: str) -> str:
    for a, b in _TE_TABLE:
        query = query.replace(a, b)
    return _te_apply("".join(_te_char(c) for c in query), _te_swaps(len(query)))


def te_unscramble(s: str) -> str:
    s = "".join(_te_char(c, True) for c in _te_apply(s, reversed(_te_swaps(len(s)))))
    for a, b in reversed(_TE_TABLE):
        s = s.replace(b, a)
    return s


def schedule_url(cfg: FetchConfig, label: str, start: dt.date, end: dt.date, view: str) -> str | None:
    """Link to the TimeEdit schedule page of a programme year (needs a KTH login),
    or None if the config lacks the object or view."""
    if label not in cfg.objects or view not in cfg.views:
        return None
    q = (f"h=t&sid={cfg.views[view]}&p={start:%Y%m%d}.x,{end:%Y%m%d}.x"
         f"&objects={cfg.objects[label]}&ox=0&types=0&fe=0")
    return f"{cfg.base.rsplit('/', 1)[0]}/ri{te_scramble(q)}.html"


def view_from_filename(path: str | Path, cfg: FetchConfig) -> str | None:
    """'CTFYS1_VT27_remiss.xlsx' -> 'remiss' (the names 'collect' gives files)."""
    m = re.search(r"_([A-Za-z]+)\.xlsx$", Path(path).name)
    return m.group(1) if m and m.group(1) in cfg.views else None


def link_exports(exports, cfg: FetchConfig, view: str | None = None) -> int:
    """Set Export.url for exports whose view is known (argument or file name)."""
    n = 0
    for ex in exports:
        v = view or view_from_filename(ex.path, cfg)
        if v and ex.range_start and ex.range_end:
            ex.url = schedule_url(cfg, ex.label, ex.range_start, ex.range_end, v) or ""
            n += bool(ex.url)
    return n


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
