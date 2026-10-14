import datetime as dt
import unittest

from schedcheck.checks.structure import CourseDiff, Occasion, classify_changes, describe_changes
from schedcheck.model import Event

NAMES = {"F": "Föreläsning", "Ö": "Övning", "KS": "Kontrollskrivning"}


def occ(spec):
    """'w1: F Ö F | w2: F Ö' -> occasions in time order."""
    out, day = [], 0
    for part in spec.split("|"):
        wk, acts = part.split(":")
        for a in acts.split():
            day += 1
            t = dt.datetime(2027, 1, 1) + dt.timedelta(hours=day)
            e = Event("t.xlsx", day, t, t + dt.timedelta(hours=1), NAMES[a])
            out.append(Occasion("XX1000", NAMES[a], ("P4", int(wk.strip()[1:])), [e]))
    return out


def diff(old, new):
    return CourseDiff("XX1000", occ(old), occ(new), [], {})


class Changes(unittest.TestCase):
    def test_pair_moved_between_weeks_is_a_move_not_a_reorder(self):
        c = classify_changes(diff("w1: F Ö F Ö | w2: F Ö F Ö", "w1: F Ö F Ö F Ö | w2: F Ö"))
        self.assertEqual(c.reordered, [])
        self.assertEqual([(f[1], t[1], acts) for f, t, acts in c.moved], [(2, 1, ["F", "Ö"])])
        self.assertEqual((c.added, c.removed), ([], []))

    def test_within_week_reorder(self):
        c = classify_changes(diff("w4: Ö F KS", "w4: F Ö KS"))
        self.assertEqual(c.moved, [])
        self.assertEqual(c.reordered, [(("P4", 4), ["Ö", "F", "KS"], ["F", "Ö", "KS"])])
        self.assertEqual(describe_changes(c), ["reordered within P4 w4: Ö F KS → F Ö KS"])

    def test_added_and_removed(self):
        c = classify_changes(diff("w1: F | w3: Ö", "w1: F F"))
        self.assertEqual(c.removed, [(("P4", 3), ["Ö"])])
        self.assertEqual(c.added, [(("P4", 1), ["F"])])


if __name__ == "__main__":
    unittest.main()


class Sequence(unittest.TestCase):
    def test_moving_between_weeks_is_not_a_difference(self):
        from schedcheck.checks.structure import sequence_hunks
        self.assertEqual(sequence_hunks(diff("w1: F Ö F Ö | w2: F Ö F Ö", "w1: F Ö F Ö F Ö | w2: F Ö")), [])

    def test_swap_is_one_bracketed_stretch(self):
        from schedcheck.checks.structure import describe_hunks, sequence_hunks
        h = sequence_hunks(diff("w3: F Ö F | w4: Ö F KS", "w3: F Ö F | w4: F Ö KS"))
        self.assertEqual(describe_hunks(h), ["P4 w4: … Ö F [Ö F] KS → … Ö F [F Ö] KS"])
