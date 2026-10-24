"""Final-review fixes: stopped runs stay gradable, overrun to the last activity, repeat question,
check-auto probe, T6 name for a non-Latin alias, box tables, minimal stage-3 output."""
import contextlib, io, os, re, sys, time, unittest
from unittest import mock
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fakes  # noqa: E402
import test_auto as TA  # noqa: E402
from fakes import fresh_ws, run, flat  # noqa: E402


def capture(w, *argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = run(w, *argv)
    return out.getvalue(), rc


class _TTY(io.StringIO):
    def isatty(self):
        return True


def FakeTTY(enc):
    """A stdout that is a console with the given encoding."""
    return type("TTY_" + enc.replace("-", ""), (_TTY,), {"encoding": enc})()


class Tables(unittest.TestCase):
    def setUp(self):
        self.w, _ = fresh_ws()

    def _render(self, enc):
        out = FakeTTY(enc)
        with mock.patch.object(sys, "stdout", out):
            return self.w.render_table(["run", "st", "score"], [["s3-aaaa-t3-bbbb", "3", "100 PASS"],
                                                              ["s1-aaaa", "1", "-"]], [16, 2, 9])

    def test_box_table_on_a_utf8_console(self):
        lines = self._render("utf-8")
        self.assertEqual(lines[0][2], "┌")
        self.assertEqual(lines[-1][2], "└")
        self.assertEqual(sum(1 for x in lines if "├" in x), 1)            # a separator only under the header
        self.assertEqual(sum(1 for x in lines if "┼" in x), 1)
        self.assertTrue(all(len(x) <= 72 for x in lines))

    def test_ascii_table_when_the_console_cannot_encode_boxes(self):
        lines = self._render("cp1252")
        self.assertFalse(any(c in "".join(lines) for c in "┌│├└"))
        self.assertTrue(all(len(x) <= 72 for x in lines))
        self.assertIn("s3-aaaa-t3-bbbb", lines[2])

    def test_ascii_table_when_stdout_is_a_pipe(self):
        lines = self.w.render_table(["a", "b"], [["1", "2"]], [3, 3])       # the test stdout is not a TTY
        self.assertEqual(len(lines), 3)
        self.assertNotIn("│", "".join(lines))

    def test_show_fits_72_columns(self):
        fakes.ready_for_s3(self.w)
        for enc in ("utf-8", "cp1252"):
            out = FakeTTY(enc)
            with mock.patch.object(sys, "stdout", out), mock.patch.dict(os.environ, {"VESPER_NO_CLEAR": "1"}):
                run(self.w, "show")
            # a path is one word; measure the VISIBLE width (a colour terminal adds escape codes)
            lines = [re.sub(r"\x1b\[[0-9;]*m", "", x) for x in out.getvalue().splitlines() if "vesper-runs" not in x]
            self.assertTrue(all(len(x) <= 72 for x in lines), [x for x in lines if len(x) > 72][:3])
            self.assertEqual(any("┌" in x for x in lines), enc == "utf-8")


class StoppedRunStaysGradable(unittest.TestCase):          # B1
    def test_partial_with_locked_grader_is_graded_later(self):
        w, _ = fresh_ws()
        fakes.ready_for_s3(w)
        capture(w, "new", "s3", "--task", "T3")
        rid = [x["run_id"] for x in w.Registry.load().actives("3")][0]
        capture(w, "done", rid, "--partial", "--no-form")
        row = w.Registry.load().row(rid, "3")
        self.assertEqual((row["grading"], row["score"], row["stopped"]), ("ungraded", "", "partial"))
        fakes.install_fake_grader(w)
        out, _ = capture(w, "grade")
        row = w.Registry.load().row(rid, "3")
        self.assertIn("stage 3: score", out)
        self.assertEqual(row["grading"], "partial")
        self.assertNotEqual(row["score"], "")


class Overrun(unittest.TestCase):                           # B2 / M2
    def test_compare_shows_over_10_min_and_is_not_matched(self):
        w, _ = fresh_ws()
        reg = w.Registry.load()
        base = dict(task="T3", model="gpt-6-luna", effort="high", cost_usd="0.10", elapsed_min="9", start="3")
        reg.data["runs"]["s3-aaaa-t3-bbbb"] = dict(folder="", task="T3", method="plain", stage="3", parent="s1-aaaa")
        reg.data["runs"]["s3-aaaa-n3-cccc"] = dict(folder="", task="T3", method="none", stage="3", parent="s1-aaaa",
                                                   skill_source="none")
        reg.set_row("s3-aaaa-t3-bbbb", "3", dict(base, score="100", overrun="no"))
        reg.set_row("s3-aaaa-n3-cccc", "3", dict(base, score="85", overrun="yes", method="none", start="4"))
        out = flat(self._cap(w, reg))
        self.assertIn("over 10 min", out)
        self.assertIn("One run was over the time box: this is not a matched comparison.", out)
        self.assertNotIn("(same model)", out)

    def _cap(self, w, reg):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            w.show_compare(reg)
        return out.getvalue()

    def test_every_stage3_page_has_the_same_stop_line(self):
        w, _ = fresh_ws()
        fakes.ready_for_s3(w)
        out, _ = capture(w, "new", "s3", "--task", "all", "--name", "MIRA")
        self.assertEqual(flat(out).count("Stop the agent at 10 min, then run its done line."), 4)   # one per page
        self.assertNotIn("15 min", out)
        self.assertNotIn("control: stop it", out)
        self.assertEqual(out.count("Start in this order"), 1)


class MinimalDone(unittest.TestCase):                       # F4
    def test_done_prints_no_compare_before_the_pair_is_complete(self):
        w, _ = fresh_ws()
        fakes.ready_for_s3(w)
        capture(w, "new", "s3", "--task", "all", "--name", "MIRA")
        ids = {x["run_id"].split("-")[2]: x["run_id"] for x in w.Registry.load().actives()}
        out, _ = capture(w, "done", ids["t3"], "--no-form")
        for bad in ("WITH vs WITHOUT", "Observed results", "Skill creation", "waiting for", "Not graded yet",
                    "Estimated cost", "Observed score gains"):
            self.assertNotIn(bad, out)
        self.assertIn("FINISHED  T3 with skill", flat(out))
        self.assertIn("3 agents are still working", flat(out))
        out, _ = capture(w, "done", ids["n3"], "--no-form")
        self.assertEqual(out.count("WITH vs WITHOUT"), 1)           # the T3 pair is complete now
        self.assertEqual(out.count("Observed results"), 1)
        self.assertNotIn("Skill creation", out)
        self.assertNotIn("Observed score gains", out)


class RepeatQuestion(unittest.TestCase):                    # M1
    def _complete(self):
        w, _ = fresh_ws()
        fakes.ready_for_s3(w)
        capture(w, "new", "s3", "--task", "all", "--name", "MIRA")
        for x in w.Registry.load().actives():
            capture(w, "done", x["run_id"], "--no-form")
        return w

    def test_complete_stage_3_is_not_repeated_silently(self):
        w = self._complete()
        n = len([r for r in w.Registry.load().data["runs"].values() if r.get("stage") == "3"])
        out, rc = capture(w, "new", "s3", "--task", "all", "--name", "MIRA")
        self.assertEqual(rc, 0)
        self.assertIn("needs a person to say yes. Add --yes", flat(out))
        self.assertEqual(len([r for r in w.Registry.load().data["runs"].values() if r.get("stage") == "3"]), n)
        out, rc = capture(w, "new", "s3", "--task", "all", "--name", "MIRA", "--yes")
        self.assertEqual(len([r for r in w.Registry.load().data["runs"].values() if r.get("stage") == "3"]), n + 4)

    def test_interactive_default_is_no(self):
        w = self._complete()
        asked = []
        w.ask = lambda p, d="": (asked.append(p), d)[1]
        n = len(w.Registry.load().data["runs"])
        tty = FakeTTY("utf-8")
        with mock.patch.object(sys.stdin, "isatty", return_value=True, create=True), \
                mock.patch.object(sys, "stdout", tty), mock.patch.dict(os.environ, {"VESPER_NO_CLEAR": "1"}):
            rc = run(w, "new", "s3", "--task", "all", "--name", "MIRA")
        self.assertIn("Stage 3 is done. Start a repeat attempt (4 new runs)? [y/N] ", asked)
        self.assertEqual(len(w.Registry.load().data["runs"]), n)


class LatinNameForT6(unittest.TestCase):                    # M7
    def _new(self, answer):
        w, _ = fresh_ws()
        fakes.ready_for_s3(w)
        reg = w.Registry.load()
        reg.data["alias"] = "דניס"
        reg.save()
        asked = []
        w.ask = lambda p, d="": (asked.append(p), answer)[1]
        capture(w, "new", "s3", "--task", "T6")
        reg = w.Registry.load()
        return [r for r in reg.data["runs"].values() if r.get("task") == "T6"][0]["name"], asked

    def test_asks_for_a_latin_name(self):
        name, asked = self._new("Dennis")
        self.assertEqual(name, "DENNIS")
        self.assertEqual(len([p for p in asked if "Latin name" in p]), 1)

    def test_enter_keeps_vesper(self):
        name, _ = self._new("")
        self.assertEqual(name, "VESPER")


class CheckAutoProbe(TA.AutoBase):                          # M4 / M5
    agent = "cursor"

    def _check(self):
        with mock.patch.object(self.w.shutil, "which", return_value=None):
            return capture(self.w, "doctor", "--agent", "cursor", "--check-auto")[0]

    def test_pass(self):
        out = self._check()
        self.assertIn("--check-auto cursor", out)
        self.assertIn("PASS", out)
        self.assertTrue(self.w.Registry.load().data["auto_probe"]["cursor"]["pass"])

    def test_fail_when_the_agent_cannot_write(self):
        os.environ["FAKE_PROBE_NOWRITE"] = "1"
        out = self._check()
        self.assertIn("could not write out/ok.txt", flat(out))
        self.assertFalse(self.w.Registry.load().data["auto_probe"]["cursor"]["pass"])

    def test_fail_when_no_version_text(self):
        os.environ["FAKE_PROBE_NOVERSION"] = "1"
        out = self._check()
        self.assertIn("did not run bin/vesper --version", flat(out))
        self.assertFalse(self.w.Registry.load().data["auto_probe"]["cursor"]["pass"])

    def test_fail_when_the_agent_writes_outside(self):
        os.makedirs(os.path.join(self.home, "user"), exist_ok=True)
        os.environ["FAKE_PROBE_OUTSIDE"] = "1"
        out = self._check()
        self.assertIn("OUTSIDE its folder", flat(out))
        self.assertFalse(self.w.Registry.load().data["auto_probe"]["cursor"]["pass"])
        left = [n for n in os.listdir(os.path.join(self.home, "user")) if n.startswith("vesper-probe")]
        self.assertEqual(left, [])                                   # the probe file is removed

    def test_warning_screen_says_only_what_was_verified(self):
        out, _ = capture(self.w, "new", "s3", "--task", "T3", "--auto")
        self.assertIn("Not verified on this computer: run  doctor --check-auto", flat(out))
        self.assertIn("It can read other folders;", flat(out))
        self.assertNotIn("Verified by", out)
        a = type("A", (), {"auto_agent": "cursor", "auto_verified": True})()
        for t in (self.w.VERIFIED, self.w.READ_NOTE):
            self.assertLessEqual(len(t), 70)
        self.assertIn("Verified by doctor --check-auto", "\n".join(self.w.auto_limit_lines(a)))


if __name__ == "__main__":
    unittest.main()
