"""done/harvest/grade do not open the browser; `submit` sends every unsubmitted row."""
import contextlib, io, os, sys, unittest
from unittest import mock
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from urllib.parse import parse_qs, urlparse  # noqa: E402
from fakes import fresh_ws, run, ready_for_s3, install_fake_grader, flat  # noqa: E402


class TTYOut(io.StringIO):
    def isatty(self):
        return True


class TTYIn(io.StringIO):
    def isatty(self):
        return True


def cap(w, *argv, tty_in=None, clip_ok=True, clips=None):
    """Run a command with a fake browser and a fake clipboard (texts copied go to `clips`)."""
    out = TTYOut() if tty_in is not None else io.StringIO()
    old = sys.stdin
    clips = clips if clips is not None else []
    if tty_in is not None:
        sys.stdin = TTYIn(tty_in)
    try:
        with contextlib.redirect_stdout(out), mock.patch.object(w.webbrowser, "open", return_value=True) as wb, \
                mock.patch.object(w, "copy_to_clipboard", side_effect=lambda t: clips.append(t) or clip_ok):
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
        self.assertNotIn("RESULTS FORM", self.harvest_out)
        out, wb = cap(self.w, "done")           # updates the finished stage 1
        self.assertFalse(wb.called)
        self.assertIn("Saved. You submit all results at the end:  python workshop.py submit", out)
        self.assertNotIn(" 1. alias", out)

    def test_refuses_when_locked_and_ungraded(self):
        self.assertFalse(os.path.exists(self.w.grader_path()))
        out, wb = cap(self.w, "submit", tty_in="\n")
        self.assertIn("Unlock the grader first:  python workshop.py unlock 4 <password from the slide>  (then run submit again)", flat(out))
        self.assertNotIn("Submit anyway", out)
        self.assertFalse(wb.called)
        self.assertFalse(any(r.get("submitted_rev") for r in self.rows().values()))

    def test_auto_grades_then_one_link(self):
        install_fake_grader(self.w)
        clips = []
        out, wb = cap(self.w, "submit", tty_in="\n", clips=clips)
        self.assertIn("Grading first:", out)
        self.assertTrue(all(r["grading"] == "graded" for r in self.rows().values() if r["stage"] in ("1", "3")))
        self.assertEqual(wb.call_count, 1)
        self.assertIn("2 results to submit, in ONE form response.", out)
        self.assertIn("The form opens in your browser, with your alias filled in.", out)
        self.assertIn("Click the all_results field and press Ctrl+V", out)
        link = wb.call_args[0][0]
        cfg = self.w.load_config()
        q = parse_qs(urlparse(link).query)
        self.assertEqual(set(q) - {"id"}, {cfg["fields"]["alias"]})      # no results in the link
        self.assertEqual(q[cfg["fields"]["alias"]], ["t"])
        self.assertLess(len(link), 300)
        self.assertEqual(len(clips), 1)
        self.assertIn(clips[0], out)                                     # also printed, for a manual copy
        lines = clips[0].split("\n")
        self.assertEqual(lines[0], "vesper-results v1")
        self.assertEqual(len(lines), 3)
        for ln in lines[1:]:
            keys = [p.split("=")[0] for p in ln.split(";")]
            self.assertNotIn("alias", keys)                       # alias has its own field
            self.assertEqual(keys, [k for k in self.w.ROW_FIELDS if k in keys])   # order kept
            self.assertTrue({"run_id", "stage", "revision"} <= set(keys))
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
        self.assertIn("1 results to submit, in ONE form response.", out)

    def test_long_data_still_one_window(self):
        """Long results never make the link long (AADSTS90015): one window, one response."""
        install_fake_grader(self.w)
        reg = self.w.Registry.load()
        for r in reg.data["rows"].values():
            r["task"] = "x" * 1000
        reg.save()
        clips = []
        out, wb = cap(self.w, "submit", tty_in="\n", clips=clips)
        self.assertEqual(wb.call_count, 1)
        self.assertLess(len(wb.call_args[0][0]), 300)
        self.assertIn("x" * 1000, clips[0])
        self.assertIn("All 2 results submitted", out)
        self.assertTrue(all(r["submitted_rev"] == r["revision"] for r in self.rows().values()))

    def test_more_than_4000_characters_makes_two_responses(self):
        install_fake_grader(self.w)
        reg = self.w.Registry.load()
        for r in reg.data["rows"].values():
            r["task"] = "x" * 3000
        reg.save()
        clips = []
        out, wb = cap(self.w, "submit", tty_in="\n\n", clips=clips)
        self.assertIn("2 results to submit, in 2 form responses.", out)
        self.assertIn("(response 2 of 2)", flat(out))
        self.assertEqual(len(clips), 2)
        self.assertTrue(all(len(c) <= 4000 for c in clips))
        self.assertIn("All 2 results submitted", out)

    def test_clipboard_fails_tells_to_copy(self):
        install_fake_grader(self.w)
        out, wb = cap(self.w, "submit", tty_in="\n", clip_ok=False)
        self.assertIn("Copy ALL the lines between the two marks below", out)
        self.assertIn("----- all_results (3 lines) -----", out)
        self.assertNotIn("Ctrl+V", out)

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
