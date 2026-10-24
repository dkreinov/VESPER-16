"""A CLI version line can come after warning lines (Linux codex prints a WARNING first)."""
import os, sys, unittest
from unittest import mock
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fakes import fresh_ws  # noqa: E402


class CliVersion(unittest.TestCase):
    def setUp(self):
        self.w, _ = fresh_ws()

    def ver(self, out):
        with mock.patch.dict(os.environ, {"VESPER_DOCTOR_SKIP_CLI": ""}), \
                mock.patch.object(self.w, "_run_text", return_value=out):
            return self.w._exe_version(["codex"])

    def test_warning_first(self):
        out = ("WARNING: failed to clean up stale arg0 temp dirs: Directory not empty (os error 39)\n"
               "codex-cli 0.163.0")
        v = self.ver(out)
        self.assertEqual(v, "codex-cli 0.163.0")
        self.assertGreaterEqual(self.w._version_tuple(v), self.w.CODEX_MIN)

    def test_plain(self):
        self.assertEqual(self.ver("codex-cli 0.154.0"), "codex-cli 0.154.0")

    def test_empty(self):
        self.assertEqual(self.ver(""), "")


if __name__ == "__main__":
    unittest.main()
