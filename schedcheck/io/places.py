"""Room capacities from KTH Places (https://www.kth.se/places).

Places pages embed their data as URL-encoded JSON (`window.__compressedData__DATA`):

    /places/building            buildings [{uid, name}]
    /places/building/<uid>      roomsByBuilding.rooms [{uid, roomDisplayName, typeName}]
    /places/room/id/<uid>       place {numSeats, numSeatsExamination, typeName, buildingName, ...}

The building pages give the names of all rooms (about 5,600) but no seat
counts, so seats are read from the room pages, only for rooms that occur in
the exports. Both are cached (default 30 days); a first run reads ~115
building pages plus one page per room used.

Room fields in TimeEdit list one or more rooms: "Q34, Q36", "FB52-53",
"012:024-025, 013:012", "FR4 (Oskar Kleins auditorium)", "Digital".
Places' display names may carry the popular name the same way
("FR4 (OSKAR KLEINS AUDITORIUM)"), so names are compared without it.

Manual capacities (rooms missing from Places, or corrections) come from a
TOML file:

    [capacity]
    "U31 Break-out" = 20
"""
from __future__ import annotations

import http.client
import json
import os
import re
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

BASE = "https://www.kth.se/places"
BUILDINGS = BASE + "/building"
DIGITAL = {"digital", "zoom", "online", "distans", "teams"}

# Room types in order of preference when one name matches several rooms
# (e.g. "B2" is a lecture hall and an entrance).
TYPE_TIERS = [{"Hörsal", "Övningssal", "Datorsal", "Seminarierum", "Grupprum", "Lektionssal"},
              {"Labb", "Lab", "Breakout", "Ritsal", "Sektionslokal", "Utställningssal", "Läsplats"}]


@dataclass
class RoomInfo:
    name: str                    # as written in the export, e.g. "FB52"
    status: str                  # ok | manual | digital | unknown | no-seats | ambiguous
    seats: int | None = None
    place: str = ""              # Places display name and type, e.g. "FD5 (Hörsal, AlbaNova)"
    url: str = ""


def _key(name: str) -> str:
    return re.sub(r"\s+", "", name).upper()


def _short(name: str) -> str:
    """Name without a trailing "(popular name)"."""
    return re.sub(r"\s*\([^)]*\)\s*$", "", name).strip()


_RANGE = re.compile(r"^(.*?)(\d+)-(\d+)$")


def split_rooms(field: str) -> list[str]:
    """Room names in a TimeEdit room field, ranges expanded ("FB52-53" ->
    FB52, FB53; "012:024-025" -> 012:024, 012:025), popular names dropped."""
    out: list[str] = []
    for tok in (t.strip() for t in (field or "").split(",")):
        if not tok:
            continue
        tok = _short(tok)
        if re.fullmatch(r"\d+\.0", tok):   # a number cell in the export, e.g. "4303.0"
            tok = tok[:-2]
        m = _RANGE.match(tok)
        if m and m.group(1) and not m.group(1).endswith("-"):
            pre, a, b = m.groups()
            if len(b) < len(a):          # "FB52-3" style
                b = a[:len(a) - len(b)] + b
            lo, hi = int(a), int(b)
            if 0 < hi - lo <= 20:
                out += [f"{pre}{n:0{len(a)}d}" for n in range(lo, hi + 1)]
                continue
        out.append(tok)
    return list(dict.fromkeys(out))


def _embedded(page: str) -> dict:
    m = re.search(r'window\.__compressedData__DATA\s*=\s*"([^"]*)"', page)
    if not m:
        raise ValueError("no embedded data found")
    return json.loads(urllib.parse.unquote(m.group(1)))


def load_manual(path: str | Path | None) -> dict[str, int]:
    if not path:
        return {}
    data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    return {_key(_short(k)): int(v) for k, v in data.get("capacity", {}).items()}


