"""Effort per row, pay-back rule, control run (--task all), charts n3 tag."""
import contextlib, io, json, os, sys, time, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fakes  # noqa: E402
from fakes import fresh_ws, run  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def capture(fn, *a):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        fn(*a)
    return out.getvalue()


class EffortTest(unittest.TestCase):
    def test_effort_from_last_turn_context_in_window(self):
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
            for dt, eff in ((0.001, "low"), (0.002, "high"), (0.003, "medium")):
                fh.write(json.dumps({"timestamp": fakes.iso(t0 + dt), "type": "turn_context",
                                     "payload": {"cwd": folder, "model": "gpt-6.1-sol", "effort": eff}}) + "\n")
        out = capture(run, w, "done", "--no-form")
        row = w.Registry.load().row(rid, "1")
        self.assertEqual(row["effort"], "medium")
        self.assertEqual(row["model"], "gpt-6.1-sol")
        self.assertIn("gpt-6.1-sol/medium", out)
        with open(os.path.join(w.ws_home(), "results.csv"), encoding="utf-8") as f:
            self.assertEqual(f.readline().strip().split(",")[-1], "effort")


class PayBackTest(unittest.TestCase):
    def _compare(self, s1, s3):
        w, _ = fresh_ws()
        reg = w.Registry.load()
        reg.data["runs"]["s1-aaaa"] = dict(folder="", task="T3", method="plain", stage="1", parent="")
        reg.data["runs"]["s3-aaaa-t3-bbbb"] = dict(folder="", task="T3", method="plain", stage="3", parent="s1-aaaa")
        reg.set_row("s1-aaaa", "1", dict(task="T3", cost_usd="1.00", score=s1, start="1"))
        reg.set_row("s1-aaaa", "2", dict(task="T3", cost_usd="0.20", elapsed_min="3", start="2"))
        reg.set_row("s3-aaaa-t3-bbbb", "3", dict(task="T3", cost_usd="0.10", score=s3, start="3"))
        return capture(w.show_compare, reg)

    def test_shown_when_not_lower(self):
        self.assertIn("pays for itself after 1 task", self._compare("100", "100"))

    def test_hidden_when_lower(self):
        out = self._compare("100", "40")
        self.assertNotIn("pays for itself", out)
        self.assertIn("The skill run scored lower (40 vs 100): no saving is counted.", out)

    def test_hidden_when_ungraded(self):
        out = self._compare("", "")
        self.assertNotIn("pays for itself", out)
        self.assertIn("Score not graded yet", out)


class TaskAllTest(unittest.TestCase):
    def setUp(self):
        self.w, _ = fresh_ws()
        self.s1, _ = fakes.ready_for_s3(self.w)

    def test_all_creates_three_runs(self):
        out = capture(run, self.w, "new", "s3", "--task", "all", "--name", "MIRA")
        reg = self.w.Registry.load()
        runs = {x["run_id"]: reg.data["runs"][x["run_id"]] for x in reg.actives()}
        self.assertEqual(len(runs), 3)
        self.assertEqual({r["parent"] for r in runs.values()}, {self.s1})
        t6 = [i for i, r in runs.items() if r["task"] == "T6"]
        n3 = [i for i, r in runs.items() if "-n3-" in i]
        t3 = [i for i, r in runs.items() if r["task"] == "T3" and "-t3-" in i]
        self.assertEqual((len(t6), len(n3), len(t3)), (1, 1, 1))
        ctl = runs[n3[0]]
        self.assertEqual((ctl["skill_source"], ctl["method"]), ("none", "none"))
        f = ctl["folder"]
        for sub in (".agents", ".claude", ".cursor"):
            self.assertFalse(os.path.exists(os.path.join(f, sub)))
        with open(os.path.join(f, "AGENTS.md"), encoding="utf-8") as fh:
            self.assertNotIn("Skills are in", fh.read())
        self.assertTrue(os.path.exists(os.path.join(runs[t3[0]]["folder"], ".agents", "skills", "vesper16", "SKILL.md")))
        for h in ("RUN 1 of 3  T3 WITH the skill",
                  "RUN 2 of 3  T3 WITHOUT the skill (control: stop it at 10 min)",
                  "RUN 3 of 3  T6 WITH the skill (bonus: a new task)",
                  "Time box 10 min: stop any agent still working at 10 min, then run its done line."):
            self.assertIn(h, out)
        for i in runs:
            self.assertIn("python workshop.py done " + i, out)
        # the control prompt: no skill sentences, same budget
        cp = out.split("PROMPT 2 ", 1)[1].split("END OF PROMPT 2", 1)[0]
        self.assertNotIn("vesper16 skill", cp)
        self.assertNotIn("SKILL NOT FOUND", cp)
        self.assertNotIn("Load the skill", cp)
        self.assertIn("You have 6 runs", cp)
        self.assertIn("Use the vesper16 skill", out)       # the other two prompts keep it

    def test_control_compare_block(self):
        capture(run, self.w, "new", "s3", "--task", "all", "--name", "MIRA")
        reg = self.w.Registry.load()
        ids = [x["run_id"] for x in reg.actives()]
        n3 = [i for i in ids if "-n3-" in i][0]
        t3 = [i for i in ids if "-t3-" in i][0]
        reg.set_row(t3, "3", dict(task="T3", cost_usd="0.10", score="100", start="3", method="plain"))
        reg.set_row(n3, "3", dict(task="T3", cost_usd="0.30", score="40", start="4", method="none"))
        out = capture(self.w.show_compare, reg, n3)
        self.assertIn("T3 WITH the skill vs T3 WITHOUT the skill (same model)", out)
        self.assertIn(t3, out)


class ChartsN3Test(unittest.TestCase):
    def test_n3_tag_is_control(self):
        import charts
        self.assertEqual(charts.parent_id("s3-aaaa-n3-1234"), "s1-aaaa")
        rows = [dict(run_id="s1-aaaa", stage="1", task="T3", alias="a", method="plain"),
                dict(run_id="s3-aaaa-t3-1111", stage="3", task="T3", method="plain"),
                dict(run_id="s3-aaaa-n3-2222", stage="3", task="T3", method="none")]
        g = charts.learners(rows)
        self.assertEqual(len(g), 1)
        self.assertEqual(g[0]["T3"]["run_id"], "s3-aaaa-t3-1111")
        self.assertEqual(g[0]["N3"]["run_id"], "s3-aaaa-n3-2222")


if __name__ == "__main__":
    unittest.main()
