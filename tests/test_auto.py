"""Stage 3 --auto with FAKE CLIs (tests/fake_agent.py): no network, no real agent.
Also: the Cursor stream-json reader, doctor readiness, and the stage-3 resume (PROMPT.txt, Ctrl+C in the pages)."""
import contextlib, io, json, os, re, shutil, sys, tempfile, time, unittest
from unittest import mock
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fakes  # noqa: E402
from fakes import fresh_ws, run, flat  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
FAKE = os.path.join(HERE, "fake_agent.py")
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import charts  # noqa: E402
import measure  # noqa: E402

ENV_KEYS = ("VESPER_CODEX_EXE", "VESPER_CURSOR_EXE", "VESPER_CLAUDE_EXE", "FAKE_SLEEP", "FAKE_SLOW_KEYS",
            "FAKE_SLOW_SEC", "FAKE_CHILD", "FAKE_FREEPLAN", "FAKE_VERSION", "FAKE_LOGIN", "FAKE_INIT_MODEL",
            "FAKE_FAIL", "FAKE_NO_USAGE", "FAKE_PROBE_NOWRITE", "FAKE_PROBE_NOVERSION", "FAKE_PROBE_OUTSIDE", "LOCALAPPDATA")


def make_echo_cmd(d, name="agent.cmd"):
    """A fake .cmd launcher (as npm's claude.cmd / codex.cmd and cursor-agent.cmd): cmd.exe runs it and passes
    %* to fake_agent.py, which writes the argv that arrived (and the stdin) to argv.json."""
    p = os.path.join(d, name)
    with open(p, "w", newline="\r\n") as f:
        f.write('@echo off\n"%s" "%s" %%*\n' % (sys.executable, FAKE))
    return p


def capture(w, *argv):
    out = io.StringIO()
    rc = None
    with contextlib.redirect_stdout(out):
        rc = run(w, *argv)
    return out.getvalue(), rc


def long_lines(text):
    bad = []
    for line in text.splitlines():
        if len(line) <= 72:
            continue
        body = line.strip()
        if len(body.split()) == 1 or body.startswith(("python ", "C:\\", "/")):
            continue
        bad.append(line)
    return bad


class AutoBase(unittest.TestCase):
    agent = "codex"

    def setUp(self):
        self.saved = {k: os.environ.get(k) for k in ENV_KEYS}
        self.w, self.home = fresh_ws()
        os.environ["LOCALAPPDATA"] = os.path.join(self.home, "localappdata")       # never the real CLIs
        for k in ("VESPER_CODEX_EXE", "VESPER_CURSOR_EXE", "VESPER_CLAUDE_EXE"):
            os.environ[k] = FAKE
        os.environ["FAKE_SLEEP"] = "0.2"
        self.s1, _ = fakes.ready_for_s3(self.w)
        reg = self.w.Registry.load()
        reg.data["agent"] = self.agent
        reg.save()
        self.w.AUTO_TICK, self.w.AUTO_POLL = 0.3, 0.05
        self.w.AUTO_BOX_SEC = 30
        self.w.AUTO_MIN_SEC = 0                  # the fake agents end in 0.2 s: not an error here

    def tearDown(self):
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def runs3(self):
        reg = self.w.Registry.load()
        return reg, {k: r for k, r in reg.data["runs"].items() if r.get("stage") == "3"}

    def rows3(self):
        reg = self.w.Registry.load()
        return {r["run_id"]: r for r in reg.data["rows"].values() if r["stage"] == "3"}


