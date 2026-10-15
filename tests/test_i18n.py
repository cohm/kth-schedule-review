"""Both languages everywhere: findings, status panel, report, comment drafts, CLI."""
import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from schedcheck.config import Config
from schedcheck.i18n import T, join
from schedcheck.io.studyplan import PlanSource
from schedcheck.io.timeedit import read_folder
from schedcheck.model import Issue
from schedcheck.report import comments, html, jsonout
from schedcheck.report.status import all_year_status
from schedcheck.reviews.program import program_review
from schedcheck.term import load_term
from tests.helpers import HEADER_VT26, HEADER_VT27, calendar_markers, course, make_export, row, write_plan_source

P3 = {"P1": 0, "P2": 0, "P3": 6, "P4": 0}


class IssueText(unittest.TestCase):
    def test_both_languages_required(self):
        Issue("info", "x.y", "S", None, T("hej", "hello"))
        with self.assertRaises(ValueError):
            Issue("info", "x.y", "S", None, "hello")
        with self.assertRaises(ValueError):
            Issue("info", "x.y", "S", None, {"en": "hello"})
        with self.assertRaises(ValueError):
            Issue("info", "x.y", "S", None, T("hej", "hello"), ask={"sv": "?"})

    def test_join(self):
        self.assertEqual(join(["a", "b", "c"], "sv"), "a, b och c")
        self.assertEqual(join(["a", "b"], "en"), "a and b")


class Review(unittest.TestCase):
    """A small programme with a missing exam, an exam clash and a changed structure."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        tmp = Path(cls.tmp.name)
        src = write_plan_source(tmp / "pv", "XPROG", {
            "HT2026": [course("AA1001", 1, p=P3, exams=["P3"]), course("AA1002", 1, p=P3, exams=["P3"])],
            "HT2025": [course("AA1001", 1, p=P3, exams=["P3"]), course("AA1002", 1, p=P3, exams=["P3"])]})
        for d in ("new", "old"):
            (tmp / d).mkdir()
        new = calendar_markers(HEADER_VT27, 2027) + [
            row(HEADER_VT27, "2027-01-18", "08:00", "10:00", "Föreläsning", "AA1001", "AA1001 Helklass", "XPROG1"),
            row(HEADER_VT27, "2027-01-18", "09:00", "11:00", "Övning", "AA1002", "AA1002 Helklass", "XPROG1"),
            row(HEADER_VT27, "2027-03-09", "08:00", "13:00", "Tentamen", "AA1002", "", "XPROG1", "TEN1")]
        old = calendar_markers(HEADER_VT26, 2026) + [
            row(HEADER_VT26, "2026-01-19", "08:00", "10:00", "Föreläsning", "AA1001", "AA1001 Helklass", "XPROG1"),
            row(HEADER_VT26, "2026-01-20", "08:00", "10:00", "Övning", "AA1001", "AA1001 Helklass", "XPROG1"),
            row(HEADER_VT26, "2026-01-19", "13:00", "15:00", "Övning", "AA1002", "AA1002 Helklass", "XPROG1"),
            row(HEADER_VT26, "2026-03-10", "08:00", "13:00", "Tentamen", "AA1001", "", "XPROG1", "TEN1"),
            row(HEADER_VT26, "2026-03-12", "08:00", "13:00", "Tentamen", "AA1002", "", "XPROG1", "TEN1")]
        make_export(tmp / "new" / "y1.xlsx", "XPROG1, Test", "2027-01-12 - 2027-08-29", new)
        make_export(tmp / "old" / "y1.xlsx", "XPROG1, Test", "2026-01-13 - 2026-08-23", old, header=HEADER_VT26)
        cls.res = program_review(load_term(read_folder(tmp / "new")), load_term(read_folder(tmp / "old")),
                                 Config(), PlanSource(str(src)))
        cls.dir = tmp

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_findings_in_both_languages(self):
        checks = {i.check for i in self.res.issues}
        self.assertTrue({"coverage.missing-exam", "teaching.overlap", "structure.counts"} <= checks, checks)
        for i in self.res.issues:
            self.assertNotEqual(i.message["sv"], i.message["en"], i.check)
        miss = next(i for i in self.res.issues if i.check == "coverage.missing-exam")
        self.assertIn("har ingen ordinarie tentamen", miss.message["sv"])
        self.assertEqual(miss.ask, T("Ska den läggas in?", "Should it be added?"))

    def test_status_and_notes(self):
        for lines in all_year_status(self.res).values():
            for line in lines:
                self.assertEqual(set(line["check"]) | set(line["text"]), {"sv", "en"})
        for n in self.res.notes:
            self.assertEqual(set(n), {"sv", "en"})

    def test_report_has_both_and_toggle(self):
        page = html.render(self.res, "sv")
        self.assertIn("data-lang='sv'", page)
        self.assertIn("id='lang'", page)
        self.assertIn("<span class='l-sv' lang='sv'>Fynd</span><span class='l-en' lang='en'>Issues</span>", page)
        self.assertIn("har ingen ordinarie tentamen", page)
        self.assertIn("has no ordinary exam", page)
        self.assertIn("data-lang='en'", html.render(self.res, "en"))

    def test_comment_drafts_follow_language(self):
        sv, en = comments.render(self.res, "sv"), comments.render(self.res, "en")
        self.assertIn("Remisskommentarer", sv)
        self.assertIn("Ska den läggas in?", sv)
        self.assertNotIn("Should it be added?", sv)
        self.assertIn("Should it be added?", en)

    def test_json_and_cli_summary(self):
        d = jsonout.to_dict(self.res)
        self.assertEqual(d["schema"], 2)
        self.assertEqual(set(d["issues"][0]["message"]), {"sv", "en"})
        self.assertIn("sammanfattning: fel", jsonout.text_summary(self.res, lang="sv"))
        self.assertIn("summary: error", jsonout.text_summary(self.res, lang="en"))

    def test_cli_language(self):
        from schedcheck.__main__ import main
        out = self.dir / "out"
        for lang, needle, draft in (("sv", "sammanfattning", "kommentarer"), ("en", "summary", "comments")):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                main(["--lang", lang, "program", "--new", str(self.dir / "new"), "--old", str(self.dir / "old"),
                      "--out", str(out / lang), "--no-plan", "--no-syllabus", "--no-rooms"])
            self.assertIn(needle, buf.getvalue())
            self.assertTrue(list((out / lang).glob(f"*_{draft}.md")))


if __name__ == "__main__":
    unittest.main()
