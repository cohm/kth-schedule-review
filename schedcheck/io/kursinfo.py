"""Course syllabus data (exam modules, round dates) from KTH's course pages.

The course page https://www.kth.se/student/kurser/kurs/<CODE> embeds its data
as URL-encoded JSON (`window.__compressedData__DATA`), including every
syllabus version (`courseData.syllabusList`, each with `course_valid_from`
and `course_examination`, an HTML list like
"<li>TEN2 - Skriftlig tentamen, 3,0 hp, betygsskala: P, F</li>") and the
course rounds (`courseData.roundsBySemester`).

Only exam modules, syllabus validity and round dates are extracted and
cached; the page also contains staff names, which are never stored.
(The KOPPS API was unavailable in 2026-10, hence the course page.)
"""
from __future__ import annotations

import http.client
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

COURSE_PAGE = "https://www.kth.se/student/kurser/kurs/{code}"
_MODULE_RE = re.compile(r"^\s*([A-ZÅÄÖ]{2,4}\d{0,2})\s*-\s*(.+?),\s*([\d,\.]+)\s*hp", re.I)


@dataclass
class ExamModule:
    code: str          # e.g. "TEN2"
    name: str          # e.g. "Skriftlig tentamen"
    credits: float

    @property
    def written_exam(self) -> bool:
        """A written exam needing a scheduled sitting (oral exams are usually
        booked individually and not in the schedule)."""
        n = self.name.casefold()
        return (self.code.upper().startswith("TEN") and self.credits > 0
                and not any(w in n for w in ("muntlig", "oral", "valfri", "optional")))

    def label(self) -> str:
        cr = f"{self.credits:g}".replace(".", ",")
        return f"{self.code} – {self.name}, {cr} hp"


@dataclass
class Syllabus:
    code: str
    valid_from: str                    # e.g. "HT2026"
    modules: list[ExamModule]
    rounds: list[dict] = field(default_factory=list)   # [{"semester", "start", "end", "application_code"}]
    source: str = ""

    @property
    def written(self) -> list[ExamModule]:
        return [m for m in self.modules if m.written_exam]


def term_key(term: str) -> tuple[int, int]:
    """'VT27' -> (2027, 1), 'HT26' -> (2026, 2) (KTH's semesterNumber)."""
    return (2000 + int(term[2:]), 1 if term.startswith("VT") else 2)


def _term_label(year: int, sem: int) -> str:
    return f"{'VT' if sem == 1 else 'HT'}{year}"


def parse_modules(html: str) -> list[ExamModule]:
    out = []
    for li in re.findall(r"<li>(.*?)</li>", html or "", flags=re.S):
        text = re.sub(r"<[^>]+>", "", li)
        m = _MODULE_RE.match(text)
        if m:
            out.append(ExamModule(m.group(1).upper(), m.group(2).strip(),
                                  float(m.group(3).replace(",", "."))))
    return out


def extract(page_html: str, code: str) -> dict:
    """The parts of a course page we keep: syllabus versions and rounds."""
    m = re.search(r'window\.__compressedData__DATA\s*=\s*"([^"]*)"', page_html)
    if not m:
        raise ValueError("no embedded course data found")
    data = json.loads(urllib.parse.unquote(m.group(1)))
    cd = data.get("courseData", {})
    syllabi = []
    for s in cd.get("syllabusList", []):
        vf = s.get("course_valid_from") or {}
        if not vf.get("year"):
            continue
        syllabi.append({"valid_from": [vf["year"], vf.get("semesterNumber", 1)],
                        "modules": [m.__dict__ for m in parse_modules(s.get("course_examination", ""))]})
    rounds = []
    for sem, rs in (cd.get("roundsBySemester") or {}).items():
        for r in rs:
            rounds.append({"semester": sem, "start": r.get("round_start_date", ""),
                           "end": r.get("round_end_date", ""),
                           "application_code": r.get("round_application_code", "")})
    return {"code": code, "syllabi": syllabi, "rounds": rounds}


def syllabus_for(extracted: dict, term: str) -> Syllabus | None:
    """The syllabus version valid for `term` (latest valid_from <= term)."""
    tk = term_key(term)
    valid = [s for s in extracted["syllabi"] if tuple(s["valid_from"]) <= tk]
    if not valid:
        return None
    s = max(valid, key=lambda s: tuple(s["valid_from"]))
    return Syllabus(extracted["code"], _term_label(*s["valid_from"]),
                    [ExamModule(**m) for m in s["modules"]], extracted.get("rounds", []),
                    COURSE_PAGE.format(code=extracted["code"]))


class SyllabusSource:
    """Fetches and caches extracted course-page data (one small JSON per course)."""

    def __init__(self, cache_dir: str | Path | None = None, max_age_days: float = 7, pause: float = 0.3):
        if cache_dir is None:
            base = os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache"
            cache_dir = Path(base) / "schedcheck"
        self.dir = Path(cache_dir) / "kursinfo"
        self.max_age = max_age_days * 86400
        self.pause = pause
        self.errors: dict[str, str] = {}

    def _fetch(self, code: str) -> dict:
        url = COURSE_PAGE.format(code=code)
        last = None
        for _ in range(3):
            try:
                with urllib.request.urlopen(url, timeout=30) as r:
                    html = r.read().decode("utf-8", errors="replace")
                return extract(html, code)
            except (urllib.error.URLError, http.client.HTTPException, OSError, ValueError) as e:
                last = e
                time.sleep(self.pause)
        raise RuntimeError(f"{url}: {last}")

    def get(self, code: str, term: str) -> Syllabus | None:
        p = self.dir / f"{code}.json"
        data = None
        if p.exists() and time.time() - p.stat().st_mtime < self.max_age:
            data = json.loads(p.read_text(encoding="utf-8"))
        else:
            try:
                data = self._fetch(code)
                time.sleep(self.pause)  # be gentle with kth.se
                try:
                    self.dir.mkdir(parents=True, exist_ok=True)
                    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                except OSError:
                    pass
            except RuntimeError as e:
                if p.exists():  # stale cache beats nothing
                    data = json.loads(p.read_text(encoding="utf-8"))
                else:
                    self.errors[code] = str(e)
                    return None
        return syllabus_for(data, term)
