"""Synthetic TimeEdit-like exports for tests (no real schedule data in the repo)."""
from __future__ import annotations

import datetime as dt
import json
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

HEADER_VT27 = ["Vecka", "Veckodag", "Startdatum", "Starttid", "Slutdatum", "Sluttid", "Aktivitet",
               "Grupper", "Tillfälleskod/kurskod", "Lokal", "Info", "Person", "Program/grupp",
               "Examinationsmodul, Examinationsmodul", "Remisskommentar"]
HEADER_VT26 = ["Vecka", "Veckodag", "Startdatum", "Starttid", "Slutdatum", "Sluttid", "Aktivitet",
               "Grupp", "Tillfälleskod/kurskod", "Lokal", "Info", "Personal", "Program/klass",
               "Examinationsmodul, Examinationsmodul", "Kund", "Förening", "Avdelning"]
DAYS = ["Måndag", "Tisdag", "Onsdag", "Torsdag", "Fredag", "Lördag", "Söndag"]


def _col(i: int) -> str:
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def write_xlsx(path: Path, rows: list[list[str]]) -> None:
    """Minimal xlsx with inline strings, like TimeEdit's exports."""
    xml_rows = []
    for r, cells in enumerate(rows, start=2):  # TimeEdit leaves row 1 empty
        cs = "".join(f'<c r="{_col(i)}{r}" t="inlineStr"><is><t>{escape(v)}</t></is></c>'
                     for i, v in enumerate(cells) if v != "")
        xml_rows.append(f'<row r="{r}">{cs}</row>')
    sheet = ('<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.openxmlformats.org/'
             'spreadsheetml/2006/main"><sheetData>' + "".join(xml_rows) + "</sheetData></worksheet>")
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("xl/worksheets/sheet1.xml", sheet)


def row(header, date, start, end, activity, code="", groups="", programs="", modules="", **kw):
    d = dt.date.fromisoformat(date)
    vals = {"Vecka": f"v {d.isocalendar()[1]}", "Veckodag": DAYS[d.weekday()],
            "Startdatum": date, "Starttid": start, "Slutdatum": date, "Sluttid": end,
            "Aktivitet": activity, "Grupper": groups, "Grupp": groups,
            "Tillfälleskod/kurskod": code, "Program/grupp": programs, "Program/klass": programs,
            "Examinationsmodul, Examinationsmodul": modules}
    vals.update(kw)
    return [vals.get(h, "") for h in header]


def make_export(path: Path, program_line: str, date_range: str, events: list[list[str]],
                header=HEADER_VT27, title="Remiss test") -> Path:
    rows = [["TimeEdit"], [title], [program_line], [date_range], header] + events
    write_xlsx(path, rows)
    return path


def calendar_markers(header, year: int, p3_exam=("03-08", "03-12"), p4_exam=("05-24", "05-28"),
                     easter_reexam=("03-30", "04-02"), june=("06-01", "06-04"), aug=("08-16", "08-20")):
    out = []
    for kind, (a, b) in [("Examinationsdag", p3_exam), ("Examinationsdag", p4_exam),
                         ("Omexamination", easter_reexam), ("Omexamination", june), ("Omexamination", aug)]:
        d = dt.date.fromisoformat(f"{year}-{a}")
        e = dt.date.fromisoformat(f"{year}-{b}")
        while d <= e:
            if d.weekday() < 5:
                out.append(row(header, str(d), "13:00", "14:00", kind))
            d += dt.timedelta(days=1)
    return out


def write_plan_source(root: Path, program: str, cohorts: dict[str, list[dict]],
                      verified: bool = True) -> Path:
    """A local ProgramVisualization-like data tree."""
    data = root / "src" / "data"
    (data / "cohorts").mkdir(parents=True, exist_ok=True)
    (data / "programs.json").write_text(json.dumps([{"code": program, "verified": verified}]))
    (data / "cohorts" / "index.json").write_text(json.dumps({program: sorted(cohorts, reverse=True)}))
    for cohort, entries in cohorts.items():
        meta = {"type": "cohortMeta", "program": program, "cohort": cohort,
                "years": [{"year": y, "sourceCohort": cohort, "approximated": False, "confidence": "exact"}
                          for y in (1, 2, 3)]}
        (data / "cohorts" / f"{program}-{cohort}.json").write_text(json.dumps([meta] + entries))
    return root


def course(code, year, category="mandatory", p=None, exams=None, name=None):
    p = p or {"P1": 0, "P2": 0, "P3": 0, "P4": 0}
    return {"code": code, "name": name or code, "year": year, "category": category,
            "totalCredits": sum(p.values()), "periodCredits": p, "exams": exams or []}
