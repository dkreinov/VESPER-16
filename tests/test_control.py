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
        time.sleep(0.1)       # the log events are at t0 + 20 ms; done must come after them (was flaky)
        out = capture(run, w, "done", "--no-form")
        row = w.Registry.load().row(rid, "1")
        self.assertEqual(row["effort"], "medium")
        self.assertEqual(row["model"], "gpt-6.1-sol")
        self.assertIn("gpt-6.1-sol/medium", out)
        with open(os.path.join(w.ws_home(), "results.csv"), encoding="utf-8") as f:
            self.assertIn("effort", f.readline().strip().split(","))


class PayBackTest(unittest.TestCase):
    def _compare(self, s1, s3):
        w, _ = fresh_ws()
        reg = w.Registry.load()
        reg.data["runs"]["s1-aaaa"] = dict(folder="", task="T3", method="plain", stage="1", parent="")
        reg.data["runs"]["s3-aaaa-t3-bbbb"] = dict(folder="", task="T3", method="plain", stage="3", parent="s1-aaaa")
        reg.data["runs"]["s3-aaaa-n3-cccc"] = dict(folder="", task="T3", method="none", stage="3", parent="s1-aaaa",
                                                   skill_source="none")
        reg.set_row("s1-aaaa", "1", dict(task="T3", cost_usd="1.00", score=s1, start="1"))
        reg.set_row("s1-aaaa", "2", dict(task="T3", cost_usd="0.20", elapsed_min="3", start="2"))
        reg.set_row("s3-aaaa-t3-bbbb", "3", dict(task="T3", cost_usd="0.10", score=s3, start="3"))
        reg.set_row("s3-aaaa-n3-cccc", "3", dict(task="T3", cost_usd="0.30", score="50" if s3 else "", start="4",
                                                 method="none"))
        return capture(w.show_compare, reg)

    def test_no_breakeven_number(self):
        out = self._compare("100", "100")
        self.assertNotIn("pays for itself", out)
        self.assertIn("Skill creation: 3.0 min, $0.20 estimated. Break-even not established.", out)
        self.assertIn("Estimated cost under the kit's price assumptions.", out)

    def test_same_line_when_lower(self):
        out = self._compare("100", "40")
        self.assertNotIn("pays for itself", out)
        self.assertNotIn("no saving is counted", out)
        self.assertIn("Break-even not established.", out)

    def test_payback_unknown_values(self):
        w, _ = fresh_ws()
        reg = w.Registry.load()
        out = capture(w.payback, reg, {}, {"elapsed_min": "", "cost_usd": ""}, {})
        self.assertIn("  Skill creation: unknown min, unknown estimated. Break-even not established.", out)
        out = capture(w.payback, reg, {}, {"elapsed_min": "2.5", "cost_usd": "0.5"}, {})
        self.assertIn("  Skill creation: 2.5 min, $0.50 estimated. Break-even not established.", out)

    def test_hidden_when_ungraded(self):
        out = self._compare("", "")
        self.assertNotIn("pays for itself", out)
        self.assertIn("Score not graded yet", out)
        self.assertNotIn("YOUR RESULT", out)


