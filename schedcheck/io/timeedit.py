"""Reader for TimeEdit schedule exports (.xlsx), stdlib only.

Layout observed in KTH exports (2026):

    row 1   (empty)
    row 2   "TimeEdit"
    row 3   title, e.g. "Remiss VT27 CTFYS1 261014" (may be blank)
    row 4   "CTFYS1, Civilingenjörsutbildning i teknisk fysik"
    row 5   "2027-01-12 - 2027-08-29 "
    row 6   column headers
    row 7+  one row per scheduled activity

Column names vary between exports (e.g. "Grupp" vs "Grupper"), so they are
mapped to canonical field names through HEADER_ALIASES. The header row is
located by content rather than position.
"""
from __future__ import annotations

import datetime as dt
import re
import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET

from ..model import CourseRef, Event, Export, ProgramGroup

_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

HEADER_ALIASES = {
    "week": ["Vecka", "Week"],
    "weekday": ["Veckodag", "Weekday", "Day"],
    "start_date": ["Startdatum", "Start date", "Begin date"],
    "start_time": ["Starttid", "Start time", "Begin time"],
    "end_date": ["Slutdatum", "End date"],
    "end_time": ["Sluttid", "End time"],
    "activity": ["Aktivitet", "Activity"],
    "groups": ["Grupper", "Grupp", "Groups", "Group"],
    "codes": ["Tillfälleskod/kurskod", "Kurskod", "Course code"],
    "room": ["Lokal", "Room", "Location"],
    "info": ["Info", "Information"],
    "staff": ["Person", "Personal", "Staff", "Teacher"],
    "programs": ["Program/grupp", "Program/klass", "Program", "Programme"],
    "exam_modules": ["Examinationsmodul, Examinationsmodul", "Examinationsmodul",
                     "Examination module"],
    "comment": ["Remisskommentar", "Comment"],
}
_ALIAS_TO_FIELD = {a.casefold(): f for f, aliases in HEADER_ALIASES.items() for a in aliases}

# KTH course codes: 2 letters + 3 digits + digit/letter (SF1674, SA114X),
# or doctoral courses with a leading F (FDD3431). Anything else in the code
# column (e.g. "8XCTFYS", a programme activity) is kept as an "other code".
_COURSE_RE = re.compile(r"^(F?[A-Z]{2}\d{3}[0-9A-Z])(?:-(\d+)\s*\((\w+)\))?$")
_PROGRAM_RE = re.compile(r"^([A-Z]{5})(\d)?(?:-(\d))?(?:-(.+))?$")
_RANGE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})\s*-\s*(\d{4}-\d{2}-\d{2})")


# --------------------------------------------------------------------------
# Low-level xlsx access

def _col_index(ref: str) -> int:
    letters = re.match(r"[A-Z]+", ref).group()
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def read_xlsx_rows(path: str | Path) -> list[tuple[int, list[str]]]:
    """Return [(row_number, [cell strings...]), ...] for the first sheet.

    Handles both inline strings (TimeEdit's choice) and shared strings.
    Numbers are returned as their raw text.
    """
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        shared: list[str] = []
        if "xl/sharedStrings.xml" in names:
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in root.iter(_NS + "si"):
                shared.append("".join(t.text or "" for t in si.iter(_NS + "t")))
        sheet = "xl/worksheets/sheet1.xml"
        if sheet not in names:
            sheet = sorted(n for n in names if n.startswith("xl/worksheets/sheet"))[0]
        root = ET.fromstring(z.read(sheet))

    rows = []
    for row in root.iter(_NS + "row"):
        cells: dict[int, str] = {}
        for c in row.findall(_NS + "c"):
            t = c.get("t")
            if t == "inlineStr":
                val = "".join(x.text or "" for x in c.iter(_NS + "t"))
            else:
                v = c.find(_NS + "v")
                val = "" if v is None else (v.text or "")
                if t == "s" and val:
                    val = shared[int(val)]
            cells[_col_index(c.get("r"))] = val
        width = max(cells) + 1 if cells else 0
        rows.append((int(row.get("r")), [cells.get(i, "") for i in range(width)]))
    return rows


# --------------------------------------------------------------------------
# Field parsing

def parse_course_codes(text: str) -> tuple[list[CourseRef], list[str]]:
    courses, other = [], []
    for tok in (t.strip() for t in text.split(",")):
        if not tok:
            continue
        m = _COURSE_RE.match(tok)
        if m:
            courses.append(CourseRef(m.group(1), m.group(2), m.group(3)))
        else:
            other.append(tok)
    # The same course can be listed several times on one row (seen in VT26
    # exports: "SE1055, SE1055, SE1055"); keep one of each.
    seen, unique = set(), []
    for c in courses:
        if c not in seen:
            seen.add(c)
            unique.append(c)
    return unique, other


