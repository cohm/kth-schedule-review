import os
import tempfile
import time
import unittest
from pathlib import Path

from schedcheck.io import fetch
from tests.helpers import make_export

CFG = """
base  = "https://example.invalid/web/staff01/ri.xlsx"
views = { remiss = 9, final = 10 }
objects = { XPROG1 = "111.16", XPROG2 = "222.16" }
[terms]
VT26 = ["2026-01-13", "2026-08-23"]
VT27 = ["2027-01-12", "2027-08-29"]
"""


class Fetch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        (self.d / "te.toml").write_text(CFG)
        self.cfg = fetch.load_config(self.d / "te.toml")

    def tearDown(self):
        self.tmp.cleanup()

    def test_url(self):
        u = fetch.export_url(self.cfg, "XPROG1", "VT27", "remiss")
        self.assertTrue(u.startswith("https://example.invalid/web/staff01/ri.xlsx?h=t&sid=9&"
                                     "p=20270112.x%2C20270829.x&objects=111.16&ox=0"), u)

    def test_unknown_term_view_object(self):
        for args in (("XPROG1", "HT30", "remiss"), ("XPROG1", "VT27", "draft"), ("NOPE1", "VT27", "remiss")):
            with self.assertRaises(ValueError):
                fetch.export_url(self.cfg, *args)

    def test_collect_files_by_header(self):
        new, old, dl = self.d / "new", self.d / "old", self.d / "dl"
        dl.mkdir()
        reqs = fetch.plan_requests(self.cfg, ["XPROG1", "XPROG2"],
                                   [("VT27", "remiss", new), ("VT26", "final", old)])
        man = fetch.write_manifest(reqs, self.d / "m.json")
        time.sleep(0.01)
        make_export(dl / "a.xlsx", "XPROG1, Test", "2027-01-12 - 2027-08-29 ", [])
        make_export(dl / "b.xlsx", "XPROG2, Test", "2027-01-12 - 2027-08-29 ", [])
        make_export(dl / "c.xlsx", "XPROG1, Test", "2026-01-13 - 2026-08-23 ", [])
        make_export(dl / "d.xlsx", "XPROG1, Test", "2027-01-01 - 2027-12-31 ", [])  # not requested
        make_export(dl / "e.xlsx", "XPROG1, Test", "2027-01-12 - 2027-08-29 ", [])  # duplicate
        os.utime(dl / "e.xlsx", (time.time() - 5, time.time() - 5))                   # ... older
        (dl / "~$a.xlsx").write_bytes(b"lock")
        res = fetch.collect(dl, man)
        filed = {d.name for _, d in res.filed}
        self.assertEqual(filed, {"XPROG1_VT27_remiss.xlsx", "XPROG2_VT27_remiss.xlsx",
                                 "XPROG1_VT26_final.xlsx"})
        self.assertTrue((new / "XPROG1_VT27_remiss.xlsx").exists())
        self.assertTrue((old / "XPROG1_VT26_final.xlsx").exists())
        self.assertEqual([(r["label"], r["term"]) for r in res.missing], [("XPROG2", "VT26")])
        self.assertEqual(sorted(p.name for p, _ in res.ignored), ["d.xlsx", "e.xlsx"])

    def test_same_term_twice_rejected(self):
        with self.assertRaises(ValueError):
            fetch.plan_requests(self.cfg, ["XPROG1"], [("VT27", "remiss", "a"), ("VT27", "final", "b")])


if __name__ == "__main__":
    unittest.main()


class Selection(unittest.TestCase):
    def test_programme_codes_and_placeholders(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "te.toml").write_text(CFG.replace('XPROG2 = "222.16"', 'XPROG2 = "222.16", YPROG1 = "333.16"'))
            cfg = fetch.load_config(Path(d) / "te.toml")
        self.assertEqual(fetch.select_labels(cfg, ["XPROG"]), ["XPROG1", "XPROG2"])
        self.assertEqual(fetch.select_labels(cfg, ["YPROG1", "XPROG2"]), ["YPROG1", "XPROG2"])
        with self.assertRaises(ValueError):
            fetch.select_labels(cfg, ["ZPROG"])
        reqs = fetch.plan_requests(cfg, ["XPROG1", "YPROG1"], [("VT27", "remiss", "out/{program}/{term}_{view}")])
        self.assertEqual([r["dest"] for r in reqs], ["out/XPROG/VT27_remiss", "out/YPROG/VT27_remiss"])


class ScheduleLinks(unittest.TestCase):
    # Links copied from TimeEdit (2026-10): CTFYS1, published VT26 and remiss VT27.
    OBSERVED = {
        "h=t&sid=10&p=20260113.x,20260823.x&objects=386379.16&ox=0&types=0&fe=0":
            "15760Yg65011Q0g1QY7461Z362X757Q63Y570yZ05Q7",
        "h=t&sid=9&p=20270112.x,20270829.x&objects=386379.16&ox=0&types=0&fe=0":
            "15Q235X46Z07Q6Z76g3Y20y6046Y12701gQY6Q5547",
    }

    def test_scramble_matches_timeedit(self):
        for query, scrambled in self.OBSERVED.items():
            self.assertEqual(fetch.te_scramble(query), scrambled)
            self.assertEqual(fetch.te_unscramble(scrambled), query)

    def test_schedule_url_and_view_from_name(self):
        import datetime as dt
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "te.toml"
            p.write_text(CFG.replace('XPROG1 = "111.16"', 'CTFYS1 = "386379.16"'))
            cfg = fetch.load_config(p)
        self.assertEqual(fetch.schedule_url(cfg, "CTFYS1", dt.date(2027, 1, 12), dt.date(2027, 8, 29), "remiss"),
                         "https://example.invalid/web/staff01/ri15Q235X46Z07Q6Z76g3Y20y6046Y12701gQY6Q5547.html")
        self.assertIsNone(fetch.schedule_url(cfg, "NOPE1", dt.date(2027, 1, 12), dt.date(2027, 8, 29), "remiss"))
        self.assertEqual(fetch.view_from_filename("x/CTFYS1_VT27_remiss.xlsx", cfg), "remiss")
        self.assertIsNone(fetch.view_from_filename("TimeEdit_export.xlsx", cfg))
