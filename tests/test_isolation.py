"""Isolation audit, overrun flag, skill inspection step (Part W5, W6, W8)."""
import contextlib, io, json, os, sys, tempfile, time, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fakes  # noqa: E402
from fakes import fresh_ws, run, iso, flat  # noqa: E402


def write_log(path, t, calls, claude=False):
    """calls: list of command strings, each one tool call at time t."""
    with open(path, "w") as f:
        for i, cmd in enumerate(calls):
            if claude:
                d = {"type": "assistant", "timestamp": iso(t + i), "message": {"content": [
                    {"type": "tool_use", "name": "Bash", "input": {"command": cmd}}]}}
            else:
                d = {"timestamp": iso(t + i), "type": "response_item", "payload": {
                    "type": "function_call", "name": "shell",
                    "arguments": json.dumps({"command": ["bash", "-lc", cmd]})}}
            f.write(json.dumps(d) + "\n")
    return path


def write_exec(path, t, codes):
    """Codex 'exec' tool calls: JavaScript code with JSON-escaped strings (two-backslash separators)."""
    with open(path, "w") as f:
        for i, code in enumerate(codes):
            f.write(json.dumps({"timestamp": iso(t + i), "type": "response_item", "payload": {
                "type": "custom_tool_call", "name": "exec", "input": code}}) + "\n")
    return path


def esc(p):
    """A path as Codex writes it in exec code: each separator is two backslash characters."""
    return p.replace("\\", "/").replace("/", "\\\\")


