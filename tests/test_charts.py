"""charts.py on a fixture Forms export: two event dates -> two sessions."""
import csv, datetime as dt, os, sys, tempfile, unittest, zipfile
from xml.sax.saxutils import escape

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import charts  # noqa: E402

DAY_A, DAY_B = dt.datetime(2026, 10, 27, 10, 30), dt.datetime(2026, 10, 28, 11, 15)
HEAD = ["ID", "Start time", "Completion time", "Email", "Name"] + charts.FIELDS


def serial(d):
    return "%.6f" % ((d - dt.datetime(1899, 12, 30)).total_seconds() / 86400)


def row(day, **kw):
    r = {f: "" for f in charts.FIELDS}
    r.update({"revision": "1", "grading": "graded", "measurement": "log"}, **kw)
    return ["1", serial(day), serial(day), "anonymous", ""] + [str(r[f]) for f in charts.FIELDS]


ROWS = [
    # session A, learner ann (method plain): T6 pass, T3 again fast, 60% of the game in the skill
    row(DAY_A, alias="ann", run_id="s1-aaaa", stage="1", task="T3", method="plain", elapsed_min="14.7", cost_usd="0.80", score="100"),
    row(DAY_A, alias="ann", run_id="s1-aaaa", stage="1", revision="2", task="T3", method="plain", elapsed_min="14.7", cost_usd="0.81", score="100"),
    row(DAY_A, alias="ann", run_id="s1-aaaa", stage="2", task="T3", method="plain", skill_has_solution="60%", elapsed_min="3.0", cost_usd="0.20"),
    row(DAY_A, alias="ann", run_id="s3-aaaa-t6-1111", stage="3", task="T6", method="plain", skill_has_solution="60%", elapsed_min="3.5", cost_usd="0.05", score="100"),
    row(DAY_A, alias="ann", run_id="s3-aaaa-t3-2222", stage="3", task="T3", method="plain", skill_has_solution="60%", elapsed_min="2.0", cost_usd="0.03", score="100"),
    # session A, learner cat (method builtin): T6 fails
    row(DAY_A, alias="cat", run_id="s1-cccc", stage="1", task="T3", method="builtin", elapsed_min="12.0", cost_usd="0.60", score="100"),
    row(DAY_A, alias="cat", run_id="s1-cccc", stage="2", task="T3", method="builtin", skill_has_solution="0%", elapsed_min="4.0", cost_usd="0.30"),
    row(DAY_A, alias="cat", run_id="s3-cccc-t6-3333", stage="3", task="T6", method="builtin", skill_has_solution="0%", elapsed_min="10.0", cost_usd="0.09", score="40"),
    # session B, learner bob
    row(DAY_B, alias="bob", run_id="s1-bbbb", stage="1", task="T3", method="superpowers", elapsed_min="9.0", cost_usd="0.50", score="100"),
    row(DAY_B, alias="bob", run_id="s3-bbbb-t6-4444", stage="3", task="T6", method="superpowers", elapsed_min="4.0", cost_usd="0.04", score="95"),
]


def write_xlsx(path, rows):
    """A minimal .xlsx like the Forms export: inline strings, numbers for the dates."""
    def cell(ci, ri, v):
        ref = "%s%d" % (chr(65 + ci) if ci < 26 else "A" + chr(65 + ci - 26), ri)
        try:
            float(v)
            return '<c r="%s"><v>%s</v></c>' % (ref, v)
        except ValueError:
            return '<c r="%s" t="inlineStr"><is><t>%s</t></is></c>' % (ref, escape(v))
    data = "".join('<row r="%d">%s</row>' % (ri, "".join(cell(ci, ri, v) for ci, v in enumerate(r)))
                   for ri, r in enumerate(rows, 1))
    m = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("xl/workbook.xml", '<workbook xmlns="%s" xmlns:r="%s"><sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets></workbook>' % (m, rel))
        z.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="%s/worksheet" Target="worksheets/sheet1.xml"/></Relationships>' % rel)
        z.writestr("xl/worksheets/sheet1.xml", '<worksheet xmlns="%s"><sheetData>%s</sheetData></worksheet>' % (m, data))


class ChartsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="charts_")
        self.xlsx = os.path.join(self.tmp, "export.xlsx")
        write_xlsx(self.xlsx, [HEAD] + ROWS)
        self.csv = os.path.join(self.tmp, "export.csv")
        with open(self.csv, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows([HEAD] + ROWS)

    def session(self, path, day):
        return charts.in_range(charts.dedup(charts.load_rows([path])), day.date(), day.date())

    def test_xlsx_reads_like_csv(self):
        self.assertEqual(charts.read_xlsx(self.xlsx), charts.read_table(self.csv))

    def test_two_dates_two_sessions(self):
        a, b = self.session(self.xlsx, DAY_A), self.session(self.xlsx, DAY_B)
        self.assertEqual({r["alias"] for r in a}, {"ann", "cat"})
        self.assertEqual({r["alias"] for r in b}, {"bob"})
        self.assertEqual(len(a), 7)                      # 8 session-A rows, the revision-1 duplicate dropped

    def test_dedup_keeps_highest_revision(self):
        a = self.session(self.csv, DAY_A)
        s1 = [r for r in a if r["run_id"] == "s1-aaaa" and r["stage"] == "1"]
        self.assertEqual([r["cost_usd"] for r in s1], ["0.81"])

    def test_stage3_rows_link_to_stage1_parent(self):
        self.assertEqual(charts.parent_id("s3-aaaa-t6-1111"), "s1-aaaa")
        self.assertEqual(charts.parent_id("s3-beef"), "")
        g = {x["label"]: x for x in charts.learners(self.session(self.xlsx, DAY_A))}
        self.assertEqual(g["ann"]["T6"]["run_id"], "s3-aaaa-t6-1111")
        self.assertEqual(g["ann"]["T3"]["run_id"], "s3-aaaa-t3-2222")
        self.assertNotIn("T3", g["cat"])

    def test_chart_data(self):
        a = self.session(self.xlsx, DAY_A)
        g = charts.learners(a)
        mt = charts.money_time(g)
        self.assertEqual(mt["labels"], ["ann", "cat"])
        self.assertEqual(mt["cost"][0], [0.81, 0.05, 0.03])
        self.assertEqual(mt["time"][1], [12.0, 10.0, None])
        pts = charts.leakage(g)
        self.assertIn({"x": 60.0, "y": 2.0, "series": "T3", "label": "ann", "passed": True}, pts)
        self.assertIn({"x": 0.0, "y": 10.0, "series": "T6", "label": "cat", "passed": False}, pts)
        self.assertEqual(charts.t6_pass(a), {"class": (1, 2), "baseline": (0, 12)})
        self.assertEqual(charts.methods(g), {"builtin": {"median_min": 10.0, "passed": 0, "n": 1},
                                             "plain": {"median_min": 3.5, "passed": 1, "n": 1}})

    def test_main_writes_one_page_per_session(self):
        out = os.path.join(self.tmp, "a")
        self.assertEqual(charts.main([self.xlsx, "--from", "2026-10-27", "--to", "2026-10-27", "--out", out]), 0)
        with open(os.path.join(out, "charts.html"), encoding="utf-8") as f:
            page = f.read()
        self.assertEqual(page.count("<svg"), 5)          # 1a, 1b, 2, 3, 4
        self.assertIn("ann", page)
        self.assertNotIn("bob", page)
        self.assertIn("1/2", page)                        # class T6 pass count
        self.assertIn("0/12", page)                       # lab baseline

    def test_empty_range_exits(self):
        with self.assertRaises(SystemExit):
            charts.main([self.csv, "--from", "2030-01-01", "--out", os.path.join(self.tmp, "x")])

    def test_results_csv_epoch_start(self):
        p = os.path.join(self.tmp, "results.csv")
        with open(p, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["alias", "run_id", "stage", "task", "score", "start"])
            w.writerow(["ann", "s3-aaaa-t6-1111", "3", "T6", "100", "%.0f" % DAY_A.timestamp()])
        rows = charts.load_rows([p])
        self.assertEqual(rows[0]["_date"].date(), DAY_A.date())


if __name__ == "__main__":
    unittest.main()
