"""Clear screen: prints ANSI sequence when sys.stdout.isatty() is true and VESPER_NO_CLEAR is not set."""
import contextlib, io, os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fakes  # noqa: E402
from fakes import fresh_ws  # noqa: E402


class FakeStdout(io.StringIO):
    """StringIO with isatty() method."""
    def __init__(self, isatty_value=False):
        super().__init__()
        self._isatty_value = isatty_value

    def isatty(self):
        return self._isatty_value


class ClearScreen(unittest.TestCase):
    def setUp(self):
        self.w, self.tmp = fresh_ws()
        self.saved_env = {k: os.environ.get(k) for k in ("VESPER_NO_CLEAR",)}
        self.addCleanup(self.restore_env)

    def restore_env(self):
        for k, v in self.saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_clear_screen_not_called_without_tty(self):
        """When stdout is not a TTY, no ANSI sequence is written."""
        original_stdout = sys.stdout
        capture = FakeStdout(isatty_value=False)
        sys.stdout = capture
        try:
            self.w.clear_screen()
        finally:
            sys.stdout = original_stdout
        output = capture.getvalue()
        self.assertNotIn("\x1b[2J", output)

    def test_clear_screen_called_with_tty(self):
        """When stdout is a TTY and VESPER_NO_CLEAR is not set, ANSI sequence is written."""
        self.w._VT[:] = [True]  # Ensure VT mode is available
        original_stdout = sys.stdout
        capture = FakeStdout(isatty_value=True)
        sys.stdout = capture
        try:
            self.w.clear_screen()
        finally:
            sys.stdout = original_stdout
        output = capture.getvalue()
        self.assertIn("\x1b[2J", output)

    def test_clear_screen_not_called_with_no_clear_env(self):
        """When VESPER_NO_CLEAR is set, no ANSI sequence is written even with TTY."""
        os.environ["VESPER_NO_CLEAR"] = "1"
        self.w._VT[:] = [True]  # Ensure VT mode is available
        original_stdout = sys.stdout
        capture = FakeStdout(isatty_value=True)
        sys.stdout = capture
        try:
            self.w.clear_screen()
        finally:
            sys.stdout = original_stdout
        output = capture.getvalue()
        self.assertNotIn("\x1b[2J", output)

    def test_new_s1_output_starts_with_clear_sequence(self):
        """When running 'new s1' with a fake TTY, output starts with clear sequence."""
        os.environ.pop("VESPER_NO_CLEAR", None)
        self.w._VT[:] = [True]  # Ensure VT mode is available
        original_stdout = sys.stdout
        capture = FakeStdout(isatty_value=True)
        sys.stdout = capture
        try:
            fakes.run(self.w, "new", "s1")
        except SystemExit:
            pass  # run exits after printing the prompt
        finally:
            sys.stdout = original_stdout
        output = capture.getvalue()
        self.assertTrue(output.startswith("\x1b[2J"), f"Output does not start with clear sequence. Output: {repr(output[:100])}")

    def test_new_s1_no_output_clear_with_env(self):
        """When running 'new s1' with VESPER_NO_CLEAR=1, output does not start with clear sequence."""
        os.environ["VESPER_NO_CLEAR"] = "1"
        self.w._VT[:] = [True]  # Ensure VT mode is available
        original_stdout = sys.stdout
        capture = FakeStdout(isatty_value=True)
        sys.stdout = capture
        try:
            fakes.run(self.w, "new", "s1")
        except SystemExit:
            pass  # run exits after printing the prompt
        finally:
            sys.stdout = original_stdout
        output = capture.getvalue()
        self.assertFalse(output.startswith("\x1b[2J"), f"Output starts with clear sequence but should not. Output: {repr(output[:100])}")


if __name__ == "__main__":
    unittest.main()
