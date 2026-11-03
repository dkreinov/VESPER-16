"""Semi mode in workshop.py: --mode, the opener (dry run), the four stage-3 pages, the stop-time table,
folder names, memory lines, and the done lines. No real app starts: VESPER_LAUNCHER_DRYRUN logs the commands."""
import contextlib, io, json, os, re, sqlite3, sys, time, unittest
from unittest import mock
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fakes  # noqa: E402
from fakes import fresh_ws, run, flat, ready_for_s3, install_fake_grader  # noqa: E402

AGENTS = ("codex", "cursor", "claude", "copilot")


def capture(w, *argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = run(w, *argv)
    return out.getvalue(), rc


def answer_numbers():
    """A fake `ask` for the end of stage 3: the numbers 1-4 for the list, y for 'did you stop', else the default."""
    nums = iter(["1", "2", "3", "4"])

    def fake(q, d=""):
        if "Type the NUMBER" in q:
            return next(nums, "q")
        return "y" if "Did you stop" in q else d
    return fake


def argparse_ns():
    import argparse
    return argparse.Namespace(no_form=True)


class Base(unittest.TestCase):
    def setUp(self):
        self.w, self.home = fresh_ws()
        self.log = os.path.join(self.home, "dry.jsonl")
        self.fake = os.path.join(self.home, "fakeapp.cmd")
        open(self.fake, "w").close()
        self.enable(*AGENTS)
        self.addCleanup(self.disable)

    def enable(self, *agents):
        os.environ["VESPER_LAUNCHER_DRYRUN"] = self.log
        for a in agents:
            os.environ["VESPER_LAUNCHER_" + a.upper()] = self.fake

    def disable(self):
        os.environ.pop("VESPER_LAUNCHER_DRYRUN", None)
        for a in AGENTS:
            os.environ["VESPER_LAUNCHER_" + a.upper()] = "none"

    def entries(self):
        if not os.path.exists(self.log):
            return []
        with open(self.log, encoding="utf-8") as f:
            return [json.loads(x) for x in f if x.strip()]

    def doctor(self, agent):
        run(self.w, "doctor", "--agent", agent, "--alias", "t")

    def stage3_ready(self, agent="codex"):
        """Stage 1 and 2 done (manual mode, no app), then the agent is set. Launchers are on again after."""
        self.disable()
        rid, _ = ready_for_s3(self.w)
        reg = self.w.Registry.load()
        reg.data["agent"] = agent
        reg.save()
        self.enable(*AGENTS)
        install_fake_grader(self.w)
        return rid


class ModeDefaults(Base):
    def a(self, **kw):
        import argparse
        return argparse.Namespace(**kw)

    def test_default_is_semi_when_the_app_is_found(self):
        self.assertEqual(self.w.want_mode(self.a(), "codex"), "semi")

    def test_default_is_manual_when_the_app_is_missing(self):
        os.environ["VESPER_LAUNCHER_CODEX"] = "none"
        self.assertEqual(self.w.want_mode(self.a(), "codex"), "manual")
        self.assertEqual(self.w.want_mode(self.a(), ""), "manual")

    def test_flags_win(self):
        self.assertEqual(self.w.want_mode(self.a(mode="manual"), "codex"), "manual")
        self.assertEqual(self.w.want_mode(self.a(mode="semi"), "codex"), "semi")
        self.assertEqual(self.w.want_mode(self.a(auto=True), "codex"), "auto")

    def test_auto_alias(self):
        x = self.w.parse(["new", "s3", "--auto"])
        self.assertEqual((x.auto, x.mode), (True, "auto"))
        y = self.w.parse(["new", "s3", "--mode", "auto"])
        self.assertEqual((y.auto, y.mode), (True, "auto"))
        z = self.w.parse(["new", "s1"])
        self.assertFalse(z.auto)
        self.assertIsNone(z.mode)
        self.assertEqual(self.w.parse(["skill", "--mode", "manual"]).mode, "manual")
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            self.w.parse(["new", "s3", "--auto", "--mode", "semi"])

    def test_mode_line_names_the_mode_and_the_retry_command(self):
        semi = self.w.mode_line("semi", "codex", "python workshop.py new s1")
        self.assertTrue(semi.startswith("Mode: SEMI"))
        self.assertIn("python workshop.py new s1 --mode manual", semi)
        man = self.w.mode_line("manual", "cursor", "python workshop.py new s1", defaulted=True)
        self.assertTrue(man.startswith("Mode: MANUAL"))
        self.assertIn("did not find the Cursor app", man)


class Stage1(Base):
    def test_semi_opens_the_app_with_one_folder(self):
        self.doctor("cursor")
        out, rc = capture(self.w, "new", "s1")
        self.assertEqual(rc, 0)
        self.assertTrue(flat(out).lstrip().startswith("Mode: SEMI"))
        self.assertIn("PROMPT", out)
        self.assertIn("same as PROMPT.txt", flat(out))
        reg = self.w.Registry.load()
        rid = reg.data["active"]["run_id"]
        folder = reg.data["runs"][rid]["folder"]
        self.assertEqual(os.path.basename(folder), rid)               # stage 1 keeps the plain name
        e = self.entries()
        self.assertEqual(len(e), 1)
        self.assertEqual(e[0]["agent"], "cursor")
        self.assertEqual(e[0]["argv"][1:], ["-n", folder])
        self.assertIn("python workshop.py done", out)
        self.assertEqual(reg.data["runs"][rid]["mode"], "semi")

    def test_semi_stage1_folder_holds_prompt_txt(self):
        """The one-line message says 'Read PROMPT.txt': the file must exist in the stage-1 folder (hand test, 2026-11-03)."""
        self.doctor("cursor")
        capture(self.w, "new", "s1")
        reg = self.w.Registry.load()
        rid = reg.data["active"]["run_id"]
        pf = os.path.join(reg.data["runs"][rid]["folder"], "PROMPT.txt")
        self.assertTrue(os.path.isfile(pf))
        txt = open(pf, encoding="utf-8").read()
        self.assertIn("Workshop run: " + rid, txt)
        self.assertIn("tasks/T3.md", txt)

    def test_codex_link_has_no_prompt_and_the_prompt_comes_after_the_enter(self):
        """Memory first: the app opens with an empty box, the prompt is shown after 'memory is off' (Dennis, 2026-11-03)."""
        self.doctor("codex")
        import tempfile
        os.environ["VESPER_LAUNCHER_CODEX"] = tempfile.mkdtemp(prefix="vcodexapp_")      # a folder = the Codex app route
        seen = []
        buf = io.StringIO()

        def fake_ask(prompt, default=""):
            seen.append(buf.getvalue())
            return ""
        with mock.patch.object(self.w, "gate_on", return_value=True),                 mock.patch.object(self.w, "ask", side_effect=fake_ask), contextlib.redirect_stdout(buf):
            run(self.w, "new", "s1")
        out = buf.getvalue()
        link = [e for e in self.entries() if e["agent"] == "codex"][0]["argv"][-1]
        self.assertTrue(link.startswith("codex://new?path="), link)
        self.assertNotIn("prompt=", link)                         # an empty box on purpose
        self.assertEqual(len(seen), 1)
        self.assertIn("/memories", seen[0])
        self.assertNotIn("END OF PROMPT", seen[0])                # the prompt was not on screen when the kit waited
        self.assertIn("END OF PROMPT", out)
        self.assertTrue("clipboard" in out or "Type this message" in out)

    def test_a_log_of_another_agent_that_mentions_the_run_id_is_not_the_session(self):
        """Dennis, 2026-11-03: a Claude Code dev session on the same PC held the run id, `done` said WRONG FOLDER."""
        fake = [{"agent": "claude", "sid": "dev", "path": "x.jsonl"}]
        with mock.patch.object(self.w, "find_sessions", return_value=fake):
            self.assertIsNone(self.w.pick_session("s1-abcd", None, 0, "cursor"))
            self.assertIsNone(self.w.pick_session("s1-abcd", None, 0, "copilot"))
            self.assertIsNone(self.w.pick_session("s1-abcd", None, 0, "codex"))
            self.assertEqual(self.w.pick_session("s1-abcd", None, 0, "claude")["sid"], "dev")
            self.assertEqual(self.w.pick_session("s1-abcd", None, 0)["sid"], "dev")        # old call: unchanged

    def test_codex_page_says_memory_off_before_the_prompt(self):
        self.doctor("codex")
        out, _ = capture(self.w, "new", "s1")
        i_mem = out.index("FIRST, BEFORE YOU SEND THE PROMPT")
        i_prompt = out.index("PROMPT ---")
        self.assertLess(i_mem, i_prompt)
        self.assertIn("/memories", out[i_mem:i_prompt])

    def test_cursor_page_has_no_early_memory_box(self):
        self.doctor("cursor")
        out, _ = capture(self.w, "new", "s1")
        self.assertNotIn("FIRST, BEFORE YOU SEND THE PROMPT", out)

    def test_restart_ends_the_active_run_and_makes_a_new_one(self):
        self.doctor("cursor")
        capture(self.w, "new", "s1")
        rid1 = self.w.Registry.load().data["active"]["run_id"]
        with self.assertRaises(SystemExit) as cm:
            capture(self.w, "new", "s1")
        self.assertIn("new s1 --restart", str(cm.exception.code))      # the learner is told how to start again
        out, rc = capture(self.w, "new", "s1", "--restart")
        self.assertEqual(rc, 0)
        self.assertIn("Started again from scratch", out)
        reg = self.w.Registry.load()
        rid2 = reg.data["active"]["run_id"]
        self.assertNotEqual(rid1, rid2)
        self.assertTrue(reg.data["runs"][rid1].get("abandoned"))
        self.assertTrue(os.path.isdir(reg.data["runs"][rid1]["folder"]))   # the old folder stays until cleanup
        self.assertEqual(reg.data["runs"][rid2]["method"], reg.data["runs"][rid1]["method"])   # no re-roll of the split

    def test_restart_keeps_the_method_in_every_draw(self):
        self.doctor("cursor")
        for _ in range(6):
            capture(self.w, "new", "s1", "--restart")
        reg = self.w.Registry.load()
        s1 = [r["method"] for k, r in reg.data["runs"].items() if k.startswith("s1-")]
        self.assertEqual(len(set(s1)), 1, s1)

    def test_the_semi_page_ends_with_the_mode_box(self):
        self.doctor("cursor")
        out, _ = capture(self.w, "new", "s1")
        tail = [l for l in out.splitlines() if l.strip()][-14:]
        t = " ".join(tail)
        self.assertIn("MODE: SEMI. Cursor opened on the run folder", t)
        self.assertIn("new s1 --mode manual", t)

    def test_codex_semi_writes_the_run_config_and_the_link(self):
        self.doctor("codex")
        out, _ = capture(self.w, "new", "s1")
        reg = self.w.Registry.load()
        folder = reg.data["runs"][reg.data["active"]["run_id"]]["folder"]
        # the dry-run stub is a file, not a folder: the Codex CLI route runs
        e = self.entries()
        self.assertEqual(e[0]["agent"], "codex")
        self.assertIn("-m", e[0]["argv"])
        self.assertIn("gpt-6.1-sol", e[0]["argv"])
        self.assertIn("/memories", out)

    def test_codex_app_link(self):
        d = os.path.join(self.home, "codexapp")
        os.makedirs(d)
        os.environ["VESPER_LAUNCHER_CODEX"] = d
        self.doctor("codex")
        capture(self.w, "new", "s1")
        reg = self.w.Registry.load()
        folder = reg.data["runs"][reg.data["active"]["run_id"]]["folder"]
        e = self.entries()
        self.assertEqual(e[0]["argv"][0], "Start-Process")
        self.assertTrue(e[0]["argv"][1].startswith("codex://new?path="))
        with open(os.path.join(folder, ".codex", "config.toml"), encoding="utf-8") as f:
            self.assertIn('model = "gpt-6.1-sol"', f.read())

    def test_manual_prints_the_manual_text_and_opens_nothing(self):
        self.doctor("cursor")
        out, rc = capture(self.w, "new", "s1", "--mode", "manual")
        self.assertEqual(rc, 0)
        self.assertEqual(self.entries(), [])
        self.assertIn("Mode: MANUAL", out)
        self.assertIn("Open this folder as a NEW project", out)
        self.assertIn("PROMPT", out)

    def test_no_app_defaults_to_manual_and_says_why(self):
        self.doctor("cursor")
        os.environ["VESPER_LAUNCHER_CURSOR"] = "none"
        out, _ = capture(self.w, "new", "s1")
        self.assertEqual(self.entries(), [])
        self.assertIn("did not find the Cursor app", flat(out))

    def test_failed_open_prints_the_manual_lines_and_the_command(self):
        self.doctor("cursor")
        with mock.patch.object(self.w.LA, "open_project", return_value=self.w.LA.Opened(
                False, "", ["The app did not start."], ["Folder: X", "Send this message in the chat: M"])):
            out, rc = capture(self.w, "new", "s1")
        self.assertEqual(rc, 0)
        self.assertIn("The app did not open on its own.", out)
        self.assertIn("Folder: X", out)
        self.assertIn("python workshop.py new s1 --mode manual", out)
        self.assertIn("python workshop.py done", out)            # the run stays valid

    def test_the_manual_command_works_after_a_failed_open(self):
        self.doctor("cursor")
        with mock.patch.object(self.w.LA, "open_project", return_value=self.w.LA.Opened(False, "", ["x"], ["y"])):
            capture(self.w, "new", "s1")
        reg = self.w.Registry.load()
        rid = reg.data["active"]["run_id"]
        out, rc = capture(self.w, "new", "s1", "--mode", "manual")
        self.assertEqual(rc, 0)
        self.assertIn("Mode: MANUAL", out)
        self.assertIn(rid, out)                                    # same run, no second folder
        self.assertEqual(len(self.w.Registry.load().actives()), 1)

    def test_memory_line_per_agent(self):
        want = {"codex": "/memories", "cursor": "Nothing to turn off", "claude": "The kit turned it off",
                "copilot": "chat.copilot.memory.enabled"}
        for agent, text in want.items():
            self.w, self.home = fresh_ws()
            self.log = os.path.join(self.home, "dry.jsonl")
            self.enable(*AGENTS)
            self.doctor(agent)
            out, _ = capture(self.w, "new", "s1")
            self.assertIn(text, flat(out), agent)
            self.assertIn("Check the model", out, agent)
        self.disable()

    def test_claude_command_sets_memory_off(self):
        self.doctor("claude")
        capture(self.w, "new", "s1")
        e = self.entries()
        self.assertEqual(e[0]["agent"], "claude")
        self.assertEqual(e[0]["env"].get("CLAUDE_CODE_DISABLE_AUTO_MEMORY"), "1")

    def test_copilot_opens_through_the_launcher(self):
        self.doctor("copilot")
        out, _ = capture(self.w, "new", "s1")
        e = self.entries()
        self.assertEqual([x["agent"] for x in e], ["copilot", "copilot"])
        self.assertEqual(e[0]["argv"][1], "-n")
        self.assertEqual(e[1]["argv"][1:3], ["chat", "-r"])
        self.assertIn("PARTIAL", out.upper())                       # the Copilot notice stays
        t = flat(out)
        self.assertNotIn("manual mode only", t)                     # the page is SEMI: no contradiction
        self.assertIn("Semi mode opens VS Code", t)
        self.assertIn("--auto", t)

    def test_copilot_stage3_semi_page_notice(self):
        self.stage3_ready("copilot")
        out, _ = capture(self.w, "new", "s3", "--task", "T3", "--mode", "semi")
        t = flat(out)
        self.assertNotIn("manual mode only", t)
        self.assertIn("PARTIAL SUPPORT", t)
        self.assertIn("--auto", t)


class Skill(Base):
    def test_semi_copies_the_prompt_and_opens_nothing(self):
        self.w, self.home = fresh_ws()
        self.log = os.path.join(self.home, "dry.jsonl")
        self.enable(*AGENTS)
        self.doctor("cursor")
        capture(self.w, "new", "s1")
        capture(self.w, "done", "--no-form")
        n = len(self.entries())
        with mock.patch.object(self.w, "copy_to_clipboard", return_value=True) as clip:
            out, rc = capture(self.w, "skill")
        self.assertEqual(rc, 0)
        self.assertEqual(len(self.entries()), n)                    # no new window
        clip.assert_called_once()
        self.assertIn("Workshop run", clip.call_args[0][0])
        self.assertIn("on the clipboard", out)
        self.assertIn("Mode: SEMI", out)

    def test_manual_skill_does_not_copy(self):
        self.doctor("cursor")
        capture(self.w, "new", "s1")
        capture(self.w, "done", "--no-form")
        with mock.patch.object(self.w, "copy_to_clipboard") as clip:
            out, _ = capture(self.w, "skill", "--mode", "manual")
        clip.assert_not_called()
        self.assertIn("Mode: MANUAL", out)


class Stage3(Base):
    def run_all(self, agent="codex", **kw):
        rid1 = self.stage3_ready(agent)
        seen = []
        orig = self.w.create_s3_run

        def spy(*a, **k):
            seen.append(sorted(os.listdir(self.w.ws_home())))
            return orig(*a, **k)
        with mock.patch.object(self.w, "create_s3_run", side_effect=spy):
            out, rc = capture(self.w, "new", "s3", "--task", "all", "--name", "MIRA", *kw.get("extra", []))
        return rid1, out, rc, seen

    def test_four_pages_one_folder_each_in_order(self):
        rid1, out, rc, seen = self.run_all("codex")
        self.assertEqual(rc, 0)
        reg = self.w.Registry.load()
        runs = [r for r in reg.data["runs"].values() if r["stage"] == "3"]
        self.assertEqual(len(runs), 4)
        names = [os.path.basename(r["folder"]) for r in runs]
        labels = [n.split("__")[0] for n in names]
        self.assertEqual(labels, ["T3_WITH_SKILL_LUNA", "T3_NO_SKILL_LUNA", "T6_WITH_SKILL_LUNA", "T6_NO_SKILL_LUNA"])
        for n, r in zip(names, runs):
            self.assertTrue(re.fullmatch(r"T[36]_(WITH|NO)_SKILL_LUNA__s3-[0-9a-f]{4}-[tn][36]-[0-9a-f]{4}", n), n)
            self.assertTrue(n.endswith("__" + [k for k, v in reg.data["runs"].items() if v is r][0]))
        # when run i was created, only i-1 stage-3 folders existed (one folder per page)
        self.assertEqual([len([x for x in s if x.startswith("T")]) for s in seen], [0, 1, 2, 3])
        # the order of the pages in the output
        pos = [out.index("RUN %d of 4  %s" % (i, lab)) for i, lab in enumerate(labels, 1)]
        self.assertEqual(pos, sorted(pos))
        self.assertEqual(len(self.entries()), 4)
        self.assertEqual(out.count("same as PROMPT.txt"), 4)

    def finish_with_answers(self, answers, now_shift=0.0):
        """Run the interactive end of stage 3 with typed answers. Returns (output, list of run ids that done ran for)."""
        self.run_all("codex")
        reg = self.w.Registry.load()
        made = [(k, r["run_id"] if "run_id" in r else k, r["folder"], "") for k, r in reg.data["runs"].items() if r["stage"] == "3"]
        made = [("t3", rid, f, p) for _, rid, f, p in made]
        ended, asked = [], list(answers)
        self.prompts = []

        def fake_done(reg2, rids, a):
            ended.extend(rids)
        buf = io.StringIO()
        with mock.patch.object(self.w, "interactive", return_value=True),                 mock.patch.object(self.w, "ask", side_effect=lambda *a, **k: (self.prompts.append(a[0]), asked.pop(0))[1]),                 mock.patch.object(self.w, "run_is_done", side_effect=lambda rid: rid in ended),                 mock.patch.object(self.w, "semi_done_all", side_effect=fake_done),                 mock.patch.object(self.w.time, "time", return_value=time.time() + now_shift),                 contextlib.redirect_stdout(buf):
            self.w.semi_s3_finish(reg, argparse_ns(), made)
        return buf.getvalue(), ended, [m[1] for m in made]

    def test_bare_enter_ends_nothing(self):
        out, ended, rids = self.finish_with_answers(["", "  ", "x", "9", "q"])
        self.assertEqual(ended, [])
        self.assertIn("Enter alone does nothing", out)
        self.assertIn("You left the list", out)

    def test_a_run_before_its_stop_time_needs_a_y(self):
        out, ended, rids = self.finish_with_answers(["1", "n", "q"])
        self.assertEqual(ended, [])
        self.assertIn("Did you stop its agent", " ".join(self.prompts))

    def test_a_run_before_its_stop_time_ends_after_y(self):
        out, ended, rids = self.finish_with_answers(["1", "y", "q"])
        self.assertEqual(ended, [rids[0]])

    def test_after_the_stop_time_a_number_ends_that_run_only_and_the_list_marks_it(self):
        out, ended, rids = self.finish_with_answers(["2", "q"], now_shift=3 * 3600)
        self.assertEqual(ended, [rids[1]])
        self.assertIn("ENDED  (done saved)", out)
        self.assertEqual(out.count("running"), 7)       # list 1: four rows running; list 2: three rows running

    def test_all_four_ended_ends_the_loop(self):
        out, ended, rids = self.finish_with_answers(["1", "2", "3", "4"], now_shift=3 * 3600)
        self.assertEqual(ended, rids)
        self.assertIn("All 4 runs are ENDED", out)
        self.assertIn("python workshop.py show", out)
        self.assertIn("python workshop.py play T3", out)       # the learner can play what the agents made
        self.assertIn("python workshop.py play T6", out)
        self.assertLess(out.index("python workshop.py play T3"), out.index("python workshop.py show"))

    def test_pages_show_prompt_memory_and_model(self):
        _, out, _, _ = self.run_all("codex")
        t = flat(out)
        self.assertEqual(t.count("Mode: SEMI"), 4)
        self.assertEqual(t.count("Run name: T"), 4)
        self.assertEqual(t.count("/memories"), 8)          # twice per page: before the prompt and after the opener
        self.assertEqual(t.count("Check the model"), 4)
        self.assertEqual(t.count("END OF PROMPT"), 4)

    def test_stop_time_table_and_next_box_when_not_interactive(self):
        _, out, _, _ = self.run_all("codex")
        i = out.index("Stop each agent at its stop time")
        table = out[i:]
        self.assertIn("STOP", table)
        for lab in ("T3_WITH_SKILL_LUNA", "T3_NO_SKILL_LUNA", "T6_WITH_SKILL_LUNA", "T6_NO_SKILL_LUNA"):
            self.assertIn(lab, table)
        stops = re.findall(r"\b(\d\d:\d\d:\d\d)\s+(\d\d:\d\d:\d\d)\s+s3-", table)
        self.assertEqual(len(stops), 4)
        for st, sp in stops:
            a = time.strptime(st, "%H:%M:%S")
            b = time.strptime(sp, "%H:%M:%S")
            diff = ((b.tm_hour * 60 + b.tm_min) - (a.tm_hour * 60 + a.tm_min)) % 1440
            self.assertEqual(diff, 10)
        self.assertEqual(table.count("python workshop.py done s3-"), 4)    # no person at the keyboard: lines, not done

    def test_numbers_then_done_for_each_run(self):
        self.stage3_ready("codex")
        asked = []
        nums = iter(["1", "2", "3", "4"])

        def fake_ask(q, d=""):
            asked.append(q)
            if "Type the NUMBER" in q:
                return next(nums, "q")
            return "y" if "Did you stop" in q else d
        with mock.patch.object(self.w, "interactive", return_value=True), \
                mock.patch.object(self.w, "ask", side_effect=fake_ask), \
                mock.patch.object(self.w, "run_is_done", side_effect=lambda rid: False), \
                mock.patch.object(self.w, "cmd_done", return_value=0) as done:
            capture(self.w, "new", "s3", "--task", "all", "--name", "MIRA")
        self.assertEqual(len(done.call_args_list), 4)                                  # one done per typed number
        self.assertEqual(len([q for q in asked if "Type the NUMBER" in q]), 5)         # four numbers, then q
        self.assertEqual(len([q for q in asked if "next page appears at once" in q]), 3)
        self.assertEqual(len([q for q in asked if "list of runs appears next" in q]), 1)

    def test_no_answer_three_times_leaves_the_list(self):
        self.stage3_ready("codex")
        with mock.patch.object(self.w, "interactive", return_value=True), \
                mock.patch.object(self.w, "ask", side_effect=lambda q, d="": d), \
                mock.patch.object(self.w, "cmd_done", return_value=0) as done:
            out, rc = capture(self.w, "new", "s3", "--task", "all", "--name", "MIRA")
        self.assertEqual(len(done.call_args_list), 0)
        self.assertIn("You left the list", out)

    def test_done_runs_for_real_with_the_labeled_folders(self):
        self.stage3_ready("codex")
        with mock.patch.object(self.w, "interactive", return_value=True), \
                mock.patch.object(self.w, "ask", side_effect=answer_numbers()):
            out, rc = capture(self.w, "new", "s3", "--task", "all", "--name", "MIRA", "--yes")
        self.assertEqual(rc, 0)
        reg = self.w.Registry.load()
        rows = [r for r in reg.data["rows"].values() if r["stage"] == "3"]
        self.assertEqual(len(rows), 4)
        self.assertEqual(reg.actives("3"), [])

    def test_manual_mode_is_the_old_flow(self):
        self.stage3_ready("codex")
        out, rc = capture(self.w, "new", "s3", "--task", "all", "--name", "MIRA", "--mode", "manual")
        self.assertEqual(rc, 0)
        self.assertEqual(self.entries(), [])
        self.assertIn("Mode: MANUAL", out)
        reg = self.w.Registry.load()
        for r in reg.data["runs"].values():
            if r["stage"] == "3":
                self.assertTrue(os.path.basename(r["folder"]).startswith("s3-"), r["folder"])   # old names

    def test_cleanup_removes_the_labeled_folders(self):
        self.stage3_ready("codex")
        capture(self.w, "new", "s3", "--task", "all", "--name", "MIRA")
        home = self.w.ws_home()
        self.assertEqual(len([n for n in os.listdir(home) if n.startswith("T")]), 4)
        capture(self.w, "cleanup", "--yes", "--no-copy")
        self.assertFalse(os.path.exists(home) and [n for n in os.listdir(home) if n.startswith("T")])

    def test_resume_shows_the_semi_pages_again(self):
        self.stage3_ready("codex")
        with mock.patch.object(self.w, "ask", side_effect=[KeyboardInterrupt()]):
            try:
                capture(self.w, "new", "s3", "--task", "all", "--name", "MIRA")
            except KeyboardInterrupt:
                pass
        reg = self.w.Registry.load()
        self.assertEqual(len(reg.actives("3")), 1)                     # only page 1 was made
        first = reg.actives("3")[0]["run_id"]
        reg.data["runs"][first]["sent_at"] = 1234.5               # the learner sent it before the break
        reg.save()
        launches = len(self.entries())
        self.assertEqual(launches, 1)
        out, rc = capture(self.w, "new", "s3", "--task", "all", "--name", "MIRA")
        self.assertIn("already set up", out)
        self.assertIn("T3_WITH_SKILL_LUNA", out)
        self.assertEqual(len(self.entries()), launches)             # no second launch: no double send
        self.assertEqual(self.w.Registry.load().data["runs"][first]["sent_at"], 1234.5)

    def test_memory_line_comes_after_a_failed_open(self):
        self.stage3_ready("claude")
        with mock.patch.object(self.w.LA, "open_project", return_value=self.w.LA.Opened(False, "", ["no"], ["Folder: F"])):
            out, _ = capture(self.w, "new", "s3", "--task", "T3", "--mode", "semi")
        self.assertNotIn("The kit turned it off", flat(out))
        self.assertIn("Nothing to turn off by hand", flat(out))

    def test_memory_line_after_a_good_open(self):
        self.stage3_ready("claude")
        out, _ = capture(self.w, "new", "s3", "--task", "T3", "--mode", "semi")
        self.assertIn("The kit turned it off", out)
        self.assertLess(out.index("A new terminal window"), out.index("The kit turned it off"))

    def test_codex_cli_page_says_paste_and_send(self):
        self.stage3_ready("codex")
        out, _ = capture(self.w, "new", "s3", "--task", "T3", "--mode", "semi")
        self.assertIn("/memories", out)
        self.assertNotIn("sent as the first prompt", out)

    def test_failed_open_prints_manual_command_on_the_page(self):
        self.stage3_ready("codex")
        with mock.patch.object(self.w.LA, "open_project", return_value=self.w.LA.Opened(False, "", ["no"], ["Folder: F"])):
            out, rc = capture(self.w, "new", "s3", "--task", "T3", "--mode", "semi")
        self.assertEqual(rc, 0)
        self.assertIn("python workshop.py new s3 --task T3 --mode manual", out)
        self.assertIn("Folder: F", out)

    def test_cursor_page_lines(self):
        self.stage3_ready("cursor")
        out, _ = capture(self.w, "new", "s3", "--task", "T3", "--name", "X")
        self.assertIn("Not Auto. Do not use Plan mode.", out)
        self.assertIn("Nothing to turn off", flat(out))


class DoneLines(Base):
    def test_cursor_line_with_model_effort_and_minutes(self):
        self.doctor("cursor")
        capture(self.w, "new", "s1")
        reg = self.w.Registry.load()
        rid = reg.data["active"]["run_id"]
        reg.get_active(rid)["start"] = time.time() - 700
        reg.save()
        now = time.time()
        with mock.patch.object(self.w.M, "cursor_app_chat", return_value={
                "model": "gpt-5.6-luna-high", "effort": "high", "first": now - 600, "last": now - 300}):
            out, _ = capture(self.w, "done", "--no-form")
        self.assertIn("Cursor chat found: model gpt-5.6-luna-high, effort high, 5.0 min", out)

    def test_cursor_chat_not_found_is_a_hint(self):
        self.doctor("cursor")
        capture(self.w, "new", "s1")
        with mock.patch.object(self.w.M, "cursor_app_chat", return_value=None):
            out, rc = capture(self.w, "done", "--no-form")
        self.assertEqual(rc, 0)
        self.assertIn("Cursor chat not found. This is only a hint", out)

    def make_state(self, mode, rid, folder):
        p = os.path.join(self.home, "state_5.sqlite")
        con = sqlite3.connect(p)
        con.execute("CREATE TABLE threads (id TEXT, memory_mode TEXT, first_user_message TEXT, cwd TEXT, updated_at INTEGER)")
        con.execute("INSERT INTO threads VALUES ('t1', ?, ?, ?, 1)", (mode, "Workshop run: %s. Read" % rid, folder))
        con.commit()
        con.close()
        os.environ["VESPER_CODEX_STATE"] = p

    def codex_done(self, mode):
        self.doctor("codex")
        os.environ["VESPER_LAUNCHER_CODEX"] = "none"
        capture(self.w, "new", "s1", "--mode", "manual")
        reg = self.w.Registry.load()
        rid = reg.data["active"]["run_id"]
        if mode:
            self.make_state(mode, rid, reg.data["runs"][rid]["folder"])
        return capture(self.w, "done", "--no-form")[0]

    def test_memory_off_verified(self):
        self.assertIn("memory: OFF (verified)", self.codex_done("disabled"))

    def test_memory_on_warns(self):
        out = self.codex_done("enabled")
        self.assertIn("This run is not clean.", out)

    def test_memory_unknown_is_silent(self):
        out = self.codex_done(None)
        self.assertNotIn("memory: OFF", out)
        self.assertNotIn("not clean", out)


class Doctor(Base):
    def test_info_line_found(self):
        out, _ = capture(self.w, "doctor", "--agent", "cursor", "--alias", "t")
        self.assertIn("INFO  app found:", out)

    def test_info_line_missing(self):
        os.environ["VESPER_LAUNCHER_CURSOR"] = "none"
        out, _ = capture(self.w, "doctor", "--agent", "cursor", "--alias", "t")
        self.assertIn("app not found: semi mode falls back to manual", out)


class EveryAgentPages(Base):
    """Stage-3 page in semi and in manual mode for each agent: exact logged commands, memory, model."""
    EXPECT = {
        "codex": (["-m", "gpt-6-luna"], "/memories", "gpt-6-luna"),
        "cursor": (["-n"], "Nothing to turn off", "GPT-5.6 Luna High"),
        "claude": (["--model", "claude-haiku-5-5"], "The kit turned it off", "Haiku 5.5"),
        "copilot": (["-n"], "chat.copilot.memory.enabled", "model picker"),
    }

    def page(self, agent, *extra):
        self.w, self.home = fresh_ws()
        self.log = os.path.join(self.home, "dry.jsonl")
        self.enable(*AGENTS)
        self.stage3_ready(agent)
        return capture(self.w, "new", "s3", "--task", "T3", "--name", "X", *extra)

    def test_semi_page_per_agent(self):
        for agent, (argv_part, mem, model) in self.EXPECT.items():
            out, rc = self.page(agent)
            t = flat(out)
            self.assertEqual(rc, 0, agent)
            self.assertIn("Mode: SEMI", t, agent)
            self.assertIn("Run name: T3_WITH_SKILL_", t, agent)
            self.assertIn(mem, t, agent)
            self.assertIn(model, t, agent)
            reg = self.w.Registry.load()
            rid, run_ = [(k, v) for k, v in reg.data["runs"].items() if v["stage"] == "3"][0]
            e = self.entries()
            self.assertEqual(e[0]["agent"], agent)
            for part in argv_part:
                self.assertIn(part, e[0]["argv"], agent)
            if agent == "codex":
                self.assertNotIn("Workshop run: %s" % rid, " ".join(e[0]["argv"]))      # pasted, not sent
            elif agent != "cursor" and agent != "copilot":
                self.assertEqual(e[0]["argv"][-1], "Workshop run: %s. Read PROMPT.txt in this folder and do what it says." % rid)
            if agent in ("cursor", "copilot"):
                self.assertIn(run_["folder"], e[0]["argv"])
            self.assertEqual(run_["mode"], "semi")

    def test_manual_page_per_agent_opens_nothing(self):
        for agent in self.EXPECT:
            out, rc = self.page(agent, "--mode", "manual")
            self.assertEqual(rc, 0, agent)
            self.assertEqual(self.entries(), [], agent)
            self.assertIn("Mode: MANUAL", out, agent)
            self.assertIn("Folder:", out, agent)
            self.assertIn("PROMPT", out, agent)

    def test_every_page_says_the_command_to_use_when_it_fails(self):
        for agent in self.EXPECT:
            out, _ = self.page(agent)
            self.assertIn("python workshop.py new s3 --task T3 --mode manual", flat(out), agent)


class NeverCrash(Base):
    def test_launcher_that_raises_does_not_stop_stage_1(self):
        self.doctor("codex")
        with mock.patch.object(self.w.LA, "open_project", side_effect=RuntimeError("boom")):
            out, rc = capture(self.w, "new", "s1")
        self.assertEqual(rc, 0)
        self.assertIn("The app did not open on its own.", out)
        self.assertIn("Folder:", out)
        self.assertIn("python workshop.py done", out)

    def test_launcher_that_raises_does_not_stop_stage_3(self):
        self.stage3_ready("codex")
        with mock.patch.object(self.w.LA, "open_project", side_effect=OSError("boom")):
            out, rc = capture(self.w, "new", "s3", "--task", "all", "--name", "MIRA")
        self.assertEqual(rc, 0)
        self.assertEqual(out.count("The app did not open on its own."), 4)
        self.assertEqual(out.count("python workshop.py done s3-"), 4)

    def test_find_app_with_an_unreadable_path_gives_none(self):
        with mock.patch.object(self.w.LA, "_which", side_effect=OSError("x")):
            os.environ["VESPER_LAUNCHER_CURSOR"] = ""
            self.assertIsNone(self.w.LA.find_app("cursor"))

    def test_reader_that_raises_does_not_stop_done(self):
        self.doctor("cursor")
        capture(self.w, "new", "s1")
        with mock.patch.object(self.w.M, "cursor_app_chat", side_effect=RuntimeError("db")):
            out, rc = capture(self.w, "done", "--no-form")
        self.assertEqual(rc, 0)
        self.assertIn("Cursor chat not found. This is only a hint", out)

    def test_memory_reader_that_raises_does_not_stop_done(self):
        self.doctor("codex")
        os.environ["VESPER_LAUNCHER_CODEX"] = "none"
        capture(self.w, "new", "s1")
        with mock.patch.object(self.w.M, "codex_memory_mode", side_effect=RuntimeError("db")):
            out, rc = capture(self.w, "done", "--no-form")
        self.assertEqual(rc, 0)
        self.assertNotIn("memory: OFF", out)

    def test_done_all_goes_on_when_one_done_fails(self):
        self.stage3_ready("codex")

        def fake_done(a):
            if a.run_id.endswith("-t6") or "-t6-" in a.run_id:
                raise RuntimeError("x")
            if "-n3-" in a.run_id:
                sys.exit("No run called that.")
            print("ok %s" % a.run_id)
            return 0
        with mock.patch.object(self.w, "interactive", return_value=True), \
                mock.patch.object(self.w, "ask", side_effect=answer_numbers()), \
                mock.patch.object(self.w, "cmd_done", side_effect=fake_done):
            out, rc = capture(self.w, "new", "s3", "--task", "all", "--name", "MIRA")
        self.assertEqual(rc, 0)
        self.assertEqual(out.count("ok s3-"), 2)
        self.assertIn("done could not finish for", out)
        self.assertIn("No run called that.", out)

    def test_clipboard_failure_is_not_fatal_in_stage_2(self):
        self.doctor("cursor")
        capture(self.w, "new", "s1")
        capture(self.w, "done", "--no-form")
        with mock.patch.object(self.w, "copy_to_clipboard", return_value=False):
            out, rc = capture(self.w, "skill")
        self.assertEqual(rc, 0)
        self.assertIn("The clipboard did not work.", out)


class CursorDone(Base):
    def make_db(self, rid, t0, t1, effort_id="effort", effort="high", model="gpt-5.6-luna-high"):
        p = os.path.join(self.home, "state.vscdb")
        con = sqlite3.connect(p)
        con.execute("CREATE TABLE cursorDiskKV (key TEXT UNIQUE ON CONFLICT REPLACE, value BLOB)")
        cd = {"createdAt": int(t0 * 1000), "lastUpdatedAt": int(t1 * 1000), "modelConfig": {
            "modelName": model, "selectedModels": [{"modelId": model, "parameters": [{"id": effort_id, "value": effort}]}]}}
        con.execute("INSERT INTO cursorDiskKV VALUES (?,?)", ("composerData:c1", json.dumps(cd)))
        con.execute("INSERT INTO cursorDiskKV VALUES (?,?)", ("bubbleId:c1:b1", json.dumps(
            {"type": 1, "text": "Workshop run: %s. Read" % rid, "createdAt": fakes.iso(t0 + 5)})))
        con.execute("INSERT INTO cursorDiskKV VALUES (?,?)", ("bubbleId:c1:b2", json.dumps(
            {"type": 2, "text": "done", "createdAt": fakes.iso(t1 - 5)})))
        con.commit()
        con.close()
        os.environ["VESPER_CURSOR_STATE"] = p
        self.addCleanup(os.environ.pop, "VESPER_CURSOR_STATE", None)
        return p

    def start(self):
        self.doctor("cursor")
        os.environ["VESPER_LAUNCHER_CURSOR"] = "none"
        capture(self.w, "new", "s1")
        reg = self.w.Registry.load()
        rid = reg.data["active"]["run_id"]
        reg.get_active(rid)["start"] = time.time() - 900
        reg.save()
        return rid

    def test_found_with_stamps_and_effort(self):
        rid = self.start()
        now = time.time()
        self.make_db(rid, now - 700, now - 400)
        out, _ = capture(self.w, "done", "--no-form")
        self.assertIn("Cursor chat found: model gpt-5.6-luna-high, effort high, 4.8 min", flat(out))

    def test_effort_name_reasoning_effort(self):
        rid = self.start()
        now = time.time()
        self.make_db(rid, now - 700, now - 400, effort_id="reasoning_effort", effort="low")
        out, _ = capture(self.w, "done", "--no-form")
        self.assertIn("effort low", out)

    def test_not_found_is_a_hint(self):
        rid = self.start()
        now = time.time()
        self.make_db("s1-zzzz", now - 700, now - 400)
        out, rc = capture(self.w, "done", "--no-form")
        self.assertEqual(rc, 0)
        self.assertIn("Cursor chat not found. This is only a hint", out)

    def test_unreadable_database(self):
        self.start()
        p = os.path.join(self.home, "garbage.vscdb")
        with open(p, "wb") as f:
            f.write(b"this is not a database" * 50)
        os.environ["VESPER_CURSOR_STATE"] = p
        self.addCleanup(os.environ.pop, "VESPER_CURSOR_STATE", None)
        out, rc = capture(self.w, "done", "--no-form")
        self.assertEqual(rc, 0)
        self.assertIn("Cursor chat not found. This is only a hint", out)


class CodexMemory(DoneLines):
    def test_unreadable_state_file(self):
        self.doctor("codex")
        capture(self.w, "new", "s1", "--mode", "manual")
        p = os.path.join(self.home, "bad.sqlite")
        with open(p, "wb") as f:
            f.write(b"not sqlite" * 100)
        os.environ["VESPER_CODEX_STATE"] = p
        out, rc = capture(self.w, "done", "--no-form")
        self.assertEqual(rc, 0)
        self.assertNotIn("memory: OFF", out)
        self.assertNotIn("not clean", out)

    def test_missing_table(self):
        self.doctor("codex")
        capture(self.w, "new", "s1", "--mode", "manual")
        p = os.path.join(self.home, "empty.sqlite")
        sqlite3.connect(p).close()
        os.environ["VESPER_CODEX_STATE"] = p
        out, rc = capture(self.w, "done", "--no-form")
        self.assertEqual(rc, 0)
        self.assertNotIn("memory: OFF", out)

    def test_found_by_folder_when_the_message_has_no_run_id(self):
        self.doctor("codex")
        capture(self.w, "new", "s1", "--mode", "manual")
        reg = self.w.Registry.load()
        rid = reg.data["active"]["run_id"]
        self.make_state("disabled", "other-id", reg.data["runs"][rid]["folder"])
        self.assertIn("memory: OFF (verified)", capture(self.w, "done", "--no-form")[0])

    def test_the_state_file_is_not_changed(self):
        self.doctor("codex")
        capture(self.w, "new", "s1", "--mode", "manual")
        reg = self.w.Registry.load()
        rid = reg.data["active"]["run_id"]
        self.make_state("enabled", rid, reg.data["runs"][rid]["folder"])
        p = os.environ["VESPER_CODEX_STATE"]
        before = open(p, "rb").read()
        capture(self.w, "done", "--no-form")
        self.assertEqual(open(p, "rb").read(), before)

    def test_auto_runs_skip_the_memory_line(self):
        self.doctor("codex")
        capture(self.w, "new", "s1", "--mode", "manual")
        reg = self.w.Registry.load()
        rid = reg.data["active"]["run_id"]
        reg.data["runs"][rid]["auto"] = True
        reg.save()
        self.make_state("enabled", rid, reg.data["runs"][rid]["folder"])
        self.assertNotIn("not clean", capture(self.w, "done", "--no-form")[0])


class DoctorAllAgents(Base):
    def test_one_info_line_per_agent_found_and_missing(self):
        for agent in AGENTS:
            self.w, self.home = fresh_ws()
            self.enable(*AGENTS)
            out, _ = capture(self.w, "doctor", "--agent", agent, "--alias", "t")
            self.assertEqual(out.count("INFO  app"), 1, agent)
            self.assertIn("INFO  app found:", out, agent)
            os.environ["VESPER_LAUNCHER_" + agent.upper()] = "none"
            out, _ = capture(self.w, "doctor", "--agent", agent, "--alias", "t")
            self.assertEqual(out.count("INFO  app not found: semi mode falls back to manual"), 1, agent)
        self.disable()

    def test_other_agent_has_no_app_line(self):
        out, _ = capture(self.w, "doctor", "--agent", "other", "--alias", "t")
        self.assertNotIn("INFO  app", out)

    def test_info_line_does_not_change_the_colour_of_the_verdict(self):
        out, _ = capture(self.w, "doctor", "--agent", "cursor", "--alias", "t")
        self.assertIn("GREEN", out)


class Labels(Base):
    def test_label_per_agent(self):
        for agent, tag in (("codex", "LUNA"), ("cursor", "LUNA"), ("claude", "HAIKU"), ("copilot", "SMALL")):
            reg = mock.Mock()
            reg.data = {"agent": agent}
            self.assertEqual(self.w.run_folder_label(reg, "T3", False), "T3_WITH_SKILL_" + tag)
            self.assertEqual(self.w.run_folder_label(reg, "T6", True), "T6_NO_SKILL_" + tag)

    def test_label_of_reads_the_front_of_the_folder_name(self):
        self.assertEqual(self.w.label_of(os.path.join("x", "T3_WITH_SKILL_LUNA__s3-ab12-t3-cd34")), "T3_WITH_SKILL_LUNA")
        self.assertEqual(self.w.label_of("/x/s1-ab12"), "s1-ab12")

    def test_show_grade_and_done_work_with_labeled_folders(self):
        self.stage3_ready("codex")
        capture(self.w, "new", "s3", "--task", "T3", "--name", "X")
        reg = self.w.Registry.load()
        rid = reg.actives("3")[0]["run_id"]
        self.assertIn("T3_WITH_SKILL_LUNA__" + rid, reg.data["runs"][rid]["folder"])
        out, rc = capture(self.w, "done", rid, "--no-form")
        self.assertEqual(rc, 0)
        self.assertEqual(capture(self.w, "show")[1], 0)
        self.assertEqual(capture(self.w, "grade", "--no-form")[1] or 0, 0)


if __name__ == "__main__":
    unittest.main()
