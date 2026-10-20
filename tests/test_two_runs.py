"""Two stage-3 runs at the same time (T6 and T3), done selection, legacy registry, compare note."""
import contextlib, io, json, os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fakes  # noqa: E402
from fakes import fresh_ws, run  # noqa: E402


def capture(fn, *a):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        fn(*a)
    return out.getvalue()


class LegacyRegistryTest(unittest.TestCase):
    def setUp(self):
        self.w, _ = fresh_ws()

    def _write(self, active):
        os.makedirs(self.w.ws_home(), exist_ok=True)
        with open(self.w.Registry.path(), "w") as f:
            json.dump({"version": 1, "agent": "codex", "alias": "", "items": [], "runs": {}, "rows": {},
                       "active": active}, f)

    def test_single_active_object_migrates(self):
        old = {"run_id": "s1-abcd", "stage": "1", "start": 5.0}
        self._write(old)
        reg = self.w.Registry.load()
        self.assertEqual(reg.actives(), [old])
        self.assertEqual(reg.get_active("s1-abcd")["stage"], "1")
        reg.save()
        with open(self.w.Registry.path()) as f:
            d = json.load(f)
        self.assertEqual(d["version"], 2)
        self.assertEqual(list(d["active_runs"]), ["s1-abcd"])
        self.assertEqual(d["active"]["run_id"], "s1-abcd")

    def test_null_active_migrates(self):
        self._write(None)
        reg = self.w.Registry.load()
        self.assertEqual(reg.actives(), [])
        self.assertIsNone(reg.data["active"])

    def test_active_mirror_is_the_latest_start(self):
        reg = self.w.Registry.load()
        reg.start_active("s3-a", "3", 1.0)
        reg.start_active("s3-b", "3", 2.0)
        self.assertEqual(reg.data["active"]["run_id"], "s3-b")
        reg.end_active("s3-b")
        self.assertEqual(reg.data["active"]["run_id"], "s3-a")
        reg.end_active("s3-a")
        self.assertIsNone(reg.data["active"])


class NextCmdTest(unittest.TestCase):
    def test_next_cmd(self):
        w, _ = fresh_ws()
        self.assertEqual(w.next_cmd({"stage": "1", "run_id": "s1-x"}), "python workshop.py done")
        self.assertEqual(w.next_cmd({"stage": "2", "run_id": "s1-x"}), "python workshop.py harvest")
        self.assertEqual(w.next_cmd({"stage": "3", "run_id": "s3-x"}), "python workshop.py done s3-x")


