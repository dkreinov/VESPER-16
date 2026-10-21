import os, sys, time, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fakes  # noqa: E402
from fakes import fresh_ws, run  # noqa: E402

SOL = "\n".join("LINE %d" % i for i in range(40))


class RegistryTest(unittest.TestCase):
    def setUp(self):
        self.w, self.tmp = fresh_ws()

    def test_rows_keyed_by_run_and_stage(self):
        r = self.w.Registry.load()
        r.set_row("s1-abcd", "1", {"score": "100"})
        r.set_row("s1-abcd", "2", {"score": ""})
        r.save()
        r2 = self.w.Registry.load()
        self.assertEqual(r2.row("s1-abcd", "1")["score"], "100")
        self.assertIsNotNone(r2.row("s1-abcd", "2"))
        r2.write_csv()
        with open(os.path.join(self.w.ws_home(), "results.csv"), encoding="utf-8") as f:
            self.assertEqual(len(f.read().strip().splitlines()), 3)

    def test_items_pending_then_done(self):
        r = self.w.Registry.load()
        p = os.path.join(self.w.ws_home(), "x")
        r.add_item(p, "dir")
        r.save()
        self.assertEqual(self.w.Registry.load().data["items"][0]["status"], "pending")
        r.mark_done(p)
        r.save()
        self.assertEqual(self.w.Registry.load().data["items"][0]["status"], "done")

    def test_home_refuses_onedrive(self):
        os.environ["VESPER_WS_HOME"] = r"C:\Users\x\OneDrive - Co\vesper-runs"
        with self.assertRaises(SystemExit):
            self.w.ws_home(check=True)


class PromptTest(unittest.TestCase):
    def setUp(self):
        self.w, _ = fresh_ws()

    def test_stage1_has_run_id_and_task(self):
        p = self.w.render_prompt("stage1", task="T4", run_id="s1-abcd")
        self.assertIn("Workshop run: s1-abcd", p)
        self.assertIn("tasks/T4.md", p)
        self.assertIn("solutions/T4.vsa", p)
        self.assertNotIn("{", p)

    def test_builtin_names_each_agents_creator(self):
        self.assertIn("$skill-creator", self.w.builtin_how("codex", "/g"))
        self.assertIn("skill-creator@claude-plugins-official", self.w.builtin_how("claude", "/g"))
        self.assertIn("/create-skill", self.w.builtin_how("cursor", "/g"))
        self.assertIn("/g/anthropic-skill-creator/SKILL.md", self.w.builtin_how("cursor", "/g"))

    def test_stage2_variants_exist_and_no_bundling_ban(self):
        for m in self.w.METHODS:
            p = self.w.render_prompt("stage2-" + m, run_id="s1-abcd", guide="/g",
                                     builtin_how=self.w.builtin_how("codex", "/g"))
            self.assertIn("skill-out/vesper16", p)
            self.assertNotIn("Do not include your finished", p)
            self.assertNotIn("{", p)


class DoctorTest(unittest.TestCase):
    def setUp(self):
        self.w, self.tmp = fresh_ws()

    def test_global_vesper_skill_found(self):
        d = os.path.join(os.environ["VESPER_WS_USERHOME"], ".agents", "skills", "vesper16")
        os.makedirs(d)
        with open(os.path.join(d, "SKILL.md"), "w") as f:
            f.write("name: vesper16")
        self.assertEqual(self.w.find_global_vesper_skills(), [d])

    def test_doctor_green(self):
        self.assertEqual(run(self.w, "doctor", "--agent", "claude", "--alias", "t"), 0)
        self.assertEqual(self.w.Registry.load().data["agent"], "claude")


class NewTest(unittest.TestCase):
    def setUp(self):
        self.w, self.tmp = fresh_ws()
        run(self.w, "doctor", "--agent", "claude", "--alias", "")

    def test_new_s1_clean_folder(self):
        run(self.w, "new", "s1", "--method", "plain")
        reg = self.w.Registry.load()
        rid = reg.data["active"]["run_id"]
        f = reg.data["runs"][rid]["folder"]
        names = sorted(os.listdir(f))
        for n in ["bin", "examples", "tasks", "player.html", "AGENTS.md", "CLAUDE.md", ".git",
                  ".vesper-runs.log", "solutions"]:
            self.assertIn(n, names)
        for n in ["locked", "unlocked", "measure.py", "workshop.py", "prompts", "guides"]:
            self.assertNotIn(n, names)
        self.assertEqual(os.listdir(os.path.join(f, "tasks")), ["T3.md"])
        # only this system's binary (Git Bash treats bin/vesper and bin/vesper.exe as one file)
        self.assertEqual(os.listdir(os.path.join(f, "bin")), ["vesper.exe" if os.name == "nt" else "vesper"])
        with open(os.path.join(f, "AGENTS.md")) as fh:
            self.assertIn(rid, fh.read())
        self.assertEqual(reg.data["runs"][rid]["method"], "plain")

    def test_new_while_active_refuses(self):
        run(self.w, "new", "s1")
        with self.assertRaises(SystemExit):
            run(self.w, "new", "s1")