class AutoCodex(AutoBase):
    def test_all_four_run_and_finish(self):
        out, rc = capture(self.w, "new", "s3", "--task", "all", "--auto", "--yes", "--name", "MIRA")
        self.assertEqual(rc, 0)
        self.assertEqual(long_lines(out), [])
        self.assertIn("STAGE 3 --auto - the tool runs the 4 agents for you", out)
        self.assertIn("Agent: codex   Model: gpt-6-luna, effort high", out)
        self.assertIn("Time box 10 min: the tool stops any agent still working.", out)
        self.assertRegex(flat(out), r"Start order: 1\. T[36] (with|without) skill\s+2\. ")
        for label in ("T3 with skill", "T3 without skill", "T6 with skill", "T6 without skill"):
            self.assertRegex(out, r"  %s +running 0:0\d" % label)
            self.assertRegex(out, r"  %s +done +0:\d\d" % label)
        reg, runs = self.runs3()
        rows = self.rows3()
        self.assertEqual(len(rows), 4)
        self.assertEqual(reg.actives(), [])                       # every run was finished by the tool
        for rid, run_ in runs.items():
            self.assertTrue(os.path.isfile(os.path.join(run_["folder"], "agent-output.jsonl")))
            r = rows[rid]
            self.assertEqual(r["settings_confirmed"], "auto")
            self.assertEqual(r["overrun"], "no")
            self.assertEqual(r["stopped"], "")
            self.assertEqual(r["model"], "gpt-6-luna")
            self.assertEqual(r["effort"], "")                      # the fake log has no effort field
            self.assertEqual(r["tok_out"], 800)
            self.assertEqual(r["tok_cache_read"], 6000)
            self.assertEqual(r["measurement"], "log")
            self.assertEqual(r["isolation"], "not_detected")
        self.assertIn("python workshop.py unlock 4", out)          # the last NEXT box
        self.assertEqual(out.count("FINISHED"), 4)

    def test_command_line_codex_verbatim(self):
        capture(self.w, "new", "s3", "--task", "T3", "--auto", "--yes")
        _, runs = self.runs3()
        rid, run_ = next(iter(runs.items()))
        with open(os.path.join(run_["folder"], "argv.json")) as f:
            d = json.load(f)
        argv = d["argv"]
        self.assertEqual(argv[:2], ["exec", "-m"])
        self.assertEqual(argv[2], "gpt-6-luna")
        for pair in (["-c", 'model_reasoning_effort="high"'], ["-c", "features.memories=false"],
                     ["-s", "workspace-write"]):
            self.assertTrue(any(argv[i:i + 2] == pair for i in range(len(argv))), pair)
        self.assertIn("--skip-git-repo-check", argv)
        self.assertEqual(argv[argv.index("-C") + 1], run_["folder"])
        self.assertEqual(argv[-1], "-")                            # the prompt comes on stdin
        self.assertIn("Workshop run: " + rid, d["stdin"])
        self.assertIn("\n", d["stdin"])                            # the whole prompt, new lines included
        self.assertEqual(os.path.normcase(d["cwd"]), os.path.normcase(run_["folder"]))

    def test_model_override(self):
        capture(self.w, "new", "s3", "--task", "T3", "--auto", "--yes", "--model", "gpt-6-sol")
        _, runs = self.runs3()
        rid, run_ = next(iter(runs.items()))
        with open(os.path.join(run_["folder"], "argv.json")) as f:
            self.assertEqual(json.load(f)["argv"][2], "gpt-6-sol")

    def test_start_time_is_the_launch_and_manual_flow_unchanged(self):
        out, _ = capture(self.w, "new", "s3", "--task", "T3")     # no --auto: no process is started
        _, runs = self.runs3()
        run_ = next(iter(runs.values()))
        self.assertFalse(os.path.exists(os.path.join(run_["folder"], "argv.json")))
        self.assertNotIn("--auto - the tool runs", out)
        self.assertEqual(run_.get("auto"), None)

    def test_auto_needs_stage3_and_known_agent(self):
        with self.assertRaises(SystemExit):
            run(self.w, "new", "s1", "--auto", "--yes")
        reg = self.w.Registry.load()
        reg.data["agent"] = "other"
        reg.save()
        with self.assertRaises(SystemExit) as cm:
            run(self.w, "new", "s3", "--task", "all", "--auto", "--yes")
        self.assertIn("not ready", str(cm.exception))

    def test_time_box_kills_the_process_tree(self):
        os.environ["FAKE_SLOW_KEYS"] = "-n3-"
        os.environ["FAKE_CHILD"] = "1"
        self.w.AUTO_BOX_SEC = 2.5
        t = time.time()
        out, rc = capture(self.w, "new", "s3", "--task", "all", "--auto", "--yes", "--name", "MIRA")
        self.assertLess(time.time() - t, 20)
        self.assertEqual(rc, 0)
        self.assertEqual(long_lines(out), [])
        self.assertRegex(out, r"T3 without skill +stopped 0:0[23]")
        rows = self.rows3()
        reg, runs = self.runs3()
        by = {("n" if self.w.is_control(r) else "t") + r["task"][-1]: k for k, r in runs.items()}
        self.assertEqual(rows[by["n3"]]["stopped"], "time")
        self.assertEqual(rows[by["n3"]]["overrun"], "no")          # never yes by design
        self.assertEqual(rows[by["n3"]]["grading"] in ("ungraded", "partial", "graded"), True)
        for k in ("t3", "t6", "n6"):
            self.assertEqual(rows[by[k]]["stopped"], "")
        # the child process of the killed run is dead: its heartbeat file no longer changes
        hb = os.path.join(runs[by["n3"]]["folder"], "heartbeat.txt")
        self.assertTrue(os.path.exists(hb))
        m1 = open(hb).read()
        time.sleep(0.6)
        self.assertEqual(open(hb).read(), m1)

    def test_ctrl_c_kills_all_and_keeps_finished(self):
        os.environ["FAKE_SLOW_KEYS"] = "-n3-,-n6-"
        os.environ["FAKE_CHILD"] = "1"
        real, first = time.sleep, []

        def fake_sleep(s):
            real(s)
            first.append(time.time()) if not first else None
            if time.time() - first[0] > 3.0:
                raise KeyboardInterrupt

        self.w._sleep = fake_sleep
        import signal
        seen = []
        real_kill = self.w.kill_tree

        def kill(proc):
            seen.append(signal.getsignal(signal.SIGINT))
            return real_kill(proc)

        self.w.kill_tree = kill
        before = signal.getsignal(signal.SIGINT)
        out, rc = capture(self.w, "new", "s3", "--task", "all", "--auto", "--yes", "--name", "MIRA")
        self.assertEqual(rc, 1)
        self.assertIn("Stopped with Ctrl+C. All agents are killed.", flat(out))
        self.assertIn("Each stopped run is saved as partial work.", flat(out))
        self.assertNotRegex(out, r"agents? (is|are) still working")   # the agents are dead
        self.assertEqual(long_lines(out), [])
        self.assertIn(signal.SIG_IGN, seen)                         # a second Ctrl+C cannot stop the kill loop
        self.assertEqual(signal.getsignal(signal.SIGINT), before)   # and the handler is back afterwards
        rows = self.rows3()
        reg, runs = self.runs3()
        self.assertEqual(len(rows), 4)
        self.assertEqual(reg.actives("3"), [])                      # the killed runs are finished as partial
        by = {("n" if self.w.is_control(r) else "t") + r["task"][-1]: k for k, r in runs.items()}
        for k in ("n3", "n6"):
            r = rows[by[k]]
            self.assertEqual(r["stopped"], "ctrl-c")
            self.assertIn(r["grading"], ("partial", "ungraded"))
            self.assertEqual(r["overrun"], "no")
            hb = os.path.join(runs[by[k]]["folder"], "heartbeat.txt")
            m1 = open(hb).read()
            time.sleep(0.6)
            self.assertEqual(open(hb).read(), m1)
        for k in ("t3", "t6"):
            self.assertEqual(rows[by[k]]["stopped"], "")
        self.assertIn("python workshop.py unlock 4", out)          # the box shows the last steps

    def test_status_block_format(self):
        items = [dict(label="T3 with skill", state="running", t0=100.0, end=None),
                 dict(label="T6 without skill", state="done", t0=100.0, end=100 + 401.0),
                 dict(label="T3 without skill", state="stopped", t0=100.0, end=100 + 600.0)]
        text = self.w.status_block(items, now=100 + 200.0)
        self.assertEqual(text.splitlines(), ["  T3 with skill     running 3:20",
                                             "  T6 without skill  done    6:41",
                                             "  T3 without skill  stopped 10:00"])
        self.assertEqual(long_lines(text), [])

    def test_launch_failure_is_reported_and_the_run_stays_active(self):
        with mock.patch.object(self.w, "start_agent", side_effect=OSError("boom")):
            out, rc = capture(self.w, "new", "s3", "--task", "T3", "--auto", "--yes")
        self.assertIn("could not start: boom", out)
        self.assertIn("RUN FAILED  T3 with skill: could not start: boom", flat(out))
        reg, _ = self.runs3()
        self.assertEqual(len(reg.actives("3")), 1)
        self.assertEqual(rc, 1)


class AutoClaude(AutoBase):
    agent = "claude"

    def test_claude_command_and_measure(self):
        out, rc = capture(self.w, "new", "s3", "--task", "T3", "--auto", "--yes")
        self.assertEqual(rc, 0)
        reg, runs = self.runs3()
        rid, run_ = next(iter(runs.items()))
        with open(os.path.join(run_["folder"], "argv.json")) as f:
            d = json.load(f)
        argv = d["argv"]
        self.assertEqual(argv[:2], ["-p", "--model"])               # no prompt in the arguments
        self.assertIn("Workshop run: " + rid, d["stdin"])           # it comes on stdin
        self.assertNotIn(d["stdin"], argv)
        self.assertEqual(argv[argv.index("--model") + 1], "haiku")
        self.assertEqual(argv[argv.index("--output-format") + 1], "json")
        self.assertEqual(argv[argv.index("--setting-sources") + 1], "project")
        self.assertEqual(argv[argv.index("--permission-mode") + 1], "dontAsk")
        tools = argv[argv.index("--allowedTools") + 1:]
        self.assertEqual(tools, self.w.CLAUDE_TOOLS)               # the last flag: nothing after the list
        for c in ("ls", "cat", "head", "tail", "grep", "wc", "find"):
            self.assertIn("Bash(%s:*)" % c, tools)
        self.assertIn("Bash(pwd)", tools)
        self.assertEqual(argv[argv.index("--append-system-prompt") + 1], self.w.CLAUDE_SYSTEM)
        self.assertIn("Do not chain commands with &&", self.w.CLAUDE_SYSTEM)
        self.assertNotIn("Shell rule", d["stdin"])                  # the task prompt itself is unchanged
        self.assertIn("Bash(bin/vesper:*)", tools)
        self.assertIn("Bash(./bin/vesper:*)", tools)
        ro = ("Bash(ls:*)", "Bash(cat:*)", "Bash(head:*)", "Bash(tail:*)", "Bash(grep:*)", "Bash(wc:*)",
              "Bash(find:*)", "Bash(pwd)", "Bash(mkdir out)", "Bash(mkdir -p out)")
        self.assertFalse([t for t in tools if t.startswith("Bash") and "vesper" not in t and t not in ro])  # no free Bash
        self.assertFalse([t for t in tools if "python" in t or t == "Bash"])
        self.assertIn("Claude may only run bin/vesper (and ls, cat, grep) and edit its run folder.", out)
        r = self.rows3()[rid]
        self.assertEqual(r["agent"], "claude")
        self.assertEqual(r["model"], "claude-haiku-5-5")
        self.assertEqual(r["tok_out"], 500)
        self.assertEqual(r["settings_confirmed"], "auto")
        self.assertEqual(long_lines(out), [])


