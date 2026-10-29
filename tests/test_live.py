"""The --auto live status screen: line formatting, last-step parser, run counter, non-TTY plain mode."""
import json, os, shutil, sys, tempfile, time, unittest
from unittest import mock
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fakes  # noqa: E402
from test_auto import AutoBase, capture, long_lines  # noqa: E402


def item(state="running", **kw):
    d = dict(label="T3 with skill", state=state, t0=100.0, end=None, key="t3", live_runs=2, live_saved=True,
             live_step="assembling")
    d.update(kw)
    return d


class LiveFormat(unittest.TestCase):
    def setUp(self):
        self.w, _ = fakes.fresh_ws()

    def test_bar(self):
        self.assertEqual(self.w.live_bar(0, 600), "[" + "." * 15 + "]")
        self.assertEqual(self.w.live_bar(300, 600), "[#######........]")
        self.assertEqual(self.w.live_bar(9999, 600), "[" + "#" * 15 + "]")

    def test_running_line(self):
        l1, l2 = self.w.live_agent_lines(item(), 190.0, 600, True, 0)
        self.assertEqual(l1, "T3 with skill     ⠋  1:30 [##.............]  runs 2/6  saved: yes")
        self.assertEqual(l2, "   last step: assembling")

    def test_ascii_fallback(self):
        l1, _ = self.w.live_agent_lines(item("done", end=190.0), 500.0, 600, False)
        self.assertIn("* done 1:30", l1)
        l1, _ = self.w.live_agent_lines(item(), 100.0, 600, False, 1)
        self.assertIn("\\", l1)

    def test_states(self):
        def f(**k):
            return self.w.live_agent_lines(item(**k), 300.0, 600)[0]
        self.assertIn("✓ done 1:30", f(state="done", end=190.0))
        self.assertIn("stopped at time box", f(state="stopped", end=700.0))
        self.assertIn("error: boom", f(state="failed", err="boom", end=110.0))
        self.assertIn("saved: no", f(live_saved=False))

    def test_72_chars(self):
        lines = self.w.live_block([item(label="T6 without skill", live_runs=6, live_step="x" * 200),
                                   item("failed", err="e" * 300)], 100 + 599, 600)
        lines += self.w.live_header("claude-haiku-5-5", [item(), item(key="n3")])
        for x in lines:
            self.assertLessEqual(len(x), 72, x)

    def test_header_uses_constants(self):
        h = self.w.live_header("m-1", [item(), item(key="t6"), item(key="n3"), item(key="n6")])
        self.assertEqual(h[0], "STAGE 3 --auto: 4 fresh agents (m-1) work alone")
        self.assertEqual(h[1], "2 use your skill, 2 do not (the control). They cannot see each other.")
        self.assertIn("Each has %d min and %d emulator runs." % (self.w.TIME_BOX_MIN, self.w.S3_RUN_BUDGET), h[2])
        for x in h + self.w.live_footer(4):
            self.assertLessEqual(len(x), 72, x)