def parse_program_group(tok: str) -> ProgramGroup | None:
    m = _PROGRAM_RE.match(tok.strip())
    if not m:
        return None
    prog, y1, y2, spec = m.groups()
    years: tuple[int, ...] = ()
    if y1 is not None:
        lo = int(y1)
        hi = int(y2) if y2 is not None else lo
        years = tuple(range(lo, hi + 1))
    return ProgramGroup(prog, years, spec)


def parse_program_groups(text: str) -> list[ProgramGroup]:
    out = []
    for tok in text.split(","):
        pg = parse_program_group(tok)
        if pg:
            out.append(pg)
    return out


def parse_exam_modules(text: str) -> list[str]:
    """'Problemtentamen. TEN2, Teoritentamen. TEN1' -> ['TEN1', 'TEN2']."""
    mods = re.findall(r"\b([A-ZÅÄÖ]{2,4}\d{0,2}(?:-\d+)?)\s*(?:,|$)", text)
    return sorted(set(mods))


def _split_list(text: str) -> list[str]:
    return [t.strip() for t in text.split(",") if t.strip()]


def _parse_date(text: str) -> dt.date:
    text = text.strip()
    if re.fullmatch(r"\d+(\.\d+)?", text):  # Excel serial date
        return dt.date(1899, 12, 30) + dt.timedelta(days=int(float(text)))
    return dt.date.fromisoformat(text)


def _parse_time(text: str) -> dt.time:
    text = text.strip()
    if re.fullmatch(r"0?\.\d+|0|1", text):  # Excel fraction of a day
        minutes = round(float(text) * 24 * 60)
        return dt.time(minutes // 60 % 24, minutes % 60)
    return dt.time.fromisoformat(text if len(text) > 4 else "0" + text)


# --------------------------------------------------------------------------
# File-level parsing

def _find_header(rows) -> int:
    for i, (_, cells) in enumerate(rows):
        fields = {_ALIAS_TO_FIELD.get(c.strip().casefold()) for c in cells}
        if {"start_date", "activity"} <= fields:
            return i
    raise ValueError("no header row with a start-date and activity column found")


def read_export(path: str | Path) -> Export:
    path = Path(path)
    rows = read_xlsx_rows(path)
    h = _find_header(rows)
    header = [_ALIAS_TO_FIELD.get(c.strip().casefold()) for c in rows[h][1]]

    # Metadata lines above the header: title, programme line, date range.
    meta = [cells[0].strip() for _, cells in rows[:h] if cells and cells[0].strip()]
    title, program, year, spec, r_start, r_end = "", None, None, None, None, None
    for line in meta:
        if line == "TimeEdit":
            continue
        m = _RANGE_RE.search(line)
        if m:
            r_start, r_end = (dt.date.fromisoformat(x) for x in m.groups())
            continue
        first = line.split(",")[0].strip()
        pg = parse_program_group(first)
        if pg and program is None and "," in line:
            program, spec = pg.program, pg.specialization
            year = pg.years[0] if len(pg.years) == 1 else None
            continue
        if not title:
            title = line

    events = []
    for rownum, cells in rows[h + 1:]:
        rec = {}
        for i, f in enumerate(header):
            if f and i < len(cells):
                rec[f] = cells[i].strip()
        if not rec.get("start_date") or not rec.get("activity", "") and not rec.get("codes"):
            continue
        try:
            sd = _parse_date(rec["start_date"])
            ed = _parse_date(rec.get("end_date") or rec["start_date"])
            st = _parse_time(rec.get("start_time") or "00:00")
            et = _parse_time(rec.get("end_time") or "23:59")
        except ValueError:
            continue
        courses, other = parse_course_codes(rec.get("codes", ""))
        events.append(Event(
            source=path.name, row=rownum,
            start=dt.datetime.combine(sd, st), end=dt.datetime.combine(ed, et),
            activity=rec.get("activity", ""),
            courses=courses, other_codes=other,
            groups=_split_list(rec.get("groups", "")),
            room=rec.get("room", ""), info=rec.get("info", ""),
            staff=rec.get("staff", ""),
            programs=parse_program_groups(rec.get("programs", "")),
            exam_modules=parse_exam_modules(rec.get("exam_modules", "")),
            comment=rec.get("comment", ""),
        ))
    events.sort(key=lambda e: (e.start, e.row))
    return Export(str(path), title, program, year, spec, r_start, r_end, events)


def read_folder(folder: str | Path) -> list[Export]:
    """Read every export in a folder, skipping Office lock files (~$*)."""
    out = []
    for p in sorted(Path(folder).glob("*.xlsx")):
        if p.name.startswith("~$"):
            continue
        out.append(read_export(p))
    return out