class ClaudeUsageFixture(unittest.TestCase):
    """Real-shaped Claude Code usage (Windows run 2026-10-24, claude-haiku-4-5, 1 h cache writes): input 114,
    cache write 52926, cache read 591456, output 32605 (15115 of it thinking). The stream-json result said
    total_cost_usd 0.3281366; the tool must give the same."""

    def test_tokens_and_cost_match_claude_result(self):
        import measure as M
        tot = dict(i=114, cw=52926, cr=591456, o=32605)
        c = M.cost(tot, {"claude-haiku-4-5-20251001"})
        self.assertAlmostEqual(c, 0.3281366, places=4)
        self.assertEqual("%.2f" % c, "0.33")

    def test_log_reader_maps_usage_fields(self):
        import measure as M, fakes
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        os.environ["CLAUDE_CONFIG_DIR"] = d
        t = time.time()
        fakes.claude_log("sid1", d, [(t, 114, 591456, 52926, 32605, "")], model="claude-haiku-4-5-20251001")
        s = M.claude_sessions(t - 5, t + 5, "sid1")
        self.assertEqual(s[0]["tot"], dict(i=114, cw=52926, cr=591456, o=32605))
        self.assertAlmostEqual(M.cost(s[0]["tot"], s[0]["models"]), 0.3281366, places=4)


class AutoCursor(AutoBase):
    agent = "cursor"

    def test_cursor_run_measured_from_agent_output(self):
        out, rc = capture(self.w, "new", "s3", "--task", "all", "--auto", "--yes", "--name", "MIRA")
        self.assertEqual(rc, 0)
        self.assertEqual(long_lines(out), [])
        self.assertIn("Agent: cursor   Model: gpt-5.6-luna-high", out)
        rows = self.rows3()
        reg, runs = self.runs3()
        self.assertEqual(len(rows), 4)
        for rid, r in rows.items():
            self.assertEqual(r["agent"], "cursor")
            self.assertEqual(r["model"], "gpt-5.6-luna-high")
            self.assertEqual((r["tok_uncached"], r["tok_cache_read"], r["tok_cache_write"], r["tok_out"]),
                             (1200, 5000, 700, 340))
            self.assertEqual(r["measurement"], "log")
            self.assertRegex(r["cost_usd"], r"^0\.\d\d$")           # gpt-5.6-luna is in the price table
            self.assertEqual(r["isolation"], "not_detected")
            self.assertEqual(r["settings_confirmed"], "auto")
            with open(os.path.join(runs[rid]["folder"], "argv.json")) as f:
                argv = json.load(f)["argv"]
            self.assertEqual(argv[0], "-p")
            self.assertEqual(argv[argv.index("--output-format") + 1], "stream-json")
            self.assertNotIn("--force", argv)
            self.assertNotIn("--yolo", argv)
            self.assertIn("--trust", argv)
            if sys.platform != "win32":
                self.assertEqual(argv[argv.index("--sandbox") + 1], "enabled")
            else:
                self.assertNotIn("--sandbox", argv)
            with open(os.path.join(runs[rid]["folder"], ".cursor", "cli.json")) as f:
                self.assertEqual(json.load(f), {"permissions": {"allow": [
                    "Shell(bin/vesper)", "Shell(bin/vesper.exe)", "Read(./**)", "Write(./**)"], "deny": []}})
            self.assertEqual(argv[argv.index("--model") + 1], "gpt-5.6-luna-high")
            self.assertEqual(os.path.normcase(argv[argv.index("--workspace") + 1]),
                             os.path.normcase(runs[rid]["folder"]))

    def test_unknown_model_cost_unknown_and_auto_recorded(self):
        os.environ["FAKE_INIT_MODEL"] = "Auto"
        out, _ = capture(self.w, "new", "s3", "--task", "T3", "--auto", "--yes")
        r = next(iter(self.rows3().values()))
        self.assertEqual(r["model"], "auto")
        self.assertEqual(r["cost_usd"], "")
        self.assertIn("cost unknown", out)

    def test_free_plan_error_is_detected(self):
        os.environ["FAKE_FREEPLAN"] = "1"
        self.w.AUTO_MIN_SEC = 0                                     # the error text alone is enough
        out, rc = capture(self.w, "new", "s3", "--task", "T3", "--auto", "--yes")
        self.assertIn("RUN FAILED  T3 with skill: ActionRequiredError: Named models unavailable", flat(out))
        self.assertIn("Do the failed runs by hand: python workshop.py new s3 --task T3 (shows their pages)", flat(out))
        self.assertEqual(long_lines(out), [])
        self.assertEqual(rc, 1)
        reg, runs = self.runs3()
        rid = next(iter(runs))
        self.assertEqual([x["run_id"] for x in reg.actives("3")], [rid])     # kept active: do it by hand
        r = self.rows3()[rid]
        self.assertEqual(r["stopped"], "error")
        self.assertIn("Named models unavailable", r["error_note"])
        self.assertEqual((r["score"], r["grading"]), ("", "none"))          # never graded
        self.assertTrue(charts.flagged(r))
        self.assertIn("run failed", charts.flag_reasons(r))
        self.assertEqual(charts.outcome(r), "ungraded")

    def test_usage_limit_recorded_score_kept(self):
        os.environ["FAKE_LIMIT"] = "1"
        out, rc = capture(self.w, "new", "s3", "--task", "T3", "--auto", "--yes")
        r = next(iter(self.rows3().values()))
        self.assertEqual(r["stopped"], "limit")
        self.assertEqual(r["error_note"], "Cursor usage limit reached")
        self.assertNotEqual(r["grading"], "none")                           # the saved solution is graded
        for k in ("tok_uncached", "tok_cache_read", "tok_cache_write", "tok_out", "cost_usd"):
            self.assertEqual(r[k], "", k)

    def test_killed_run_tokens_and_cost_unknown(self):
        os.environ["FAKE_NO_USAGE"] = "1"
        capture(self.w, "new", "s3", "--task", "T3", "--auto", "--yes")
        r = next(iter(self.rows3().values()))
        self.assertEqual(r["measurement"], "log, stopped before the usage report")
        for k in ("tok_uncached", "tok_cache_read", "tok_cache_write", "tok_out", "cost_usd"):
            self.assertEqual(r[k], "", k)                                   # unknown, never 0

    def test_cmd_too_long_is_not_launched(self):
        if os.name != "nt":
            self.skipTest("cmd.exe limit: Windows only")
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        cmd = make_echo_cmd(d)
        os.environ["VESPER_CURSOR_EXE"] = cmd
        self.w.CMD_MAX = 300
        out, rc = capture(self.w, "new", "s3", "--task", "T3", "--auto", "--yes")
        self.assertIn("the command line is too long for cursor-agent.cmd", flat(out))
        self.assertIn("RUN FAILED", out)
        _, runs = self.runs3()
        self.assertFalse(os.path.exists(os.path.join(next(iter(runs.values()))["folder"], "argv.json")))

    def test_wrong_folder_from_init_cwd(self):
        # a stream-json file whose init cwd is not the run folder -> the wrong-folder check fires
        d = tempfile.mkdtemp()
        p = os.path.join(d, "agent-output.jsonl")
        with open(p, "w") as f:
            f.write(json.dumps({"type": "system", "subtype": "init", "cwd": os.path.join(d, "elsewhere"),
                                "model": "Auto", "session_id": "x"}) + "\n")
            f.write(json.dumps({"type": "result", "subtype": "success", "duration_ms": 1000,
                                "usage": {"inputTokens": 1, "outputTokens": 1}}) + "\n")
        outside = self.w.outside_workdirs([p], 0, time.time() + 10, os.path.join(d, "run"))
        self.assertEqual(len(outside), 1)
        inside = self.w.outside_workdirs([p], 0, time.time() + 10, os.path.join(d, "elsewhere"))
        self.assertEqual(inside, [])


