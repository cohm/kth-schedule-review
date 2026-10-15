"""Room capacity: parsing room fields, Places lookup (from a seeded cache,
no network), and the comparison with the reference term."""
import json
import tempfile
import time
import unittest
from pathlib import Path

from schedcheck.checks.rooms import grade
from schedcheck.config import Config
from schedcheck.io.places import RoomSource, split_rooms
from schedcheck.io.timeedit import read_folder
from schedcheck.reviews.course import course_review
from schedcheck.term import load_term
from tests.helpers import HEADER_VT26, HEADER_VT27, calendar_markers, make_export, row


def seeded_source(tmp: Path, manual=None) -> RoomSource:
    """A RoomSource whose cache already holds a few rooms (fresh, so no fetch)."""
    d = tmp / "cache" / "places"
    d.mkdir(parents=True)
    rooms = [
        {"uid": "u-fr4", "name": "FR4 (Oskar Kleins auditorium)", "type": "Hörsal"},
        {"uid": "u-fd5", "name": "FD5", "type": "Hörsal"},
        {"uid": "u-b2", "name": "B2", "type": "Hörsal"},
        {"uid": "u-b2e", "name": "B2", "type": "Entré"},
        {"uid": "u-q33", "name": "Q33", "type": "Övningssal"},
        {"uid": "u-q34", "name": "Q34", "type": "Övningssal"},
        {"uid": "u-lab", "name": "012:024", "type": "Labb"},
        {"uid": "u-bo", "name": "U1, U61 Break-out", "type": "Breakout"},
        {"uid": "u-bru", "name": "4V6 Bru (Brun)", "type": "Datorsal"},
    ]
    now = time.time()
    seats = {"u-fr4": 267, "u-fd5": 114, "u-b2": 131, "u-b2e": None, "u-q33": 60, "u-q34": 60,
             "u-lab": None, "u-bo": 20, "u-bru": 40}
    (d / "rooms.json").write_text(json.dumps(rooms), encoding="utf-8")
    (d / "seats.json").write_text(json.dumps(
        {u: {"seats": s, "name": u, "type": "", "building": "", "fetched": now} for u, s in seats.items()}),
        encoding="utf-8")
    src = RoomSource(tmp / "cache", manual=manual)
    src._get = lambda url: (_ for _ in ()).throw(AssertionError(f"network access: {url}"))
    return src


class SplitRooms(unittest.TestCase):
    def test_lists_ranges_and_popular_names(self):
        self.assertEqual(split_rooms("Q34, Q36"), ["Q34", "Q36"])
        self.assertEqual(split_rooms("FB52-53"), ["FB52", "FB53"])
        self.assertEqual(split_rooms("V1-3"), ["V1", "V2", "V3"])
        self.assertEqual(split_rooms("012:024-025, 013:012"), ["012:024", "012:025", "013:012"])
        self.assertEqual(split_rooms("FR4 (Oskar Kleins auditorium)"), ["FR4"])
        self.assertEqual(split_rooms("4303.0"), ["4303"])
        # hyphens that are not ranges
        self.assertEqual(split_rooms("Ka-203, Ka-Sal A (Östen Mäkitalo)"), ["Ka-203", "Ka-Sal A"])
        self.assertEqual(split_rooms(""), [])


class Lookup(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.src = seeded_source(Path(self.tmp.name), manual={"U31BREAK-OUT": 25})

    def tearDown(self):
        self.tmp.cleanup()

    def test_popular_name_and_case(self):
        self.assertEqual(self.src.lookup("FR4").seats, 267)
        self.assertEqual(self.src.lookup("4V6 Bru").seats, 40)

    def test_teaching_room_preferred(self):
        info = self.src.lookup("B2")
        self.assertEqual((info.status, info.seats), ("ok", 131))

    def test_part_of_a_combined_name(self):
        self.assertEqual(self.src.lookup("U61 Break-out").seats, 20)

    def test_statuses(self):
        self.assertEqual(self.src.lookup("012:024").status, "no-seats")
        self.assertEqual(self.src.lookup("XYZ99").status, "unknown")
        self.assertEqual(self.src.lookup("Digital").status, "digital")
        self.assertEqual((self.src.lookup("U31 Break-out").status, self.src.lookup("U31 Break-out").seats),
                         ("manual", 25))


class Grade(unittest.TestCase):
    def test_thresholds(self):
        self.assertIsNone(grade(100, 95))
        self.assertEqual(grade(100, 90), "lower")
        self.assertEqual(grade(100, 80), "much-lower")
        self.assertEqual(grade(100, 60), "far-lower")
        self.assertEqual(grade(100, 150), "higher")
        self.assertIsNone(grade(100, 149))


class Compare(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        tmp = Path(cls.tmp.name)
        for name in ("old", "new"):
            (tmp / name).mkdir()

        def course_rows(h, y, rooms):
            # F, Ö, F, Ö in P3 weeks 1-2, plus an exam (never compared)
            return [row(h, f"{y}-01-{d}", "08:00", "10:00", a, "XX1000", "XX1000 Helklass", "XPROG1", Lokal=r)
                    for d, a, r in zip(("19", "21", "26", "28"), ("Föreläsning", "Övning", "Föreläsning", "Övning"), rooms)] + [
                row(h, f"{y}-03-10", "08:00", "13:00", "Tentamen", "XX1000", "", "XPROG1", "TEN1", Lokal="Q33")]

        make_export(tmp / "old" / "y1.xlsx", "XPROG1, Test", "2026-01-13 - 2026-08-23",
                    calendar_markers(HEADER_VT26, 2026) + course_rows(HEADER_VT26, 2026,
                                                                       ["FR4 (Oskar Kleins auditorium)", "Q33", "FD5", "Q34"]),
                    header=HEADER_VT26)
        make_export(tmp / "new" / "y1.xlsx", "XPROG1, Test", "2027-01-12 - 2027-08-29",
                    calendar_markers(HEADER_VT27, 2027) + course_rows(HEADER_VT27, 2027,
                                                                       ["FD5", "Q33, Q34", "Digital", ""]))
        cls.src = seeded_source(tmp)
        cls.res = course_review(["XX1000"], load_term(read_folder(tmp / "new")),
                                load_term(read_folder(tmp / "old")), Config(), None, cls.src)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_pairs(self):
        pairs = self.res.ctx.room_comparison["XX1000"]["pairs"]
        self.assertEqual([p["abbrev"] for p in pairs], ["F", "Ö", "F", "Ö"])   # exam not compared
        self.assertEqual([(p["old"]["seats"], p["new"]["seats"]) for p in pairs[:2]], [(267, 114), (60, 120)])
        self.assertEqual([p["level"] for p in pairs], ["far-lower", "higher", None, None])
        self.assertEqual([p["mode"] for p in pairs], [None, None, "now digital", "no room booked"])

    def test_issue(self):
        [i] = [i for i in self.res.issues if i.check == "rooms.capacity"]
        self.assertEqual(i.severity, "warning")
        self.assertEqual(i.details["counts"]["far-lower"], 1)
        self.assertIn("FR4 267 → FD5 114", i.message["en"])
        self.assertIn("minst 40 % färre platser", i.message["sv"])
        self.assertEqual(i.details["no_room"], 1)


if __name__ == "__main__":
    unittest.main()