class OutsideReadsTest(unittest.TestCase):
    def setUp(self):
        self.w, self.home = fresh_ws()
        self.runs = self.w.ws_home()
        self.folder = os.path.join(self.runs, "s1-aaaa")
        os.makedirs(self.folder)
        self.t = time.time()
        self.log = os.path.join(self.home, "log.jsonl")

    def scan(self, cmd, writer=False, claude=False):
        write_log(self.log, self.t, [cmd], claude=claude)
        return self.w.detect_outside_reads([self.log], self.t - 5, self.t + 5, self.folder, writer=writer)

    def scan_exec(self, code, writer=False, folder=None):
        write_exec(self.log, self.t, [code])
        return self.w.detect_outside_reads([self.log], self.t - 5, self.t + 5, folder or self.folder, writer=writer)

    # ---------------------------------------------------------------- allowed, or not of interest
    def test_inside_path(self):
        st, note = self.scan("cat %s/tasks/T3.md && ls bin examples" % self.folder)
        self.assertEqual((st, note), ("not_detected", ""))
        st, _ = self.scan("python bin/vesper run game.vsp 2>/dev/null; cat /tmp/x")
        self.assertEqual(st, "not_detected")
        st, _ = self.scan("cat examples/../tasks/T3.md")
        self.assertEqual(st, "not_detected")

    def test_paths_outside_the_guarded_places_are_ignored(self):
        for cmd in ("cat /home/other/secret.txt", "type C:\\Users\\other\\notes.txt", "ls /usr/lib /etc",
                    "curl https://example.com/a/../b", "ls -la ~", "cat ~/notes.txt", "dir %USERPROFILE%"):
            self.assertEqual(self.scan(cmd), ("not_detected", ""), cmd)

    def test_own_folder_with_escaped_backslashes(self):
        code = ('const r = await tools.exec_command({cmd:"Get-Content tasks/T3.md",workdir:"%s"});\n'
                'text(await tools.view_image({path:"%s"}));'
                % (esc(self.folder), esc(os.path.join(self.folder, "out", "a.png"))))
        self.assertEqual(self.scan_exec(code), ("not_detected", ""))

    def test_non_path_tokens(self):
        code = ('const ok = /skill/i.test(name) && !/extra/.test(x); for (const f of files) { f: 1 };\n'
                'const r = await tools.exec_command({cmd:"ls ~; Get-ChildItem f:",workdir:"%s"});' % esc(self.folder))
        self.assertEqual(self.scan_exec(code), ("not_detected", ""))

    def test_agent_plugin_cache(self):
        cache = os.path.join(self.w.M.codex_home(), "plugins", "cache", "curated", "superpowers", "6.4.2", "skills",
                             "using-superpowers", "SKILL.md")
        self.assertEqual(self.scan("cat %s" % cache), ("not_detected", ""))
        code = 'await tools.exec_command({cmd:"Get-Content %s"});' % esc("C:/Users/x/.codex/plugins/cache/a/SKILL.md")
        self.assertEqual(self.scan_exec(code), ("not_detected", ""))

    def test_dotdot_in_written_or_quoted_text(self):
        st, _ = self.scan('echo "Copy the helpers from ../templates/ before you start" > notes.txt')
        self.assertEqual(st, "not_detected")
        code = ('await tools.apply_patch("*** Begin Patch\\n*** Add File: %s\\n+Copy ../templates/. and read '
                '../s1-dddd/x and T6.md\\n*** End Patch\\n");' % esc(os.path.join(self.folder, "skill-out", "SKILL.md")))
        self.assertEqual(self.scan_exec(code, writer=True), ("not_detected", ""))

    def test_with_skill_run_reads_its_own_installed_skill(self):
        f = os.path.join(self.runs, "s3-aaaa-t3-bbbb")
        os.makedirs(f)
        code = 'await tools.exec_command({cmd:"Get-Content .agents/skills/vesper16/SKILL.md",workdir:"%s"});' % esc(f)
        self.assertEqual(self.scan_exec(code, folder=f), ("not_detected", ""))

    # ---------------------------------------------------------------- guarded places
    def test_other_run_folder(self):
        st, note = self.scan("ls %s" % os.path.join(self.runs, "s1-dddd", "solutions"))
        self.assertEqual(st, "detected")
        self.assertIn("other run s1-dddd/solutions", note)
        st, note = self.scan("ls ../s3-bbbb-t3-cccc")
        self.assertEqual(st, "detected")
        self.assertIn("s3-bbbb-t3-cccc", note)

    def test_other_run_folder_with_escaped_backslashes(self):
        other = os.path.join(self.runs, "s3-bbbb-n3-cccc")
        code = 'await tools.exec_command({cmd:"Get-Content solutions/T3.vsa",workdir:"%s"});' % esc(other)
        st, note = self.scan_exec(code)
        self.assertEqual(st, "detected")
        self.assertIn("other run s3-bbbb-n3-cccc", note)

    def test_dotdot_escape(self):
        st, _ = self.scan("cat ../notes.txt")             # no such file in the runs home: nothing to read
        self.assertEqual(st, "not_detected")
        open(os.path.join(self.runs, "notes.txt"), "w").close()
        st, note = self.scan("cat ../notes.txt")
        self.assertEqual(st, "detected")
        self.assertIn("runs home notes.txt", note)
        st, _ = self.scan("cd .. && ls")
        self.assertEqual(st, "detected")

    def test_skills_store(self):
        st, note = self.scan("cat %s" % os.path.join(self.runs, ".skills", "s1-aaaa", "vesper16", "SKILL.md"))
        self.assertEqual(st, "detected")
        self.assertIn("runs home .skills/s1-aaaa", note)
        st, _ = self.scan("cat ../.skills/s1-aaaa/vesper16/SKILL.md")
        self.assertEqual(st, "detected")

    def test_kit_files(self):
        kit = self.w.KIT
        st, note = self.scan("cat %s" % os.path.join(kit, "solutions", "T3.vsa"))
        self.assertEqual(st, "detected")
        self.assertIn("kit solutions/t3.vsa", note.lower())
        code = 'await tools.exec_command({cmd:"Get-Content MANUAL.md",workdir:"%s"});' % esc(kit)
        st, _ = self.scan_exec(code)
        self.assertEqual(st, "detected")
        if os.name == "nt":                                 # the Git Bash spelling of the same folder
            gb = "/" + kit[0].lower() + kit[2:].replace("\\", "/")
            st, _ = self.scan("cat %s/guides/x.md" % gb)
            self.assertEqual(st, "detected")

    def test_writer_reads_t6(self):
        st, _ = self.scan("cat tasks/T6.md", writer=False)
        self.assertEqual(st, "not_detected")
        st, note = self.scan("cat tasks/T6.md", writer=True)
        self.assertEqual(st, "detected")
        st, _ = self.scan("python t6font.py", writer=True)
        self.assertEqual(st, "detected")
        st, note = self.scan("cat %s" % os.path.join(self.w.KIT, "tasks", "T6.md"), writer=True)
        self.assertEqual(st, "detected")
        self.assertIn("kit tasks/t6.md", note.lower())

    def test_memory_files(self):
        st, note = self.scan("cat ~/.codex/memories/MEMORY.md")
        self.assertEqual(st, "detected")
        self.assertIn("memory", note)
        st, _ = self.scan("ls %s" % os.path.join(self.w.M.codex_home(), "memories"))
        self.assertEqual(st, "detected")
        st, _ = self.scan("cat %s" % os.path.join(self.w.M.claude_home(), "projects", "p", "memory", "MEMORY.md"))
        self.assertEqual(st, "detected")

    def test_claude_tool_use(self):
        st, _ = self.scan("cat ../s1-dddd/x", claude=True)
        self.assertEqual(st, "detected")

    def test_only_tool_calls_and_window(self):
        bad = os.path.join(self.runs, "s1-dddd", "x")
        with open(self.log, "w") as f:      # prose mentioning a path is not a tool call
            f.write(json.dumps({"timestamp": iso(self.t), "type": "response_item", "payload": {
                "type": "message", "content": [{"type": "output_text", "text": "see %s" % bad}]}}) + "\n")
        st, _ = self.w.detect_outside_reads([self.log], self.t - 5, self.t + 5, self.folder)
        self.assertEqual(st, "not_detected")
        write_log(self.log, self.t - 500, ["cat %s" % bad])      # outside [t0, t1]
        st, _ = self.w.detect_outside_reads([self.log], self.t - 5, self.t + 5, self.folder)
        self.assertEqual(st, "not_detected")

    def test_note_limits(self):
        cmd = " ".join(os.path.join(self.runs, "s1-%s" % (c * 4), "x" * 80) for c in "bcdef0")
        st, note = self.scan(cmd)
        self.assertEqual(st, "detected")
        self.assertLessEqual(len(note), 200)
        self.assertLessEqual(note.count("other run"), 3)

    def test_no_log(self):
        self.assertEqual(self.w.detect_outside_reads([], 0, 1, self.folder), ("unknown", ""))
        self.assertEqual(self.w.detect_outside_reads([os.path.join(self.home, "none.jsonl")], 0, 1, self.folder),
                         ("unknown", ""))
        self.assertEqual(self.w.detect_outside_reads(None, 0, 1, self.folder), ("unknown", ""))


