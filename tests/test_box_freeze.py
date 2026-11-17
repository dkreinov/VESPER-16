"""10-minute save: in the app the kit does not stop the agent. When the learner presses Enter after send, a background
process copies the solution at sent_at + 10 min. `done` after that time grades the copy and measures up to that time."""
import contextlib, io, json, os, sys, time, unittest
from unittest import mock
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fakes import fresh_ws, run, ready_for_s3, install_fake_grader  # noqa: E402


class BoxFreeze(unittest.TestCase):
    def setUp(self):
        self.w, self.home = fresh_ws()
        install_fake_grader(self.w)
        with contextlib.redirect_stdout(io.StringIO()):
            ready_for_s3(self.w)
            run(self.w, "new", "s3", "--task", "T3", "--mode", "manual")
        reg = self.w.Registry.load()
        self.rid = reg.actives("3")[0]["run_id"]
        self.sol = os.path.join(reg.data["runs"][self.rid]["folder"], "solutions", "T3.vsa")
        os.makedirs(os.path.dirname(self.sol), exist_ok=True)

    def write_sol(self, text, mtime=None):
        with open(self.sol, "w") as f:
            f.write(text)
        if mtime:
            os.utime(self.sol, (mtime, mtime))

    def done(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            run(self.w, "done", self.rid, "--no-form")
        return out.getvalue(), self.w.Registry.load().row(self.rid, "3")

    def test_start_launches_once_at_send_plus_box(self):
        reg = self.w.Registry.load()
        reg.data["runs"][self.rid]["sent_at"] = 1000.0
        os.environ.pop("VESPER_NO_BOXSAVE", None)
        try:
            with mock.patch.object(self.w, "bg_launch") as bg:
                self.w.start_boxsave(reg, self.rid)
                self.w.start_boxsave(reg, self.rid)          # a resume of the page: never a second process
        finally:
            os.environ["VESPER_NO_BOXSAVE"] = "1"
        self.assertEqual(bg.call_count, 1)
        argv = bg.call_args[0][0]
        self.assertEqual(argv[-4:], ["boxsave", self.rid, "--at", "%.0f" % (1000 + self.w.TIME_BOX_MIN * 60)])
        self.assertEqual(self.w.Registry.load().data["runs"][self.rid]["box_at"], 1000 + self.w.TIME_BOX_MIN * 60)

    def test_no_launch_for_auto_runs_or_in_tests(self):
        reg = self.w.Registry.load()
        reg.data["runs"][self.rid].update(sent_at=1000.0)
        with mock.patch.object(self.w, "bg_launch") as bg:
            self.w.start_boxsave(reg, self.rid)              # VESPER_NO_BOXSAVE is set by fakes
            os.environ.pop("VESPER_NO_BOXSAVE", None)
            try:
                reg.data["runs"][self.rid]["auto"] = True
                self.w.start_boxsave(reg, self.rid)
            finally:
                os.environ["VESPER_NO_BOXSAVE"] = "1"
        bg.assert_not_called()

    def test_box_save_skips_a_run_with_a_result(self):
        self.write_sol("A")
        self.done()
        self.assertIsNone(self.w.box_save(self.rid, time.time()))
        self.assertFalse(os.path.exists(self.w.box_paths(self.rid)[1]))

    def test_done_after_the_box_grades_the_copy(self):
        at = time.time() - 60
        self.write_sol("AT TEN MINUTES")
        info = self.w.box_save(self.rid, at)
        self.assertTrue(info["exists"])
        self.write_sol("LATER WORK", mtime=time.time())     # the agent goes on after the box
        out, row = self.done()
        self.assertEqual(row["cutoff"], "%.0f" % at)
        self.assertEqual(row["solution_sha"], info["sha"])
        self.assertEqual(row["overrun"], "no")
        self.assertEqual(row["stopped"], "time")
        self.assertIn("Later changes do not count.", out)
        with open(self.w.snap_path(self.rid, "3")) as f:
            self.assertEqual(f.read(), "AT TEN MINUTES")

    def test_no_change_after_the_box_is_not_a_stop(self):
        at = time.time() - 60
        self.write_sol("DONE EARLY", mtime=at - 30)
        self.w.box_save(self.rid, at)
        _, row = self.done()
        self.assertEqual(row["cutoff"], "%.0f" % at)
        self.assertEqual(row["stopped"], "")

    def test_no_solution_at_the_box(self):
        at = time.time() - 60
        self.w.box_save(self.rid, at)
        self.write_sol("TOO LATE", mtime=time.time())
        _, row = self.done()
        self.assertEqual(row["solution_sha"], "")
        self.assertEqual(row["score"], "0")

    def test_a_late_save_is_not_used(self):
        at = time.time() - 900
        self.write_sol("A")
        self.w.box_save(self.rid, at)                         # saved_at is now: 900 s late (the laptop slept)
        t = time.time()
        _, row = self.done()
        self.assertGreaterEqual(float(row["cutoff"]), t - 2)

    def test_done_before_the_box_is_unchanged(self):
        self.write_sol("A")
        t = time.time()
        _, row = self.done()
        self.assertGreaterEqual(float(row["cutoff"]), t - 2)
        self.assertEqual(row["stopped"], "")

    def test_boxsave_command_waits_then_saves(self):
        self.write_sol("A")
        at = time.time() + 30
        with mock.patch.object(self.w, "_sleep") as sl:
            run(self.w, "boxsave", self.rid, "--at", "%.0f" % at)
        self.assertAlmostEqual(sl.call_args[0][0], 30, delta=3)
        with open(self.w.box_paths(self.rid)[1]) as f:
            self.assertTrue(json.load(f)["exists"])

    def test_stop_table_has_the_box_line(self):
        reg = self.w.Registry.load()
        reg.data["runs"][self.rid]["sent_at"] = time.time()
        f = reg.data["runs"][self.rid]["folder"]
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.w.stop_table(reg, [("t3", self.rid, f, "")])
        self.assertIn("the kit saves the result by itself", out.getvalue())


if __name__ == "__main__":
    unittest.main()