class RoomSource:
    """Looks up room capacities in KTH Places, with a local cache."""

    def __init__(self, cache_dir: str | Path | None = None, max_age_days: float = 30,
                 pause: float = 0.2, manual: dict[str, int] | None = None):
        if cache_dir is None:
            base = os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache"
            cache_dir = Path(base) / "schedcheck"
        self.dir = Path(cache_dir) / "places"
        self.max_age = max_age_days * 86400
        self.pause = pause
        self.manual = manual or {}
        self.errors: list[str] = []
        self._index: dict[str, list[dict]] | None = None
        self._seats: dict[str, dict] | None = None
        self._cache: dict[str, RoomInfo] = {}

    # -- network ---------------------------------------------------------
    def _get(self, url: str) -> dict:
        last = None
        for _ in range(3):
            try:
                with urllib.request.urlopen(url, timeout=30) as r:
                    page = r.read().decode("utf-8", errors="replace")
                return _embedded(page)
            except (urllib.error.URLError, http.client.HTTPException, OSError, ValueError) as e:
                last = e
                time.sleep(self.pause)
        raise RuntimeError(f"{url}: {last}")

    def _fresh(self, p: Path) -> bool:
        return p.exists() and time.time() - p.stat().st_mtime < self.max_age

    def _save(self, p: Path, data) -> None:
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass

    # -- room names --------------------------------------------------------
    def index(self) -> dict[str, list[dict]]:
        """Normalised room name -> candidate rooms [{uid, name, type}]."""
        if self._index is not None:
            return self._index
        p = self.dir / "rooms.json"
        rooms = None
        if self._fresh(p):
            rooms = json.loads(p.read_text(encoding="utf-8"))
        else:
            try:
                rooms = self._crawl()
                self._save(p, rooms)
            except RuntimeError as e:
                self.errors.append(f"room list: {e}")
                if p.exists():   # stale cache beats nothing
                    rooms = json.loads(p.read_text(encoding="utf-8"))
        idx: dict[str, list[dict]] = {}
        for r in rooms or []:
            # Some display names list several names ("U1, U61 Break-out").
            names = [r["name"]] + [n.strip() for n in r["name"].split(",")]
            for k in {f(n) for n in names for f in (_key, lambda n: _key(_short(n)))}:
                idx.setdefault(k, []).append(r)
        self._index = idx
        return idx

    def _crawl(self) -> list[dict]:
        buildings = self._get(BUILDINGS).get("buildings", [])
        if not buildings:
            raise RuntimeError(f"{BUILDINGS}: no buildings listed")
        rooms, failed = [], 0
        for b in buildings:
            try:
                d = self._get(f"{BUILDINGS}/{b['uid']}")
            except RuntimeError:
                failed += 1
                continue
            for r in (d.get("roomsByBuilding") or {}).get("rooms", []):
                if r.get("uid") and r.get("roomDisplayName"):
                    rooms.append({"uid": r["uid"], "name": r["roomDisplayName"],
                                  "type": r.get("typeName", "")})
            time.sleep(self.pause)
        if failed > len(buildings) // 10:
            raise RuntimeError(f"{failed} of {len(buildings)} building pages could not be read")
        if failed:
            self.errors.append(f"{failed} building page(s) could not be read; some rooms may be unknown")
        return rooms

    # -- seats -------------------------------------------------------------
    def _seat_cache(self) -> dict[str, dict]:
        if self._seats is None:
            p = self.dir / "seats.json"
            self._seats = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        return self._seats

    def room(self, uid: str) -> dict | None:
        cache = self._seat_cache()
        hit = cache.get(uid)
        if hit and time.time() - hit.get("fetched", 0) < self.max_age:
            return hit
        try:
            pl = self._get(f"{BASE}/room/id/{uid}").get("place") or {}
        except RuntimeError as e:
            self.errors.append(str(e))
            return hit       # stale entry, or None
        seats = pl.get("numSeats")
        rec = {"seats": int(seats) if str(seats or "").isdigit() else None,
               "name": pl.get("roomDisplayName", ""), "type": pl.get("typeName", ""),
               "building": pl.get("buildingName", ""), "fetched": time.time()}
        cache[uid] = rec
        self._save(self.dir / "seats.json", cache)
        time.sleep(self.pause)
        return rec

    def lookup(self, name: str) -> RoomInfo:
        if name in self._cache:
            return self._cache[name]
        info = self._lookup(name)
        self._cache[name] = info
        return info

    def _lookup(self, name: str) -> RoomInfo:
        k = _key(_short(name))
        if k in self.manual:
            return RoomInfo(name, "manual", self.manual[k], "manual capacity")
        if name.strip().casefold() in DIGITAL:
            return RoomInfo(name, "digital")
        cands = self.index().get(k, []) or self.index().get(_key(name), [])
        if not cands:
            return RoomInfo(name, "unknown")
        for tier in TYPE_TIERS + [None]:
            pick = [c for c in cands if tier is None or c["type"] in tier]
            if pick:
                cands = pick
                break
        recs = [(c, self.room(c["uid"])) for c in {c["uid"]: c for c in cands}.values()]
        seats = {r["seats"] for _, r in recs if r}
        if len(seats) != 1 or None in seats:
            st = "ambiguous" if len(seats - {None}) > 1 else "no-seats"
            return RoomInfo(name, st, None, "; ".join(f"{c['name']} ({c['type']})" for c, _ in recs))
        c, r = recs[0]
        return RoomInfo(name, "ok", seats.pop(),
                        f"{r['name'] or c['name']} ({', '.join(x for x in (r['type'], r['building']) if x)})",
                        f"{BASE}/room/id/{c['uid']}")