@unittest.skipUnless(os.name == "nt", "cmd.exe launchers exist on Windows only")
class CmdLauncher(AutoBase):
    """B1: npm's claude.cmd / codex.cmd and cursor-agent.cmd go through cmd.exe. Every flag and the whole
    prompt must arrive (cmd.exe cuts an argument at the first new line)."""

    def launch(self, agent):
        reg = self.w.Registry.load()
        reg.data["agent"] = agent
        reg.save()
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        os.environ["VESPER_%s_EXE" % agent.upper()] = make_echo_cmd(d)
        out, rc = capture(self.w, "new", "s3", "--task", "T3", "--auto", "--yes")
        _, runs = self.runs3()
        rid, run_ = next(iter(runs.items()))
        with open(os.path.join(run_["folder"], "argv.json"), encoding="utf-8") as f:
            d = json.load(f)
        with open(os.path.join(run_["folder"], "PROMPT.txt"), encoding="utf-8") as f:
            prompt = f.read()
        return rid, run_, d, prompt, out

    def test_claude_cmd(self):
        rid, run_, d, prompt, out = self.launch("claude")
        self.assertEqual(d["argv"], ["-p", "--model", "haiku", "--output-format", "json", "--permission-mode",
                                     "dontAsk", "--setting-sources", "project", "--append-system-prompt",
                                     self.w.CLAUDE_SYSTEM, "--disallowedTools"] + self.w.CLAUDE_DENY
                         + ["--allowedTools"] + self.w.CLAUDE_TOOLS)
        self.assertEqual(d["stdin"], prompt)                        # the whole prompt, on stdin
        self.assertGreater(prompt.count("\n"), 1)
        self.assertEqual(self.rows3()[rid]["tok_out"], 500)         # the run was measured

    def test_codex_cmd(self):
        rid, run_, d, prompt, out = self.launch("codex")
        self.assertEqual(d["argv"], ["exec", "-m", "gpt-6-luna", "-c", "model_reasoning_effort=high", "-c",
                                     "features.memories=false", "-s", "workspace-write", "--skip-git-repo-check",
                                     "-C", run_["folder"], "-"])
        self.assertEqual(d["stdin"], prompt)

    def test_cursor_cmd(self):
        rid, run_, d, prompt, out = self.launch("cursor")
        sb = [] if sys.platform == "win32" else ["--sandbox", "enabled"]
        self.assertEqual(d["argv"], ["-p", "--model", "gpt-5.6-luna-high", "--output-format", "stream-json"] + sb
                         + ["--trust", "--workspace", run_["folder"], " ".join(prompt.split()).replace('"', "'")])
        self.assertIn("Workshop run: " + rid, d["argv"][-1])
        self.assertEqual(self.rows3()[rid]["tok_out"], 340)


class AutoConfirm(AutoBase):
    """M1: a warning per agent and "Start the 4 agents? [y/N]" before anything is created."""

    def test_no_terminal_and_no_yes_starts_nothing(self):
        out, rc = capture(self.w, "new", "s3", "--task", "all", "--auto", "--name", "MIRA")
        self.assertEqual(rc, 1)
        self.assertIn("--auto starts the 4 agents with no window. What they may do:", out)
        self.assertIn("  Codex starts in a sandbox: it may change files in its run folder only.", out)
        self.assertIn("Not started: no terminal to answer. Add --yes to start them.", out)
        self.assertEqual(self.runs3()[1], {})                       # no run folder was made
        self.assertEqual(long_lines(out), [])

    def test_question_default_is_no(self):
        asked, answer = [], [""]

        def ask(p, d=""):
            asked.append(p)
            return (answer[0] or d) if "Start" in p else d

        self.w.ask = ask
        with mock.patch.object(sys.stdin, "isatty", return_value=True):
            out, rc = capture(self.w, "new", "s3", "--task", "all", "--auto", "--name", "MIRA")
            self.assertEqual(rc, 1)
            self.assertIn("  Start the 4 agents? [y/N] ", asked)
            self.assertEqual(self.runs3()[1], {})
            answer[0] = "y"
            out, rc = capture(self.w, "new", "s3", "--task", "T3", "--auto")
        self.assertIn("  Start the agent? [y/N] ", asked)
        self.assertEqual(rc, 0)
        self.assertEqual(len(self.rows3()), 1)

    def test_warning_lines_per_agent(self):
        for ag, text in self.w.AUTO_SAFETY.items():
            self.assertLessEqual(len("  " + text), 72, ag)
        self.assertIn("only run bin/vesper", self.w.AUTO_SAFETY["cursor"])


