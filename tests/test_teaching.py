"""Teaching-overlap check on a small synthetic programme year."""
import tempfile
import unittest
from pathlib import Path

from schedcheck.config import Config
from schedcheck.io.studyplan import PlanSource
from schedcheck.io.timeedit import read_folder
from schedcheck.reviews.program import program_review
from schedcheck.term import load_term
from tests.helpers import HEADER_VT27 as H, calendar_markers, course, make_export, row, write_plan_source

P3 = {"P1": 0, "P2": 0, "P3": 6, "P4": 0}


class TeachingOverlap(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        tmp = Path(cls.tmp.name)
        src = write_plan_source(tmp / "pv", "XPROG", {"HT2026": [
            course("AA1001", 1, p=P3), course("AA1002", 1, p=P3), course("AA1003", 1, p=P3),
            course("EE1001", 1, "recommended", P3), course("FF1001", 1, "recommended", P3)]})
        d = tmp / "new"
        d.mkdir()
        rows = calendar_markers(H, 2027) + [
            # whole-class vs whole-class, both mandatory -> error
            row(H, "2027-01-18", "08:00", "10:00", "Föreläsning", "AA1001", "AA1001 Helklass", "XPROG1"),
            row(H, "2027-01-18", "09:00", "11:00", "Övning", "AA1002", "AA1002 Helklass", "XPROG1"),
            # whole-class vs one group -> warning
            row(H, "2027-01-19", "13:00", "15:00", "Föreläsning", "AA1002", "AA1002 Helklass", "XPROG1"),
            row(H, "2027-01-19", "13:00", "15:00", "Laboration", "AA1003", "AA1003 grupp A", "XPROG1"),
            # touching, not overlapping (10-12 after 08-10) -> nothing
            row(H, "2027-01-20", "08:00", "10:00", "Föreläsning", "AA1001", "AA1001 Helklass", "XPROG1"),
            row(H, "2027-01-20", "10:00", "12:00", "Föreläsning", "AA1003", "AA1003 Helklass", "XPROG1"),
            # one session under two codes (co-listed) -> nothing
            row(H, "2027-01-21", "08:00", "10:00", "Föreläsning", "AA1003, ZZ9001", "", "XPROG1"),
            # unrelated electives overlapping -> not reported
            row(H, "2027-01-22", "08:00", "10:00", "Föreläsning", "EE1001", "", "XPROG1"),
            row(H, "2027-01-22", "08:00", "10:00", "Föreläsning", "FF1001", "", "XPROG1"),
            # own programme activity vs mandatory lecture -> error
            row(H, "2027-01-25", "12:00", "13:00", "Information", "8XXPROG", "", "XPROG1"),
            row(H, "2027-01-25", "12:00", "14:00", "Föreläsning", "AA1001", "AA1001 Helklass", "XPROG1"),
            # re-exam during a lecture: other students, not a clash
            row(H, "2027-01-26", "08:00", "13:00", "Omtenta", "AA1002", "", "XPROG1"),
            row(H, "2027-01-26", "08:00", "10:00", "Föreläsning", "AA1001", "AA1001 Helklass", "XPROG1"),
        ]
        make_export(d / "y1.xlsx", "XPROG1, Test", "2027-01-12 - 2027-08-29", rows)
        res = program_review(load_term(read_folder(d)), None, Config(), PlanSource(str(src)))
        cls.by_pair = {tuple(i.details["courses"]): i for i in res.issues if i.check == "teaching.overlap"}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_severities(self):
        self.assertEqual(self.by_pair[("AA1001", "AA1002")].severity, "error")
        self.assertEqual(self.by_pair[("AA1002", "AA1003")].severity, "warning")
        self.assertEqual(self.by_pair[("8XXPROG", "AA1001")].severity, "error")

    def test_not_clashes(self):
        self.assertNotIn(("AA1001", "AA1003"), self.by_pair)     # touching only
        self.assertNotIn(("AA1003", "ZZ9001"), self.by_pair)     # co-listed
        self.assertNotIn(("EE1001", "FF1001"), self.by_pair)     # unrelated electives
        self.assertEqual(self.by_pair[("AA1001", "AA1002")].details["count"], 1)  # re-exam ignored


if __name__ == "__main__":
    unittest.main()


class SelfOverlap(unittest.TestCase):
    def evs(self, rows):
        from schedcheck.io.timeedit import read_export
        with tempfile.TemporaryDirectory() as d:
            p = make_export(Path(d) / "x.xlsx", "XPROG1, Test", "2027-01-12 - 2027-08-29", rows)
            return read_export(p).events

    def test_whole_class_lab_and_seminar_clash(self):
        from schedcheck.checks.teaching import self_overlaps
        evs = self.evs([
            row(H, "2027-04-20", "09:00", "12:00", "Laboration", "AA1001", "AA1001 Helklass", "XPROG1"),
            row(H, "2027-04-20", "10:00", "12:00", "Seminarium", "AA1001", "AA1001 Helklass", "XPROG1")])
        self.assertEqual(len(self_overlaps(evs, "AA1001")), 1)

    def test_parallel_subgroups_and_split_rooms_are_fine(self):
        from schedcheck.checks.teaching import self_overlaps
        evs = self.evs([
            row(H, "2027-04-20", "09:00", "12:00", "Laboration", "AA1001", "AA1001 grupp A", "XPROG1"),
            row(H, "2027-04-20", "09:00", "12:00", "Seminarium", "AA1001", "AA1001 grupp B", "XPROG1"),
            row(H, "2027-04-21", "08:00", "10:00", "Övning", "AA1001", "AA1001 Helklass", "XPROG1", Lokal="Q1"),
            row(H, "2027-04-21", "08:00", "10:00", "Övning", "AA1001", "AA1001 Helklass", "XPROG1", Lokal="Q2")])
        self.assertEqual(self_overlaps(evs, "AA1001"), [])

    def test_same_group_double_booked(self):
        from schedcheck.checks.teaching import self_overlaps
        evs = self.evs([
            row(H, "2027-04-20", "09:00", "12:00", "Laboration", "AA1001", "AA1001 grupp A", "XPROG1"),
            row(H, "2027-04-20", "11:00", "12:00", "Seminarium", "AA1001", "AA1001 grupp A", "XPROG1")])
        self.assertEqual(len(self_overlaps(evs, "AA1001")), 1)


class Alternatives(unittest.TestCase):
    def test_pick_one_options_are_not_paired(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        t = Path(tmp.name)
        group = {"type": "optionGroup", "name": "Degree project", "year": 3, "category": "conditionallyElective",
                 "kind": "pickN", "pickN": 1, "options": ["XX130X", "XX135X"],
                 "periodCredits": {"P3": 7.5, "P4": 7.5}, "exams": []}
        src = write_plan_source(t / "pv", "XPROG", {"HT2024": [
            course("XX130X", 3, "conditionallyElective", P3), course("XX135X", 3, "conditionallyElective", P3),
            group]})
        d = t / "new"
        d.mkdir()
        make_export(d / "y3.xlsx", "XPROG3, Test", "2027-01-12 - 2027-08-29", calendar_markers(H, 2027) + [
            row(H, "2027-01-18", "08:00", "10:00", "Seminarium", "XX130X", "", "XPROG3"),
            row(H, "2027-01-18", "08:00", "10:00", "Föreläsning", "XX135X", "", "XPROG3")])
        res = program_review(load_term(read_folder(d)), None, Config(), PlanSource(str(src)))
        self.assertEqual([i for i in res.issues if i.check == "teaching.overlap"], [])


class AlternativesAlsoElective(unittest.TestCase):
    def test_pick_one_options_that_are_also_electives_are_paired(self):
        from schedcheck.checks.exams import alternatives
        from schedcheck.checks import YearPlan
        from schedcheck.io.studyplan import parse_cohort
        pick = {"type": "optionGroup", "name": "Pick one", "year": 3, "category": "conditionallyElective",
                "kind": "pickN", "pickN": 1, "options": ["SF1677", "SF1678"], "periodCredits": {}, "exams": []}
        elect = {"type": "optionGroup", "name": "Electives", "year": 3, "category": "electivePlaceholder",
                 "kind": "minCredits", "options": ["SF1677", "SF1678", "XX1000"], "periodCredits": {}, "exams": []}
        only_pick = parse_cohort([pick])
        both = parse_cohort([pick, elect])
        self.assertTrue(alternatives(YearPlan("X", 3, None, "HT2024", only_pick), "SF1677", "SF1678"))
        self.assertFalse(alternatives(YearPlan("X", 3, None, "HT2024", both), "SF1677", "SF1678"))
