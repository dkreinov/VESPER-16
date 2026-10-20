"""Locked part 4 (opt-in): set VESPER_PART4_PW to the part-4 password to run. Never write the password into a file."""
import json, os, subprocess, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fakes  # noqa: E402
from fakes import fresh_ws, run  # noqa: E402

PW = os.environ.get("VESPER_PART4_PW", "")


@unittest.skipUnless(PW, "set VESPER_PART4_PW to test locked part 4")
class Part4Test(unittest.TestCase):
    def setUp(self):
        try:
            import numpy  # noqa: F401
        except ImportError:
            self.skipTest("the grader needs numpy")
        self.w, self.tmp = fresh_ws()
        run(self.w, "doctor", "--agent", "codex", "--alias", "")
        run(self.w, "unlock", "4", PW)
        self.g = os.path.dirname(self.w.grader_path())

    def test_font_copy_is_identical(self):
        with open(os.path.join(self.g, "t6font.py"), "rb") as a, open(os.path.join(fakes.ROOT, "t6font.py"), "rb") as b:
            self.assertEqual(a.read().replace(b"\r\n", b"\n"), b.read().replace(b"\r\n", b"\n"))

    def test_grades_t6_with_name(self):
        r = subprocess.run([sys.executable, self.w.grader_path(), "T6", os.path.join(fakes.ROOT, "examples", "fill.vsa"),
                            "--name", "mira", "--bin", self.w.vesper_bin()],
                           capture_output=True, text=True, timeout=900, env=dict(os.environ, VESPER_NO_LOG="1"))
        out = json.loads(r.stdout)
        self.assertEqual(out["task"], "T6")
        self.assertIn("name_pixels", out["checks"])
        self.assertLess(out["score"], 90)


if __name__ == "__main__":
    unittest.main()
