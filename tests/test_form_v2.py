"""The form keeps 18 questions; a T6 stage-3 row pre-fills task=T6 and its run_id (which names the parent)."""
import os, sys, unittest
from urllib.parse import parse_qs, urlparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fakes import fresh_ws  # noqa: E402


class FormV2(unittest.TestCase):
    def setUp(self):
        self.w, _ = fresh_ws()
        self.cfg = self.w.load_config()

    def test_eighteen_questions_no_name_field(self):
        self.assertEqual(len(self.cfg["fields"]), 18)
        self.assertNotIn("name", self.cfg["fields"])
        self.assertTrue(set(self.cfg["fields"]) <= set(self.w.ROW_FIELDS))

    def test_t6_row_prefills_task_and_run_id(self):
        link = self.w.form_link({"run_id": "s3-ab12-t6-9f3c", "stage": "3", "task": "T6"}, self.cfg)
        q = parse_qs(urlparse(link).query)
        self.assertEqual(q[self.cfg["fields"]["task"]], ["T6"])
        self.assertEqual(q[self.cfg["fields"]["run_id"]], ["s3-ab12-t6-9f3c"])
        self.assertEqual(q[self.cfg["fields"]["stage"]], ["3"])


if __name__ == "__main__":
    unittest.main()
