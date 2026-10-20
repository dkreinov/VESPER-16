"""memory_used (Codex Memories leak), the prompt sentence, and the doctor warning."""
import contextlib, io, json, os, sys, tempfile, time, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fakes  # noqa: E402
from fakes import fresh_ws, run  # noqa: E402

SENT = "Do not read memory files or notes from earlier sessions.\n\nWork on your own"


class MemoryUsed(unittest.TestCase):
    def setUp(self):
        self.w, _ = fresh_ws()

    def _detect(self, *evs):
        fd, p = tempfile.mkstemp(suffix=".jsonl")
        t = time.time()
        with os.fdopen(fd, "w") as f:
            for e in evs:
                f.write(json.dumps(dict(e, timestamp=fakes.iso(t))) + "\n")
        self.addCleanup(os.remove, p)
        return self.w.detect_memory_used(p, t - 5, t + 5)

    @staticmethod
    def _dev(text):
        return {"type": "response_item", "payload": {"type": "message", "role": "developer",
                                                     "content": [{"type": "input_text", "text": text}]}}

    def test_injected_memory_with_vesper_is_yes(self):
        self.assertEqual(self._detect(self._dev("Rules.\n## Memory\nYou have access to a memory folder. VESPER-16 tips")), "yes")

    def test_memory_section_without_vesper_is_no(self):
        self.assertEqual(self._detect(self._dev("## Memory\nYou have access to a memory folder. Other topic")), "no")

    def test_vesper_outside_memory_section_is_no(self):
        self.assertEqual(self._detect(self._dev("VESPER task rules\n## Memory\nnothing")), "no")

    def test_tool_call_reading_memories_is_yes(self):
        for cmd in (r"cat C:\Users\me\.codex\memories\MEMORY.md", "cat ~/.codex/memories/skills/x/SKILL.md"):
            call = {"type": "response_item", "payload": {"type": "function_call", "name": "shell",
                                                         "arguments": json.dumps({"cmd": cmd})}}
            self.assertEqual(self._detect(call), "yes", cmd)

    def test_neither_is_no_and_prose_is_not_a_read(self):
        prose = {"type": "response_item", "payload": {"type": "message", "role": "user", "content": [
            {"type": "input_text", "text": "see .codex/memories"}]}}
        self.assertEqual(self._detect(prose), "no")

    def test_no_log_is_empty(self):
        self.assertEqual(self.w.detect_memory_used(None, 0, 1), "")

    def test_done_records_it(self):
        w = self.w
        run(w, "doctor", "--agent", "codex", "--alias", "t")
        run(w, "new", "s1")
        reg = w.Registry.load()
        rid = reg.data["active"]["run_id"]
        t0 = reg.data["active"]["start"]
        log = fakes.codex_log("0c0d0e0f-0000-1111-2222-333344445555", reg.data["runs"][rid]["folder"],
                              [(t0 + 0.01, 10, 0, 1, "Workshop run: %s" % rid), (t0 + 0.02, 20, 0, 2, "")])
        with open(log, "a") as fh:
            fh.write(json.dumps(dict(self._dev("## Memory\nvesper notes"), timestamp=fakes.iso(t0))) + "\n")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            run(w, "done", "--no-form")
        self.assertEqual(w.Registry.load().row(rid, "1")["memory_used"], "yes")
        self.assertIn("Agent memory in context: yes (Codex Memories; see the debrief)", out.getvalue())
        with open(os.path.join(w.ws_home(), "results.csv"), encoding="utf-8") as f:
            self.assertEqual(f.readline().strip().split(",")[-1], "memory_used")


class Prompts(unittest.TestCase):
    def test_sentence_in_all_prompts(self):
        w, _ = fresh_ws()
        for n in ("stage1", "stage3", "stage2-builtin", "stage2-plain", "stage2-superpowers"):
            p = w.render_prompt(n, task="T6", run_id="s1-ab12", guide="/g", builtin_how="x")
            self.assertIn(SENT, p, n)


class DoctorMemories(unittest.TestCase):
    def _doctor(self, content, agent="codex"):
        w, home = fresh_ws()
        if content is not None:
            d = os.path.join(home, "user", ".codex", "memories")
            os.makedirs(d)
            with open(os.path.join(d, "MEMORY.md"), "w") as f:
                f.write(content)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = run(w, "doctor", "--agent", agent, "--alias", "t")
        return rc, out.getvalue()

    def test_warns_with_vesper_notes(self):
        rc, out = self._doctor("Notes on VESPER-16 skills")
        self.assertIn("Codex Memories hold VESPER notes from earlier sessions; they would leak", out)
        self.assertNotIn("FAIL", out)
        self.assertEqual(rc, 0)

    def test_silent_without_it(self):
        for c in (None, "other notes"):
            self.assertNotIn("Codex Memories", self._doctor(c)[1])

    def test_silent_for_claude(self):
        self.assertNotIn("Codex Memories", self._doctor("vesper", "claude")[1])


class MemoriesCard(unittest.TestCase):
    CARD = "Codex Memories are ON on this computer. Stage 3 must be a fresh agent with only the skill:"

    def _card(self, config=None, memfile=None):
        w, home = fresh_ws()
        cd = os.path.join(home, "user", ".codex")
        os.makedirs(cd)
        if config is not None:
            with open(os.path.join(cd, "config.toml"), "w") as f:
                f.write(config)
        if memfile is not None:
            os.makedirs(os.path.join(cd, "memories"))
            with open(os.path.join(cd, "memories", "MEMORY.md"), "w") as f:
                f.write(memfile)
        reg = w.Registry.load()
        reg.data["agent"] = "codex"
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            w.memories_card(reg)
        return out.getvalue()

    def test_shown_with_config_flag(self):
        out = self._card(config="[features]\n memories = true  # on\n")
        self.assertIn(self.CARD, out)
        self.assertIn("type /memories first", out)

    def test_shown_with_memory_file(self):
        self.assertIn(self.CARD, self._card(memfile="anything"))

    def test_not_shown_with_neither(self):
        self.assertEqual(self._card(), "")
        self.assertEqual(self._card(config="[features]\nmemories = false\n[other]\nmemories = true\n"), "")


if __name__ == "__main__":
    unittest.main()
