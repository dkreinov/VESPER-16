"""Isolation audit, overrun flag, skill inspection step (Part W5, W6, W8)."""
import contextlib, io, json, os, sys, tempfile, time, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fakes  # noqa: E402
from fakes import fresh_ws, run, iso  # noqa: E402


def write_log(path, t, calls, claude=False):
    """calls: list of command strings, each one tool call at time t."""
    with open(path, "w") as f:
        for i, cmd in enumerate(calls):
            if claude:
                d = {"type": "assistant", "timestamp": iso(t + i), "message": {"content": [
                    {"type": "tool_use", "name": "Bash", "input": {"command": cmd}}]}}
            else:
                d = {"timestamp": iso(t + i), "type": "response_item", "payload": {
                    "type": "function_call", "name": "shell",
                    "arguments": json.dumps({"command": ["bash", "-lc", cmd]})}}
            f.write(json.dumps(d) + "\n")
    return path


class OutsideReadsTest(unittest.TestCase):
    def setUp(self):
        self.w, self.home = fresh_ws()
        self.folder = os.path.join(self.w.ws_home(), "s1-aaaa")
        os.makedirs(self.folder)
        self.t = time.time()
        self.log = os.path.join(self.home, "log.jsonl")

    def scan(self, cmd, writer=False, claude=False):
        write_log(self.log, self.t, [cmd], claude=claude)
        return self.w.detect_outside_reads([self.log], self.t - 5, self.t + 5, self.folder, writer=writer)

    def test_inside_path(self):
        st, note = self.scan("cat %s/tasks/T3.md && ls bin examples" % self.folder)
        self.assertEqual((st, note), ("not_detected", ""))
        st, _ = self.scan("python bin/vesper run game.vsp 2>/dev/null; cat /tmp/x")
        self.assertEqual(st, "not_detected")

    def test_absolute_outside_path(self):
        st, note = self.scan("cat /home/other/secret.txt")
        self.assertEqual(st, "detected")
        self.assertIn("/home/other/secret.txt", note)
        st, note = self.scan("type C:\\Users\\other\\notes.txt")
        self.assertEqual(st, "detected")

    def test_dotdot_escape(self):
        st, note = self.scan("cat ../notes.txt")
        self.assertEqual(st, "detected")
        st, _ = self.scan("cat examples/../tasks/T3.md")
        self.assertEqual(st, "not_detected")

    def test_other_run_folder_name(self):
        st, note = self.scan("ls s3-bbbb-t3-cccc")
        self.assertEqual(st, "detected")
        self.assertIn("s3-bbbb-t3-cccc", note)
        other = os.path.join(self.w.ws_home(), "s1-dddd", "solutions")
        st, _ = self.scan("ls %s" % other)
        self.assertEqual(st, "detected")

    def test_skills_folder(self):
        st, note = self.scan("ls ~/.skills/s1-aaaa")
        self.assertEqual(st, "detected")

    def test_writer_reads_t6(self):
        st, _ = self.scan("cat tasks/T6.md", writer=False)
        self.assertEqual(st, "not_detected")
        st, note = self.scan("cat tasks/T6.md", writer=True)
        self.assertEqual(st, "detected")
        st, _ = self.scan("python t6font.py", writer=True)
        self.assertEqual(st, "detected")

    def test_claude_tool_use(self):
        st, _ = self.scan("cat /home/other/x", claude=True)
        self.assertEqual(st, "detected")

    def test_only_tool_calls_and_window(self):
        with open(self.log, "w") as f:      # prose mentioning a path is not a tool call
            f.write(json.dumps({"timestamp": iso(self.t), "type": "response_item", "payload": {
                "type": "message", "content": [{"type": "output_text", "text": "see /home/other/x"}]}}) + "\n")
        st, _ = self.w.detect_outside_reads([self.log], self.t - 5, self.t + 5, self.folder)
        self.assertEqual(st, "not_detected")
        write_log(self.log, self.t - 500, ["cat /home/other/x"])      # outside [t0, t1]
        st, _ = self.w.detect_outside_reads([self.log], self.t - 5, self.t + 5, self.folder)
        self.assertEqual(st, "not_detected")

    def test_note_limits(self):
        cmd = " ".join("/home/o/%s%s" % (c, "x" * 80) for c in "abcdef")
        st, note = self.scan(cmd)
        self.assertEqual(st, "detected")
        self.assertLessEqual(len(note), 200)
        self.assertLessEqual(note.count("outside path"), 3)

    def test_no_log(self):
        self.assertEqual(self.w.detect_outside_reads([], 0, 1, self.folder), ("unknown", ""))
        self.assertEqual(self.w.detect_outside_reads([os.path.join(self.home, "none.jsonl")], 0, 1, self.folder),
                         ("unknown", ""))
        self.assertEqual(self.w.detect_outside_reads(None, 0, 1, self.folder), ("unknown", ""))


class DoneFieldsTest(unittest.TestCase):
    def _s1(self, wall, calls):
        w, _ = fresh_ws()
        run(w, "doctor", "--agent", "codex", "--alias", "t")
        run(w, "new", "s1")
        reg = w.Registry.load()
        rid = reg.data["active"]["run_id"]
        t0 = reg.data["active"]["start"]
        folder = reg.data["runs"][rid]["folder"]
        log = fakes.codex_log("0c0d0e0f-0000-1111-2222-333344445555", folder,
                              [(t0 + 0.01, 10, 0, 1, "Workshop run: %s" % rid), (t0 + 0.02, 20, 0, 2, "")])
        with open(log, "a") as fh:
            for i, c in enumerate(calls):
                fh.write(json.dumps({"timestamp": iso(t0 + 0.03 + i * 0.001), "type": "response_item", "payload": {
                    "type": "function_call", "name": "shell",
                    "arguments": json.dumps({"command": ["bash", "-lc", c]})}}) + "\n")
        reg.data["active_runs"][rid]["start"] = t0 - wall
        reg.save()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            run(w, "done", "--no-form")
        return w, rid, out.getvalue()

    def test_not_detected_and_no_overrun(self):
        w, rid, out = self._s1(60, ["ls"])
        row = w.Registry.load().row(rid, "1")
        self.assertEqual((row["isolation"], row["overrun"]), ("not_detected", "no"))
        self.assertIn("  Isolation check: not_detected. (A scan finds some outside reads; not proof.)", out)
        self.assertNotIn("time box: flagged", out)

    def test_detected_and_overrun(self):
        w, rid, out = self._s1(700, ["cat tasks/T6.md"])
        row = w.Registry.load().row(rid, "1")
        self.assertEqual((row["isolation"], row["overrun"]), ("detected", "yes"))
        self.assertTrue(row["isolation_note"])
        self.assertIn("  Isolation check: detected.", out)
        self.assertIn("  Over the 10-minute time box: flagged in the results.", out)


class HarvestStepTest(unittest.TestCase):
    def test_inspection_step(self):
        w, _ = fresh_ws()
        rid, out = fakes.ready_for_s3(w)
        self.assertIn("Before stage 3 (2 minutes): open ", out)
        self.assertIn("SKILL.md and find one verified rule, one reusable code part, and one uncertainty.", out)
        self.assertLess(out.index("Before stage 3"), out.index("NEXT:"))
        self.assertIn("Isolation check:", out)


if __name__ == "__main__":
    unittest.main()
