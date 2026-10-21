"""The form has two questions: alias and all_results. A T6 row travels as a v1 line carrying task=T6 and its run_id."""
import os, sys, unittest
from urllib.parse import parse_qs, urlparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fakes import fresh_ws  # noqa: E402


class FormV2(unittest.TestCase):
    def setUp(self):
        self.w, _ = fresh_ws()
        self.cfg = self.w.load_config()

    def test_two_questions(self):
        self.assertEqual(list(self.cfg["fields"]), ["alias"])
        self.assertTrue(self.cfg["all_results_field"])

    def test_t6_row_in_all_results(self):
        link = self.w.form_link([{"alias": "a", "run_id": "s3-ab12-t6-9f3c", "stage": "3", "task": "T6"}], self.cfg)
        q = parse_qs(urlparse(link).query)
        self.assertEqual(set(q) - {"id"}, {self.cfg["fields"]["alias"], self.cfg["all_results_field"]})
        line = q[self.cfg["all_results_field"]][0].split("\n")[1]
        self.assertIn("task=T6", line.split(";"))
        self.assertIn("run_id=s3-ab12-t6-9f3c", line.split(";"))
        self.assertIn("stage=3", line.split(";"))


if __name__ == "__main__":
    unittest.main()