class LastStep(unittest.TestCase):
    def setUp(self):
        self.w, _ = fakes.fresh_ws()
        self.d = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def step(self, *events, tail=""):
        with open(os.path.join(self.d, "agent-output.jsonl"), "w") as f:
            for e in events:
                f.write((e if isinstance(e, str) else json.dumps(e)) + "\n")
            f.write(tail)
        return self.w.last_step(self.d)

    def codex(self, t, **it):
        return {"type": "item.completed", "item": dict(type=t, **it)}

    def test_codex(self):
        c = "command_execution"
        self.assertEqual(self.step(self.codex(c, command="bin/vesper run a.vsa")), "running the emulator")
        self.assertEqual(self.step(self.codex(c, command="powershell bin\\vesper asm a.vsa")), "assembling")
        self.assertEqual(self.step(self.codex(c, command="cat skills/x/SKILL.md")), "reading the skill")
        self.assertEqual(self.step(self.codex(c, command="cat tasks/T3.md")), "reading the task")
        self.assertEqual(self.step(self.codex("file_change")), "writing code")
        self.assertEqual(self.step(self.codex("agent_message", text="hi")), "thinking")

    def test_claude(self):
        def tu(name, **inp):
            return {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": name, "input": inp}]}}
        self.assertEqual(self.step(tu("Bash", command="bin/vesper run a.vsa")), "running the emulator")
        self.assertEqual(self.step(tu("Read", file_path="/x/SKILL.md")), "reading the skill")
        self.assertEqual(self.step(tu("Read", file_path="tasks/T3.md")), "reading the task")
        self.assertEqual(self.step(tu("Write", file_path="solutions/T3.vsa")), "writing code")
        self.assertEqual(self.step(tu("Edit", file_path="solutions/T3.vsa")), "writing code")

    def test_cursor(self):
        def tc(k, **a):
            return {"type": "tool_call", "subtype": "started", "tool_call": {k: {"args": a}}}
        self.assertEqual(self.step(tc("shellToolCall", command="bin/vesper asm a")), "assembling")
        self.assertEqual(self.step(tc("readToolCall", path="SKILL.md")), "reading the skill")
        self.assertEqual(self.step(tc("editToolCall", path="solutions/T3.vsa")), "writing code")

    def test_partial_last_line_and_garbage(self):
        e = self.codex("command_execution", command="bin/vesper run a")
        self.assertEqual(self.step(e, "not json", tail='{"type": "item.comp'), "running the emulator")
        self.assertEqual(self.step(tail="{"), "")
        self.assertEqual(self.w.last_step(os.path.join(self.d, "nope")), "")

    def test_big_file_reads_tail_only(self):
        with open(os.path.join(self.d, "agent-output.jsonl"), "w") as f:
            f.write(json.dumps(self.codex("file_change")) + "\n")
            f.write(("x" * 100 + "\n") * 2000)
        self.assertEqual(self.w.last_step(self.d), "")      # the old event is outside the 64 KB tail


class RunCounter(unittest.TestCase):
    def test_refresh_counts_runs_and_saved(self):
        w, _ = fakes.fresh_ws()
        d = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(d, "solutions"))
            now = time.time()
            with open(os.path.join(d, ".vesper-runs.log"), "w") as f:
                f.write("%f run a\n%f asm a\n%f run a\n%f run a\n" % (now - 5, now - 4, now - 3, now - 2))
            it = item(folder=d, t0=now - 10, sol_task="T3", live_saved=False, live_runs=0)
            w.live_refresh([it], now)
            self.assertEqual(it["live_runs"], 3)
            self.assertFalse(it["live_saved"])
            open(os.path.join(d, "solutions", "T3.vsa"), "w").close()
            w.live_refresh([it], now)
            self.assertTrue(it["live_saved"])
        finally:
            shutil.rmtree(d, ignore_errors=True)


class LiveViewDraw(unittest.TestCase):
    def test_redraw_uses_cursor_up_without_wrap(self):
        w, _ = fakes.fresh_ws()
        its = [item(folder="nowhere", t0=time.time()), item(folder="nowhere", t0=time.time(), key="n3")]
        v = w.LiveView(its, 600, "m")
        out = []
        with mock.patch.object(v, "_w", side_effect=out.append):
            v.draw()
            v.draw()
        n = 2 * 2 + 1 + 2
        self.assertEqual(v.height, n)
        self.assertTrue(out[1].startswith("\x1b[%dA" % n))
        self.assertEqual(out[1].count("\n"), n)


class PlainModeKept(AutoBase):
    def test_non_tty_prints_old_plain_lines(self):
        self.assertFalse(self.w.live_enabled())
        out, rc = capture(self.w, "new", "s3", "--task", "T3", "--auto", "--yes")
        self.assertRegex(out, r"  T3 with skill +running 0:0\d")
        self.assertNotIn("\x1b[", out)
        self.assertNotIn("last step:", out)
        self.assertEqual(long_lines(out), [])

    def test_no_live_env(self):
        with mock.patch.object(sys.stdout, "isatty", return_value=True), \
             mock.patch.dict(os.environ, {"VESPER_NO_LIVE": "1"}):
            self.assertFalse(self.w.live_enabled())


if __name__ == "__main__":
    unittest.main()