class AutoErrors(AutoBase):
    """M2: an agent that fails at once gives no data row: stopped=error, not graded, the run stays active."""

    def test_quick_exit_fails_and_the_learner_does_it_by_hand(self):
        self.w.AUTO_MIN_SEC = 60                                    # the fake agent ends after 0.2 s
        out, rc = capture(self.w, "new", "s3", "--task", "all", "--auto", "--yes", "--name", "MIRA")
        self.assertEqual(rc, 1)
        self.assertEqual(len(re.findall(r"RUN FAILED  [^:]+: the agent ended after \d+ s \(exit code 0\)", flat(out))), 4)
        self.assertEqual(flat(out).count("Do the failed runs by hand: python workshop.py new s3 --task all "
                                         "(shows their pages)"), 1)          # the fix line once, not per run
        self.assertIn("4 runs failed. Do them by hand:", flat(out))
        self.assertNotIn("FINISHED", out)
        self.assertEqual(long_lines(out), [])
        reg, runs = self.runs3()
        self.assertEqual(len(reg.actives("3")), 4)
        for rid, r in self.rows3().items():
            self.assertEqual(r["stopped"], "error")
            self.assertIn("the agent ended after", r["error_note"])
            self.assertEqual((r["score"], r["grading"], r["solution_sha"]), ("", "none", ""))
            self.assertEqual(r["revision"], 1)
        # by hand: the pages make the runs manual; `done` then writes a normal row (a new revision)
        out2, _ = capture(self.w, "new", "s3", "--task", "all")
        self.assertEqual(out2.count("Workshop run: s3-"), 4)
        reg, runs = self.runs3()
        rid = next(iter(runs))
        self.assertEqual(runs[rid]["mode"], "manual")
        self.assertNotIn("auto", runs[rid])
        run(self.w, "done", rid, "--no-form")
        r = self.rows3()[rid]
        self.assertEqual((r["stopped"], r["error_note"]), ("", ""))
        self.assertEqual(r["revision"], 2)
        self.assertNotEqual(r["settings_confirmed"], "auto")

    def test_error_text_note_is_short_and_anonymous(self):
        secret = os.path.join(self.home, "user", ".codex", "auth.json")
        os.environ["FAKE_FAIL"] = "Error: Authentication required (%s) " % secret + "x" * 300
        out, rc = capture(self.w, "new", "s3", "--task", "T3", "--auto", "--yes")
        r = next(iter(self.rows3().values()))
        self.assertEqual(r["stopped"], "error")
        self.assertTrue(r["error_note"].startswith("Error: Authentication required (~"), r["error_note"])
        self.assertNotIn(self.home, r["error_note"])
        self.assertLessEqual(len(r["error_note"]), 200)
        self.assertNotIn(secret, out)
        self.assertEqual(self.w.ROW_FIELDS[-2:], ["stopped", "error_note"])

    def test_nonzero_exit_without_tool_calls(self):
        os.environ["FAKE_FAIL"] = "something odd happened"
        out, rc = capture(self.w, "new", "s3", "--task", "T3", "--auto", "--yes")
        r = next(iter(self.rows3().values()))
        self.assertEqual(r["stopped"], "error")
        self.assertEqual(r["error_note"], "exit code 1 and no tool calls")

    def test_orphans_of_an_ended_agent_are_killed(self):
        os.environ["FAKE_CHILD"] = "1"                              # the agent ends; its child would live on
        capture(self.w, "new", "s3", "--task", "T3", "--auto", "--yes")
        _, runs = self.runs3()
        hb = os.path.join(next(iter(runs.values()))["folder"], "heartbeat.txt")
        self.assertTrue(os.path.exists(hb))
        m1 = open(hb).read()
        time.sleep(0.6)
        self.assertEqual(open(hb).read(), m1)


class AutoResume(AutoBase):
    """M5: a resume with --auto starts only --auto runs that are not done and that no live agent holds."""

    def failed_run(self):
        with mock.patch.object(self.w, "start_agent", side_effect=OSError("boom")):
            capture(self.w, "new", "s3", "--task", "T3", "--auto", "--yes")
        _, runs = self.runs3()
        rid, r = next(iter(runs.items()))
        self.assertEqual(r["mode"], "auto")
        return rid, r

    def write_lock(self, folder, pid):
        with open(os.path.join(folder, ".agent.lock"), "w") as f:
            json.dump({"pid": pid, "start": time.time(), "mode": "auto"}, f)

    def test_manual_run_is_never_launched(self):
        capture(self.w, "new", "s3", "--task", "T3")                # the learner pastes the prompt by hand
        _, runs = self.runs3()
        rid, r = next(iter(runs.items()))
        self.assertEqual(r["mode"], "manual")
        out, rc = capture(self.w, "new", "s3", "--task", "T3", "--auto", "--yes")
        self.assertEqual(rc, 1)
        self.assertIn("you run it by hand", out)
        self.assertIn("python workshop.py done " + rid, out)
        self.assertFalse(os.path.exists(os.path.join(r["folder"], "argv.json")))
        reg, runs = self.runs3()
        self.assertNotEqual(runs[rid].get("settings_confirmed"), "auto")
        self.assertEqual(len(reg.actives("3")), 1)

    def test_failed_auto_run_is_relaunched_with_a_lock(self):
        rid, r = self.failed_run()
        out, rc = capture(self.w, "new", "s3", "--task", "T3", "--auto", "--yes")
        self.assertEqual(rc, 0)
        self.assertIn("FINISHED", out)
        lk = self.w.read_lock(r["folder"])
        self.assertEqual((lk["pid"], lk["mode"]), (os.getpid(), "auto"))
        row = self.rows3()[rid]
        self.assertEqual((row["stopped"], row["error_note"]), ("", ""))
        self.assertEqual(row["revision"], 2)                        # one more than the failed row

    def test_live_lock_is_never_launched_into(self):
        import subprocess
        rid, r = self.failed_run()
        p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        self.addCleanup(p.kill)
        self.write_lock(r["folder"], p.pid)
        out, rc = capture(self.w, "new", "s3", "--task", "T3", "--auto", "--yes")
        self.assertIn("an agent still works on it in another window", out)
        self.assertFalse(os.path.exists(os.path.join(r["folder"], "argv.json")))
        out2, _ = capture(self.w, "new", "s3", "--task", "T3")      # the manual pages do not show it either
        self.assertIn("in another window", out2)
        self.assertNotIn("Workshop run: " + rid, out2)

    def test_stale_lock_with_partial_work_asks_default_no(self):
        import subprocess
        rid, r = self.failed_run()
        p = subprocess.Popen([sys.executable, "-c", "pass"])
        p.wait()
        self.write_lock(r["folder"], p.pid)                         # its tool is gone: the lock is stale
        os.makedirs(os.path.join(r["folder"], "solutions"), exist_ok=True)
        with open(os.path.join(r["folder"], "solutions", "T3.vsa"), "w") as f:
            f.write("; partial\n")
        asked = []
        real = self.w.ask
        self.w.ask = lambda q, d="": asked.append(q) or real(q, d)
        out, rc = capture(self.w, "new", "s3", "--task", "T3", "--auto", "--yes")
        self.assertTrue(any("has work from an earlier agent" in q and "[y/N]" in q for q in asked))
        self.assertFalse(os.path.exists(os.path.join(r["folder"], "argv.json")))
        self.w.ask = lambda q, d="": "y" if "earlier agent" in q else d
        out, rc = capture(self.w, "new", "s3", "--task", "T3", "--auto", "--yes")
        self.assertTrue(os.path.exists(os.path.join(r["folder"], "argv.json")))

    def test_pid_alive(self):
        self.assertTrue(self.w.pid_alive(os.getpid()))
        self.assertFalse(self.w.pid_alive(0))
        self.assertFalse(self.w.pid_alive("x"))