class MeasureTest(unittest.TestCase):
    def setUp(self):
        self.w, self.tmp = fresh_ws()

    def test_codex_by_run_code_with_baseline(self):
        t = time.time()
        fakes.codex_log("01a0aaaa-0000-1111-2222-333344445555", "/x", [
            (t - 100, 1000, 0, 10, "Workshop run: s1-abcd"),
            (t - 50, 5000, 3000, 60, ""),
            (t - 10, 9000, 6000, 110, "")])
        fakes.codex_log("02b0bbbb-0000-1111-2222-333344445555", "/y", [(t - 50, 777, 0, 7, "other")])
        s = self.w.find_sessions("s1-abcd")
        self.assertEqual([x["sid"] for x in s], ["01a0aaaa-0000-1111-2222-333344445555"])
        m = self.w.measure_stage({"session": s[0], "folder": self.tmp}, t - 60, t)
        self.assertEqual(m["tok_out"], 100)
        self.assertEqual(m["tok_cache_read"], 6000)
        self.assertEqual(m["tok_uncached"], 2000)
        self.assertEqual(m["model"], "gpt-6.1-sol")
        self.assertNotEqual(m["cost_usd"], "")

    def test_claude_by_run_code(self):
        t = time.time()
        fakes.claude_log("aaaa-bbbb", "/x", [(t - 30, 5, 100, 50, 20, "Workshop run: s3-beef"),
                                             (t - 10, 5, 200, 0, 30, "")])
        s = self.w.find_sessions("s3-beef")
        self.assertEqual(s[0]["agent"], "claude")
        m = self.w.measure_stage({"session": s[0], "folder": self.tmp}, t - 60, t)
        self.assertEqual(m["tok_cache_read"], 300)
        self.assertEqual(m["measurement"], "log, output lower bound")

    def test_count_runs_by_event_time(self):
        t = int(time.time())
        with open(os.path.join(self.tmp, ".vesper-runs.log"), "w") as fh:
            fh.write("%d run a.vsa\n%d asm a.vsa\n%d run a.vsa\n%d run a.vsa\n" % (t - 100, t - 5, t - 4, t + 100))
        self.assertEqual(self.w.count_runs(self.tmp, t - 10, t), 1)
        self.assertIsNone(self.w.count_runs(os.path.join(self.tmp, "missing"), t - 10, t))


