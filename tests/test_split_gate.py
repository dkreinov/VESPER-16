"""Split Codex threads (parent_child rollout files) and the per-run confirmation gate."""
import contextlib, io, os, sys, time, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fakes  # noqa: E402
from fakes import fresh_ws, run, codex_log  # noqa: E402

P = "01a15dd4-8bae-7ab1-b6c2-d3131c119a0c"
C = "01a15dd4-d9fb-77d2-80f3-57da067494eb"
OTHER = "0aaaaaaa-1111-2222-3333-444444444444"


class TTYOut(io.StringIO):
    def isatty(self):
        return True


class SplitThread(unittest.TestCase):
    def setUp(self):
        self.w, self.home = fresh_ws()
        self.t = time.time() - 600
        t = self.t
        self.parent = codex_log(P, "/x", [(t, 100, 0, 10, "run s1-abcd"), (t + 5, 200, 50, 148, "")], model="gpt-6-luna")
        self.child = codex_log(P + "_" + C, "/x", [(t + 10, 1000, 400, 5000, "run s1-abcd"), (t + 60, 3000, 900, 9000, "")],
                               model="gpt-6.1-sol")

    def test_one_session(self):
        s = self.w.find_sessions("s1-abcd")
        self.assertEqual(len(s), 1)
        self.assertEqual(s[0]["sid"], P)
        self.assertEqual(sorted(s[0]["paths"]), sorted([self.parent, self.child]))
        self.assertEqual(self.w.pick_session("s1-abcd", "/x")["sid"], P)

    def test_different_threads_stay_separate(self):
        codex_log(OTHER, "/x", [(self.t, 1, 0, 1, "run s1-abcd"), (self.t + 5, 2, 0, 2, "")])
        self.assertEqual(len(self.w.find_sessions("s1-abcd")), 2)

    def test_measure_sums_and_marks_switch(self):
        s = self.w.find_sessions("s1-abcd")[0]
        m = self.w.measure_stage({"folder": self.home, "session": s}, self.t - 1, time.time())
        self.assertEqual(m["tok_out"], 148 + 9000)
        self.assertEqual(m["tok_cache_read"], 50 + 900)
        self.assertEqual(m["tok_uncached"], (200 - 50) + (3000 - 900))
        self.assertEqual(m["model"], "gpt-6.1-sol")
        self.assertEqual(m["model_switched"], "yes")

    def test_same_model_not_switched(self):
        os.remove(self.child)
        codex_log(P + "_" + C, "/x", [(self.t + 10, 10, 0, 10, "run s1-abcd"), (self.t + 60, 30, 0, 90, "")], model="gpt-6-luna")
        s = self.w.find_sessions("s1-abcd")[0]
        m = self.w.measure_stage({"folder": self.home, "session": s}, self.t - 1, time.time())
        self.assertEqual(m["model_switched"], "no")

    def test_single_file_has_no_switch_field(self):
        os.remove(self.child)
        s = self.w.find_sessions("s1-abcd")[0]
        m = self.w.measure_stage({"folder": self.home, "session": s}, self.t - 1, time.time())
        self.assertEqual(m["model_switched"], "")

    def test_method_and_memory_scan_all_files(self):
        s = self.w.find_sessions("s1-abcd")[0]
        import json
        with open(self.child, "a") as f:
            f.write(json.dumps({"timestamp": fakes.iso(self.t + 30), "type": "response_item", "payload": {
                "type": "function_call", "name": "shell",
                "arguments": json.dumps({"cmd": "cat ~/.codex/memories/MEMORY.md"})}}) + "\n")
        self.assertEqual(self.w.detect_memory_used(self.w.session_paths(s), self.t - 1, time.time()), "yes")
        self.assertEqual(self.w.detect_memory_used(self.parent, self.t - 1, time.time()), "no")

    def test_old_stored_session_finds_siblings(self):
        old = {"agent": "codex", "sid": P, "path": self.parent}
        self.assertEqual(sorted(self.w.session_paths(old)), sorted([self.parent, self.child]))


