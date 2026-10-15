"""Study plans from the ProgramVisualization data set.

ProgramVisualization (https://github.com/cohm/ProgramVisualization) extracts
KTH study plans per programme and cohort into JSON files:

    src/data/programs.json                 programme list, verified/disabled flags
    src/data/cohorts/index.json            {PROG: ["HT2026", "HT2025", ...]}
    src/data/cohorts/<PROG>-HT<yyyy>.json  [cohortMeta, course/optionGroup entries...]

A source can be a local clone (directory) or a base URL (default: GitHub raw,
branch configurable). Downloaded files are cached on disk.
"""
from __future__ import annotations

import http.client
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_SOURCE = "https://raw.githubusercontent.com/cohm/ProgramVisualization/main"
DATA_PREFIX = "src/data"


class PlanUnavailable(Exception):
    pass


@dataclass
class PlanCourse:
    code: str
    name: str
    year: int | None
    category: str                     # mandatory / conditionallyElective / recommended / ...
    credits: float
    period_credits: dict[str, float]
    exams: list[str]                  # periods with an exam, e.g. ["P3"]
    specializations: list[str] = field(default_factory=list)
    period_credits_by_spec: dict[str, dict[str, float]] = field(default_factory=dict)

    def credits_in(self, periods, spec: str | None = None) -> float:
        pc = self.period_credits_by_spec.get(spec, self.period_credits) if spec else self.period_credits
        return sum(pc.get(p, 0) or 0 for p in periods)


@dataclass
class OptionGroup:
    name: str
    year: int | None
    category: str                     # conditionallyElective / electivePlaceholder / ...
    kind: str                         # "pickN" / "minCredits" / ""
    options: list[str]
    period_credits: dict[str, float]
    exams: list[str]
    specializations: list[str] = field(default_factory=list)
    pick_n: int | None = None
    min_credits: float | None = None
    # course code -> [{"code": master programme, "name": ..., "required": bool}]
    qualifies_for: dict[str, list[dict]] = field(default_factory=dict)
    comment: str = ""


@dataclass
class ExpectedCourse:
    code: str
    name: str
    category: str                     # effective category for this programme year
    group: str | None                 # option-group name, if any
    exam_periods: list[str]
    periods: list[str]                # periods (of the term) with credits


@dataclass
class StudyPlan:
    program: str
    cohort: str                       # e.g. "HT2025"
    years_meta: list[dict]
    courses: dict[str, PlanCourse]
    groups: list[OptionGroup]
    source: str

    def year_confidence(self, year: int) -> dict[str, str]:
        """How reliable the plan is for a year, e.g. {"en": "exact"} or
        "approximated from HT2023 (high)", in both languages."""
        from ..i18n import T
        for y in self.years_meta:
            if y.get("year") == year:
                if y.get("approximated"):
                    src, conf = y.get("sourceCohort"), y.get("confidence", "unknown")
                    return T(f"uppskattad från {src} ({conf})", f"approximated from {src} ({conf})")
                c = y.get("confidence", "exact")
                return T("exakt" if c == "exact" else c, c)
        return T("okänd", "unknown")

    def _applies(self, specs: list[str], spec: str | None) -> bool:
        return not specs or spec is None or spec in specs

    def expected(self, year: int, periods: tuple[str, ...], spec: str | None = None) -> list[ExpectedCourse]:
        """Courses the given programme year should have in the given periods."""
        out: dict[str, ExpectedCourse] = {}
        for c in self.courses.values():
            if c.year != year or not self._applies(c.specializations, spec):
                continue
            ex = [p for p in c.exams if p in periods]
            if c.credits_in(periods, spec) > 0 or ex:
                out[c.code] = ExpectedCourse(
                    c.code, c.name, c.category, None, ex,
                    [p for p in periods if (c.period_credits.get(p) or 0) > 0])
        for g in self.groups:
            if g.year != year or not self._applies(g.specializations, spec):
                continue
            if sum(g.period_credits.get(p, 0) or 0 for p in periods) <= 0 and not set(g.exams) & set(periods):
                continue
            for code in g.options:
                c = self.courses.get(code)
                if c is None:
                    continue
                ex = [p for p in c.exams if p in periods]
                if c.credits_in(periods, spec) <= 0 and not ex:
                    continue
                cat = c.category if c.category != "mandatory" else g.category
                prev = out.get(code)
                if prev is None or prev.category not in ("mandatory",):
                    out[code] = ExpectedCourse(
                        code, c.name, cat, g.name, ex,
                        [p for p in periods if (c.period_credits.get(p) or 0) > 0])
        return sorted(out.values(), key=lambda e: e.code)

    def groups_for(self, year: int, spec: str | None = None) -> list[OptionGroup]:
        return [g for g in self.groups if g.year == year and self._applies(g.specializations, spec)]

    def eligibility_groups(self, year: int | None = None) -> dict[str, dict]:
        """Master programme -> {"name", "required": set(codes), "optional": set(codes)}."""
        out: dict[str, dict] = {}
        for g in self.groups:
            if year is not None and g.year != year:
                continue
            for code, masters in g.qualifies_for.items():
                for m in masters:
                    rec = out.setdefault(m["code"], {"name": m.get("name", ""),
                                                     "required": set(), "optional": set()})
                    rec["required" if m.get("required") else "optional"].add(code)
        return out


