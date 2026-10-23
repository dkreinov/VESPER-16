"""Learner-facing card text: project name on the card; no grading hint after stage 1."""
import contextlib, io, os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fakes  # noqa: E402
from fakes import fresh_ws, run  # noqa: E402


def capture(w, *argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        run(w, *argv)
    return out.getvalue()


class CardText(unittest.TestCase):
    def setUp(self):
        self.w, _ = fresh_ws()
        capture(self.w, "doctor", "--agent", "codex", "--alias", "t")

    def test_stage1_card_shows_project_name(self):
        out = capture(self.w, "new", "s1")
        rid = self.w.Registry.load().data["active"]["run_id"]
        name = os.path.basename(os.path.normpath(self.w.Registry.load().data["runs"][rid]["folder"]))
        self.assertIn("Project name in the app: %s" % name, out)

    def test_stage1_done_has_no_grading_hint(self):
        capture(self.w, "new", "s1")
        reg = self.w.Registry.load()
        rid = reg.data["active"]["run_id"]
        t0 = reg.data["active"]["start"]
        fakes.codex_log("0c0d0e0f-0000-1111-2222-333344445555", reg.data["runs"][rid]["folder"],
                        [(t0 + 0.01, 10, 0, 1, "Workshop run: %s" % rid), (t0 + 0.02, 20, 0, 2, "")])
        out = capture(self.w, "done", "--no-form")
        self.assertNotIn("Not graded yet", out)
        self.assertNotIn("unlock 4", out)


if __name__ == "__main__":
    unittest.main()
