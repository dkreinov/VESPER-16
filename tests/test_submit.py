"""done/harvest/grade do not open the browser; `submit` sends every unsubmitted row."""
import contextlib, io, os, sys, unittest
from unittest import mock
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fakes import fresh_ws, run, ready_for_s3  # noqa: E402


class TTYOut(io.StringIO):
    def isatty(self):
        return True


class TTYIn(io.StringIO):
    def isatty(self):
        return True


def cap(w, *argv, tty_in=None):
    out = TTYOut() if tty_in is not None else io.StringIO()
    old = sys.stdin
    if tty_in is not None:
        sys.stdin = TTYIn(tty_in)
    try:
        with contextlib.redirect_stdout(out), mock.patch.object(w.webbrowser, "open", return_value=True) as wb:
            run(w, *argv)
    finally:
        sys.stdin = old
    return out.getvalue(), wb


class Submit(unittest.TestCase):
    def setUp(self):
        self.w, _ = fresh_ws()
        self.rid, self.harvest_out = ready_for_s3(self.w)

    def rows(self):
        return self.w.Registry.load().data["rows"]

    def test_done_and_harvest_no_browser_no_answers(self):
        self.assertIn("python workshop.py submit", self.harvest_out)
        self.assertNotIn("RESULTS FORM", self.harvest_out)
        out, wb = cap(self.w, "done")           # updates the finished stage 1
        self.assertFalse(wb.called)
        self.assertIn("Saved. You submit all results at the end:  python workshop.py submit", out)
        self.assertNotIn(" 1. alias", out)

    def test_submit_marks_skips_and_resubmits(self):
        n = len(self.rows())
        self.assertEqual(n, 2)
        out, wb = cap(self.w, "submit", tty_in="\n\n")
        self.assertEqual(wb.call_count, n)
        self.assertIn("Result 1 of 2", out)
        self.assertIn("All 2 results submitted", out)
        self.assertTrue(all(r["submitted_rev"] == r["revision"] for r in self.rows().values()))
        out, wb = cap(self.w, "submit", tty_in="")
        self.assertIn("Nothing to submit", out)
        self.assertFalse(wb.called)
        cap(self.w, "done", self.rid)            # new revision of stage 1
        out, wb = cap(self.w, "submit", tty_in="s\n")
        self.assertIn("Result 1 of 1", out)
        self.assertIn("1 skipped", out)
        self.assertEqual(self.rows()[self.rid + "|1"]["submitted_rev"], 1)
        out, wb = cap(self.w, "submit", tty_in="\n")
        self.assertIn("All 1 results submitted", out)
        self.assertEqual(self.rows()[self.rid + "|1"]["submitted_rev"], 2)

    def test_no_form_prints_only(self):
        out, wb = cap(self.w, "submit", "--no-form", tty_in="\n\n")
        self.assertFalse(wb.called)
        self.assertIn("RESULTS FORM", out)
        self.assertFalse(any(r.get("submitted_rev") for r in self.rows().values()))
        out, wb = cap(self.w, "submit")          # stdout is not a TTY
        self.assertFalse(wb.called)
        self.assertFalse(any(r.get("submitted_rev") for r in self.rows().values()))

    def test_form_command_marks_on_enter(self):
        out, wb = cap(self.w, "form", self.rid, "1", tty_in="\n")
        self.assertTrue(wb.called)
        self.assertEqual(self.rows()[self.rid + "|1"]["submitted_rev"], 1)


if __name__ == "__main__":
    unittest.main()