class ReviewInputsTest(unittest.TestCase):
    """Every failing input of the 2026-10-21 adversarial review (MAJOR-4..7, MINOR-6)."""
    setUp = OutsideReadsTest.setUp
    scan = OutsideReadsTest.scan

    def tearDown(self):
        os.environ.pop("VESPER_WS_USERHOME", None)

    def scan_tool(self, name, inp):
        with open(self.log, "w") as f:
            f.write(json.dumps({"type": "assistant", "timestamp": iso(self.t), "message": {"content": [
                {"type": "tool_use", "name": name, "input": inp}]}}) + "\n")
        return self.w.detect_outside_reads([self.log], self.t - 5, self.t + 5, self.folder)

    def scan_shell_command(self, args):
        with open(self.log, "w") as f:
            f.write(json.dumps({"timestamp": iso(self.t), "type": "response_item", "payload": {
                "type": "function_call", "name": "shell_command", "arguments": json.dumps(args)}}) + "\n")
        return self.w.detect_outside_reads([self.log], self.t - 5, self.t + 5, self.folder)

    def test_glob_reads_of_other_runs(self):          # MAJOR-4
        for cmd in ("cat ../s1-*/solutions/*.vsa", "ls ../*/solutions",
                    "cat %s/*/solutions/T3.vsa" % self.runs, "Get-ChildItem ..\\* -Recurse",
                    "cat %s/s?-*/solutions/T3.vsa" % self.runs.replace("\\", "/")):
            self.assertEqual(self.scan(cmd)[0], "detected", cmd)
        self.assertEqual(self.scan_tool("Glob", {"pattern": "../**/*.vsa"})[0], "detected")
        self.assertEqual(self.scan_tool("Glob", {"pattern": "*/solutions/*.vsa", "path": self.runs})[0], "detected")
        for cmd in ("ls *.vsa solutions/*", "cat ../s1-aaaa/solutions/*.vsa"):     # globs in the own folder
            self.assertEqual(self.scan(cmd), ("not_detected", ""), cmd)

    def test_pwd_and_env_forms(self):                 # MAJOR-5
        for cmd in ('cat "$PWD/../s1-dddd/solutions/T3.vsa"', "cat $(pwd)/../s1-dddd/solutions/T3.vsa",
                    "Get-Content $PWD\\..\\s1-dddd\\solutions\\T3.vsa", "type %CD%\\..\\s1-dddd\\solutions\\T3.vsa",
                    "cat ${PWD}/../s1-dddd/x", "Get-Content (Get-Location)\\..\\s1-dddd\\x"):
            st, note = self.scan(cmd)
            self.assertEqual(st, "detected", cmd)
            self.assertIn("other run s1-dddd", note, cmd)
        os.environ["VESPER_TEST_RUNS"] = self.runs
        try:
            for cmd in ("Get-Content ${env:VESPER_TEST_RUNS}\\s1-dddd\\x", "Get-Content $env:VESPER_TEST_RUNS\\s1-dddd\\x",
                        "type %VESPER_TEST_RUNS%\\s1-dddd\\x", "cat $VESPER_TEST_RUNS/s1-dddd/x"):
                self.assertEqual(self.scan(cmd)[0], "detected", cmd)
        finally:
            del os.environ["VESPER_TEST_RUNS"]

    def test_recursive_search_from_an_ancestor(self):  # MAJOR-5, R7
        os.environ["VESPER_WS_USERHOME"] = self.home         # the runs home is inside the user home
        for cmd in ("find ~ -name '*.vsa'", "rg --files -g '*.vsa' ~", "Get-ChildItem -Recurse %s" % self.home,
                    "Get-ChildItem ${env:USERPROFILE} -Recurse -Filter *.vsa", "dir /s %s\\*.vsa" % self.home,
                    "find %s -name '*.vsa'" % self.runs, "cd ~ && find . -name '*.vsa'",
                    "ls -R ../..", "find %s -name x" % self.w.KIT):
            self.assertEqual(self.scan(cmd)[0], "detected", cmd)
        for cmd in ("ls -la ~", "cat ~/notes.txt", "find . -name '*.vsa'", "rg --files", "grep -rn x .",
                    "cp -r examples out"):
            self.assertEqual(self.scan(cmd), ("not_detected", ""), cmd)
        st, note = self.scan("find ~ -name '*.vsa'")
        self.assertNotIn(self.home.replace("\\", "/").lower(), note.lower())

    def test_cd_into_a_subfolder_is_not_an_escape(self):   # MAJOR-6
        os.makedirs(os.path.join(self.folder, "examples", "a"))
        for cmd in ("cd examples && ls ..", "cd examples/a && cat ../../tasks/T3.md", "pushd examples; ls ..",
                    "Set-Location examples; Get-ChildItem .."):
            self.assertEqual(self.scan(cmd), ("not_detected", ""), cmd)
        self.assertEqual(self.scan_shell_command({"command": "ls ..", "workdir": os.path.join(self.folder, "examples")}),
                         ("not_detected", ""))
        for cmd in ("cd examples && ls ../..", "cd .. && ls", "cd .. && cat s1-dddd/x", "cd examples && cd .. && ls .."):
            self.assertEqual(self.scan(cmd)[0], "detected", cmd)
        self.assertEqual(self.scan_shell_command({"command": "ls ..", "workdir": self.folder})[0], "detected")

    def test_long_token_is_linear(self):               # MAJOR-7 / R8
        blob = "A" * 200000
        for cmd in ("echo %s" % blob, "python -c 'x=\"%s\"'" % ("/a" * 100000)):
            t = time.time()
            self.assertEqual(self.scan(cmd), ("not_detected", ""))
            self.assertLess(time.time() - t, 1.0)

    def test_note_has_no_home_or_user_name(self):       # MINOR-6 / R10
        slug = "c--users-jdoe-work-s1-aaaa"
        st, note = self.scan("cat %s" % os.path.join(self.w.M.claude_home(), "projects", slug, "memory", "MEMORY.md"))
        self.assertEqual(st, "detected")
        self.assertNotIn("jdoe", note)
        self.assertIn("memory (claude project memory)", note)
        os.environ["VESPER_WS_USERHOME"] = self.home
        st, note = self.scan("cat ~/.codex/memories/MEMORY.md")
        self.assertEqual(st, "detected")
        self.assertNotIn(self.home.replace("\\", "/").lower(), note.lower())


