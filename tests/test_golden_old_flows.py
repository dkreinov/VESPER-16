"""The OLD flows print the same text as before semi mode: manual pages with no launcher (every agent) and --auto.
The golden files in tests/golden were captured from the code BEFORE the semi-mode change (commit fc7690d) with
tests/golden_capture.py. Only text that the spec adds is ignored: the mode line, the doctor INFO line for the app,
and the Cursor 'chat not found' hint. Windows only (the golden text was captured on Windows)."""
import os, re, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import golden_capture as G  # noqa: E402

GOLD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golden")
_CACHE = {}


def strip_added(text):
    t = text.replace("\\", "/")
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r" ?Mode: MANUAL\..*?--mode semi", "", t)
    t = t.replace(" INFO app not found: semi mode falls back to manual", "")
    t = re.sub(r" ?Cursor chat not found\. This is only a hint.*?when the chat is saved\.", "", t)
    for tok in ("Python <V>",):
        t = t.replace(tok, "")
    return t.strip()


def current():
    if not _CACHE:
        _CACHE.update(G.capture_all())
    return _CACHE


@unittest.skipUnless(sys.platform == "win32", "golden text was captured on Windows")
class GoldenOldFlows(unittest.TestCase):
    def check(self, prefix):
        names = sorted(n[:-4] for n in os.listdir(GOLD) if n.startswith(prefix) and n.endswith(".txt"))
        self.assertTrue(names)
        got = current()
        for n in names:
            with self.subTest(page=n):
                with open(os.path.join(GOLD, n + ".txt"), encoding="utf-8") as f:
                    want = f.read()
                self.assertIn(n, got)
                self.assertEqual(strip_added(got[n]), strip_added(want))

    def test_codex_manual(self):
        self.check("codex-")

    def test_claude_manual(self):
        self.check("claude-")

    def test_cursor_manual(self):
        self.check("cursor-")

    def test_copilot_manual(self):
        self.check("copilot-")

    def test_the_pages_are_there_for_all_four_agents(self):
        got = current()
        for agent in G.AGENTS:
            for page in ("doctor", "new-s1", "done-s1", "skill", "harvest", "new-s3-all", "new-s3-T3-again"):
                self.assertIn("%s-%s" % (agent, page), got)
        for agent in G.AUTO_AGENTS:
            self.assertIn("%s-auto-T3" % agent, got)


if __name__ == "__main__":
    unittest.main()
