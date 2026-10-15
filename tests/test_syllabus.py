"""Syllabus parsing and the syllabus-based exam checks (no network: stub source)."""
import json
import tempfile
import unittest
import urllib.parse
from pathlib import Path

from schedcheck.config import Config
from schedcheck.io.kursinfo import ExamModule, Syllabus, extract, parse_modules, syllabus_for
from schedcheck.io.studyplan import PlanSource
from schedcheck.io.timeedit import read_folder
from schedcheck.reviews.program import program_review
from schedcheck.term import load_term
from tests.helpers import HEADER_VT27 as H, calendar_markers, course, make_export, row, write_plan_source


def page(syllabi, rounds):
    data = {"courseData": {"syllabusList": syllabi, "roundsBySemester": rounds,
                           "courseInfo": {"course_examiners": "<p>Some Examiner</p>"}}}
    return f'<script>window.__compressedData__DATA = "{urllib.parse.quote(json.dumps(data))}";</script>'


class Parsing(unittest.TestCase):
    def test_modules_and_term_selection(self):
        html = page([{"course_valid_from": {"year": 2026, "semesterNumber": 2},
                      "course_examination": "<ul><li>LAB1 - Laborationer, 1,5 hp, betygsskala: P, F</li>"
                                            "<li>TEN2 - Skriftlig tentamen, 3,0 hp, betygsskala: P, F</li></ul>"},
                     {"course_valid_from": {"year": 2024, "semesterNumber": 1},
                      "course_examination": "<ul><li>TEN1 - Tentamen, 3,0 hp, betygsskala: A, B</li></ul>"}],
                    {"20271": [{"round_start_date": "2027-01-12", "round_end_date": "2027-05-31",
                                "round_application_code": "11549"}]})
        x = extract(html, "XX1000")
        self.assertNotIn("Examiner", json.dumps(x))           # staff names are never kept
        self.assertEqual([m.code for m in syllabus_for(x, "VT27").written], ["TEN2"])
        self.assertEqual([m.code for m in syllabus_for(x, "VT26").written], ["TEN1"])
        self.assertIsNone(syllabus_for(x, "VT23"))

    def test_written_exam_rules(self):
        mods = parse_modules("<li>TENA - Valfri tentamen, 0 hp, x</li><li>TEN1 - Muntlig tentamen, 3 hp</li>"
                             "<li>TEN2 - Skriftlig tentamen, 3,0 hp</li><li>MAS1 - Mästarprov, 1,5 hp</li>")
        self.assertEqual([m.code for m in mods if m.written_exam], ["TEN2"])


class StubSource:
    def __init__(self, syllabi):
        self.syllabi, self.errors = syllabi, {}

    def get(self, code, term):
        return self.syllabi.get(code)


P4 = {"P1": 0, "P2": 0, "P3": 0, "P4": 6}


class Checks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        t = Path(cls.tmp.name)
        src = write_plan_source(t / "pv", "XPROG", {"HT2024": [
            course("AA2000", 3, "recommended", P4), course("BB2000", 3, "recommended", P4),
            course("CC2000", 3, "recommended", P4)]})
        d = t / "new"
        d.mkdir()
        make_export(d / "y3.xlsx", "XPROG3, Test", "2027-01-12 - 2027-08-29", calendar_markers(H, 2027) + [
            # AA2000: taught, no exam at all, syllabus has a written exam -> missing exam (syllabus only)
            row(H, "2027-03-16", "08:00", "10:00", "Föreläsning", "AA2000-1 (VT27), ZZ232V-2 (VT27)", "", "XPROG3"),
            # BB2000: exam registered under a module the current syllabus lacks
            row(H, "2027-03-17", "08:00", "10:00", "Föreläsning", "BB2000", "", "XPROG3"),
            row(H, "2027-05-24", "08:00", "13:00", "Tentamen", "BB2000-3 (VT27)", "", "XPROG3", "Tentamen. TEN1"),
            # CC2000: shared exam row with a doctoral variant; module belongs to CC2000
            row(H, "2027-03-18", "08:00", "10:00", "Föreläsning", "CC2000", "", "XPROG3"),
            row(H, "2027-05-26", "08:00", "13:00", "Tentamen", "CC2000-4 (VT27), FCC3000-5 (VT27)", "", "XPROG3",
                "Tentamen. TEN1"),
        ])
        rounds = [{"semester": "20271", "start": "2027-01-12", "end": "2027-05-31", "application_code": "1"}]
        ten = lambda c: ExamModule(c, "Skriftlig tentamen", 3.0)
        stub = StubSource({
            "AA2000": Syllabus("AA2000", "HT2026", [ten("TEN2")], rounds),
            "ZZ232V": Syllabus("ZZ232V", "VT2027", [ten("TEN2")], rounds),
            "BB2000": Syllabus("BB2000", "HT2026", [ten("TEN2")], rounds),
            "CC2000": Syllabus("CC2000", "HT2026", [ten("TEN1")], rounds),
            "FCC3000": Syllabus("FCC3000", "VT2019", [ExamModule("EXA1", "Examination", 6.0)], rounds),
        })
        res = program_review(load_term(read_folder(d)), None, Config(), PlanSource(str(src)), None, stub)
        cls.issues = res.issues

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def find(self, check, course):
        return [i for i in self.issues if i.check == check and i.course == course]

    def test_syllabus_only_missing_exam_is_a_warning(self):
        hits = self.find("coverage.missing-exam", "AA2000")
        self.assertEqual([i.severity for i in hits], ["warning"])
        self.assertIn("TEN2", hits[0].message)

    def test_alternative_code_not_reported_separately(self):
        self.assertEqual(self.find("coverage.missing-exam", "ZZ232V"), [])

    def test_unknown_module(self):
        self.assertEqual([i.severity for i in self.find("syllabus.unknown-module", "BB2000")], ["warning"])

    def test_shared_row_modules_from_any_course(self):
        self.assertEqual(self.find("syllabus.unknown-module", "FCC3000"), [])
        self.assertEqual(self.find("syllabus.unknown-module", "CC2000"), [])


if __name__ == "__main__":
    unittest.main()
