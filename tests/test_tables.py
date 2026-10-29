"""Result tables: aligned columns (PASS/FAIL marks included), the 'what' column, the change column."""
import contextlib, io, os, re, sys, unittest
from unittest import mock
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fakes import fresh_ws  # noqa: E402


class _TTY(io.StringIO):
    def isatty(self):
        return True


def tty(enc):
    return type("TTY_" + enc.replace("-", ""), (_TTY,), {"encoding": enc})()


# The organiser's real rows (Windows PowerShell).
ORGANISER_ROWS = [
    dict(run_id="s1-6bd6", stage="1", task="T3", elapsed_min="6.8", emulator_runs="4", cost_usd="0.51", score="100.0"),
    dict(run_id="s1-6bd6", stage="2", task="T3", elapsed_min="3.9", emulator_runs="1", cost_usd="0.21", score=""),
    dict(run_id="s3-6bd6-t6-7264", stage="3", task="T6", elapsed_min="7.9", emulator_runs="6", cost_usd="0.03",
         score="100.0", method="plain"),
    dict(run_id="s3-6bd6-n3-d263", stage="3", task="T3", elapsed_min="9.4", emulator_runs="0", cost_usd="0.03",
         score="5.0", method="none", grading="partial"),
]


def pair(score_with="100", score_without="100"):
    """Fake WITH / WITHOUT rows of one task (the numbers of a typical run)."""
    base = dict(stage="3", task="T3", model="gpt-x", effort="high")
    rw = dict(base, run_id="s3-aaaa-t3-1111", elapsed_min="5.0", emulator_runs="3", cost_usd="0.30",
              tok_uncached="200000", tok_cache_read="1000000", tok_cache_write="0", tok_out="30000",
              score=score_with, method="plain")
    rc = dict(base, run_id="s3-aaaa-n3-2222", elapsed_min="5.9", emulator_runs="1", cost_usd="0.60",
              tok_uncached="300000", tok_cache_read="1200000", tok_cache_write="0", tok_out="45000",
              score=score_without, method="none")
    return rw, rc


class Fixture(unittest.TestCase):
    def setUp(self):
        self.w, _ = fresh_ws()

    def shown(self, enc, fn, *a, **k):
        out = tty(enc)
        with mock.patch.object(sys, "stdout", out), mock.patch.object(self.w, "term_cols", lambda: 120):
            fn(*a, **k)
        return [re.sub(r"\x1b\[[0-9;]*m", "", x) for x in out.getvalue().splitlines()]

    def assert_aligned(self, lines, enc):
        """Every border / cell separator of every table line sits in the same character column."""
        if enc == "utf-8":
            t = [x for x in lines if x[2:3] and x[2:3] in "┌│├└"]
            seps = [[i for i, c in enumerate(x) if c in "│┌┬┐├┼┤└┴┘"] for x in t]
            self.assertTrue(t)
            self.assertTrue(all(s == seps[0] for s in seps), "\n".join(t))
            self.assertEqual(len({len(x) for x in t}), 1, "\n".join(t))