def parse_cohort(entries: list[dict], source: str = "") -> StudyPlan:
    meta = entries[0] if entries and entries[0].get("type") == "cohortMeta" else {}
    courses: dict[str, PlanCourse] = {}
    groups: list[OptionGroup] = []
    for e in entries[1:] if meta else entries:
        if e.get("type") == "optionGroup":
            groups.append(OptionGroup(
                name=e.get("name", ""), year=e.get("year"),
                category=e.get("category", ""), kind=e.get("kind", ""),
                options=list(e.get("options", [])),
                period_credits=e.get("periodCredits", {}) or {},
                exams=list(e.get("exams", []) or []),
                specializations=list(e.get("specializations", []) or []),
                pick_n=e.get("pickN"), min_credits=e.get("minCredits"),
                qualifies_for=e.get("qualifiesFor", {}) or {},
                comment=e.get("comment", ""),
            ))
        elif e.get("code"):
            courses[e["code"]] = PlanCourse(
                code=e["code"], name=e.get("name", ""), year=e.get("year"),
                category=e.get("category", ""), credits=e.get("totalCredits", 0) or 0,
                period_credits=e.get("periodCredits", {}) or {},
                exams=list(e.get("exams", []) or []),
                specializations=list(e.get("specializations", []) or []),
                period_credits_by_spec=e.get("periodCreditsBySpecialization", {}) or {},
            )
    return StudyPlan(meta.get("program", ""), meta.get("cohort", ""),
                     meta.get("years", []), courses, groups, source)


def cohort_for(term: str, year: int) -> str:
    """Cohort (intake term) of programme year `year` in `term`.

    VT27 belongs to academic year 2026/27, so year 1 started HT2026,
    year 2 HT2025, ...; HT26 is academic year 2026/27 as well.
    """
    yy = int(term[2:])
    start_year = 2000 + (yy - 1 if term.startswith("VT") else yy)
    return f"HT{start_year - (year - 1)}"


class PlanSource:
    def __init__(self, source: str | None = None, cache_dir: str | Path | None = None):
        self.source = source or DEFAULT_SOURCE
        self.is_url = self.source.startswith(("http://", "https://"))
        if cache_dir is None:
            base = os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache"
            cache_dir = Path(base) / "schedcheck"
        self.cache_dir = Path(cache_dir)

    def _local_path(self, rel: str) -> Path:
        root = Path(self.source)
        for cand in (root / DATA_PREFIX / rel, root / rel):
            if cand.exists():
                return cand
        raise PlanUnavailable(f"{rel} not found under {root}")

    def _cache_path(self, rel: str) -> Path:
        safe = self.source.split("://", 1)[-1].replace("/", "_")
        return self.cache_dir / safe / rel

    def load_json(self, rel: str, refresh: bool = False):
        if not self.is_url:
            return json.loads(self._local_path(rel).read_text(encoding="utf-8"))
        cp = self._cache_path(rel)
        if cp.exists() and not refresh:
            return json.loads(cp.read_text(encoding="utf-8"))
        url = f"{self.source.rstrip('/')}/{DATA_PREFIX}/{rel}"
        data, err = None, None
        for _attempt in range(3):
            try:
                with urllib.request.urlopen(url, timeout=30) as r:
                    data = r.read()
                break
            except urllib.error.HTTPError as e:
                raise PlanUnavailable(f"{url}: HTTP {e.code}") from e
            except (urllib.error.URLError, http.client.HTTPException, OSError) as e:
                err = e  # transient network trouble: retry
        if data is None:
            if cp.exists():
                return json.loads(cp.read_text(encoding="utf-8"))
            raise PlanUnavailable(f"{url}: {err}")
        try:
            cp.parent.mkdir(parents=True, exist_ok=True)
            cp.write_bytes(data)
        except OSError:
            pass  # caching is best-effort
        return json.loads(data)

    def program_info(self, program: str) -> dict | None:
        try:
            for p in self.load_json("programs.json"):
                if p.get("code") == program:
                    return p
        except PlanUnavailable:
            pass
        return None

    def cohorts(self, program: str) -> list[str]:
        return self.load_json("cohorts/index.json").get(program, [])

    def plan(self, program: str, cohort: str) -> StudyPlan:
        if cohort not in self.cohorts(program):
            raise PlanUnavailable(f"no study plan for {program} cohort {cohort} in {self.source}")
        rel = f"cohorts/{program}-{cohort}.json"
        return parse_cohort(self.load_json(rel), f"{self.source} {rel}")