class CursorReader(unittest.TestCase):
    def write(self, lines):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "agent-output.jsonl")
        with open(p, "w") as f:
            for x in lines:
                f.write(json.dumps(x) + "\n")
        self.addCleanup(shutil.rmtree, d, True)
        return p

    def test_tokens_model_cwd_time_tools(self):
        p = self.write([
            {"type": "system", "subtype": "init", "cwd": "C:\\runs\\s3-aaaa-t3-bbbb", "session_id": "sid1",
             "model": "gpt-5.6-luna-high"},
            {"type": "tool_call", "subtype": "started", "timestamp_ms": 1000000,
             "tool_call": {"shellToolCall": {"args": {"command": "bin/vesper run solutions/T3.vsa"}}}},
            {"type": "tool_call", "subtype": "completed", "timestamp_ms": 1002000,
             "tool_call": {"shellToolCall": {"args": {"command": "bin/vesper run solutions/T3.vsa"}}}},
            {"type": "tool_call", "subtype": "started", "timestamp_ms": 1003000,
             "tool_call": {"shellToolCall": {"args": {"command": "bin/vesper asm solutions/T3.vsa"}}}},
            {"type": "assistant", "timestamp_ms": 1060000, "message": {}},
            {"type": "result", "subtype": "success", "duration_ms": 60000,
             "usage": {"inputTokens": 10, "outputTokens": 20, "cacheReadTokens": 30, "cacheWriteTokens": 40}},
        ])
        (c,) = measure.cursor_sessions(p)
        self.assertEqual(c["tot"], dict(i=10, cr=30, cw=40, o=20))
        self.assertEqual(c["models"], {"gpt-5.6-luna-high"})
        self.assertEqual(c["cwd"], "C:\\runs\\s3-aaaa-t3-bbbb")
        self.assertEqual((c["first"], c["last"]), (1000.0, 1060.0))
        self.assertEqual(len(c["tools"]), 2)
        self.assertEqual(c["emulator_runs"], 1)                    # `vesper run` only; asm is free
        self.assertTrue(c["complete"])
        self.assertEqual(c["sid"], "sid1")

    def test_duration_is_not_a_time_stamp(self):
        # no timestamp_ms at all: duration_ms gives a separate value, never first=0 / last=duration (epoch)
        p = self.write([{"type": "system", "subtype": "init", "cwd": "/x", "model": "Auto", "session_id": "s"},
                        {"type": "result", "subtype": "success", "duration_ms": 60000,
                         "usage": {"inputTokens": 1, "outputTokens": 1}}])
        (c,) = measure.cursor_sessions(p)
        self.assertEqual((c["first"], c["last"], c["duration"]), (None, None, 60.0))
        w, _ = fresh_ws()
        run_ = {"session": {"agent": "cursor", "path": p}, "folder": os.path.dirname(p)}
        self.assertEqual(w.measure_stage(run_, 1000.0, 1100.0)["elapsed_min"], "1.0")
        p2 = self.write([{"type": "system", "subtype": "init", "cwd": "/x", "model": "Auto"},
                         {"type": "result", "duration_ms": 9e9, "usage": {"inputTokens": 1}}])
        run_ = {"session": {"agent": "cursor", "path": p2}, "folder": os.path.dirname(p2)}
        self.assertEqual(w.measure_stage(run_, 1000.0, 1100.0)["elapsed_min"], "")   # longer than the wall time

    def test_auto_model_and_incomplete_run(self):
        p = self.write([{"type": "system", "subtype": "init", "cwd": "/x", "model": "Auto", "session_id": "s"},
                        {"type": "assistant", "timestamp_ms": 5000, "message": {}}])
        (c,) = measure.cursor_sessions(p)
        self.assertEqual(c["models"], {"auto"})
        self.assertFalse(c["complete"])
        self.assertEqual(c["tot"], dict(i=0, cr=0, cw=0, o=0))
        self.assertEqual(measure.cursor_sessions(self.write([{"type": "assistant"}])), [])

    def test_isolation_scan_reads_tool_calls(self):
        w, home = fresh_ws()
        folder = os.path.join(home, "vesper-runs", "s3-aaaa-t3-bbbb")
        other = os.path.join(home, "vesper-runs", "s1-cccc")
        os.makedirs(folder)
        t = time.time()
        p = self.write([
            {"type": "system", "subtype": "init", "cwd": folder, "model": "Auto"},
            {"type": "tool_call", "subtype": "started", "timestamp_ms": int(t * 1000),
             "tool_call": {"shellToolCall": {"args": {"command": "cat " + other + "/solutions/T3.vsa"}}}}])
        st, note = w.detect_outside_reads([p], t - 5, t + 5, folder)
        self.assertEqual(st, "detected")
        p2 = self.write([
            {"type": "system", "subtype": "init", "cwd": folder, "model": "Auto"},
            {"type": "tool_call", "subtype": "started", "timestamp_ms": int(t * 1000),
             "tool_call": {"shellToolCall": {"args": {"command": "cat solutions/T3.vsa"}}}}])
        self.assertEqual(w.detect_outside_reads([p2], t - 5, t + 5, folder)[0], "not_detected")