class DoneFieldsTest(unittest.TestCase):
    def _s1(self, wall, calls):
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
            for i, c in enumerate(calls):
                fh.write(json.dumps({"timestamp": iso(t0 + 0.03 + i * 0.001), "type": "response_item", "payload": {
                    "type": "function_call", "name": "shell",
                    "arguments": json.dumps({"command": ["bash", "-lc", c]})}}) + "\n")
        reg.data["active_runs"][rid]["start"] = t0 - wall
        reg.save()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            run(w, "done", "--no-form")
        return w, rid, out.getvalue()

    def test_not_detected_and_no_overrun(self):
        w, rid, out = self._s1(60, ["ls"])
        row = w.Registry.load().row(rid, "1")
        self.assertEqual((row["isolation"], row["overrun"]), ("not_detected", ""))   # no time box in stage 1
        self.assertIn("Isolation OK", out)          # summary line (organiser's approved layout); no extra lines
        self.assertNotIn("not proof", out)
        self.assertNotIn("time box: flagged", out)

    def test_detected_and_overrun(self):
        w, rid, out = self._s1(700, ["cat tasks/T6.md"])
        row = w.Registry.load().row(rid, "1")
        self.assertEqual((row["isolation"], row["overrun"]), ("detected", ""))      # 700 s in stage 1: not an overrun
        self.assertTrue(row["isolation_note"])
        self.assertIn("CHECK: the agent may have read outside the run folder.", flat(out))
        self.assertIn(row["isolation_note"][:20], flat(out))
        self.assertNotIn("time box: flagged", out)

    def _s3(self, setup_s, prompt_before_cutoff, log=True, work_s=30):
        """A stage-3 run whose folder was made setup_s before 'done'; the prompt was sent prompt_before_cutoff s before."""
        w, _ = fresh_ws()
        fakes.ready_for_s3(w)
        with contextlib.redirect_stdout(io.StringIO()):
            run(w, "new", "s3", "--task", "T3")
        reg = w.Registry.load()
        rid = [x["run_id"] for x in reg.actives("3")][0]
        folder = reg.data["runs"][rid]["folder"]
        now = time.time()
        if log:
            p = now - prompt_before_cutoff
            fakes.codex_log("0c0d0e0f-0000-1111-2222-3333444455%02d" % int(setup_s % 97), folder,
                            [(p - 5, 5, 0, 1, "# Workshop run %s (AGENTS.md)" % rid),
                             (p, 10, 0, 1, "Workshop run: %s\nBuild T3." % rid), (p + work_s, 20, 0, 2, "")])
        reg.data["active_runs"][rid]["start"] = now - setup_s
        reg.save()
        with contextlib.redirect_stdout(io.StringIO()):
            run(w, "done", rid, "--no-form")
        return w.Registry.load().row(rid, "3")

    def test_overrun_counts_from_the_prompt_to_the_last_activity(self):     # B2: never to the `done` time
        # the agent worked 8.8 min; the learner ran `done` 14 min after the folder was made: no overrun
        self.assertEqual(self._s3(14 * 60, 9 * 60, work_s=9 * 60 - 10)["overrun"], "no")
        self.assertEqual(self._s3(14 * 60, 11 * 60, work_s=11 * 60 - 10)["overrun"], "yes")   # worked 10.8 min
        # a learner who runs `done` 40 minutes after the agent finished is NOT flagged
        self.assertEqual(self._s3(50 * 60, 48 * 60, work_s=7 * 60)["overrun"], "no")
        # no agent log: no activity time is known, so the run is not flagged
        self.assertEqual(self._s3(14 * 60, 0, log=False)["overrun"], "")

    def test_prompt_time(self):
        w, home = fresh_ws()
        p = os.path.join(home, "c.jsonl")
        with open(p, "w") as f:
            for t, d in ((100, {"type": "user", "message": {"content": [{"type": "tool_result", "content": "x"}]}}),
                         (110, {"type": "user", "message": {"content": "hello"}}),
                         (120, {"type": "user", "message": {"content": [{"type": "text", "text": "Workshop run: s3-a"}]}})):
                d["timestamp"] = iso(t)
                f.write(json.dumps(d) + "\n")
        self.assertAlmostEqual(w.prompt_time([p], "s3-a", 50, 200), 120, places=3)
        self.assertAlmostEqual(w.prompt_time([p], "s3-b", 50, 200), 110, places=3)    # first user message in the window
        self.assertIsNone(w.prompt_time([p], "s3-b", 150, 200))
        self.assertIsNone(w.prompt_time([], "s3-b", 0, 200))

    def test_overrun_rule_stage3_only(self):
        w, _ = fresh_ws()
        self.assertEqual(w.overrun_flag("3", 0, 601), "yes")
        self.assertEqual(w.overrun_flag("3", 0, 600), "no")
        self.assertEqual(w.overrun_flag("1", 0, 3000), "")
        self.assertEqual(w.overrun_flag("2", 0, 3000), "")


