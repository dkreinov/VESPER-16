"""Stage-2 prompt sentences, and harvest records which skill-writing help the agent really used."""
import contextlib, io, json, os, sys, tempfile, time, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fakes  # noqa: E402
from fakes import fresh_ws, run  # noqa: E402

MEMORY = "The skill will be used later, on other tasks, by agents that do not have the memory of this session."
NO_GUIDE = "Do not use a skill-creator or skill-writing skill or guide. Write the skill from your own knowledge."


class Stage2Prompts(unittest.TestCase):
    def setUp(self):
        self.w, _ = fresh_ws()

    def render(self, name):
        return self.w.render_prompt(name, task="T6", run_id="s1-ab12", guide="/g", builtin_how="x")

    def test_plain_has_both_sentences_in_order(self):
        p = self.render("stage2-plain")
        self.assertIn("mark anything uncertain.\n\n" + MEMORY + "\n\n" + NO_GUIDE + "\n\n", p)

    def test_others_have_only_the_first(self):
        for n in ("stage2-builtin", "stage2-superpowers"):
            p = self.render(n)
            self.assertIn("mark anything uncertain.\n\n" + MEMORY + "\n\n", p, n)
            self.assertNotIn("Do not use a skill-creator", p, n)


class HarvestMethodUsed(unittest.TestCase):
    def setUp(self):
        self.w, _ = fresh_ws()

    def _harvest(self, mention):
        w = self.w
        run(w, "doctor", "--agent", "codex", "--alias", "t")
        run(w, "new", "s1", "--method", "plain")
        reg = w.Registry.load()
        rid = reg.data["active"]["run_id"]
        f = reg.data["runs"][rid]["folder"]
        t0 = reg.data["active"]["start"]
        log = fakes.codex_log("0c0d0e0f-0000-1111-2222-333344445555", f,
                              [(t0 + 0.01, 10, 0, 1, "Workshop run: %s" % rid), (t0 + 0.02, 20, 0, 2, "")])
        run(w, "done", "--no-form")
        run(w, "skill")
        sk = os.path.join(f, "skill-out", "vesper16")
        os.makedirs(sk)
        with open(os.path.join(sk, "SKILL.md"), "w") as fh:
            fh.write("---\nname: vesper16\ndescription: x\n---\nhi\n")
        # the stage-2 prompt itself names skill-creator (plain prompt); it must not count
        ev = [{"timestamp": fakes.iso(time.time()), "type": "response_item", "payload": {
            "type": "message", "role": "user",
            "content": [{"type": "input_text", "text": "Do not use a skill-creator ..."}]}}]
        if mention:
            ev.append({"timestamp": fakes.iso(time.time()), "type": "response_item", "payload": {
                "type": "function_call", "name": "shell", "arguments": json.dumps({"cmd": "use $skill-creator now"})}})
        with open(log, "a") as fh:
            for e in ev:
                fh.write(json.dumps(e) + "\n")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            run(w, "harvest", "--no-form")
        return rid, out.getvalue()

    def test_skill_creator_detected(self):
        rid, out = self._harvest(True)
        row = self.w.Registry.load().row(rid, "2")
        self.assertEqual(row["method_used"], "skill-creator")
        self.assertIn("Skill help the agent used: skill-creator (drawn method: plain)", out)
        with open(os.path.join(self.w.ws_home(), "results.csv"), encoding="utf-8") as f:
            self.assertEqual(f.readline().strip().split(",")[-1], "method_used")

    def test_none_when_not_mentioned(self):
        rid, out = self._harvest(False)
        self.assertEqual(self.w.Registry.load().row(rid, "2")["method_used"], "none")
        self.assertIn("Skill help the agent used: none (drawn method: plain)", out)

    def _detect(self, *blocks):
        """blocks: (role, content-block) pairs written as Claude-style log lines inside the window."""
        fd, p = tempfile.mkstemp(suffix=".jsonl")
        t = time.time()
        with os.fdopen(fd, "w") as f:
            for role, b in blocks:
                f.write(json.dumps({"type": role, "timestamp": fakes.iso(t), "message": {"content": [b]}}) + "\n")
        self.addCleanup(os.remove, p)
        return self.w.detect_method_used(p, t - 5, t + 5)

    def test_prose_is_not_use(self):
        prose = ("assistant", {"type": "text", "text": "I did not use a skill-creator or writing-skills"})
        self.assertEqual(self._detect(prose), "none")

    def test_tool_call_reading_skill_md_is_use(self):
        for path, want in (("C:\\Users\\me\\.codex\\skills\\.system\\skill-creator\\SKILL.md", "skill-creator"),
                           ("/home/me/guides/anthropic-skill-creator/SKILL.md", "skill-creator"),
                           ("/g/superpowers-writing-skills/SKILL.md", "writing-skills")):
            call = ("assistant", {"type": "tool_use", "name": "Read", "input": {"file_path": path}})
            self.assertEqual(self._detect(call), want, path)
        res = ("user", {"type": "tool_result", "content": "cat /x/skill-creator/SKILL.md"})
        self.assertEqual(self._detect(res), "skill-creator")

    def test_skill_tool_invocation_is_use(self):
        call = ("assistant", {"type": "tool_use", "name": "Skill", "input": {"skill": "superpowers:writing-skills"}})
        self.assertEqual(self._detect(call), "writing-skills")

    def test_no_log_is_empty(self):
        self.assertEqual(self.w.detect_method_used(None, 0, 1), "")
        self.assertEqual(self.w.detect_method_used("/no/such/file.jsonl", 0, 1), "")


if __name__ == "__main__":
    unittest.main()
