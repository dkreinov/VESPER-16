"""Learner output is short and narrow: no line over 72 characters, one summary line per run."""
import contextlib, io, os, sys, unittest
from unittest import mock
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fakes  # noqa: E402
from fakes import fresh_ws, run, flat  # noqa: E402


def capture(w, *argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        run(w, *argv)
    return out.getvalue()


def long_lines(text):
    """Lines over 72 characters that are not a single path or command token."""
    bad = []
    for line in text.splitlines():
        if len(line) <= 72:
            continue
        body = line.strip()
        if len(body.split()) == 1 or body.startswith(("python ", "C:\\", "/")):
            continue
        bad.append(line)
    return bad


class Narrow(unittest.TestCase):
    def setUp(self):
        self.w, _ = fresh_ws()

    def test_new_s1_and_done_stage1(self):
        run(self.w, "doctor", "--agent", "codex", "--alias", "t")
        self.assertEqual(long_lines(capture(self.w, "new", "s1", "--method", "plain")), [])
        out = capture(self.w, "done", "--no-form")
        self.assertEqual(long_lines(out), [])
        self.assertRegex(flat(out), r"Time .*Cost ")
        self.assertIn("Score", out)
        self.assertNotIn("not proof", out)
        self.assertNotIn("run_id", out)                       # no table

    def test_harvest_note_hint_no_card(self):
        mem = os.path.join(os.environ["CODEX_HOME"], "memories")
        os.makedirs(mem)
        with open(os.path.join(mem, "m.md"), "w") as f:       # Codex Memories on: the card would show
            f.write("x")
        _, out = fakes.ready_for_s3(self.w)
        self.assertEqual(long_lines(out), [])
        flat_out = flat(out)
        self.assertIn("STAGE 2 DONE: skill saved", out)
        self.assertIn("Why stage 3 also runs a DIFFERENT task (T6)", out)
        self.assertIn("Optional (2 min): python workshop.py judge", out)
        self.assertNotIn("Codex Memories are ON", flat_out)
        self.assertNotIn("Skill help the agent used", out)
        self.assertNotIn("not proof", out)
        lines = out.splitlines()
        summary = next(i for i, x in enumerate(lines) if x.startswith("  Time "))
        why = next(i for i, x in enumerate(lines) if "Why stage 3" in x)
        opt = next(i for i, x in enumerate(lines) if "Optional (2 min)" in x)
        nxt = next(i for i, x in enumerate(lines) if "NEXT:" in x)
        self.assertTrue(summary < why < opt < nxt)

    def test_new_s3_all_and_done_stage3(self):
        fakes.ready_for_s3(self.w)
        out = capture(self.w, "new", "s3", "--task", "all", "--name", "mira")
        self.assertEqual(long_lines(out), [])
        reg = self.w.Registry.load()
        ids = [x["run_id"] for x in reg.actives()]
        self.assertEqual(len(ids), 4)
        out = capture(self.w, "done", ids[0], "--no-form")
        self.assertEqual(long_lines(out), [])
        self.assertIn("FINISHED", out)

    def test_show_narrow_terminal_gives_blocks(self):
        fakes.ready_for_s3(self.w)
        with mock.patch.object(self.w.shutil, "get_terminal_size",
                               return_value=os.terminal_size((30, 24))):
            out = capture(self.w, "show")
        self.assertIn("    what: 2: new skill", out)
        self.assertIn("    what: 1: solve T3", out)
        self.assertNotIn("emulator_runs", out)
        self.assertEqual(long_lines(out), [])


class DataLinesNotWrapped(unittest.TestCase):
    def test_all_results_lines_stay_whole(self):
        w, _ = fresh_ws()
        t = w.all_results_text([{"run_id": "s3-ab12-t6-9f3c", "stage": "3", "task": "T6", "isolation": "detected",
                                 "isolation_note": "worked outside the run folder: ~/OneDrive - Mobileye/Documents/"
                                                   "ChatGPT/workshop_testing/s1-5364 and more text", "score": "100.0"}])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            w.print(t)
        self.assertEqual(out.getvalue().strip(), t.strip())

    def test_normal_text_still_wrapped(self):
        w, _ = fresh_ws()
        self.assertGreater(len(w.wrap_line("  " + "word " * 30)), 1)


if __name__ == "__main__":
    unittest.main()
