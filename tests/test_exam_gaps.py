import datetime as dt
import unittest

from schedcheck.checks.exams import base_severity, soften
from schedcheck.config import DEFAULT_THRESHOLDS
from schedcheck.model import Event
from schedcheck.term import Exam


def exam(code, day, start="08:00", end="13:00"):
    d = dt.date.fromisoformat(day)
    ev = Event("t.xlsx", 1, dt.datetime.combine(d, dt.time.fromisoformat(start)),
               dt.datetime.combine(d, dt.time.fromisoformat(end)), "Tentamen")
    return Exam(code, ev, "ordinary", None)


class Gaps(unittest.TestCase):
    def sev(self, a, b):
        return base_severity(a, b, DEFAULT_THRESHOLDS)

    def test_overlap_and_same_day(self):
        self.assertEqual(self.sev(exam("A", "2027-05-24"), exam("B", "2027-05-24")), ("error", "overlapping"))
        self.assertEqual(self.sev(exam("A", "2027-05-24"), exam("B", "2027-05-24", "14:00", "18:00")),
                         ("error", "same day"))

    def test_adjacent_and_two_days(self):
        self.assertEqual(self.sev(exam("A", "2027-05-24"), exam("B", "2027-05-25"))[0], "warning")
        self.assertEqual(self.sev(exam("A", "2027-05-24"), exam("B", "2027-05-26"))[0], "info")

    def test_friday_to_monday_is_not_flagged(self):
        # Calendar days: the weekend counts as study time.
        self.assertIsNone(self.sev(exam("A", "2027-05-28"), exam("B", "2027-05-31"))[0])

    def test_soften(self):
        self.assertEqual(soften("error", 1), "warning")
        self.assertEqual(soften("warning", 2), None)


if __name__ == "__main__":
    unittest.main()