class ShowTable(Fixture):
    def test_regression_organiser_rows_aligned_box_and_ascii(self):
        for enc in ("utf-8", "cp1252"):
            lines = self.shown(enc, self.w.show_rows, ORGANISER_ROWS)
            self.assert_aligned(lines, enc)
            self.assertTrue(all(len(x) <= 72 for x in lines), enc)
            text = "\n".join(lines)
            self.assertIn("100.0 PASS", text)
            self.assertIn("5.0 FAIL*", text)
            if enc == "utf-8":
                # the score column is as wide as its widest final cell, so the border is not pushed out
                score_w = max(len("score"), len("100.0 PASS"), len("5.0 FAIL*"))
                rows = [x for x in lines if x.startswith("  │")]
                self.assertTrue(all(len(x.split("│")[-2]) == score_w + 2 for x in rows), text)
            else:
                data = [x for x in lines if x.startswith("  s")]
                self.assertEqual(len({x.index("100.0 PASS") if "100.0 PASS" in x else x.index("5.0 FAIL*")
                                      for x in data if "PASS" in x or "FAIL" in x}), 1, text)

    def test_what_column_says_what_each_row_is(self):
        lines = self.shown("utf-8", self.w.show_rows, ORGANISER_ROWS)
        text = "\n".join(lines)
        for want in ("1: solve T3", "2: new skill", "T6 + skill", "T3, no skill", "what"):
            self.assertIn(want, text)
        self.assertNotIn(" st ", text)
        self.assertIn("s3-6bd6-n3-d263", text)           # the full run id: `done <run_id>` needs it

    def test_what_for_all_four_stage3_kinds_with_registry_control(self):
        rows = [dict(run_id="a", stage="3", task="T3"), dict(run_id="b", stage="3", task="T3"),
                dict(run_id="c", stage="3", task="T6"), dict(run_id="d", stage="3", task="T6")]

        class Reg:
            data = {"runs": {"a": {"stage": "3", "skill_source": "x"}, "b": {"stage": "3", "skill_source": "none"},
                             "c": {"stage": "3", "skill_source": "x"}, "d": {"stage": "3", "skill_source": "none"}}}
        self.assertEqual([self.w.row_what(r, Reg) for r in rows],
                         ["T3 + skill", "T3, no skill", "T6 + skill", "T6, no skill"])

    def test_stage2_row_has_no_task_and_no_score(self):
        text = "\n".join(self.shown("utf-8", self.w.show_rows, ORGANISER_ROWS))
        row = [x for x in text.splitlines() if "2: new skill" in x][0]
        cells = [c.strip() for c in row.strip("│ ").split("│")]
        self.assertEqual(cells[-1], "-")
        self.assertNotIn("T3", row)


class ChangeColumn(Fixture):
    def test_both_pass_fills_the_change_column(self):
        rw, rc = pair()
        for enc in ("utf-8", "cp1252"):
            lines = self.shown(enc, self.w.compare_control, None, rw, rc)
            text = "\n".join(lines)
            self.assertIn("change", text)
            self.assert_aligned(lines, enc)
            self.assertTrue(all(len(x) <= 72 for x in lines))
            row = lambda name: [x for x in lines if name in x][0]
            self.assertIn("-0.9", row("Time (min)"))
            self.assertIn("+2", row("Emulator runs"))
            self.assertIn("-300k", row("Tokens in"))
            self.assertIn("-15k", row("Tokens out"))
            self.assertIn("-0.30", row("Cost (USD)"))
            self.assertNotIn("Change not shown", text)

    def test_one_failed_draws_no_change_column_and_prints_the_line(self):
        for sw, sc in (("100", "5"), ("5", "100")):
            rw, rc = pair(sw, sc)
            for enc in ("utf-8", "cp1252"):
                lines = self.shown(enc, self.w.compare_control, None, rw, rc)
                text = "\n".join(lines)
                self.assertNotIn("change", text)
                self.assert_aligned(lines, enc)
                self.assertTrue(all(len(x) <= 72 for x in lines))
                self.assertIn("Change not shown: one attempt failed, so time and cost are not comparable.",
                              re.sub(r"\s+", " ", text))
                self.assertIn("At least one attempt failed.", re.sub(r"\s+", " ", text))     # the honest line stays
                if enc == "utf-8":
                    head = [x for x in lines if "with skill" in x and x.startswith("  │")][0]
                    self.assertEqual(head.count("│"), 4)                     # 3 columns, no empty 4th

    def test_diff_text_units(self):
        d = self.w.diff_text
        self.assertEqual(d("%.1f", 5.9, 5.0), "-0.9")
        self.assertEqual(d("%.1f", 5.0, 5.9), "+0.9")
        self.assertEqual(d("%d", 1, 3), "+2")
        self.assertEqual(d("k", 3000000, 1700000), "-1.3M")
        self.assertEqual(d("k", 1500000, 1200000), "-300k")
        self.assertEqual(d("%.2f", 0.6, 0.3), "-0.30")
        self.assertEqual(d("%d", 100, 100), "+0")
        self.assertEqual(d("%d", None, 3), "-")


if __name__ == "__main__":
    unittest.main()
