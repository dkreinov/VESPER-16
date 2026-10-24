"""Cursor app (manual) learners: stage-3 page lines, model and time from Cursor's local data, charts."""
import contextlib, io, json, os, sqlite3, sys, time, unittest
from unittest import mock
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fakes  # noqa: E402
from fakes import fresh_ws, run, flat  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
import charts  # noqa: E402
import measure  # noqa: E402


def capture(w, *argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = run(w, *argv)
    return out.getvalue(), rc


def make_db(path, chats):
    """chats: list of (composer id, run id in the first message, createdAt s, lastUpdatedAt s, modelName)."""
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE cursorDiskKV (key TEXT UNIQUE ON CONFLICT REPLACE, value BLOB)")
    for cid, rid, c, l, model in chats:
        d = {"createdAt": int(c * 1000), "lastUpdatedAt": int(l * 1000)}
        if model is not None:
            d["modelConfig"] = {"modelName": model}
        con.execute("INSERT INTO cursorDiskKV VALUES (?, ?)", ("composerData:" + cid, json.dumps(d)))
        con.execute("INSERT INTO cursorDiskKV VALUES (?, ?)", ("bubbleId:%s:b1" % cid,
                    json.dumps({"type": 1, "text": "Workshop run: %s. Do the task." % rid})))
        con.execute("INSERT INTO cursorDiskKV VALUES (?, ?)", ("bubbleId:%s:b2" % cid, json.dumps({"text": "ok"})))
    con.commit()
    con.close()


class CursorAppData(unittest.TestCase):
    def setUp(self):
        self.w, self.home = fresh_ws()
        self.db = os.path.join(self.home, "state.vscdb")
        os.environ["VESPER_CURSOR_STATE"] = self.db
        self.addCleanup(os.environ.pop, "VESPER_CURSOR_STATE", None)

    def test_finds_the_chat_by_run_id(self):
        now = time.time()
        make_db(self.db, [("c1", "s1-aaaa", now - 900, now - 600, "gpt-5.6-luna-high"),
                          ("c2", "s1-bbbb", now - 500, now - 100, "default")])
        c = measure.cursor_app_chat("s1-aaaa", self.db)
        self.assertEqual(c["model"], "gpt-5.6-luna-high")
        self.assertAlmostEqual(c["last"] - c["first"], 300, delta=1)
        self.assertEqual(measure.cursor_app_chat("s1-bbbb", self.db)["model"], "auto")      # "default" = Auto
        self.assertIsNone(measure.cursor_app_chat("s1-zzzz", self.db))

    def test_never_crashes(self):
        self.assertIsNone(measure.cursor_app_chat("s1-aaaa", os.path.join(self.home, "none.vscdb")))
        with open(self.db, "w") as f:
            f.write("this is not a database")
        self.assertIsNone(measure.cursor_app_chat("s1-aaaa", self.db))
        os.remove(self.db)
        con = sqlite3.connect(self.db)
        con.execute("CREATE TABLE other (a)")
        con.close()
        self.assertIsNone(measure.cursor_app_chat("s1-aaaa", self.db))

    def test_database_is_opened_read_only(self):
        make_db(self.db, [("c1", "s1-aaaa", 1, 2, "x")])
        before = os.path.getmtime(self.db)
        measure.cursor_app_chat("s1-aaaa", self.db)
        self.assertEqual(os.path.getmtime(self.db), before)

    def _start(self):
        run(self.w, "doctor", "--agent", "cursor", "--alias", "t")
        capture(self.w, "new", "s1")
        reg = self.w.Registry.load()
        rid = reg.data["active"]["run_id"]
        return rid

    def _backdate(self, rid, sec=600):
        reg = self.w.Registry.load()
        reg.get_active(rid)["start"] = time.time() - sec
        reg.save()

    def test_done_records_model_and_time_without_asking(self):
        rid = self._start()
        self._backdate(rid)
        now = time.time()
        make_db(self.db, [("c1", rid, now - 590, now - 290, "gpt-5.6-luna-high")])
        with mock.patch.object(self.w, "ask", side_effect=AssertionError("asked")):
            out, _ = capture(self.w, "done", "--no-form")
        self.assertIn("  Tokens and cost: not available in the Cursor app.", out)
        self.assertNotIn("input tokens", out)
        r = self.w.Registry.load().row(rid, "1")
        self.assertEqual((r["measurement"], r["model"]), ("cursor-app", "gpt-5.6-luna-high"))
        self.assertAlmostEqual(float(r["elapsed_min"]), 5.0, delta=0.2)
        self.assertEqual(r["tok_out"], "")
        self.assertEqual(r["cost_usd"], "")

    def test_done_without_data_is_unknown_not_a_crash(self):
        rid = self._start()
        out, rc = capture(self.w, "done", "--no-form")
        self.assertEqual(rc, 0)
        self.assertIn("Tokens and cost: not available in the Cursor app.", out)
        r = self.w.Registry.load().row(rid, "1")
        self.assertEqual((r["measurement"], r["model"], r["elapsed_min"]), ("cursor-app", "", ""))

    def test_auto_model_is_not_a_matched_pair(self):
        self.assertEqual(self.w.settings_match({"model": "auto"}, {"model": "auto"}), "")
        self.assertEqual(self.w.settings_match({"model": "gpt-5.6-luna-high"}, {"model": "gpt-5.6-luna-high"}),
                         "no_effort")

    def test_stage3_page_lines_for_cursor(self):
        run(self.w, "doctor", "--agent", "cursor", "--alias", "t")
        fakes.ready_for_s3  # (the codex helper is not used: this learner uses Cursor)
        reg = self.w.Registry.load()
        lines = self.w.cursor_app_lines("cursor")
        self.assertEqual(lines, ["  Model: GPT-5.6 Luna High (gpt-5.6-luna-high) in all 4 chats.",
                                 "  Not Auto. Do not use Plan mode.",
                                 "  Tokens and cost: not shown by the Cursor app. Want them? Use --auto."])
        self.assertTrue(all(len(x) <= 72 for x in lines))
        self.assertEqual(self.w.cursor_app_lines("codex"), [])


class ChartsCursorApp(unittest.TestCase):
    def test_cost_chart_leaves_cursor_app_rows_out(self):
        base = dict(alias="a", agent="cursor", effort="", grading="graded", stage="3", revision="1")
        rows = [dict(base, run_id="s1-aaaa", stage="1", task="T3", score="100", cost_usd="0.50", measurement="log",
                     elapsed_min="4", model="m"),
                dict(base, run_id="s3-aaaa-t6-bbbb", task="T6", score="100", cost_usd="0.10",
                     measurement="cursor-app", elapsed_min="3", model="m")]
        mt = charts.money_time(charts.learners(rows))
        self.assertEqual(mt["cost"][0][1], None)
        self.assertEqual(mt["time"][0][1], 3.0)
        specs = charts.chart_specs(rows)
        self.assertIn("cursor-app", specs[0]["hint"])
        self.assertEqual(charts.chart_specs([r for r in rows if r["measurement"] != "cursor-app"])[0]["hint"], "")


if __name__ == "__main__":
    unittest.main()