class FlowTest(unittest.TestCase):
    """Full stage 1 -> 2 -> 3 flow with fake agent logs (no real agent)."""

    def setUp(self):
        self.w, self.tmp = fresh_ws()
        run(self.w, "doctor", "--agent", "codex", "--alias", "t")
        run(self.w, "new", "s1", "--method", "plain")
        reg = self.w.Registry.load()
        self.rid = reg.data["active"]["run_id"]
        self.f = reg.data["runs"][self.rid]["folder"]

    def _solve(self, folder, text=SOL):
        with open(os.path.join(folder, "solutions", "T3.vsa"), "w") as f:
            f.write(text)

    def test_done_freezes_and_revises(self):
        self._solve(self.f)
        run(self.w, "done", "--no-form")
        r1 = self.w.Registry.load().row(self.rid, "1")
        self.assertEqual(r1["grading"], "ungraded")
        self.assertEqual(r1["measurement"], "none")
        self._solve(self.f, "changed")
        run(self.w, "done", "--no-form")
        r2 = self.w.Registry.load().row(self.rid, "1")
        self.assertEqual(r2["cutoff"], r1["cutoff"])
        self.assertEqual(r2["solution_sha"], r1["solution_sha"])
        self.assertEqual(int(r2["revision"]), 2)

    def test_full_flow(self):
        t0 = self.w.Registry.load().data["active"]["start"]      # events must be inside the stage window
        time.sleep(0.05)
        fakes.codex_log("0c0d0e0f-0000-1111-2222-333344445555", self.f,
                        [(t0 + 0.01, 10, 0, 1, "Workshop run: %s" % self.rid), (t0 + 0.02, 2000, 1000, 50, "")])
        self._solve(self.f)
        run(self.w, "done", "--no-form")
        r1 = self.w.Registry.load().row(self.rid, "1")
        self.assertEqual(r1["measurement"], "log")
        self.assertEqual(run(self.w, "form", "--no-form"), 0)          # reopen the form for the last stage
        with self.assertRaises(SystemExit):
            run(self.w, "form", self.rid, "3", "--no-form")
        with self.assertRaises(SystemExit):             # harvest before skill
            run(self.w, "harvest", "--no-form")
        with self.assertRaises(SystemExit):             # stage 3 before harvest
            run(self.w, "new", "s3", "--skill", "own")
        run(self.w, "skill")
        start = self.w.Registry.load().data["active"]["start"]
        run(self.w, "skill")                            # again: prints the prompt, keeps the clock
        self.assertEqual(self.w.Registry.load().data["active"]["start"], start)
        with self.assertRaises(SystemExit):             # SKILL.md missing -> no state change
            run(self.w, "harvest", "--no-form")
        self.assertEqual(self.w.Registry.load().data["active"]["stage"], "2")
        sk = os.path.join(self.f, "skill-out", "vesper16")
        os.makedirs(sk)
        with open(os.path.join(sk, "SKILL.md"), "w") as f:
            f.write("---\nname: vesper16\ndescription: x\n---\nhi\n")
        with open(os.path.join(sk, "game.vsa"), "w") as f:
            f.write(SOL)
        run(self.w, "harvest", "--no-form", "--move-aside")
        reg = self.w.Registry.load()
        self.assertEqual(reg.data["runs"][self.rid]["skill_has_solution"], "removed")
        self.assertEqual(reg.row(self.rid, "2")["grading"], "none")
        self.assertEqual(reg.row(self.rid, "2")["skill_has_solution"], "removed")
        self.assertFalse(os.path.exists(
            os.path.join(self.w.ws_home(), ".skills", self.rid, "vesper16", "game.vsa")))
        with self.assertRaises(SystemExit) as cm:               # harvest again -> points to form
            run(self.w, "harvest", "--no-form")
        self.assertIn("workshop.py form", str(cm.exception.code))
        run(self.w, "new", "s3", "--skill", "own")
        reg = self.w.Registry.load()
        s3 = reg.data["active"]["run_id"]
        f3 = reg.data["runs"][s3]["folder"]
        for sub in (".agents", ".claude"):
            self.assertTrue(os.path.exists(os.path.join(f3, sub, "skills", "vesper16", "SKILL.md")))
            self.assertFalse(os.path.exists(os.path.join(f3, sub, "skills", "vesper16", "game.vsa")))
        self.assertEqual(reg.data["runs"][s3]["parent"], self.rid)
        self.assertEqual(reg.data["runs"][s3]["skill_hash"], reg.data["runs"][self.rid]["skill_hash"])
        self._solve(f3)
        run(self.w, "done", "--no-form")
        self.assertEqual(len(self.w.Registry.load().data["rows"]), 3)
        import contextlib, io
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.w.show_compare(self.w.Registry.load())
        self.assertIn("No control runs", out.getvalue())
        self.assertNotIn("Cost (USD)", out.getvalue())

    def test_detector_share_helper_vs_game(self):
        snap = os.path.join(self.tmp, "sol.vsa")
        with open(snap, "w") as f:
            f.write(SOL)
        sk = os.path.join(self.tmp, "sk")
        os.makedirs(sk)
        with open(os.path.join(sk, "probe.vsa"), "w") as f:
            f.write("\n".join(SOL.splitlines()[:5]))
        found, share = self.w.detect_solution(sk, snap)
        self.assertEqual(len(found), 1)
        self.assertLess(share, self.w.GAME_SHARE)        # a helper, not the game
        with open(os.path.join(sk, "game.md"), "w") as f:
            f.write("```\n" + SOL + "\n```\n")
        found, share = self.w.detect_solution(sk, snap)
        self.assertEqual(share, 1.0)

    def test_cleanup_removes_only_own_items(self):
        mine = os.path.join(self.tmp, "keep.txt")
        with open(mine, "w") as f:
            f.write("x")
        run(self.w, "cleanup", "--yes", "--no-copy")
        self.assertFalse(os.path.exists(self.w.ws_home()))
        self.assertTrue(os.path.exists(mine))

    def test_unlock_wrong_password(self):
        with self.assertRaises(SystemExit):
            run(self.w, "unlock", "4", "wrong")

    def test_form_link(self):
        cfg = {"form_url": "https://forms.office.com/r/x?id=1", "fields": {"alias": "r1"}, "all_results_field": "r9"}
        link = self.w.form_link([{"alias": "t", "run_id": "q"}], cfg)
        self.assertTrue(link.startswith("https://forms.office.com/r/x?id=1&r1=t&r9=vesper-results+v1"))


if __name__ == "__main__":
    unittest.main()
