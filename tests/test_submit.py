"""done/harvest/grade do not open the browser; `submit` sends every unsubmitted row."""
import contextlib, io, os, sys, unittest
from unittest import mock
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from urllib.parse import parse_qs, urlparse  # noqa: E402
from fakes import fresh_ws, run, ready_for_s3, install_fake_grader  # noqa: E402


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

    def test_refuses_when_locked_and_ungraded(self):
        self.assertFalse(os.path.exists(self.w.grader_path()))
        out, wb = cap(self.w, "submit", tty_in="\n")
        self.assertIn("Unlock the grader first:  python workshop.py unlock 4 <password from the slide>  (then run submit again)", out)
        self.assertNotIn("Submit anyway", out)
        self.assertFalse(wb.called)
        self.assertFalse(any(r.get("submitted_rev") for r in self.rows().values()))

    def test_auto_grades_then_one_link(self):
        install_fake_grader(self.w)
        out, wb = cap(self.w, "submit", tty_in="\n")
        self.assertIn("Grading first:", out)
        self.assertTrue(all(r["grading"] == "graded" for r in self.rows().values() if r["stage"] in ("1", "3")))
        self.assertEqual(wb.call_count, 1)
        self.assertIn("The form opens in ONE browser window. Check it and click Submit, then press Enter here.", out)
        self.assertIn("2 results to submit.", out)
        self.assertNotIn("window 1 of", out)
        link = wb.call_args[0][0]
        cfg = self.w.load_config()
        q = parse_qs(urlparse(link).query)
        self.assertEqual(set(q) - {"id"}, {cfg["fields"]["alias"], cfg["all_results_field"]})
        self.assertEqual(q[cfg["fields"]["alias"]], ["t"])
        lines = q[cfg["all_results_field"]][0].split("\n")
        self.assertEqual(lines[0], "vesper-results v1")
        self.assertEqual(len(lines), 3)
        for ln in lines[1:]:
            keys = [p.split("=")[0] for p in ln.split(";")]
            self.assertNotIn("alias", keys)                       # alias has its own field
            self.assertEqual(keys, [k for k in self.w.ROW_FIELDS if k in keys])   # order kept
            self.assertTrue({"run_id", "stage", "revision"} <= set(keys))
        self.assertLess(len(link), self.w.MAX_LINK)
        self.assertTrue(all(r["submitted_rev"] == r["revision"] for r in self.rows().values()))
        out, wb = cap(self.w, "submit", tty_in="")
        self.assertIn("Nothing to submit", out)

    def test_skip_marks_nothing_and_new_revision_resubmits(self):
        install_fake_grader(self.w)
        out, wb = cap(self.w, "submit", tty_in="s\n")
        self.assertEqual(wb.call_count, 1)
        self.assertFalse(any(r.get("submitted_rev") for r in self.rows().values()))
        cap(self.w, "submit", tty_in="\n")
        cap(self.w, "done", self.rid)            # new revision of stage 1
        out, wb = cap(self.w, "submit", tty_in="\n")
        self.assertIn("1 results to submit.", out)

    def test_long_data_splits_into_windows(self):
        install_fake_grader(self.w)
        reg = self.w.Registry.load()
        for r in reg.data["rows"].values():
            r["task"] = "x" * 4000
        reg.save()
        out, wb = cap(self.w, "submit", tty_in="\n\n")
        self.assertIn("in 2 windows", out)
        self.assertIn("window 1 of 2", out)
        self.assertIn("window 2 of 2", out)
        self.assertEqual(wb.call_count, 2)
        cfg = self.w.load_config()
        for c in wb.call_args_list:
            q = parse_qs(urlparse(c[0][0]).query)
            self.assertEqual(set(q) - {"id"}, {cfg["fields"]["alias"], cfg["all_results_field"]})
            self.assertEqual(len(q[cfg["all_results_field"]][0].split("\n")), 2)
        self.assertIn("All 2 results submitted", out)
        self.assertTrue(all(r["submitted_rev"] == r["revision"] for r in self.rows().values()))

    def test_escaping(self):
        t = self.w.all_results_text([{"run_id": "a;b=c\nd%"}])
        self.assertEqual(t.split("\n")[1].split(";")[0], "run_id=a%3Bb%3Dc%0Ad%25")

    def test_short_lines(self):
        """Empty fields and the alias are left out; solution_sha is cut to 12 characters; the reader still works."""
        import charts
        t = self.w.all_results_text([{"alias": "t", "run_id": "s1-ab12", "stage": "1", "task": "T3",
                                      "skill_hash": "", "solution_sha": "f" * 64, "score": "100.0"}])
        self.assertEqual(t.split("\n")[1], "run_id=s1-ab12;stage=1;task=T3;score=100.0;solution_sha=" + "f" * 12)
        d = charts.expand_all_results(t)[0]
        self.assertEqual((d["run_id"], d["score"], d.get("skill_hash", "")), ("s1-ab12", "100.0", ""))

    def test_no_form_prints_only(self):
        install_fake_grader(self.w)
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

    def test_form_command_sends_one_row_in_all_results(self):
        out, wb = cap(self.w, "form", self.rid, "1", tty_in="\n")
        cfg = self.w.load_config()
        q = parse_qs(urlparse(wb.call_args[0][0]).query)
        self.assertEqual(set(q) - {"id"}, {cfg["fields"]["alias"], cfg["all_results_field"]})
        lines = q[cfg["all_results_field"]][0].split("\n")
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0], "vesper-results v1")
        self.assertIn("run_id=" + self.rid, lines[1])
        self.assertIn("vesper-results v1", out)
        self.assertNotIn(" 1. alias", out)


if __name__ == "__main__":
    unittest.main()