class TwoRunsTest(unittest.TestCase):
    def setUp(self):
        self.w, self.tmp = fresh_ws()
        self.s1, self.harvest_out = fakes.ready_for_s3(self.w)

    def _new(self, task, *extra):
        out = capture(run, self.w, "new", "s3", "--task", task, *extra)
        reg = self.w.Registry.load()
        rid = [x["run_id"] for x in reg.actives() if reg.data["runs"][x["run_id"]]["task"] == task][0]
        return rid, out

    def test_harvest_box_recommends_task_both(self):
        self.assertIn("python workshop.py new s3 --task both", self.harvest_out)

    def test_new_s3_both_creates_two_runs(self):
        out = capture(run, self.w, "new", "s3", "--task", "both", "--name", "MIRA")
        reg = self.w.Registry.load()
        acts = reg.actives()
        self.assertEqual(sorted(reg.data["runs"][x["run_id"]]["task"] for x in acts), ["T3", "T6"])
        runs = [reg.data["runs"][x["run_id"]] for x in acts]
        self.assertEqual({r["stage"] for r in runs}, {"3"})
        self.assertEqual({r["parent"] for r in runs}, {self.s1})
        t6 = [x["run_id"] for x in acts if reg.data["runs"][x["run_id"]]["task"] == "T6"][0]
        self.assertEqual(reg.data["runs"][t6]["name"], "MIRA")
        self.assertIn("RUN 1 of 2  T6 (new task)", out)
        self.assertIn("RUN 2 of 2  T3 (same task as stage 1)", out)
        self.assertIn("name on T6: MIRA", out)
        for x in acts:
            self.assertIn("python workshop.py done " + x["run_id"], out)
        with self.assertRaises(SystemExit):
            run(self.w, "new", "s3", "--task", "both")

    def test_name_from_alias_without_question(self):
        reg = self.w.Registry.load()
        reg.data["alias"] = "muad'dib"
        reg.save()
        self.w.ask = lambda *a, **k: self.fail("must not ask")
        out = capture(run, self.w, "new", "s3", "--task", "both")
        self.assertIn("name on T6: MUADDIB", out)
        self.assertIn("(change: --name OTHER)", out)
        reg = self.w.Registry.load()
        t6 = [x["run_id"] for x in reg.actives() if reg.data["runs"][x["run_id"]]["task"] == "T6"][0]
        self.assertEqual(reg.data["runs"][t6]["name"], "MUADDIB")

    def test_compact_output_codex_and_next_box(self):
        out = capture(run, self.w, "new", "s3", "--task", "both", "--name", "MIRA")
        self.assertIn("model gpt-6-luna", out)
        self.assertNotIn("Haiku", out)
        self.assertNotIn("Cursor", out)
        self.assertEqual(out.count("new thread"), 1)
        self.assertIn("NEXT:", out)
        self.assertNotIn("(change: --name OTHER)", out)

    def test_both_keeps_t6_when_t3_fails(self):
        orig = self.w.make_run_folder
        def boom(reg, rid, task, *a, **k):
            if task == "T3":
                raise RuntimeError("disk full")
            return orig(reg, rid, task, *a, **k)
        self.w.make_run_folder = boom
        try:
            capture(run, self.w, "new", "s3", "--task", "both", "--name", "MIRA")
        finally:
            self.w.make_run_folder = orig
        reg = self.w.Registry.load()
        self.assertEqual([reg.data["runs"][x["run_id"]]["task"] for x in reg.actives()], ["T6"])
        self.assertEqual(len([r for r in reg.data["runs"].values() if r["stage"] == "3"]), 1)

    def test_run_id_names_the_parent(self):
        rid, _ = self._new("T6", "--name", "mira")
        self.assertRegex(rid, r"^s3-%s-t6-[0-9a-f]{4}$" % self.s1[3:])

    def test_two_active_and_done_selection(self):
        t6, out6 = self._new("T6", "--name", "mira")
        self.assertIn("python workshop.py new s3 --task T3", out6)          # hint: start the second run
        self.assertIn("python workshop.py done " + t6, out6)
        t3, _ = self._new("T3")
        reg = self.w.Registry.load()
        self.assertEqual([x["run_id"] for x in reg.actives()], [t6, t3])
        with self.assertRaises(SystemExit):                     # one run per stage-3 task
            run(self.w, "new", "s3", "--task", "T3")
        with self.assertRaises(SystemExit):                     # no stage 1 while stage 3 runs
            run(self.w, "new", "s1")
        with self.assertRaises(SystemExit):                     # no stage 2 while stage 3 runs
            run(self.w, "skill")
        with self.assertRaises(SystemExit) as cm:               # two active, no TTY: name the run
            run(self.w, "done", "--no-form")
        self.assertIn("python workshop.py done " + t6, str(cm.exception.code))
        self.assertIn("python workshop.py done " + t3, str(cm.exception.code))
        out = capture(run, self.w, "done", t6, "--no-form")
        self.assertIn("python workshop.py done " + t3, out)       # NEXT box for the other agent
        reg = self.w.Registry.load()
        self.assertEqual(reg.row(t6, "3")["task"], "T6")
        self.assertEqual([x["run_id"] for x in reg.actives()], [t3])
        run(self.w, "done", "--no-form")                        # one left: no argument needed
        reg = self.w.Registry.load()
        self.assertEqual(reg.actives(), [])
        self.assertEqual(sorted(reg.data["rows"]),
                         sorted(["%s|1" % self.s1, "%s|2" % self.s1, "%s|3" % t6, "%s|3" % t3]))

    def test_done_run_id_updates_a_finished_stage(self):
        t6, _ = self._new("T6")
        run(self.w, "done", t6, "--no-form")
        run(self.w, "done", t6, "--no-form")
        self.assertEqual(int(self.w.Registry.load().row(t6, "3")["revision"]), 2)

    def test_done_unknown_run_id(self):
        with self.assertRaises(SystemExit):
            run(self.w, "done", "s3-zzzz-t6-0000", "--no-form")

    def test_show_and_compare(self):
        t6, _ = self._new("T6", "--name", "mira")
        t3, _ = self._new("T3")
        out = capture(run, self.w, "show")
        self.assertIn("Active: stage 3 of %s (T6). Next:  python workshop.py done %s" % (t6, t6), out)
        self.assertIn("Active: stage 3 of %s (T3)" % t3, out)
        run(self.w, "done", t6, "--no-form")
        run(self.w, "done", t3, "--no-form")
        out = capture(self.w.show_compare, self.w.Registry.load())
        self.assertEqual(out.count("YOUR RESULT"), 2)
        self.assertIn("different task: compare with the measured baseline", out)
        self.assertIn("0/12 pass in 5 min", out)


if __name__ == "__main__":
    unittest.main()
