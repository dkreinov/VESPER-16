"""Display only: frame picture (half blocks / '#' fallback) and the ordered last-steps NEXT box."""
import contextlib, io, os, sys, tempfile, types, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fakes import fresh_ws  # noqa: E402


class Out(io.StringIO):
    def __init__(self, encoding):
        super().__init__()
        self._enc = encoding

    @property
    def encoding(self):
        return self._enc


def frame_text(w, encoding):
    px = bytearray(3072)
    px[0 * 64 + 0] = px[1 * 64 + 0] = 1      # column 0: top + bottom
    px[0 * 64 + 1] = 1                        # column 1: top only
    px[1 * 64 + 2] = 1                        # column 2: bottom only; column 3: none

    def fake_run(cmd, **kw):
        with open(cmd[cmd.index("--dump") + 1], "wb") as f:
            f.write(bytes(px))
        return types.SimpleNamespace(returncode=0)

    sol = tempfile.NamedTemporaryFile(suffix=".vsa", delete=False)
    sol.close()
    real = w.subprocess
    w.subprocess = types.SimpleNamespace(run=fake_run)
    out = Out(encoding)
    try:
        with contextlib.redirect_stdout(out):
            return w.ascii_frame(sol.name)
    finally:
        w.subprocess = real
        os.remove(sol.name)


class FrameTest(unittest.TestCase):
    def setUp(self):
        self.w, _ = fresh_ws()

    def test_half_blocks(self):
        txt = frame_text(self.w, "utf-8")
        lines = txt.split("\n")
        self.assertEqual(len(lines), 1 + 1 + 24 + 1)
        self.assertTrue(lines[2].startswith("|█▀▄ "))
        self.assertNotIn("#", "".join(lines[2:]))

    def test_ascii_fallback(self):
        txt = frame_text(self.w, "ascii")
        lines = txt.split("\n")
        self.assertEqual(len(lines), 1 + 1 + 24 + 1)
        self.assertTrue(lines[2].startswith("|### "))
        self.assertNotIn("█", txt)
        self.assertTrue(lines[1].startswith("+---"))


class AllDoneBoxTest(unittest.TestCase):
    def setUp(self):
        self.w, _ = fresh_ws()
        self.reg = self.w.Registry.load()

    def box(self, **kw):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.w.all_done_box(self.reg, **kw)
        return out.getvalue()

    def _grader(self, on):
        p = self.w.grader_path()
        if on:
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, "w").close()

    def test_locked_ungraded(self):
        self.reg.set_row("s1-a", "1", dict(task="T3", grading="ungraded", start="1"))
        out = self.box()
        self.assertIn("NEXT: all agents are done. Now:", out)
        for n, t in enumerate(("unlock 4 <password from the slide>   (once)", "grade", "show", "submit"), 1):
            self.assertIn("%d. python workshop.py %s" % (n, t), out)

    def test_unlocked_ungraded(self):
        self._grader(True)
        self.reg.set_row("s1-a", "1", dict(task="T3", grading="ungraded", start="1"))
        out = self.box()
        self.assertNotIn("unlock", out)
        self.assertIn("1. python workshop.py grade", out)
        self.assertIn("2. python workshop.py show", out)
        self.assertIn("3. python workshop.py submit", out)

    def test_after_grade_shows_show_then_submit(self):
        self._grader(True)
        self.reg.set_row("s1-a", "1", dict(task="T3", grading="graded", score="90", start="1"))
        out = self.box()
        self.assertNotIn("workshop.py grade", out)
        self.assertIn("1. python workshop.py show", out)
        self.assertIn("2. python workshop.py submit", out)

    def test_after_show_only_submit(self):
        self._grader(True)
        self.reg.set_row("s1-a", "1", dict(task="T3", grading="graded", score="90", start="1"))
        out = self.box(show=False)
        self.assertNotIn("workshop.py show", out)
        self.assertIn("1. python workshop.py submit", out)


if __name__ == "__main__":
    unittest.main()
