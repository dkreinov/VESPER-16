"""judge: a fresh-thread check of the harvested skill; folder, prompt, clipboard, errors, cleanup."""
import os, sys, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fakes
from fakes import fresh_ws, run
from test_submit import cap


class Judge(unittest.TestCase):
    def setUp(self):
        self.w, _ = fresh_ws()

    def _ready(self):
        rid, out = fakes.ready_for_s3(self.w)
        snap = self.w.snap_path(rid, "1")
        os.makedirs(os.path.dirname(snap), exist_ok=True)
        with open(snap, "w") as f:
            f.write("; T3 solution\nbounce: nop\n")
        return rid, out

    def test_harvest_prints_hint(self):
        _, out = self._ready()
        self.assertIn("Want a better check (2 minutes, optional)?  python workshop.py judge", out)

    def test_error_without_skill(self):
        with self.assertRaises(SystemExit) as cm:
            run(self.w, "judge")
        self.assertIn("No harvested skill", str(cm.exception))

    def test_folder_prompt_clipboard_cleanup(self):
        w = self.w
        rid, _ = self._ready()
        clips = []
        out, _ = cap(w, "judge", clips=clips)
        folder = os.path.join(w.ws_home(), "judge-" + rid)
        for rel in ("skill/SKILL.md", "t3-solution.vsa", "tasks/T3.md", "kit-examples/fill.vsa"):
            self.assertTrue(os.path.isfile(os.path.join(folder, rel)), rel)
        self.assertIn(folder, [i["path"] for i in w.Registry.load().data["items"]])
        self.assertEqual(len(clips), 1)
        for t in (clips[0], out):
            for path in ("skill/", "t3-solution.vsa", "tasks/T3.md", "kit-examples/"):
                self.assertIn(path, t)
            self.assertIn("KNOWLEDGE", t)
            self.assertIn("ANSWER", t)
        self.assertIn("Open a NEW thread (any model; memory off)", out)
        self.assertIn("Nothing is graded or sent.", out)
        run(w, "cleanup", "--yes", "--no-copy")
        self.assertFalse(os.path.exists(folder))


if __name__ == "__main__":
    unittest.main()
