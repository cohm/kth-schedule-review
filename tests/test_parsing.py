import datetime as dt
import tempfile
import unittest
from pathlib import Path

from schedcheck.calendar import build_calendar
from schedcheck.io.studyplan import cohort_for, parse_cohort
from schedcheck.io.timeedit import (parse_course_codes, parse_exam_modules, parse_program_groups,
                                    read_export, read_folder)
from tests.helpers import HEADER_VT26, HEADER_VT27, calendar_markers, course, make_export, row


class FieldParsing(unittest.TestCase):
    def test_course_codes(self):
        cs, other = parse_course_codes("SF1674-12368 (VT27), FDD3431-13040 (VT27), 8XCTFYS")
        self.assertEqual([c.code for c in cs], ["SF1674", "FDD3431"])
        self.assertEqual((cs[0].round_id, cs[0].round_term), ("12368", "VT27"))
        self.assertEqual(other, ["8XCTFYS"])

    def test_plain_and_duplicate_codes(self):
        cs, _ = parse_course_codes("SE1055, SE1055, SA114X")
        self.assertEqual([c.code for c in cs], ["SE1055", "SA114X"])

    def test_program_groups(self):
        pgs = parse_program_groups("CTMAT2-3, CLGYM3-MAFY, TTFYM1-TFYA-B, CTFYS1")
        self.assertEqual(pgs[0].years, (2, 3))
        self.assertEqual((pgs[1].program, pgs[1].years, pgs[1].specialization), ("CLGYM", (3,), "MAFY"))
        self.assertEqual(pgs[2].specialization, "TFYA-B")

    def test_exam_modules(self):
        self.assertEqual(parse_exam_modules("Problemtentamen. TEN2, Teoritentamen. TEN1"), ["TEN1", "TEN2"])
        self.assertEqual(parse_exam_modules("Skriftlig tentamen, vågrörelselära. TENV"), ["TENV"])
        self.assertEqual(parse_exam_modules("Tentamen. TEN1-2"), ["TEN1-2"])

    def test_cohort_for(self):
        self.assertEqual(cohort_for("VT27", 1), "HT2026")
        self.assertEqual(cohort_for("VT27", 3), "HT2024")
        self.assertEqual(cohort_for("HT26", 2), "HT2025")


