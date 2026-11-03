"""Cursor message-stamp timing and effort; Codex memory_mode reader (real layouts, temp SQLite files)."""
import json, os, sqlite3, sys, tempfile, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
import measure  # noqa: E402


def cursor_db(path, bubbles, composer, cid="c1"):
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE cursorDiskKV (key TEXT UNIQUE ON CONFLICT REPLACE, value BLOB)")
    for i, b in enumerate(bubbles):
        con.execute("INSERT INTO cursorDiskKV VALUES (?, ?)", ("bubbleId:%s:b%d" % (cid, i), json.dumps(b)))
    con.execute("INSERT INTO cursorDiskKV VALUES (?, ?)", ("composerData:" + cid, json.dumps(composer)))
    con.commit()
    con.close()


def codex_db(path, rows, table="threads"):
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE %s (id TEXT, cwd TEXT, model TEXT, reasoning_effort TEXT, memory_mode TEXT, "
                "first_user_message TEXT, updated_at INTEGER)" % table)
    for r in rows:
        con.execute("INSERT INTO %s VALUES (?,?,?,?,?,?,?)" % table, r)
    con.commit()
    con.close()


class CursorStamps(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.addCleanup(self.d.cleanup)
        self.db = os.path.join(self.d.name, "state.vscdb")

    def comp(self, params=None):
        return {"createdAt": 1000 * 1000, "lastUpdatedAt": 1900 * 1000,
                "modelConfig": {"modelName": "grok-4.7",
                                "selectedModels": [{"modelId": "grok-4.7", "parameters": params or []}]}}

    def test_stamps_beat_composer_times(self):
        cursor_db(self.db, [
            {"type": 1, "createdAt": "2026-11-03T08:44:56.582Z", "text": "Workshop run: s1-x. go"},
            {"type": 2, "createdAt": "2026-11-03T08:45:00.382Z", "text": "ok"}], self.comp())
        c = measure.cursor_app_chat("s1-x", self.db)
        self.assertAlmostEqual(c["last"] - c["first"], 3.8, delta=0.01)
        self.assertEqual(c["model"], "grok-4.7")
        self.assertEqual(c["effort"], "")

    def test_first_is_user_bubble_with_run_id(self):
        cursor_db(self.db, [
            {"type": 1, "createdAt": "2026-11-03T08:00:00Z", "text": "hello"},
            {"type": 1, "createdAt": "2026-11-03T08:10:00Z", "text": "run s1-x"},
            {"type": 2, "createdAt": "2026-11-03T08:12:00Z", "text": "s1-x ok"}], self.comp())
        c = measure.cursor_app_chat("s1-x", self.db)
        self.assertAlmostEqual(c["last"] - c["first"], 120, delta=0.01)

    def test_fallback_to_composer_times(self):
        cursor_db(self.db, [{"type": 1, "text": "run s1-x"}, {"type": 2, "createdAt": "garbage"}], self.comp())
        c = measure.cursor_app_chat("s1-x", self.db)
        self.assertEqual((c["first"], c["last"]), (1000.0, 1900.0))

    def test_effort_names(self):
        for pid in ("effort", "reasoning_effort"):
            if os.path.exists(self.db):
                os.remove(self.db)
            cursor_db(self.db, [{"type": 1, "text": "s1-x"}],
                      self.comp([{"id": "context", "value": "1m"}, {"id": pid, "value": "high"}]))
            self.assertEqual(measure.cursor_app_chat("s1-x", self.db)["effort"], "high")


class CodexMemory(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.addCleanup(self.d.cleanup)
        self.db = os.path.join(self.d.name, "state_5.sqlite")

    def test_by_run_id_newest(self):
        codex_db(self.db, [("1", "C:\\a\\x", "m", "high", "enabled", "Workshop run: s1-q", 10),
                           ("2", "C:\\a\\y", "m", "high", "disabled", "Workshop run: s1-q", 20),
                           ("3", "C:\\a\\z", "m", "high", "enabled", "other", 30)])
        self.assertEqual(measure.codex_memory_mode("s1-q", db=self.db), "disabled")

    def test_by_cwd_with_verbatim_prefix(self):
        codex_db(self.db, [("1", "\\\\?\\C:\\w\\cod4", "m", "", "enabled", "x", 10),
                           ("2", "\\\\?\\C:\\w\\cod6", "m", "", "disabled", "x", 11)])
        self.assertEqual(measure.codex_memory_mode("none", "C:\\w\\cod4", self.db), "enabled")
        self.assertEqual(measure.codex_memory_mode("none", "/tmp/cod6/", self.db), "disabled")

    def test_none_cases(self):
        self.assertIsNone(measure.codex_memory_mode("s1", db=os.path.join(self.d.name, "no.sqlite")))
        codex_db(self.db, [], table="other")
        self.assertIsNone(measure.codex_memory_mode("s1", db=self.db))
        os.remove(self.db)
        codex_db(self.db, [("1", "C:\\a", "m", "", "enabled", "hi", 1)])
        self.assertIsNone(measure.codex_memory_mode("s9", "C:\\nope", self.db))

    def test_locked_file(self):
        codex_db(self.db, [("1", "C:\\a", "m", "", "enabled", "s1-q", 1)])
        con = sqlite3.connect(self.db, isolation_level=None)
        con.execute("BEGIN EXCLUSIVE")
        try:
            r = measure.codex_memory_mode("s1-q", db=self.db)
        finally:
            con.execute("ROLLBACK")
            con.close()
        self.assertIsNone(r)                 # the reader is locked out: unknown, never an error

    def test_env_override(self):
        codex_db(self.db, [("1", "C:\\a", "m", "", "disabled", "s1-q", 1)])
        os.environ["VESPER_CODEX_STATE"] = self.db
        self.addCleanup(os.environ.pop, "VESPER_CODEX_STATE", None)
        self.assertEqual(measure.codex_memory_mode("s1-q"), "disabled")


if __name__ == "__main__":
    unittest.main()