class HarvestStepTest(unittest.TestCase):
    def test_inspection_step(self):
        w, _ = fresh_ws()
        rid, out = fakes.ready_for_s3(w)
        self.assertNotIn("Before stage 3 (2 minutes)", out)
        self.assertIn("  No copied block of your T3 solution was found in your skill", out)
        self.assertIn("  Why stage 3 also runs a DIFFERENT task (T6):", out)
        self.assertIn("    1. Memory: the agent remembers the earlier session.", out)
        self.assertIn("    2. The skill holds parts of the T3 answer itself.", out)
        self.assertLess(out.index("Why stage 3 also runs"), out.index("NEXT:"))
        self.assertNotIn("Knowledge or the answer?", out)      # learners see no code blocks
        self.assertNotIn("Isolation OK", out)

    def test_harvest_note_with_share(self):
        w, _ = fresh_ws()
        lines = w.harvest_note(0.13)
        self.assertIn("13% of your T3 solution's own lines are in your skill", lines[0])
        self.assertTrue(any("DIFFERENT task (T6)" in x for x in lines))


if __name__ == "__main__":
    unittest.main()


class WrongFolderTest(unittest.TestCase):
    """The agent worked in another folder than the run folder (Documents instead of the run folder)."""
    def setUp(self):
        self.w, self.home = fresh_ws()
        self.t = time.time()

    def _log(self, name, cwd_forms, claude=False):
        p = os.path.join(self.home, name)
        with open(p, "w") as f:
            for i, c in enumerate(cwd_forms):
                if claude:
                    d = {"type": "assistant", "timestamp": iso(self.t + i), "cwd": c, "message": {"content": []}}
                else:
                    d = {"type": "event_msg", "timestamp": iso(self.t + i), "payload": {
                        "type": "item_completed", "item": {"cwd": c}}}
                f.write(json.dumps(d) + "\n")
        return p

    def test_inside_both_forms_and_subfolder(self):
        folder = os.path.join(self.home, "Run Dir", "s1-aaaa")
        os.makedirs(folder)
        url = "file:///" + folder.replace("\\", "/").replace(" ", "%20")
        p = self._log("a.jsonl", [folder, url, os.path.join(folder, "sub")])
        self.assertEqual(self.w.outside_workdirs([p], self.t - 5, self.t + 5, folder), [])
        self.assertEqual(len(self.w.session_workdirs([p], self.t - 5, self.t + 5)), 2)

    def test_outside_and_window(self):
        folder = os.path.join(self.home, "runs", "s1-aaaa")
        docs = os.path.join(self.home, "Docs Dir")
        url = "file:///" + docs.replace("\\", "/").replace(" ", "%20")
        p = self._log("b.jsonl", [folder, url])
        out = self.w.outside_workdirs([p], self.t - 5, self.t + 5, folder)
        self.assertEqual(out, [self.w._npath(docs)])
        self.assertEqual(self.w.outside_workdirs([p], self.t + 100, self.t + 200, folder), [])

    def test_claude_log(self):
        folder = os.path.join(self.home, "runs", "s1-aaaa")
        p = self._log("c.jsonl", [folder, os.path.join(self.home, "elsewhere")], claude=True)
        self.assertEqual(len(self.w.outside_workdirs([p], self.t - 5, self.t + 5, folder)), 1)

    def _stage1(self, cwd_of):
        w = self.w
        run(w, "doctor", "--agent", "codex", "--alias", "t")
        run(w, "new", "s1", "--method", "plain")
        reg = w.Registry.load()
        rid = reg.data["active"]["run_id"]
        f = reg.data["runs"][rid]["folder"]
        t0 = reg.data["active"]["start"]
        cwd = cwd_of(f)
        log = fakes.codex_log("0c0d0e0f-0000-1111-2222-333344445555", cwd,
                              [(t0 + 0.01, 10, 0, 1, "Workshop run: %s" % rid), (t0 + 0.02, 20, 0, 2, "")])
        return rid, f, cwd, log

    def _done(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            run(self.w, "done", "--no-form")
        return out.getvalue()

    def test_done_inside_no_warning(self):
        rid, f, _, _ = self._stage1(lambda f: f)
        out = self._done()
        self.assertNotIn("WRONG FOLDER", out)
        self.assertEqual(self.w.Registry.load().row(rid, "1")["isolation"], "not_detected")

    def test_done_outside_warns_and_anonymises(self):
        docs = os.path.join(os.path.expanduser("~"), "Documents")
        rid, f, _, _ = self._stage1(lambda f: docs)
        out = self._done()
        self.assertIn("WRONG FOLDER: your agent worked in", out)
        self.assertIn("redo the step there", out)
        self.assertLess(out.index("WRONG FOLDER"), out.index("STAGE 1 FINISHED"))
        row = self.w.Registry.load().row(rid, "1")
        self.assertEqual(row["isolation"], "detected")
        self.assertTrue(row["isolation_note"].startswith("worked outside the run folder: ~"), row["isolation_note"])
        self.assertNotIn(os.path.basename(os.path.expanduser("~")).lower(), row["isolation_note"].lower())

    def test_harvest_names_skill_in_outside_dir(self):
        rid, f, _, log = self._stage1(lambda f: f)
        self._done()
        run(self.w, "skill")
        other = os.path.join(self.home, "elsewhere")
        sk = os.path.join(other, "skill-out", "vesper16")
        os.makedirs(sk)
        with open(os.path.join(sk, "SKILL.md"), "w") as fh0:
            fh0.write("x")
        with open(log, "a") as fh:
            fh.write(json.dumps({"type": "event_msg", "timestamp": iso(time.time()), "payload": {
                "type": "item_completed", "item": {"cwd": other}}}) + "\n")
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit) as cm:
            run(self.w, "harvest", "--no-form")
        txt = out.getvalue()
        self.assertIn("WRONG FOLDER", txt, str(cm.exception))
        self.assertIn("run harvest again", txt)
        self.assertIn("A skill was written here instead:", txt)
        self.assertIn("No skill at", str(cm.exception))


