"""End-to-end checks on a synthetic programme ("XPROG") - nothing CTFYS-specific."""
import tempfile
import unittest
from pathlib import Path

from schedcheck.checks.structure import occasions
from schedcheck.config import Config, apply_accepted
from schedcheck.io.studyplan import PlanSource
from schedcheck.io.timeedit import read_folder
from schedcheck.reviews.course import course_review
from schedcheck.reviews.program import program_review
from schedcheck.term import load_term
from tests.helpers import HEADER_VT26, HEADER_VT27, calendar_markers, course, make_export, row

P3 = {"P1": 0, "P2": 0, "P3": 6, "P4": 0}
P4 = {"P1": 0, "P2": 0, "P3": 0, "P4": 6}


def plan_entries(cohort_year1: bool):
    """Year 1: AB1001 (P3, exam), AB1002 (P4, exam), AB1003 (P4, mandatory, missing in new).
    Year 2: electives CD2001/CD2002 (same master), CD2003, and mandatory CD2010."""
    entries = []
    if cohort_year1:
        entries += [course("AB1001", 1, p=P3, exams=["P3"]), course("AB1002", 1, p=P4, exams=["P4"]),
                    course("AB1003", 1, p=P4)]
    else:
        entries += [course("CD2010", 2, p=P4, exams=["P4"]),
                    course("CD2001", 2, "recommended", P4), course("CD2002", 2, "recommended", P4),
                    course("XY2003", 2, "recommended", P4),
                    {"type": "optionGroup", "name": "Electives", "year": 2,
                     "category": "electivePlaceholder", "kind": "minCredits",
                     "options": ["CD2001", "CD2002", "XY2003"], "periodCredits": P4, "exams": [],
                     "qualifiesFor": {"CD2001": [{"code": "TMASM", "name": "M", "required": True}],
                                      "CD2002": [{"code": "TMASM", "name": "M", "required": True}]}}]
    return entries


def build(tmp: Path):
    from tests.helpers import write_plan_source
    # Plans: VT27 year 1 = HT2026, year 2 = HT2025; VT26 year 1 = HT2025, year 2 = HT2024.
    cohorts = {}
    for c in ("HT2024", "HT2025", "HT2026"):
        cohorts[c] = plan_entries(True) + plan_entries(False)
    src = write_plan_source(tmp / "pv", "XPROG", cohorts)

    def year1(header, y, extra=()):
        return [
            row(header, f"{y}-01-19", "08:00", "10:00", "Föreläsning", "AB1001", "AB1001 Helklass", "XPROG1"),
            row(header, f"{y}-01-21", "10:00", "12:00", "Övning", "AB1001", "AB1001 grupp A", "XPROG1"),
            row(header, f"{y}-01-21", "13:00", "15:00", "Övning", "AB1001", "AB1001 grupp B", "XPROG1"),
            row(header, f"{y}-03-15", "08:00", "10:00", "Föreläsning", "AB1002", "AB1002 Helklass", "XPROG1"),
            *extra,
        ]

    new_dir, old_dir = tmp / "new", tmp / "old"
    new_dir.mkdir(), old_dir.mkdir()
    h = HEADER_VT27
    make_export(new_dir / "y1.xlsx", "XPROG1, Test programme", "2027-01-12 - 2027-08-29",
                calendar_markers(h, 2027) + year1(h, 2027, [
                    row(h, "2027-03-08", "08:00", "13:00", "Tentamen", "AB1001-1 (VT27)", "", "XPROG1",
                        "Tentamen. TEN1"),
                    row(h, "2027-05-24", "08:00", "13:00", "Tentamen", "AB1002-2 (VT27)", "", "XPROG1",
                        "Tentamen. TEN1"),
                    row(h, "2027-06-01", "08:00", "13:00", "Omtenta", "AB1001", "", "XPROG1", "Tentamen. TEN1"),
                    row(h, "2027-08-16", "08:00", "13:00", "Omtenta", "AB1002", "", "XPROG1", "Tentamen. TEN1"),
                    row(h, "2027-02-01", "08:00", "10:00", "Föreläsning", "AB1002-2 (HT25)", "", "XPROG1"),
                ]))
    make_export(new_dir / "y2.xlsx", "XPROG2, Test programme", "2027-01-12 - 2027-08-29",
                calendar_markers(h, 2027) + [
                    row(h, "2027-03-16", "08:00", "10:00", "Föreläsning", "CD2010", "", "XPROG2"),
                    row(h, "2027-03-16", "10:00", "12:00", "Föreläsning", "CD2001", "", "XPROG2"),
                    row(h, "2027-03-16", "13:00", "15:00", "Föreläsning", "CD2002", "", "XPROG2"),
                    row(h, "2027-03-17", "13:00", "15:00", "Föreläsning", "XY2003", "", "XPROG2"),
                    # CD2010 (mandatory) on Tue 05-25, the day after year-1 AB1002 (re-exam path).
                    row(h, "2027-05-25", "08:00", "13:00", "Tentamen", "CD2010", "", "XPROG2", "Tentamen. TEN1"),
                    # Same-master electives on the same day -> error.
                    row(h, "2027-05-26", "08:00", "13:00", "Tentamen", "CD2001", "", "XPROG2", "Tentamen. TEN1"),
                    row(h, "2027-05-26", "14:00", "18:00", "Tentamen", "CD2002", "", "XPROG2", "Tentamen. TEN1"),
                    # Unrelated elective Friday; Monday after is 3 days -> nothing.
                    row(h, "2027-05-28", "08:00", "13:00", "Tentamen", "XY2003, ZZ9999", "", "XPROG2",
                        "Tentamen. TEN1"),
                ])
    h = HEADER_VT26
    make_export(old_dir / "y1.xlsx", "XPROG1, Test programme", "2026-01-13 - 2026-08-30",
                calendar_markers(h, 2026, p3_exam=("03-09", "03-13"), p4_exam=("05-25", "05-29"),
                                 easter_reexam=("04-07", "04-10"), june=("06-02", "06-05"),
                                 aug=("08-17", "08-21"))
                + [
                    row(h, "2026-01-20", "08:00", "10:00", "Föreläsning", "AB1001", "AB1001 Helklass", "XPROG1"),
                    row(h, "2026-01-22", "10:00", "12:00", "Övning", "AB1001", "AB1001 grupp A, AB1001 grupp B", "XPROG1"),
                    row(h, "2026-01-23", "10:00", "12:00", "Övning", "AB1001", "AB1001 grupp A, AB1001 grupp B", "XPROG1"),
                    row(h, "2026-03-16", "08:00", "10:00", "Föreläsning", "AB1002", "AB1002 Helklass", "XPROG1"),
                    row(h, "2026-03-17", "08:00", "10:00", "Föreläsning", "AB1003", "AB1003 Helklass", "XPROG1"),
                    row(h, "2026-03-10", "08:00", "13:00", "Tentamen", "AB1001", "", "XPROG1", "Tentamen. TEN1"),
                    row(h, "2026-05-25", "08:00", "13:00", "Tentamen", "AB1002", "", "XPROG1", "Tentamen. TEN1"),
                    # Next term's teaching inside the export range: must be ignored.
                    row(h, "2026-08-25", "08:00", "10:00", "Föreläsning", "AB0001", "", "XPROG1"),
                ], header=HEADER_VT26)
    new, old = load_term(read_folder(new_dir)), load_term(read_folder(old_dir))
    return new, old, PlanSource(str(src))


