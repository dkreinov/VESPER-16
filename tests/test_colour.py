"""Terminal colour: on only when asked, never inside the prompt text."""
import contextlib, io, os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fakes  # noqa: E402
from fakes import fresh_ws  # noqa: E402


class Colour(unittest.TestCase):
    def setUp(self):
        self.w, self.tmp = fresh_ws()
        self.saved = {k: os.environ.get(k) for k in ("FORCE_COLOR", "NO_COLOR")}
        self.addCleanup(self.restore)

    def restore(self):
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def out(self, fn, *args):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            fn(*args)
        return buf.getvalue()

    def test_force_color_on(self):
        os.environ["FORCE_COLOR"] = "1"
        os.environ.pop("NO_COLOR", None)
        self.w._VT[:] = [True]
        self.assertIn("\x1b[", self.out(self.w.banner, "HELLO"))

    def test_no_color_off(self):
        os.environ.pop("FORCE_COLOR", None)
        os.environ["NO_COLOR"] = "1"
        self.assertNotIn("\x1b[", self.out(self.w.banner, "HELLO"))

    def test_prompt_text_plain(self):
        os.environ["FORCE_COLOR"] = "1"
        self.w._VT[:] = [True]
        text = self.out(self.w.prompt_block, "copy me\nline two")
        self.assertIn("\x1b[", text)
        lines = text.splitlines()
        for body in ("copy me", "line two"):
            self.assertIn(body, lines)  # whole line equals the text: no codes

    def test_change_colour_rules(self):
        os.environ["FORCE_COLOR"] = "1"
        self.w._VT[:] = [True]
        for zero in ("+0%", "-0%"):
            self.assertEqual(self.w.color_change(zero), zero.rjust(10))
        self.assertIn("\x1b[32m", self.w.color_change("-20%"))
        self.assertIn("\x1b[31m", self.w.color_change("+5%"))
        self.assertEqual(self.w.color_change(""), " " * 10)

    def test_tasks_plural(self):
        self.assertEqual(self.w.tasks_word(1), "task")
        self.assertEqual(self.w.tasks_word(2), "tasks")


if __name__ == "__main__":
    unittest.main()