class DoctorAuto(unittest.TestCase):
    def setUp(self):
        self.saved = {k: os.environ.get(k) for k in ENV_KEYS + ("VESPER_DOCTOR_SKIP_CLI",)}
        self.w, self.home = fresh_ws()
        os.environ.pop("VESPER_DOCTOR_SKIP_CLI", None)
        os.environ["LOCALAPPDATA"] = os.path.join(self.home, "localappdata")
        for k in ("VESPER_CODEX_EXE", "VESPER_CURSOR_EXE", "VESPER_CLAUDE_EXE"):
            os.environ.pop(k, None)

    def tearDown(self):
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def doctor(self, agent, *extra):
        out, _ = capture(self.w, "doctor", "--agent", agent, "--alias", "t", *extra)
        return out

    def test_ready_agents_and_ready_flag(self):
        os.environ["VESPER_CODEX_EXE"] = FAKE
        os.environ["VESPER_CURSOR_EXE"] = FAKE
        with mock.patch.object(self.w.shutil, "which", return_value=None):
            out = self.doctor("codex")
        self.assertIn("--auto codex: ready (codex-cli 0.163.0)", out)
        self.assertNotIn("--auto cursor", out)                      # only the learner's agent CLI is started
        self.assertNotIn("--auto claude", out)
        reg = self.w.Registry.load()
        self.assertEqual(reg.data["auto_ready"], {"codex": True})
        self.assertEqual(reg.data["doctor"]["level"], 0)           # an unready --auto never turns doctor yellow
        with mock.patch.object(self.w.shutil, "which", return_value=None):
            out = self.doctor("claude")
        self.assertIn("--auto claude: NOT ready - claude was not found", flat(out))
        self.assertEqual(self.w.Registry.load().data["auto_ready"], {"claude": False})

    def test_only_the_chosen_cli_is_started(self):
        calls = []
        real = self.w.auto_ready
        self.w.auto_ready = lambda ag: calls.append(ag) or real(ag)
        os.environ["VESPER_CURSOR_EXE"] = FAKE
        with mock.patch.object(self.w.shutil, "which", return_value=None):
            self.doctor("cursor")
            self.doctor("other")
        self.assertEqual(calls, ["cursor"])

    def test_doctor_auto_lines_are_short(self):
        os.environ["VESPER_CURSOR_EXE"] = FAKE
        os.environ["FAKE_FREEPLAN"] = "1"
        rules = os.path.join(self.home, "user", ".cursor", "rules")
        os.makedirs(rules)
        with open(os.path.join(rules, "x.mdc"), "w") as f:
            f.write("---\nalwaysApply: true\n---\n")
        with mock.patch.object(self.w.shutil, "which", return_value=None):
            lines, _ = self.w.doctor_auto_lines("cursor", True)
            os.environ.pop("VESPER_CURSOR_EXE")
            lines += self.w.doctor_auto_lines("cursor")[0]
        os.environ["FAKE_VERSION"] = "codex-cli 0.154.0"
        with mock.patch.object(self.w.shutil, "which", side_effect=lambda n: FAKE if n == "codex" else None):
            lines += self.w.doctor_auto_lines("codex")[0]
        text = "\n".join(lines)
        self.assertIn("Named models need a paid plan.", text)
        self.assertIn("open a NEW PowerShell window" if os.name == "nt" else "agent login", text)
        self.assertEqual(long_lines(text), [])

    def test_check_auto_timeout_kills_the_tree(self):
        os.environ["VESPER_CURSOR_EXE"] = FAKE
        os.environ["FAKE_SLEEP"] = "30"
        os.environ["FAKE_CHILD"] = "1"                              # a grandchild that would hold a pipe
        self.w.AUTO_CHECK_SEC = 1
        t = time.time()
        ok, text = self.w.check_auto_run("cursor")
        self.assertLess(time.time() - t, 15)
        self.assertFalse(ok)
        self.assertIn("no answer in 1 s", text)

    def test_cursor_not_logged_in_and_install_help(self):
        os.environ["VESPER_CURSOR_EXE"] = FAKE
        os.environ["FAKE_LOGIN"] = "no"
        with mock.patch.object(self.w.shutil, "which", return_value=None):
            out = self.doctor("cursor")
        self.assertIn("--auto cursor: NOT ready - Cursor is not logged in", out)
        self.assertIn("agent login", out)
        os.environ.pop("VESPER_CURSOR_EXE")
        with mock.patch.object(self.w.shutil, "which", return_value=None):
            out = self.doctor("cursor")
        self.assertIn("cursor-agent was not found", out)
        if os.name == "nt":
            self.assertIn("irm 'https://cursor.com/install?win32=true' | iex", out)
        else:
            self.assertIn("https://cursor.com/install", out)
        self.assertNotIn("%", "".join(l for l in out.splitlines() if "install" in l))
        self.assertIn("User Rules", out)                           # the one-line reminder

    def test_cursor_always_apply_rules_warn(self):
        os.environ["VESPER_CURSOR_EXE"] = FAKE
        rules = os.path.join(self.home, "user", ".cursor", "rules")
        os.makedirs(rules)
        with open(os.path.join(rules, "x.mdc"), "w") as f:
            f.write("---\nalwaysApply: true\n---\nBe nice.\n")
        with mock.patch.object(self.w.shutil, "which", return_value=None):
            out = self.doctor("cursor")
        self.assertIn("alwaysApply rules in", out)
        self.assertEqual(self.w.Registry.load().data["doctor"]["level"], 1)

    def test_codex_on_path_too_old(self):
        os.environ["FAKE_VERSION"] = "codex-cli 0.154.0"
        os.environ.pop("VESPER_CODEX_EXE", None)
        with mock.patch.object(self.w.shutil, "which", side_effect=lambda n: FAKE if n == "codex" else None):
            out = self.doctor("codex")
        self.assertIn("codex on PATH is too old (codex-cli 0.154.0); it needs 0.163 or newer", flat(out))
        os.environ["FAKE_VERSION"] = "codex-cli 0.170.2"
        with mock.patch.object(self.w.shutil, "which", side_effect=lambda n: FAKE if n == "codex" else None):
            out = self.doctor("codex")
        self.assertIn("--auto codex: ready (codex-cli 0.170.2)", out)

    def test_check_auto_ok_free_plan_and_error(self):
        os.environ["VESPER_CURSOR_EXE"] = FAKE
        with mock.patch.object(self.w.shutil, "which", return_value=None):
            out = self.doctor("cursor", "--check-auto")
            self.assertIn("--check-auto cursor (gpt-5.6-luna-high): PASS", out)
            os.environ["FAKE_FREEPLAN"] = "1"
            out = self.doctor("cursor", "--check-auto")
            self.assertIn("--check-auto cursor (gpt-5.6-luna-high): free plan: only Auto", out)
            self.assertEqual(self.w.Registry.load().data["auto_ready"]["cursor"], False)
            os.environ.pop("FAKE_FREEPLAN")
            self.w.AUTO_CHECK_SEC = 0.01
            out = self.doctor("cursor", "--check-auto")
            self.assertIn("error: no answer", out)

    def test_harvest_box_puts_auto_first_only_when_ready(self):
        os.environ["VESPER_CODEX_EXE"] = FAKE
        with mock.patch.object(self.w.shutil, "which", return_value=None):
            self.doctor("codex")
        reg = self.w.Registry.load()
        box = io.StringIO()
        with contextlib.redirect_stdout(box):
            self.w.s3_choice_box(reg, "stage 3. Choose one:")
        lines = box.getvalue()
        self.assertLess(lines.index("--task all --auto"), lines.index("--task all  "))
        self.assertEqual(long_lines(lines), [])
        reg.data["auto_ready"] = {"codex": False}
        box = io.StringIO()
        with contextlib.redirect_stdout(box):
            self.w.s3_choice_box(reg, "stage 3. Choose one:")
        lines = box.getvalue()
        self.assertGreater(lines.index("--task all --auto"), lines.index("--task all  "))


class ChartsAuto(unittest.TestCase):
    def test_auto_counts_as_confirmed(self):
        self.assertFalse(charts.unconfirmed({"stage": "3", "settings_confirmed": "auto"}))
        self.assertFalse(charts.flagged({"stage": "3", "settings_confirmed": "auto", "score": "100",
                                         "overrun": "no", "isolation": "not_detected"}))
        self.assertTrue(charts.unconfirmed({"stage": "3", "settings_confirmed": "not_asked"}))
        self.assertTrue(charts.unconfirmed({"stage": "3", "settings_confirmed": ""}))

    def test_stopped_and_failed_runs(self):
        self.assertEqual(charts.FIELDS[-2:], ["stopped", "error_note"])
        bad = {"stage": "3", "settings_confirmed": "auto", "score": "100", "grading": "graded", "stopped": "error",
               "error_note": "Authentication required", "task": "T3"}
        self.assertEqual(charts.flag_reasons(bad), ["run failed"])
        self.assertEqual(charts.outcome(bad), "ungraded")          # never a pass
        self.assertEqual(charts.counts([bad])["pass"], 0)
        ok = dict(bad, stopped="ctrl-c", grading="partial")
        self.assertEqual(charts.outcome(ok), "pass")
        rows = charts.expand_all_results("vesper-results v1\nrun_id=x;stage=3;stopped=error;error_note=a%3Bb")
        x = {f: rows[0].get(f, "") for f in charts.FIELDS}
        self.assertEqual((x["stopped"], x["error_note"]), ("error", "a;b"))


