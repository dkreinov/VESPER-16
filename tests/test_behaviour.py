"""Participant mistakes that the workshop must survive (spec section 10)."""
import os, sys, time, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fakes  # noqa: E402
from fakes import fresh_ws, run  # noqa: E402


class Behaviour(unittest.TestCase):
    def setUp(self):
        self.w, self.tmp = fresh_ws()

    def test_skip_doctor(self):
        run(self.w, "new", "s1")                      # new runs doctor by itself
        reg = self.w.Registry.load()
        self.assertTrue(reg.data.get("doctor"))
        self.assertEqual(reg.data["active"]["stage"], "1")

    def test_skill_before_done_refused(self):
        run(self.w, "new", "s1")
        with self.assertRaises(SystemExit):
            run(self.w, "skill")

    def test_done_without_new(self):
        with self.assertRaises(SystemExit):
            run(self.w, "done", "--no-form")

    def test_interrupted_new_is_recoverable(self):
        run(self.w, "doctor", "--agent", "codex", "--alias", "")
        reg = self.w.Registry.load()
        half = os.path.join(self.w.ws_home(), "s1-dead")
        reg.add_item(half, "dir")                      # registered, then "Ctrl+C" before creation
        reg.save()
        os.makedirs(os.path.join(half, "bin"))         # partly created
        run(self.w, "cleanup", "--yes", "--no-copy")
        self.assertFalse(os.path.exists(half))

    def test_two_sessions_same_code(self):
        t = time.time()
        for sid in ("0a0a0a0a-1111-2222-3333-444455556666", "0b0b0b0b-1111-2222-3333-444455556666"):
            fakes.codex_log(sid, "/x", [(t - 5, 10, 0, 1, "Workshop run: s1-cafe")])
        s = self.w.find_sessions("s1-cafe")
        self.assertEqual(len(s), 2)
        self.assertEqual(self.w.pick_session("s1-cafe"), s[0])   # no TTY: first one

    def test_global_skill_blocks_stage3(self):
        run(self.w, "doctor", "--agent", "codex", "--alias", "")
        d = os.path.join(os.environ["VESPER_WS_USERHOME"], ".codex", "skills", "vesper16")
        os.makedirs(d)
        with open(os.path.join(d, "SKILL.md"), "w") as f:
            f.write("---\nname: vesper16\n---\n")
        with self.assertRaises(SystemExit):
            run(self.w, "new", "s3", "--skill", "own")

    def test_manual_tokens_path_keeps_row(self):
        run(self.w, "new", "s1")
        run(self.w, "done", "--no-form")              # no log, no TTY: measurement "none", row kept
        rows = self.w.Registry.load().data["rows"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(list(rows.values())[0]["measurement"], "none")

    def test_missing_solution_scores_zero_when_graded(self):
        self.assertEqual(self.w.grade_snapshot("T3", None), ("", "ungraded"))


if __name__ == "__main__":
    unittest.main()