class FindSessionsSinceTest(unittest.TestCase):
    def setUp(self):
        self.w, self.home = fresh_ws()
        d = os.path.join(os.environ["CODEX_HOME"], "sessions", "2026", "10", "18")
        os.makedirs(d)
        self.d = d

    def _log(self, name, text, mtime):
        p = os.path.join(self.d, name)
        with open(p, "w") as f:
            f.write(text)
        os.utime(p, (mtime, mtime))
        return p

    def test_old_log_not_opened_new_log_found(self):
        now = time.time()
        old = self._log("rollout-2026-10-18T10-00-00-0a0b0c0d-0000-1111-2222-333344445555.jsonl", "s1-zzzz\n", now - 3600)
        self._log("rollout-2026-10-18T11-00-00-0a0b0c0d-0000-1111-2222-333344445556.jsonl", "s1-zzzz\n", now)
        real_open, opened = open, []

        def spy(p, *a, **k):
            opened.append(str(p))
            return real_open(p, *a, **k)
        self.w.open = spy
        try:
            s = self.w.find_sessions("s1-zzzz", since=now - 60)
        finally:
            del self.w.open
        self.assertEqual(len(s), 1)
        self.assertNotIn(old, opened)
        self.assertEqual(len(self.w.find_sessions("s1-zzzz")), 2)     # without since: both

    def test_key_across_chunk_edge_and_big_new_log(self):
        self.w.CHUNK = 16
        now = time.time()
        self._log("rollout-2026-10-18T11-00-00-0a0b0c0d-0000-1111-2222-333344445556.jsonl", "x" * 13 + "s1-qqqq" + "y" * 40, now)
        self.assertEqual(len(self.w.find_sessions("s1-qqqq", since=now - 60)), 1)
        self.assertEqual(len(self.w.find_sessions("s1-nope", since=now - 60)), 0)
