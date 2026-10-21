"""v2 prompt lines: work alone in every stage; stage 3 has a budget of 6 runs and the small-model card."""
import contextlib, io, os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fakes  # noqa: E402
from fakes import fresh_ws, run  # noqa: E402

WORK_ALONE = "Work on your own until the task is done. Do not stop to ask for approval or a design review."


class PromptsV2(unittest.TestCase):
    def setUp(self):
        self.w, _ = fresh_ws()

    def render(self, name):
        return self.w.render_prompt(name, task="T6", run_id="s3-ab12-t6-9f3c", guide="/g", builtin_how="x")

    def test_every_prompt_says_work_alone(self):
        for n in ["stage1", "stage3"] + ["stage2-" + m for m in self.w.METHODS]:
            self.assertIn(WORK_ALONE, self.render(n), n)

    def test_stage3_budget_is_6_and_stage1_stays_20(self):
        p3 = self.render("stage3")
        self.assertIn("You have 6 runs of `bin/vesper run`", p3)
        self.assertNotIn("20 runs", p3)
        self.assertIn("You have 20 runs of `bin/vesper run`", self.render("stage1"))
        # F11: assert that str(S3_RUN_BUDGET) appears in prompts/stage3.md
        with open(os.path.join(self.w.KIT, "prompts", "stage3.md"), encoding="utf-8") as f:
            self.assertIn(str(self.w.S3_RUN_BUDGET), f.read())

    def test_stage3_card_names_small_model_and_time_box(self):
        fakes.ready_for_s3(self.w)                       # agent = codex
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            run(self.w, "new", "s3", "--task", "T6", "--name", "mira")
        text = out.getvalue()
        for s in ("model gpt-6-luna", "Time box 10 min: stop any agent still working at 10 min, then run its done line.", "6 runs each", "RUN  T6 (new task)", "name on T6: MIRA"):
            self.assertIn(s, text)
        self.assertNotIn("Haiku", text)


if __name__ == "__main__":
    unittest.main()