class Gate(unittest.TestCase):
    def setUp(self):
        self.w, _ = fresh_ws()
        os.environ["VESPER_NO_CLEAR"] = "1"
        self.addCleanup(os.environ.pop, "VESPER_NO_CLEAR", None)

    def _tty(self, answers, *argv):
        asked = []

        def fake_ask(prompt, default=""):
            if "Done with these" not in prompt and "Press Enter" not in prompt:
                return default
            asked.append(prompt)
            sys.stdout.write(prompt)
            return answers.pop(0) if answers else default
        self.w.ask = fake_ask
        out = TTYOut()
        with contextlib.redirect_stdout(out):
            run(self.w, *argv)
        return out.getvalue(), asked

    def test_s1_gate_repeats_on_n_and_records(self):
        out, asked = self._tty(["n", "y"], "new", "s1")
        self.assertEqual([p for p in asked if "Done with these steps" in p].__len__(), 2)
        self.assertEqual(out.count("Open this folder as a NEW project"), 2)
        self.assertIn("your default model", out)
        self.assertLess(out.index("Done with these steps"), out.rindex("PROMPT"))
        self.assertIn("Paste it and send it.", out)
        self.assertEqual(out.count("NEXT:"), 1)
        reg = self.w.Registry.load()
        self.assertEqual(list(reg.data["runs"].values())[0]["settings_confirmed"], "yes")

    def test_prompt_hidden_before_confirmation(self):
        out, _ = self._tty(["y"], "new", "s1")
        first = out.index("Done with these steps")
        self.assertNotIn("END OF PROMPT", out[:first])

    def test_not_tty_no_questions(self):
        real = self.w.ask
        self.w.ask = lambda p, d="": self.fail(p) if ("Done with" in p or "Press Enter" in p) else real(p, d)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            run(self.w, "new", "s1")
        self.assertIn("END OF PROMPT", out.getvalue())
        self.assertNotIn("Done with these steps", out.getvalue())
        reg = self.w.Registry.load()
        rid = list(reg.data["runs"])[0]
        self.assertNotIn("settings_confirmed", reg.data["runs"][rid])

    def test_s3_not_tty_records_not_asked(self):        # ruling R9: no gate -> "not_asked", never "no"
        fakes.ready_for_s3(self.w)
        with contextlib.redirect_stdout(io.StringIO()):
            run(self.w, "new", "s3", "--task", "all", "--name", "MIRA")
        reg = self.w.Registry.load()
        rids = [x["run_id"] for x in reg.actives("3")]
        self.assertEqual(len(rids), 4)
        self.assertEqual({reg.data["runs"][r].get("settings_confirmed") for r in rids}, {"not_asked"})
        with contextlib.redirect_stdout(io.StringIO()):
            run(self.w, "done", rids[0], "--no-form")
        self.assertEqual(self.w.Registry.load().row(rids[0], "3")["settings_confirmed"], "not_asked")

    def test_s3_both_pages_and_row(self):
        s1, _ = fakes.ready_for_s3(self.w)
        out, asked = self._tty(["y", "", "y"], "new", "s3", "--task", "both", "--name", "MIRA")
        self.assertEqual(len([p for p in asked if "Done with these steps" in p]), 2)
        self.assertEqual(len([p for p in asked if "Press Enter for the next run" in p]), 1)
        self.assertIn("RUN 1 of 2", out)
        self.assertIn("gpt-6-luna", out)
        self.assertEqual(out.count("NEXT:"), 1)
        reg = self.w.Registry.load()
        rids = [x["run_id"] for x in reg.actives()]
        self.assertEqual({reg.data["runs"][r].get("settings_confirmed") for r in rids}, {"yes"})
        self.assertIn("settings_confirmed", self.w.ROW_FIELDS)
        self.assertEqual(self.w.ROW_FIELDS[-5:], ["isolation", "isolation_note", "overrun", "stopped", "error_note"])


if __name__ == "__main__":
    unittest.main()
