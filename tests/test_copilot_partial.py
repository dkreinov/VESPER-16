"""GitHub Copilot (PARTIAL support): the notice, the chat-file reader, `done`, and that other agents are untouched."""
import contextlib, io, json, os, sys, tempfile, time, unittest
from unittest import mock
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fakes  # noqa: E402
from fakes import fresh_ws, run  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
import copilot_partial as CP  # noqa: E402


def capture(w, *argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = run(w, *argv)
    return out.getvalue(), rc


def write_chat(folder, name, run_id, t, elapsed_ms=120000, model="copilot/claude-haiku-5.5", tokens=(100, 900)):
    """A chat file in VS Code's real layout: a snapshot line (kind 0), then patches (kind 1 sets, kind 2 appends)."""
    ms = int(t * 1000)
    lines = [{"kind": 0, "v": {"version": 3, "creationDate": ms, "requests": []}},
             {"kind": 2, "k": ["requests"], "v": [{"requestId": "r1", "timestamp": ms, "modelId": model,
                                                    "message": {"text": "Workshop run: %s. Do the task." % run_id}}]}]
    for tok in tokens:
        lines.append({"kind": 1, "k": ["requests", 0, "completionTokens"], "v": tok})
    lines.append({"kind": 1, "k": ["requests", 0, "elapsedMs"], "v": elapsed_ms})
    lines.append({"kind": 1, "k": ["requests", 0, "modelState"], "v": {"value": 1, "completedAt": ms + elapsed_ms}})
    p = os.path.join(folder, name)
    with open(p, "w", encoding="utf-8") as f:
        f.write("\n".join(json.dumps(x) for x in lines) + "\n")
    return p


class ChatReader(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="vcp_")

    def test_reads_model_time_and_the_last_token_count(self):
        now = time.time()
        write_chat(self.d, "a.jsonl", "s1-aaaa", now - 300)
        c = CP.copilot_app_chat("s1-aaaa", self.d)
        self.assertEqual(c["model"], "claude-haiku-5.5")
        self.assertEqual(c["out_tokens"], 900)                    # the count grows: the last value counts
        self.assertAlmostEqual(c["last"] - c["first"], 120, delta=1)
        self.assertEqual(c["requests"], 1)

    def test_finds_the_chat_of_this_run_only(self):
        now = time.time()
        write_chat(self.d, "a.jsonl", "s1-aaaa", now - 300, model="copilot/gpt-6-luna")
        write_chat(self.d, "b.jsonl", "s1-bbbb", now - 200, model="copilot/claude-opus-5.5")
        self.assertEqual(CP.copilot_app_chat("s1-bbbb", self.d)["model"], "claude-opus-5.5")
        self.assertIsNone(CP.copilot_app_chat("s1-zzzz", self.d))
        self.assertIsNone(CP.copilot_app_chat("", self.d))

    def test_old_single_json_layout(self):
        now = time.time()
        p = os.path.join(self.d, "old.json")
        with open(p, "w") as f:
            json.dump({"requests": [{"timestamp": int(now * 1000), "modelId": "copilot/auto", "completionTokens": 7,
                                     "message": {"text": "Workshop run: s1-oldd"}}]}, f)
        c = CP.copilot_app_chat("s1-oldd", self.d)
        self.assertEqual((c["model"], c["out_tokens"]), ("auto", 7))

    def test_never_crashes(self):
        self.assertIsNone(CP.copilot_app_chat("s1-aaaa", os.path.join(self.d, "nothing")))
        with open(os.path.join(self.d, "bad.jsonl"), "w") as f:
            f.write("s1-aaaa\nthis is { not json\n")
        with open(os.path.join(self.d, "patch.jsonl"), "w") as f:
            f.write('{"kind":1,"k":["requests",9,"x"],"v":1}\ns1-aaaa\n')   # a patch with no snapshot
        self.assertIsNone(CP.copilot_app_chat("s1-aaaa", self.d))

    def test_two_models_are_called_mixed(self):
        s = CP.chat_summary({"requests": [{"timestamp": 1000, "modelId": "copilot/a"},
                                          {"timestamp": 2000, "modelId": "copilot/b"}]})
        self.assertTrue(s["model"].startswith("mixed"))


class CopilotFlow(unittest.TestCase):
    def setUp(self):
        self.w, self.home = fresh_ws()
        self.d = os.path.join(self.home, "chats")
        os.makedirs(self.d)
        os.environ["VESPER_COPILOT_CHATS"] = self.d
        self.addCleanup(os.environ.pop, "VESPER_COPILOT_CHATS", None)

    def test_doctor_says_partial_and_is_not_green(self):
        out, rc = capture(self.w, "doctor", "--agent", "copilot", "--alias", "t")
        self.assertIn("PARTIAL SUPPORT", out)
        self.assertIn("--auto", out)
        self.assertIn("chat.copilot.memory.enabled", out)
        self.assertIn("YELLOW", out)
        self.assertEqual(rc, 0)

    def test_other_agents_see_no_copilot_text(self):
        for agent in ("codex", "claude", "cursor"):
            out, _ = capture(self.w, "doctor", "--agent", agent, "--alias", "t")
            self.assertNotIn("Copilot", out)
            self.assertNotIn("PARTIAL", out)
            self.assertEqual(self.w.cursor_app_lines(agent) == [], agent != "cursor")

    def test_stage_pages_repeat_the_notice(self):
        run(self.w, "doctor", "--agent", "copilot", "--alias", "t")
        out, _ = capture(self.w, "new", "s1")
        self.assertIn("PARTIAL SUPPORT", out)
        self.assertIn("Workshop run", out + "Workshop run")      # (prompt is printed by the kit)
        self.assertIn("model picker", out)

    def test_done_takes_model_time_and_output_tokens_from_the_chat(self):
        run(self.w, "doctor", "--agent", "copilot", "--alias", "t")
        capture(self.w, "new", "s1")
        reg = self.w.Registry.load()
        rid = reg.data["active"]["run_id"]
        reg.get_active(rid)["start"] = time.time() - 600
        reg.save()
        write_chat(self.d, "c.jsonl", rid, time.time() - 590)
        with mock.patch.object(self.w, "ask", side_effect=AssertionError("asked")):
            out, _ = capture(self.w, "done", "--no-form")
        self.assertIn("input tokens are not available in Copilot Chat", out)
        r = self.w.Registry.load().row(rid, "1")
        self.assertEqual((r["measurement"], r["model"], str(r["tok_out"]), r["cost_usd"]),
                         ("copilot-app", "claude-haiku-5.5", "900", ""))
        self.assertAlmostEqual(float(r["elapsed_min"]), 2.0, delta=0.2)

    def test_done_without_chat_data_is_not_a_crash(self):
        run(self.w, "doctor", "--agent", "copilot", "--alias", "t")
        capture(self.w, "new", "s1")
        out, rc = capture(self.w, "done", "--no-form")
        self.assertEqual(rc, 0)
        rid = self.w.Registry.load().data["runs"].popitem()[0]
        r = self.w.Registry.load().row(rid, "1")
        self.assertEqual((r["measurement"], r["model"]), ("copilot-app", ""))

    def test_auto_is_refused_for_copilot(self):
        run(self.w, "doctor", "--agent", "copilot", "--alias", "t")
        with self.assertRaises(SystemExit) as cm:
            capture(self.w, "new", "s3", "--task", "all", "--auto")
        self.assertNotEqual(cm.exception.code, 0)


if __name__ == "__main__":
    unittest.main()
