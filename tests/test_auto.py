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
            "LOCALAPPDATA")


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
        out, rc = capture(self.w, "new", "s3", "--task", "all", "--auto", "--name", "MIRA")
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
        capture(self.w, "new", "s3", "--task", "T3", "--auto")
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
        self.assertIn("Workshop run: " + rid, argv[-1])
        self.assertEqual(os.path.normcase(d["cwd"]), os.path.normcase(run_["folder"]))

    def test_model_override(self):
        capture(self.w, "new", "s3", "--task", "T3", "--auto", "--model", "gpt-6-sol")
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
            run(self.w, "new", "s1", "--auto")
        reg = self.w.Registry.load()
        reg.data["agent"] = "other"
        reg.save()
        with self.assertRaises(SystemExit) as cm:
            run(self.w, "new", "s3", "--task", "all", "--auto")
        self.assertIn("not ready", str(cm.exception))

    def test_time_box_kills_the_process_tree(self):
        os.environ["FAKE_SLOW_KEYS"] = "-n3-"
        os.environ["FAKE_CHILD"] = "1"
        self.w.AUTO_BOX_SEC = 2.5
        t = time.time()
        out, rc = capture(self.w, "new", "s3", "--task", "all", "--auto", "--name", "MIRA")
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
        out, rc = capture(self.w, "new", "s3", "--task", "all", "--auto", "--name", "MIRA")
        self.assertEqual(rc, 1)
        self.assertIn("Stopped with Ctrl+C. All agents are killed. Finished results are saved.", flat(out))
        self.assertEqual(long_lines(out), [])
        rows = self.rows3()
        reg, runs = self.runs3()
        self.assertEqual(len(rows), 2)                              # the two quick runs are finished
        self.assertEqual(len(reg.actives("3")), 2)                  # the killed ones stay active: `done` works
        for r in rows.values():
            self.assertEqual(r["stopped"], "")
        for k, r in runs.items():
            if k not in rows:
                hb = os.path.join(r["folder"], "heartbeat.txt")
                m1 = open(hb).read()
                time.sleep(0.6)
                self.assertEqual(open(hb).read(), m1)

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
            out, rc = capture(self.w, "new", "s3", "--task", "T3", "--auto")
        self.assertIn("could not start: boom", out)
        reg, _ = self.runs3()
        self.assertEqual(len(reg.actives("3")), 1)


class AutoClaude(AutoBase):
    agent = "claude"

    def test_claude_command_and_measure(self):
        out, rc = capture(self.w, "new", "s3", "--task", "T3", "--auto")
        self.assertEqual(rc, 0)
        reg, runs = self.runs3()
        rid, run_ = next(iter(runs.items()))
        with open(os.path.join(run_["folder"], "argv.json")) as f:
            argv = json.load(f)["argv"]
        self.assertEqual(argv[0], "-p")
        self.assertIn("Workshop run: " + rid, argv[1])
        self.assertEqual(argv[argv.index("--model") + 1], "haiku")
        self.assertEqual(argv[argv.index("--output-format") + 1], "json")
        self.assertEqual(argv[argv.index("--setting-sources") + 1], "project")
        self.assertEqual(argv[argv.index("--permission-mode") + 1], "acceptEdits")
        r = self.rows3()[rid]
        self.assertEqual(r["agent"], "claude")
        self.assertEqual(r["model"], "claude-haiku-5-5")
        self.assertEqual(r["tok_out"], 500)
        self.assertEqual(r["settings_confirmed"], "auto")
        self.assertEqual(long_lines(out), [])


class AutoCursor(AutoBase):
    agent = "cursor"

    def test_cursor_run_measured_from_agent_output(self):
        out, rc = capture(self.w, "new", "s3", "--task", "all", "--auto", "--name", "MIRA")
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
            self.assertIn("--force", argv)
            self.assertIn("--trust", argv)
            self.assertEqual(argv[argv.index("--model") + 1], "gpt-5.6-luna-high")
            self.assertEqual(os.path.normcase(argv[argv.index("--workspace") + 1]),
                             os.path.normcase(runs[rid]["folder"]))

    def test_unknown_model_cost_unknown_and_auto_recorded(self):
        os.environ["FAKE_INIT_MODEL"] = "Auto"
        out, _ = capture(self.w, "new", "s3", "--task", "T3", "--auto")
        r = next(iter(self.rows3().values()))
        self.assertEqual(r["model"], "auto")
        self.assertEqual(r["cost_usd"], "")
        self.assertIn("Cost unknown", out)

    def test_free_plan_error_is_detected(self):
        os.environ["FAKE_FREEPLAN"] = "1"
        out, rc = capture(self.w, "new", "s3", "--task", "T3", "--auto")
        self.assertIn("Cursor says: free plan: only Auto.", flat(out))
        self.assertEqual(long_lines(out), [])

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
        self.assertIn("--auto cursor: ready", out)
        self.assertRegex(out, r"--auto claude: NOT ready - claude was not found")
        reg = self.w.Registry.load()
        self.assertEqual(reg.data["auto_ready"], {"codex": True, "claude": False, "cursor": True})
        self.assertEqual(reg.data["doctor"]["level"], 0)           # an unready --auto never turns doctor yellow

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
        self.assertIn("codex on PATH is too old (codex-cli 0.154.0); it needs 0.163 or newer", out)
        os.environ["FAKE_VERSION"] = "codex-cli 0.170.2"
        with mock.patch.object(self.w.shutil, "which", side_effect=lambda n: FAKE if n == "codex" else None):
            out = self.doctor("codex")
        self.assertIn("--auto codex: ready (codex-cli 0.170.2)", out)

    def test_check_auto_ok_free_plan_and_error(self):
        os.environ["VESPER_CURSOR_EXE"] = FAKE
        with mock.patch.object(self.w.shutil, "which", return_value=None):
            out = self.doctor("cursor", "--check-auto")
            self.assertIn("--check-auto cursor (gpt-5.6-luna-high): OK", out)
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


class ResumeStage3(unittest.TestCase):
    def setUp(self):
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
        asked = []
        real_ask = self.w.ask
        self.w.ask = lambda p, d="": asked.append(p) or real_ask(p, d)
        out, rc = capture(self.w, "new", "s3", "--task", "all", "--auto")
        self.assertEqual(rc, 0)
        self.assertTrue(any("Start the agents for the 3 runs that are not done?" in x for x in asked))
        self.assertIn("Showing its pages again", out)
        self.assertEqual(out.count("FINISHED"), 3)
        self.assertEqual(len(self.w.Registry.load().actives("3")), 0)
        started = [r["folder"] for r in self.w.Registry.load().data["runs"].values()
                   if r.get("stage") == "3" and os.path.exists(os.path.join(r["folder"], "argv.json"))]
        self.assertEqual(len(started), 3)


if __name__ == "__main__":
    unittest.main()