class ResumeStage3(unittest.TestCase):
    def setUp(self):
        old = os.environ.get("LOCALAPPDATA")
        self.addCleanup(lambda: os.environ.__setitem__("LOCALAPPDATA", old) if old is not None
                        else os.environ.pop("LOCALAPPDATA", None))
        self.w, self.home = fresh_ws()
        self.s1, _ = fakes.ready_for_s3(self.w)

    def test_prompt_txt_saved_at_creation(self):
        out, _ = capture(self.w, "new", "s3", "--task", "all", "--name", "MIRA")
        reg = self.w.Registry.load()
        runs = [r for r in reg.data["runs"].values() if r.get("stage") == "3"]
        self.assertEqual(len(runs), 4)
        for r in runs:
            with open(os.path.join(r["folder"], "PROMPT.txt"), encoding="utf-8") as f:
                text = f.read()
            self.assertIn("Workshop run: ", text)
            self.assertIn(text.rstrip("\n").splitlines()[0], out)   # the same prompt that the page showed
            self.assertEqual(text.rstrip("\n").splitlines()[2].startswith("Write the game"), True)
            self.assertEqual("vesper16" in text, r["skill_source"] != "none")

    def test_second_command_shows_pages_again_and_lists_done(self):
        out1, _ = capture(self.w, "new", "s3", "--task", "all", "--name", "MIRA")
        reg = self.w.Registry.load()
        acts = [x["run_id"] for x in reg.actives("3")]
        self.assertEqual(len(acts), 4)
        out2, rc = capture(self.w, "new", "s3", "--task", "all")
        self.assertEqual(rc, 0)
        self.assertIn("Stage 3 is already set up. Showing its pages again.", out2)
        self.assertEqual(long_lines(out2), [])
        for rid in acts:
            self.assertIn("Workshop run: " + rid, out2)
            self.assertIn("python workshop.py done " + rid, out2)
        order = re.findall(r"Start in this order: (.*)", flat(out2))[0]
        self.assertEqual(len(self.w.Registry.load().actives("3")), 4)          # nothing new was created
        # the pages follow the start order of the first command
        first = [m for m in re.findall(r"RUN (\d) of 4  (T\d [A-Z]*[^\n]*)", out1)]
        again = [m for m in re.findall(r"RUN (\d) of 4  (T\d [A-Z]*[^\n]*)", out2)]
        self.assertEqual(first, again)
        # one run finishes: it is listed as done, not shown
        done_id = acts[0]
        run(self.w, "done", done_id, "--no-form")
        out3, _ = capture(self.w, "new", "s3", "--task", "all")
        self.assertIn("Already done:", out3)
        self.assertIn(done_id, out3)
        self.assertNotIn("Workshop run: " + done_id, out3)
        self.assertEqual(out3.count("RUN "), 3)
        self.assertIn("RUN 3 of 3", out3)

    def test_ctrl_c_in_the_page_gate(self):
        self.w.gate_on = lambda: True

        def ask(prompt, default=""):
            raise KeyboardInterrupt

        self.w.ask = ask
        out, rc = capture(self.w, "new", "s3", "--task", "all", "--name", "MIRA")
        self.assertEqual(rc, 130)
        self.assertIn("Stopped. Run the same command again to see the pages.", out)
        reg = self.w.Registry.load()
        self.assertEqual(len(reg.actives("3")), 4)                  # the runs exist; nothing is lost
        self.w.gate_on = lambda: False
        out2, rc2 = capture(self.w, "new", "s3", "--task", "all")
        self.assertEqual(rc2, 0)
        self.assertIn("Showing its pages again", out2)
        self.assertEqual(out2.count("Workshop run: s3-"), 4)

    def test_single_task_resume(self):
        capture(self.w, "new", "s3", "--task", "T3")
        out, rc = capture(self.w, "new", "s3", "--task", "T3")
        self.assertEqual(rc, 0)
        self.assertIn("Showing its pages again", out)
        self.assertEqual(out.count("Workshop run: s3-"), 1)

    def test_auto_resume_starts_only_runs_not_done(self):
        for k in ("VESPER_CODEX_EXE",):
            os.environ[k] = FAKE
        os.environ["FAKE_SLEEP"] = "0.2"
        self.addCleanup(os.environ.pop, "VESPER_CODEX_EXE", None)
        self.addCleanup(os.environ.pop, "FAKE_SLEEP", None)
        os.environ["LOCALAPPDATA"] = os.path.join(self.home, "localappdata")
        self.w.AUTO_TICK, self.w.AUTO_POLL, self.w.AUTO_BOX_SEC = 0.3, 0.05, 30
        capture(self.w, "new", "s3", "--task", "all", "--name", "MIRA")      # manual pages first
        reg = self.w.Registry.load()
        acts = [x["run_id"] for x in reg.actives("3")]
        run(self.w, "done", acts[0], "--no-form")
        out, rc = capture(self.w, "new", "s3", "--task", "all", "--auto", "--yes")
        self.assertEqual(rc, 1)
        self.assertIn("Showing its pages again", out)
        self.assertEqual(out.count("you run it by hand"), 3)        # manual runs: --auto never starts them
        self.assertIn("No run can be started by --auto now.", out)
        self.assertEqual(out.count("FINISHED"), 0)
        self.assertEqual(len(self.w.Registry.load().actives("3")), 3)
        started = [r["folder"] for r in self.w.Registry.load().data["runs"].values()
                   if r.get("stage") == "3" and os.path.exists(os.path.join(r["folder"], "argv.json"))]
        self.assertEqual(started, [])

    def test_auto_resume_after_failed_runs_starts_only_those(self):
        os.environ["VESPER_CODEX_EXE"] = FAKE
        os.environ["FAKE_SLEEP"] = "0.2"
        self.addCleanup(os.environ.pop, "VESPER_CODEX_EXE", None)
        self.addCleanup(os.environ.pop, "FAKE_SLEEP", None)
        os.environ["LOCALAPPDATA"] = os.path.join(self.home, "localappdata")
        self.w.AUTO_TICK, self.w.AUTO_POLL, self.w.AUTO_BOX_SEC = 0.3, 0.05, 30
        self.w.AUTO_MIN_SEC = 60                                    # all 4 end at once: all 4 fail
        capture(self.w, "new", "s3", "--task", "all", "--auto", "--yes", "--name", "MIRA")
        self.assertEqual(len(self.w.Registry.load().actives("3")), 4)
        acts = [x["run_id"] for x in self.w.Registry.load().actives("3")]
        self.w.AUTO_MIN_SEC = 0
        out, rc = capture(self.w, "new", "s3", "--task", "all", "--auto", "--yes")
        self.assertEqual(rc, 0)
        self.assertEqual(out.count("FINISHED"), 4)
        self.assertEqual(self.w.Registry.load().actives("3"), [])
        rows = {r["run_id"]: r for r in self.w.Registry.load().data["rows"].values() if r["stage"] == "3"}
        self.assertEqual(sorted(rows), sorted(acts))
        self.assertTrue(all(r["stopped"] == "" and r["revision"] == 2 for r in rows.values()))


if __name__ == "__main__":
    unittest.main()