class ExportReading(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_header_aliases_both_formats(self):
        for header in (HEADER_VT26, HEADER_VT27):
            p = make_export(self.dir / "x.xlsx", "CTFYS2, Teknisk fysik", "2027-01-12 - 2027-08-29 ",
                            [row(header, "2027-01-12", "08:00", "10:00", "Föreläsning", "SE1055",
                                 "SE1055 Helklass", "CTFYS2, CTMAT3")], header=header)
            ex = read_export(p)
            self.assertEqual((ex.program, ex.year), ("CTFYS", 2))
            self.assertEqual(ex.range_end, dt.date(2027, 8, 29))
            e = ex.events[0]
            self.assertEqual(e.codes, ["SE1055"])
            self.assertEqual(e.groups, ["SE1055 Helklass"])
            self.assertEqual(e.programs[1].program, "CTMAT")

    def test_lock_files_ignored(self):
        make_export(self.dir / "a.xlsx", "CTFYS1, x", "2027-01-12 - 2027-08-29", [])
        (self.dir / "~$a.xlsx").write_bytes(b"not a zip")
        self.assertEqual(len(read_folder(self.dir)), 1)


class Calendar(unittest.TestCase):
    def test_windows_periods_and_easter_week(self):
        with tempfile.TemporaryDirectory() as d:
            p = make_export(Path(d) / "a.xlsx", "CTFYS1, x", "2027-01-12 - 2027-08-29",
                            calendar_markers(HEADER_VT27, 2027))
            cal = build_calendar([read_export(p)])
        self.assertEqual(cal.term, "VT27")
        self.assertEqual([p for p, _, _ in cal.periods], ["P3", "P4"])
        self.assertEqual(cal.periods[1][1], dt.date(2027, 3, 15))  # Monday after P3 exams
        self.assertEqual(len(cal.reexam_windows), 3)
        # Easter re-exam week (w13) is skipped: 2027-04-06 is P4 teaching week 3.
        self.assertEqual(cal.teaching_week(dt.date(2027, 3, 16)), ("P4", 1))
        self.assertEqual(cal.teaching_week(dt.date(2027, 4, 6)), ("P4", 3))
        self.assertEqual(cal.end, dt.date(2027, 8, 20))


class StudyPlanParsing(unittest.TestCase):
    def test_expected_and_eligibility(self):
        entries = [
            {"type": "cohortMeta", "program": "XPROG", "cohort": "HT2024", "years": []},
            course("AA1001", 3, "recommended", {"P1": 0, "P2": 0, "P3": 7.5, "P4": 0}),
            course("AA1002", 3, "recommended", {"P1": 0, "P2": 0, "P3": 0, "P4": 7.5}),
            course("AA1003", 3, "mandatory", {"P1": 7.5, "P2": 0, "P3": 0, "P4": 0}, ["P1"]),
            {"type": "optionGroup", "name": "Electives", "year": 3, "category": "electivePlaceholder",
             "kind": "minCredits", "options": ["AA1001", "AA1002"],
             "periodCredits": {"P3": 7.5, "P4": 7.5}, "exams": [],
             "qualifiesFor": {"AA1001": [{"code": "TXXXM", "name": "X", "required": True}],
                              "AA1002": [{"code": "TXXXM", "name": "X", "required": True}]}},
        ]
        plan = parse_cohort(entries)
        self.assertEqual([e.code for e in plan.expected(3, ("P3", "P4"))], ["AA1001", "AA1002"])
        self.assertEqual(plan.eligibility_groups(3)["TXXXM"]["required"], {"AA1001", "AA1002"})


if __name__ == "__main__":
    unittest.main()


class Links(unittest.TestCase):
    def test_linkify_codes_not_terms(self):
        from schedcheck.report.html import linkify
        out = linkify("DD2352 and FDD3431 in the HT2025 plan, VT2027, TEN1, FB42")
        self.assertIn("kurs/DD2352", out)
        self.assertIn("kurs/FDD3431", out)
        for not_code in ("HT2025", "VT2027", "TEN1", "FB42"):
            self.assertNotIn(f"kurs/{not_code}", out)


class ExportTime(unittest.TestCase):
    def test_metadata_then_file_name(self):
        import datetime as dt
        import tempfile
        import zipfile
        from pathlib import Path
        from schedcheck.io.timeedit import export_time_text, exported_at, read_export
        from tests.helpers import HEADER_VT27, make_export
        with tempfile.TemporaryDirectory() as tmp:
            p = make_export(Path(tmp) / "TimeEdit_2026-10-14_20_03.xlsx", "XPROG1, Test",
                            "2027-01-12 - 2027-08-29", [], HEADER_VT27)
            t, how = exported_at(p)       # no metadata: TimeEdit's default file name (local time)
            self.assertEqual((how, t.strftime("%Y-%m-%d %H:%M")), ("file name", "2026-10-14 20:03"))
            with zipfile.ZipFile(p, "a") as z:
                z.writestr("docProps/core.xml", '<cp:coreProperties xmlns:dcterms="x" xmlns:xsi="y">'
                           '<dcterms:created xsi:type="dcterms:W3CDTF">2026-10-14T21:54:18Z</dcterms:created>'
                           '</cp:coreProperties>')
            t, how = exported_at(p)
            self.assertEqual((how, t), ("metadata", dt.datetime(2026, 10, 14, 21, 54, 18, tzinfo=dt.timezone.utc)))
            self.assertEqual(export_time_text([read_export(p)]), "2026-10-14 23:54")   # Stockholm, CEST