class ProgramReview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.new, cls.old, cls.src = build(Path(cls.tmp.name))
        cls.res = program_review(cls.new, cls.old, Config(), cls.src)
        cls.by_check = {}
        for i in cls.res.issues:
            cls.by_check.setdefault(i.check, []).append(i)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def find(self, check, **kw):
        return [i for i in self.by_check.get(check, [])
                if all(getattr(i, k) == v for k, v in kw.items())]

    def test_missing_mandatory_course(self):
        hits = self.find("coverage.missing-course", course="AB1003")
        self.assertEqual([i.severity for i in hits], ["error"])

    def test_missing_exam_for_planned_exam_course(self):
        hits = self.find("coverage.missing-exam", course="CD2010")
        self.assertEqual(hits, [])  # CD2010 has its exam
        self.assertEqual(self.find("coverage.missing-reexam", course="CD2010")[0].severity, "warning")

    def test_eligibility_pair_same_day_is_error(self):
        hits = [i for i in self.find("exams.spacing", scope="XPROG2")
                if set(i.details["courses"]) == {"CD2001", "CD2002"}]
        self.assertEqual([i.severity for i in hits], ["error"])

    def test_friday_monday_not_flagged(self):
        for i in self.by_check.get("exams.spacing", []):
            self.assertNotIn("XY2003", i.details["courses"])

    def test_reexam_path_adjacent_day(self):
        hits = [i for i in self.find("exams.reexam-path") if set(i.details["courses"]) == {"AB1002", "CD2010"}]
        self.assertEqual([i.severity for i in hits], ["info"])  # adjacent=warning, one step softer

    def test_stale_round_code(self):
        hits = self.find("dataquality.round-term", course="AB1002")
        self.assertEqual([i.severity for i in hits], ["warning"])
        self.assertIn("HT25", hits[0].key)

    def test_out_of_term_rows_ignored(self):
        self.assertNotIn("AB0001", self.old.courses())

    def test_accept_list(self):
        issues = list(self.res.issues)
        apply_accepted(issues, [{"check": "coverage.missing-course", "course": "AB1003", "note": "discontinued"}])
        self.assertEqual(self.find("coverage.missing-course", course="AB1003")[0].accepted, "discontinued")


class Structure(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.new, cls.old, _ = build(Path(cls.tmp.name))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_parallel_groups_collapse(self):
        occ = occasions(self.new, "AB1001")
        ov = [o for o in occ if o.activity == "Övning"]
        self.assertEqual(len(ov), 1)
        self.assertEqual(ov[0].parallel, 2)
        # Old term: two meetings per group in the same week -> two occasions.
        self.assertEqual(len([o for o in occasions(self.old, "AB1001") if o.activity == "Övning"]), 2)

    def test_course_review_counts(self):
        res = course_review(["AB1001"], self.new, self.old, Config())
        counts = [i for i in res.issues if i.check == "structure.counts"]
        self.assertEqual(len(counts), 1)
        self.assertEqual(counts[0].details["counts"]["Övning"], [2, 1])


if __name__ == "__main__":
    unittest.main()
