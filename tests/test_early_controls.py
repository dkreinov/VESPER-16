"""Early controls: `python workshop.py new small` makes the two no-skill runs (T3, T6; small model) during stage 1.
They are stage-3 registry runs (skill_source none, parent = the stage-1 run, early=True). Before stage 3 no learner
text names them "without the skill"; `new s3 --task all` then makes only the missing runs (normally t3 and t6)."""
import contextlib, io, os, re, sys, unittest
from unittest import mock
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fakes  # noqa: E402
from fakes import fresh_ws, run, flat, install_fake_grader  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
FAKE = os.path.join(HERE, "fake_agent.py")
AGENTS = ("codex", "cursor", "claude", "copilot")
# words that must not be on a learner screen before stage 3 (owner, 2026-11-17)
BANNED = re.compile(r"without|control|NO_SKILL|benchmark|no skill|unlock|grade|submit|play T", re.I)


def capture(w, *argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = run(w, *argv)
    return out.getvalue(), rc


def exit_text(w, *argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        try:
            run(w, *argv)
        except SystemExit as e:
            return out.getvalue() + "\n" + str(e.code)
    raise AssertionError("no exit: %s" % (argv,))


class Base(unittest.TestCase):
    def setUp(self):
        self.w, self.home = fresh_ws()
        install_fake_grader(self.w)      # the grader is here: before stage 3 the kit must still not say grade

    def s1(self, task="T3"):
        run(self.w, "doctor", "--agent", "codex", "--alias", "mira")
        capture(self.w, "new", "s1", "--method", "plain", "--task", task)
        return self.w.Registry.load().data["active"]["run_id"]

    def small(self, *extra):
        return capture(self.w, "new", "small", *extra)

    def early(self):
        reg = self.w.Registry.load()
        return {r["run_id"] if "run_id" in r else k: r for k, r in reg.data["runs"].items() if r.get("early")}

    def by_key(self, runs=None):
        reg = self.w.Registry.load()
        out = {}
        for k, r in reg.data["runs"].items():
            if r.get("stage") == "3" and not r.get("abandoned"):
                out.setdefault(k.split("-")[2], []).append(k)
        return out

    def assertClean(self, text):
        bad = [ln for ln in text.splitlines() if BANNED.search(ln)]
        self.assertEqual(bad, [], "words of stage 3 before stage 3:\n" + "\n".join(bad))

    def finish_s1(self, rid):
        return capture(self.w, "done", rid, "--no-form")

    def write_skill(self, rid):
        reg = self.w.Registry.load()
        sk = os.path.join(reg.data["runs"][rid]["folder"], "skill-out", "vesper16")
        os.makedirs(sk, exist_ok=True)
        with open(os.path.join(sk, "SKILL.md"), "w") as fh:
            fh.write("---\nname: vesper16\ndescription: VESPER-16 games\n---\nUse bin/vesper.\n")


class NewSmall(Base):
    def test_needs_a_stage_1_run(self):
        run(self.w, "doctor", "--agent", "codex", "--alias", "mira")
        t = exit_text(self.w, "new", "small")
        self.assertIn("Start stage 1 first:  python workshop.py new s1", t)
        self.assertEqual(self.early(), {})

    def test_makes_two_early_runs_during_stage_1(self):
        s1 = self.s1()
        out, rc = self.small()
        self.assertEqual(rc, 0)
        reg = self.w.Registry.load()
        runs = self.early()
        self.assertEqual(sorted(k.split("-")[2] for k in runs), ["n3", "n6"])
        for rid, r in runs.items():
            self.assertEqual((r["stage"], r["skill_source"], r["method"], r["parent"]), ("3", "none", "none", s1))
            self.assertTrue(r["early"])
            self.assertTrue(rid.startswith("s3-" + s1.split("-")[1] + "-"))
            for sub in (".agents", ".claude", ".cursor"):
                self.assertFalse(os.path.exists(os.path.join(r["folder"], sub)))
            self.assertTrue(reg.get_active(rid))
        n6 = [r for k, r in runs.items() if "-n6-" in k][0]
        self.assertEqual(n6["name"], "MIRA")
        self.assertEqual(reg.data["runs"][s1]["t6_name"], "MIRA")
        self.assertTrue(reg.get_active(s1))                      # stage 1 goes on
        self.assertIn("python workshop.py done " + s1, out)      # the stage-1 line is in the NEXT box
        for rid in runs:
            self.assertIn("python workshop.py done " + rid, out)
        self.assertIn("SMALL RUN 1 of 2   T3", out)
        self.assertIn("SMALL RUN 2 of 2   T6   name on T6: MIRA", flat(out))
        self.assertClean(out)

    def test_stage_1_next_box_offers_the_small_runs(self):
        run(self.w, "doctor", "--agent", "codex", "--alias", "mira")
        out, _ = capture(self.w, "new", "s1", "--method", "plain")
        self.assertIn("While the agent works, start 2 small runs (small model, 10 min each):", flat(out))
        self.assertIn("python workshop.py new small", out)
        self.assertClean(out)

    def test_no_small_line_for_t4(self):
        run(self.w, "doctor", "--agent", "codex", "--alias", "mira")
        out, _ = capture(self.w, "new", "s1", "--method", "plain", "--task", "T4")
        self.assertNotIn("new small", out)

    def test_name_flag_and_the_name_question(self):
        self.s1()
        capture(self.w, "new", "small", "--name", "Zed")
        runs = self.early()
        self.assertEqual([r["name"] for k, r in runs.items() if "-n6-" in k], ["ZED"])

    def test_again_while_active_shows_the_pages_again(self):
        self.s1()
        self.small()
        before = set(self.early())
        out, rc = self.small()
        self.assertEqual(set(self.early()), before)
        self.assertIn("already set up", out)
        self.assertClean(out)

    def test_again_when_done_makes_nothing(self):
        s1 = self.s1()
        self.small()
        for rid in self.early():
            capture(self.w, "done", rid, "--no-form")
        before = set(self.early())
        out, rc = self.small()
        self.assertEqual(rc, 0)
        self.assertEqual(set(self.early()), before)
        self.assertIn("python workshop.py done " + s1, out)
        self.assertClean(out)

    def test_global_skill_check_runs(self):
        self.s1()
        g = os.path.join(os.environ["VESPER_WS_USERHOME"], ".claude", "skills", "vesper16")
        os.makedirs(g)
        with open(os.path.join(g, "SKILL.md"), "w") as fh:
            fh.write("x")
        t = exit_text(self.w, "new", "small")
        self.assertIn("A VESPER skill is in a global folder", t)
        self.assertEqual(self.early(), {})


class BeforeStage3(Base):
    def test_done_of_a_small_run_points_to_stage_1(self):
        s1 = self.s1()
        self.small()
        n3 = [k for k in self.early() if "-n3-" in k][0]
        out, _ = capture(self.w, "done", n3, "--no-form")
        self.assertIn("FINISHED  T3 small run", flat(out))
        self.assertIn("python workshop.py done " + s1, out)
        self.assertNotIn("all agents are done", out)
        self.assertClean(out)

    def test_last_small_run_done_after_stage_1_points_to_skill(self):
        s1 = self.s1()
        self.small()
        self.finish_s1(s1)
        ids = sorted(self.early())
        capture(self.w, "done", ids[0], "--no-form")
        out, _ = capture(self.w, "done", ids[1], "--no-form")
        self.assertIn("python workshop.py skill", out)
        self.assertNotIn("all agents are done", out)
        self.assertClean(out)

    def test_skill_is_not_blocked_and_lists_the_small_runs(self):
        s1 = self.s1()
        self.small()
        self.finish_s1(s1)
        out, rc = capture(self.w, "skill")
        self.assertEqual(rc, 0)
        self.assertTrue(self.w.Registry.load().actives("2"))
        for rid in self.early():
            self.assertIn("python workshop.py done " + rid, out)
        self.assertIn("SAME large model as stage 1", flat(out))
        self.assertClean(out.replace("writes a skill", "").replace("the skill is written", ""))

    def test_show_has_no_last_steps_before_stage_3(self):
        s1 = self.s1()
        self.small()
        self.finish_s1(s1)
        for rid in self.early():
            capture(self.w, "done", rid, "--no-form")
        out, _ = capture(self.w, "show")
        self.assertNotIn("all agents are done", out)
        self.assertIn("T3 small run", out)
        self.assertClean(out)

    def test_choose_active_names_stage_1(self):
        s1 = self.s1()
        self.small()
        t = exit_text(self.w, "done")
        self.assertIn("(stage 1)", t)
        self.assertIn("python workshop.py done " + s1, t)
        self.assertIn("3 runs are active:", t)
        self.assertClean(t)

    def test_new_s1_while_small_runs_work_names_them_small(self):
        s1 = self.s1()
        self.small()
        self.finish_s1(s1)
        t = exit_text(self.w, "new", "s1")
        self.assertIn("is still active", t)
        self.assertClean(t)


class Stage3(Base):
    def to_stage3(self, small=True, finish_small=True):
        s1 = self.s1()
        if small:
            self.small()
        self.finish_s1(s1)
        if small and finish_small:
            for rid in self.early():
                capture(self.w, "done", rid, "--no-form")
        capture(self.w, "skill")
        self.write_skill(s1)
        out, _ = capture(self.w, "harvest", "--no-form")
        return s1, out

    def test_harvest_box_counts_two_runs(self):
        s1, out = self.to_stage3()
        self.assertIn("2 new agents WITH the skill", flat(out))
        self.assertIn("you open 2 threads", flat(out))
        self.assertNotIn("FOUR", out)

    def test_all_makes_only_the_two_with_skill_runs(self):
        s1, _ = self.to_stage3()
        out, rc = capture(self.w, "new", "s3", "--task", "all", "--name", "OTHER")
        self.assertEqual(rc, 0)
        k = self.by_key()
        self.assertEqual(sorted(k), ["n3", "n6", "t3", "t6"])
        self.assertTrue(all(len(v) == 1 for v in k.values()))
        reg = self.w.Registry.load()
        self.assertEqual(reg.data["runs"][k["t6"][0]]["name"], "MIRA")      # the name of the early T6 run
        self.assertEqual(reg.data["runs"][k["t3"][0]]["parent"], s1)
        self.assertIn("Stage 3: 2 runs WITH the skill. The runs without the skill were done earlier.", flat(out))
        self.assertNotIn("RUN 1 of 4", out)

    def test_still_active_small_runs_do_not_block_and_are_listed(self):
        s1, _ = self.to_stage3(finish_small=False)
        out, rc = capture(self.w, "new", "s3", "--task", "all")
        self.assertEqual(rc, 0)
        k = self.by_key()
        self.assertEqual(sorted((x, len(v)) for x, v in k.items()), [("n3", 1), ("n6", 1), ("t3", 1), ("t6", 1)])
        for rid in self.early():
            self.assertIn("python workshop.py done " + rid, out)
        self.assertNotIn("already set up", out)

    def test_skipped_step_makes_all_four(self):
        s1, out = self.to_stage3(small=False)
        self.assertIn("FOUR new agents", out)
        out, rc = capture(self.w, "new", "s3", "--task", "all")
        self.assertEqual(sorted(self.by_key()), ["n3", "n6", "t3", "t6"])
        self.assertIn("RUN 1 of 4", out)

    def test_abandoned_or_failed_control_is_made_again(self):
        s1, _ = self.to_stage3()
        reg = self.w.Registry.load()
        ids = {k.split("-")[2]: k for k in self.early()}
        reg.data["runs"][ids["n6"]]["abandoned"] = True
        reg.data["rows"]["%s|3" % ids["n3"]]["stopped"] = "error"
        reg.save()
        out, rc = capture(self.w, "new", "s3", "--task", "all")
        k = self.by_key()
        self.assertEqual(len(k["t3"]), 1)
        self.assertEqual(len(k["t6"]), 1)
        self.assertEqual(len([x for x in k["n6"] if x != ids["n6"]]), 1)
        self.assertEqual(len([x for x in k["n3"] if x != ids["n3"]]), 1)

    def test_auto_makes_only_the_missing_runs(self):
        s1, _ = self.to_stage3()
        seen = []

        def fake_setup(reg, a):
            a.auto_agent, a.auto_argv, a.auto_model, a.auto_verified = "codex", ["x"], "gpt-6-luna", False
        with mock.patch.object(self.w, "auto_setup", side_effect=fake_setup), \
                mock.patch.object(self.w, "run_auto", side_effect=lambda reg, a, items: seen.extend(items) or 0):
            out, rc = capture(self.w, "new", "s3", "--task", "all", "--auto", "--yes")
        self.assertEqual(sorted(it["key"] for it in seen), ["t3", "t6"])
        self.assertIn("the 2 agents", out)

    def test_wiki_skill_takes_the_parent_of_the_early_runs(self):
        s1, _ = self.to_stage3()
        d = os.path.join(self.w.ws_home(), ".prebuilt", "skills", "M4-distill")
        os.makedirs(d)
        with open(os.path.join(d, "SKILL.md"), "w") as fh:
            fh.write("---\nname: vesper16\ndescription: x\n---\nwiki\n")
        out, rc = capture(self.w, "new", "s3", "--task", "all", "--skill", "wiki")
        reg = self.w.Registry.load()
        made = [r for r in reg.data["runs"].values() if r.get("stage") == "3" and not r.get("early")]
        self.assertEqual(len(made), 2)
        self.assertEqual({r["parent"] for r in made}, {s1})
        self.assertEqual({r["skill_source"] for r in made}, {"wiki"})

    def test_repeat_attempt_counts_two_runs(self):
        s1, _ = self.to_stage3()
        capture(self.w, "new", "s3", "--task", "all")
        reg = self.w.Registry.load()
        for x in reg.actives("3"):
            capture(self.w, "done", x["run_id"], "--no-form")
        out, rc = capture(self.w, "new", "s3", "--task", "all")
        self.assertIn("A repeat attempt (2 new runs)", flat(out))
        out, rc = capture(self.w, "new", "s3", "--task", "all", "--yes")
        k = self.by_key()
        self.assertEqual((len(k["t3"]), len(k["n3"])), (2, 1))

    def test_from_stage_3_on_the_early_runs_are_named_without_the_skill(self):
        s1, _ = self.to_stage3()
        capture(self.w, "new", "s3", "--task", "all")
        reg = self.w.Registry.load()
        for x in reg.actives("3"):
            capture(self.w, "done", x["run_id"], "--no-form")
        out, _ = capture(self.w, "show")
        self.assertIn("T3, no skill", out)
        self.assertIn("WITH vs WITHOUT the skill", out)
        self.assertIn("all agents are done", out)


class Restart(Base):
    def test_small_restart_abandons_only_the_small_runs(self):
        s1 = self.s1()
        self.small()
        old = set(self.early())
        out, rc = self.small("--restart")
        reg = self.w.Registry.load()
        self.assertTrue(reg.get_active(s1))
        for rid in old:
            self.assertTrue(reg.data["runs"][rid]["abandoned"])
            self.assertFalse(reg.get_active(rid))
        new = set(self.early()) - old
        self.assertEqual(sorted(k.split("-")[2] for k in new), ["n3", "n6"])

    def test_s1_restart_abandons_the_small_runs_too(self):
        s1 = self.s1()
        self.small()
        capture(self.w, "new", "s1", "--restart")
        reg = self.w.Registry.load()
        for rid in self.early():
            self.assertTrue(reg.data["runs"][rid]["abandoned"])
        self.assertTrue(reg.data["runs"][s1]["abandoned"])

    def test_s3_restart_keeps_the_small_runs(self):
        s1 = self.s1()
        self.small()
        self.finish_s1(s1)
        capture(self.w, "skill")
        self.write_skill(s1)
        capture(self.w, "harvest", "--no-form")
        capture(self.w, "new", "s3", "--task", "all")
        capture(self.w, "new", "s3", "--task", "all", "--restart")
        reg = self.w.Registry.load()
        for rid in self.early():
            self.assertFalse(reg.data["runs"][rid].get("abandoned"))
            self.assertTrue(reg.get_active(rid))


class Semi(Base):
    def setUp(self):
        super().setUp()
        self.log = os.path.join(self.home, "dry.jsonl")
        fake = os.path.join(self.home, "fakeapp.cmd")
        open(fake, "w").close()
        os.environ["VESPER_LAUNCHER_DRYRUN"] = self.log
        for a in AGENTS:
            os.environ["VESPER_LAUNCHER_" + a.upper()] = fake
        self.addCleanup(self.off)

    def off(self):
        os.environ.pop("VESPER_LAUNCHER_DRYRUN", None)
        for a in AGENTS:
            os.environ["VESPER_LAUNCHER_" + a.upper()] = "none"

    def test_semi_pages_folder_labels_and_next(self):
        s1 = self.s1()
        out, rc = self.small()
        self.assertEqual(rc, 0)
        labels = sorted(os.path.basename(r["folder"]).split("__")[0] for r in self.early().values())
        self.assertEqual(labels, ["T3_LUNA", "T6_LUNA"])
        self.assertIn("SMALL RUN 1 of 2   T3", out)
        self.assertIn("SMALL RUN 2 of 2   T6   name on T6: MIRA", flat(out))
        self.assertIn("python workshop.py new small --mode manual", out)
        self.assertIn("python workshop.py done " + s1, out)
        self.assertClean(out)

    def test_semi_list_end_points_to_stage_1(self):
        s1 = self.s1()
        nums = iter(["1", "2"])

        def fake_ask(q, d=""):
            if "Type the NUMBER" in q:
                return next(nums, "q")
            return "y" if "Did you stop" in q else d
        with mock.patch.object(self.w, "interactive", return_value=True), \
                mock.patch.object(self.w, "ask", side_effect=fake_ask):
            out, rc = self.small()
        self.assertIn("All 2 runs are ENDED.", out)
        tail = out.split("All 2 runs are ENDED.")[1]
        self.assertIn("python workshop.py done " + s1, tail)
        self.assertClean(out)


class Auto(Base):
    ENV = ("VESPER_CODEX_EXE", "FAKE_SLEEP", "LOCALAPPDATA")

    def setUp(self):
        super().setUp()
        self.saved = {k: os.environ.get(k) for k in self.ENV}
        os.environ["LOCALAPPDATA"] = os.path.join(self.home, "localappdata")
        os.environ["VESPER_CODEX_EXE"] = FAKE
        os.environ["FAKE_SLEEP"] = "0.2"
        self.w.AUTO_TICK, self.w.AUTO_POLL, self.w.AUTO_BOX_SEC, self.w.AUTO_MIN_SEC = 0.3, 0.05, 30, 0
        self.addCleanup(self.restore)

    def restore(self):
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_new_small_auto_runs_the_two(self):
        s1 = self.s1()
        out, rc = self.small("--auto", "--yes")
        self.assertEqual(rc, 0)
        reg = self.w.Registry.load()
        rows = [r for r in reg.data["rows"].values() if r["stage"] == "3"]
        self.assertEqual(len(rows), 2)
        self.assertEqual(reg.actives("3"), [])
        self.assertIn("T3 small run", out)
        self.assertIn("python workshop.py done " + s1, out)
        self.assertClean(out)


if __name__ == "__main__":
    unittest.main()
