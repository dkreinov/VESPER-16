"""T6 in stage 3: the name font, the task file, the run record and grading with --name."""
import os, subprocess, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fakes  # noqa: E402
from fakes import fresh_ws, run  # noqa: E402

MIRA = ["#.#.###.##...#.", "###..#..#.#.#.#", "###..#..##..###", "#.#..#..#.#.#.#", "#.#.###.#.#.#.#"]


class FontTest(unittest.TestCase):
    def setUp(self):
        fresh_ws()
        import t6font
        self.f = t6font

    def test_normalise(self):
        self.assertEqual(self.f.normalise("  Jo-hn2 smith!"), "JOHNSMIT")
        self.assertEqual(self.f.normalise("Alexandria"), "ALEXANDR")
        self.assertEqual(self.f.normalise(""), "VESPER")
        self.assertEqual(self.f.normalise("123"), "VESPER")

    def test_rows_mira(self):
        self.assertEqual(self.f.rows("mira"), MIRA)

    def test_pixels_start_at_column1_row1(self):
        px = self.f.pixels("MIRA")
        self.assertEqual(len(px), 41)
        self.assertEqual(min(c for c, _ in px), 1)
        self.assertEqual((min(r for _, r in px), max(r for _, r in px)), (1, 5))

    def test_template_fill(self):
        with open(os.path.join(fakes.ROOT, "tasks", "T6.md"), encoding="utf-8") as fh:
            tpl = fh.read()
        self.assertIn("{NAME}", tpl)
        self.assertIn("{NAME_ROWS}", tpl)
        self.assertNotIn("(see the docs)", tpl)
        md = self.f.task_md(tpl, "mira")
        self.assertIn("**MIRA**", md)
        self.assertIn("\n".join(MIRA), md)
        self.assertNotIn("{NAME", md)

    def test_cli_writes_task_md(self):
        out = os.path.join(tempfile.mkdtemp(), "T6.md")
        subprocess.run([sys.executable, os.path.join(fakes.ROOT, "t6font.py"), "mira", "--task-md", out], check=True)
        with open(out, encoding="utf-8") as fh:
            self.assertIn("**MIRA**", fh.read())


class T6RunTest(unittest.TestCase):
    def setUp(self):
        self.w, self.tmp = fresh_ws()
        self.s1, _ = fakes.ready_for_s3(self.w)

    def _active(self):
        reg = self.w.Registry.load()
        rid = reg.data["active"]["run_id"]
        return rid, reg.data["runs"][rid]

    def test_new_s3_t6_writes_named_task(self):
        run(self.w, "new", "s3", "--task", "T6", "--name", "mira")
        rid, r = self._active()
        self.assertEqual((r["task"], r["name"]), ("T6", "MIRA"))
        self.assertEqual(os.listdir(os.path.join(r["folder"], "tasks")), ["T6.md"])
        with open(os.path.join(r["folder"], "tasks", "T6.md"), encoding="utf-8") as fh:
            md = fh.read()
        self.assertIn("**MIRA**", md)
        self.assertIn(MIRA[0], md)
        self.assertNotIn("{NAME", md)

    def test_no_name_without_tty_is_vesper(self):
        reg = self.w.Registry.load()
        reg.data["alias"] = ""
        reg.save()
        run(self.w, "new", "s3", "--task", "T6")
        self.assertEqual(self._active()[1]["name"], "VESPER")

    def test_t6_is_not_a_stage1_task(self):
        with self.assertRaises(SystemExit):
            run(self.w, "new", "s1", "--task", "T6")

    def test_grade_passes_name_for_t6_only(self):
        fakes.install_fake_grader(self.w)
        sol = os.path.join(self.tmp, "x.vsa")
        with open(sol, "w") as fh:
            fh.write("x")
        self.assertEqual(self.w.grade_snapshot("T6", sol, "mira"), ("100", "graded"))
        self.assertEqual(self.w.grade_snapshot("T3", sol, "mira"), ("1", "graded"))

    def test_done_grades_t6_with_the_stored_name(self):
        fakes.install_fake_grader(self.w)
        run(self.w, "new", "s3", "--task", "T6", "--name", "Mira")
        rid, r = self._active()
        with open(os.path.join(r["folder"], "solutions", "T6.vsa"), "w") as fh:
            fh.write("x")
        run(self.w, "done", "--no-form")
        self.assertEqual(self.w.Registry.load().row(rid, "3")["score"], "100")

    def test_room_path_grade_passes_the_stored_name(self):
        """Room: done while part 4 is locked (ungraded), then the grader appears, then `grade`."""
        run(self.w, "new", "s3", "--task", "T6", "--name", "Mira")
        rid, r = self._active()
        with open(os.path.join(r["folder"], "solutions", "T6.vsa"), "w") as fh:
            fh.write("x")
        run(self.w, "done", "--no-form")
        self.assertEqual(self.w.Registry.load().row(rid, "3")["grading"], "ungraded")
        fakes.install_fake_grader(self.w)
        run(self.w, "grade", "--no-form")
        row = self.w.Registry.load().row(rid, "3")
        self.assertEqual((row["score"], row["grading"]), ("100", "graded"))


if __name__ == "__main__":
    unittest.main()