class TaskAllTest(unittest.TestCase):
    def setUp(self):
        self.w, _ = fresh_ws()
        self.s1, _ = fakes.ready_for_s3(self.w)

    def test_all_creates_four_runs(self):
        out = capture(run, self.w, "new", "s3", "--task", "all", "--name", "MIRA")
        reg = self.w.Registry.load()
        runs = {x["run_id"]: reg.data["runs"][x["run_id"]] for x in reg.actives()}
        self.assertEqual(len(runs), 4)
        self.assertEqual({r["parent"] for r in runs.values()}, {self.s1})
        by = {}
        for i, r in runs.items():
            by[i.split("-")[2]] = (i, r)
        self.assertEqual(sorted(by), ["n3", "n6", "t3", "t6"])
        for k in ("n3", "n6"):
            ctl = by[k][1]
            self.assertEqual((ctl["skill_source"], ctl["method"]), ("none", "none"))
            f = ctl["folder"]
            for sub in (".agents", ".claude", ".cursor"):
                self.assertFalse(os.path.exists(os.path.join(f, sub)))
            with open(os.path.join(f, "AGENTS.md"), encoding="utf-8") as fh:
                self.assertNotIn("Skills are in", fh.read())
        for k in ("t3", "t6"):
            self.assertTrue(os.path.exists(os.path.join(by[k][1]["folder"], ".agents", "skills", "vesper16", "SKILL.md")))
        self.assertEqual(by["n6"][1]["task"], "T6")
        with open(os.path.join(by["n6"][1]["folder"], "tasks", "T6.md"), encoding="utf-8") as fh:
            self.assertIn("MIRA", fh.read())
        keys = self.w.start_order_keys(self.s1)        # pages follow the randomised start order (seed = stage-1 run)
        for i, k in enumerate(keys, 1):
            self.assertIn("RUN %d of 4  %s" % (i, self.w.ALL_DESC[k]), out)
        self.assertIn("RUN %d of 4  T6 WITH the skill (a different task that shares components with T3)"
                      % (keys.index("t6") + 1), out)
        self.assertNotIn("real test", out)
        self.assertIn("Time box 10 min: stop any agent still working at 10 min, then run its done line.", out)
        self.assertLess(out.index("Start in this order"), out.index("RUN 1 of 4"))
        for i in runs:
            self.assertIn("python workshop.py done " + i, out)
        for n in (str(keys.index("n3") + 1), str(keys.index("n6") + 1)):   # the control prompts: no skill sentences
            cp = out.split("PROMPT %s " % n, 1)[1].split("END OF PROMPT %s" % n, 1)[0]
            self.assertNotIn("vesper16 skill", cp)
            self.assertNotIn("SKILL NOT FOUND", cp)
            self.assertNotIn("Load the skill", cp)
            self.assertIn("You have 6 runs", cp)
        self.assertIn("Use the vesper16 skill", out)       # the other two prompts keep it

    def _graded(self, t3, n3, t6, n6, tm=(2, 5, 3, 6)):
        capture(run, self.w, "new", "s3", "--task", "all", "--name", "MIRA")
        reg = self.w.Registry.load()
        ids = {x["run_id"].split("-")[2]: x["run_id"] for x in reg.actives()}
        for k, sc, m, t in zip(("t3", "n3", "t6", "n6"), (t3, n3, t6, n6), ("plain", "none", "plain", "none"), tm):
            reg.set_row(ids[k], "3", dict(task=k.upper().replace("N", "T"), cost_usd="0.10", score=sc,
                                          elapsed_min=str(t), start=str(3 + len(k) + int(k[1])), method=m))
        return reg, ids

    def test_control_compare_blocks_and_leakage(self):
        reg, ids = self._graded("100", "40", "90", "50")
        out = capture(self.w.show_compare, reg, ids["n3"])
        self.assertIn("T3: WITH vs WITHOUT the skill", out)
        out = capture(self.w.show_compare, reg)
        self.assertIn("T6: WITH vs WITHOUT the skill - different task; shares components with T3", out)
        self.assertNotIn("YOUR RESULT", out)
        self.assertIn("  Leakage check: Observed score gains: T3 +60; T6 +40. "
                      "These results neither identify nor rule out answer reuse.", out)
        self.assertNotIn("much larger", out)
        self.assertEqual(out.count("Leakage check"), 1)

    def test_failed_control_no_change_column_and_score_only_gains(self):
        reg, ids = self._graded("85", "10", "70", "5", tm=(3, 0.8, 4, 0.5))
        out = capture(self.w.show_compare, reg)
        self.assertIn("At least one attempt failed. Costs describe attempts, not equal-quality savings.", out)
        self.assertNotIn("Control failed", out)
        self.assertIn("85 FAIL", out)
        self.assertIn("10 FAIL", out)
        self.assertNotIn("%", out.split("Leakage check")[0].split("Time (min)")[1].split("\n")[0])
        self.assertIn("Observed score gains: T3 +75; T6 +65.", out)
        self.assertEqual(out.count("Leakage check"), 1)

    def _concl(self, scores):
        reg, ids = self._graded(*scores)
        return capture(self.w.show_compare, reg)

    def test_conclusion_similar_with_time_when_controls_pass(self):
        out = self._concl(("100", "100", "100", "90"))
        self.assertNotIn("At least one attempt failed", out)
        self.assertIn("100 PASS", out)
        self.assertIn("T3 +0; T6 +10.", out)

    def test_leakage_gain_pairs(self):
        for (g3, g6), sc in (((0, 0), ("100", "100", "95", "95")), ((90, 85), ("100", "10", "95", "10")),
                             ((75, 10), ("100", "25", "95", "85"))):
            reg, ids = self._graded(*sc)
            line = self.w.leakage_line(reg, reg.data["runs"][ids["t3"]]["parent"])
            self.assertEqual(line, "  Leakage check: Observed score gains: T3 %+d; T6 %+d. "
                             "These results neither identify nor rule out answer reuse." % (g3, g6))
            self.assertNotIn("%", line)
            self.setUp()

    def test_observed_note_once_and_settings_differ(self):
        reg, ids = self._graded("100", "40", "90", "50")
        out = capture(self.w.show_compare, reg)
        self.assertEqual(out.count("Observed results: one attempt per condition. Check pass/fail before time or cost; reliability is unknown."), 1)
        self.assertEqual(out.count("Estimated cost under the kit's price assumptions."), 1)
        self.assertEqual(out.count("Settings differ: this is not a matched comparison."), 2)
        self.assertNotIn("(same model)", out)
        self.assertIn("100 PASS", out)
        self.assertIn("40 FAIL", out)

    def test_same_model_needs_same_effort(self):
        reg, ids = self._graded("100", "100", "95", "95")
        for r in reg.data["rows"].values():
            r["model"], r["effort"] = "m1", "high"
        out = capture(self.w.show_compare, reg)
        self.assertEqual(out.count("(same model)"), 2)
        self.assertNotIn("Settings differ", out)
        reg.data["rows"]["%s|3" % ids["n3"]]["effort"] = "low"
        out = capture(self.w.show_compare, reg)
        self.assertEqual(out.count("(same model)"), 1)
        self.assertEqual(out.count("Settings differ"), 1)
        reg.data["rows"]["%s|3" % ids["n3"]]["effort"] = ""         # empty effort = unknown = not the same
        reg.data["rows"]["%s|3" % ids["t3"]]["effort"] = ""
        out = capture(self.w.show_compare, reg)
        self.assertEqual(out.count("Settings differ"), 1)

    def test_passed_rule(self):
        p = self.w.passed
        self.assertTrue(p({"task": "T6", "score": "90"}))
        self.assertFalse(p({"task": "T6", "score": "89"}))
        self.assertTrue(p({"task": "T3", "score": "100"}))
        self.assertFalse(p({"task": "T3", "score": "95"}))
        self.assertFalse(p({"task": "T3", "score": ""}))

    def test_start_order_per_run_and_stable(self):
        self.assertEqual(self.w.start_order("s1-aaaa"), self.w.start_order("s1-aaaa"))
        seen = {tuple(self.w.start_order("s1-%04x" % i)) for i in range(40)}
        self.assertGreater(len(seen), 1)
        for o in seen:
            self.assertEqual(sorted(o), ["T3 with skill", "T3 without skill", "T6 with skill", "T6 without skill"])
            self.assertEqual(o[0][:2], "T3")
        out = capture(run, self.w, "new", "s3", "--task", "all", "--name", "MIRA")
        self.assertIn("  Start in this order: 1. ", out)
        self.assertIn(" 4. T6 ", out)

    def test_only_real_pairs_never_stage1_or_t3_vs_t6(self):
        reg, ids = self._graded("100", "40", "90", "50")
        reg.set_row("s1-x", "1", dict(task="T3", model="big", cost_usd="2.00", score="100", start="1"))
        out = capture(self.w.show_compare, reg)
        self.assertNotIn("YOUR RESULT", out)
        self.assertNotIn("no skill (stage 1", out)
        self.assertEqual(out.count("WITH vs WITHOUT the skill"), 2)
        self.assertNotIn("T3 vs T6", out)
        self.assertEqual(out.count("different task; shares components with T3"), 1)

    def test_waiting_line_for_incomplete_pair(self):
        reg, ids = self._graded("100", "40", "90", "50")
        for k in [k for k, r in reg.data["rows"].items() if r["run_id"] == ids["n6"]]:
            del reg.data["rows"][k]
        out = capture(self.w.show_compare, reg)
        self.assertIn("T6: waiting for its control run (T6 without skill)", out)
        self.assertIn("T3: WITH vs WITHOUT the skill", out)
        self.assertNotIn("T6: WITH vs WITHOUT", out)
        self.assertNotIn("Leakage check", out)

    def test_no_leakage_line_when_t6_ungraded(self):
        reg, ids = self._graded("100", "40", "", "")
        out = capture(self.w.show_compare, reg)
        self.assertNotIn("Leakage check", out)


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
