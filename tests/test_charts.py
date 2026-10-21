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
    r.update({"revision": "1", "grading": "graded", "measurement": "log", "settings_confirmed": "yes"}, **kw)
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


class AllResultsTest(unittest.TestCase):
    def test_round_trip(self):
        sys.path.insert(0, ROOT)
        import workshop
        rows = []
        for i, (rid, st, rev) in enumerate([("s1-aaaa", "1", "1"), ("s1-aaaa", "1", "2"), ("s3-aaaa-t6-1111", "3", "1")]):
            r = {k: "" for k in workshop.ROW_FIELDS}
            r.update(alias="ann", run_id=rid, stage=st, revision=rev, task="T3", method="plain", score="100",
                     grading="graded", measurement="log", cost_usd="0.5", agent="a;b=c")
            rows.append(r)
        text = workshop.all_results_text(rows)
        form = {f: "" for f in charts.FIELDS}
        form.update(alias="ann", run_id="ALL", stage="all", all_results=text)
        tmp = tempfile.mkdtemp(prefix="charts_ar_")
        p = os.path.join(tmp, "e.csv")
        old = ["x"] + [f for f in charts.FIELDS]
        oldrow = {f: "" for f in charts.FIELDS}
        oldrow.update(alias="bob", run_id="s1-bbbb", stage="1", revision="1", score="9")
        with open(p, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["Start time"] + charts.FIELDS + ["all_results"])
            w.writerow([serial(DAY_A)] + [form[k] for k in charts.FIELDS] + [text])
            w.writerow([serial(DAY_A)] + [oldrow[k] for k in charts.FIELDS] + [""])
        got = charts.dedup(charts.load_rows([p]))
        self.assertEqual(len(got), 3)           # 2 expanded (dup collapsed to rev 2) + 1 old single row
        by = {(r["run_id"], r["stage"]): r for r in got}
        self.assertNotIn(("ALL", "all"), by)
        self.assertEqual(by[("s1-aaaa", "1")]["revision"], "2")
        self.assertEqual(by[("s1-aaaa", "1")]["agent"], "a;b=c")
        self.assertEqual(by[("s1-aaaa", "1")]["alias"], "ann")
        self.assertEqual(by[("s1-bbbb", "1")]["score"], "9")


class TwoColumnExportTest(unittest.TestCase):
    def test_alias_and_all_results_only(self):
        import workshop
        rows = []
        for rid, st in (("s1-aaaa", "1"), ("s3-aaaa-t6-1111", "3")):
            r = {k: "" for k in workshop.ROW_FIELDS}
            r.update(alias="ann", run_id=rid, stage=st, revision="1", task="T3", score="100", grading="graded")
            rows.append(r)
        p = os.path.join(tempfile.mkdtemp(prefix="charts_2c_"), "e.csv")
        with open(p, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["ID", "Start time", "Completion time", "Email", "Name", "1. alias", "2. all_results"])
            w.writerow(["1", serial(DAY_A), serial(DAY_A), "anonymous", "", "ann", workshop.all_results_text(rows)])
        got = charts.dedup(charts.load_rows([p]))
        self.assertEqual({(r["run_id"], r["stage"]) for r in got}, {("s1-aaaa", "1"), ("s3-aaaa-t6-1111", "3")})
        self.assertEqual({r["alias"] for r in got}, {"ann"})
        self.assertEqual(len(charts.in_range(got, DAY_A.date(), DAY_A.date())), 2)


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
        self.assertFalse(hasattr(charts, "leakage"))
        t = charts.t6_pass(a)
        self.assertEqual((t["class"], t["baseline"], t["flagged"]), ((1, 2), (0, 12), 0))
        self.assertEqual(charts.methods(g), {"builtin": {"median_min": 10.0, "passed": 0, "n": 1},
                                             "plain": {"median_min": 3.5, "passed": 1, "n": 1}})

    def test_main_writes_one_page_per_session(self):
        out = os.path.join(self.tmp, "a")
        self.assertEqual(charts.main([self.xlsx, "--from", "2026-10-27", "--to", "2026-10-27", "--out", out]), 0)
        with open(os.path.join(out, "charts.html"), encoding="utf-8") as f:
            page = f.read()
        self.assertEqual(page.count("<svg"), 5)          # 1a, 1b, 2 (paired), 3, 4
        self.assertNotIn("Leakage", page)
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


def r3(rid, task, **kw):
    d = {f: "" for f in charts.FIELDS}
    d.update(alias="x", run_id=rid, stage="3", task=task, revision="1", grading="graded", settings_confirmed="yes",
             model="m", effort="high", method="plain")
    d.update(kw)
    d["_date"] = DAY_A
    return d


def s1(code):
    d = {f: "" for f in charts.FIELDS}
    d.update(alias=code, run_id="s1-" + code, stage="1", task="T3", revision="1", grading="graded", score="100", method="plain")
    d["_date"] = DAY_A
    return d


class ArmsAndPairsTest(unittest.TestCase):
    def test_control_never_counts_as_skill(self):
        rows = [s1("aaaa"), r3("s3-aaaa-t6-1111", "T6", score="40"),
                r3("s3-aaaa-n6-2222", "T6", score="100", method="none")]
        self.assertEqual(charts.arm(rows[2]), "control")
        self.assertEqual(charts.arm(rows[1]), "skill")
        self.assertEqual(charts.t6_pass(rows)["class"], (0, 1))     # the n6 pass does not raise it
        g = charts.learners(rows)[0]
        self.assertEqual(g["T6"]["run_id"], "s3-aaaa-t6-1111")
        self.assertEqual(g["N6"]["run_id"], "s3-aaaa-n6-2222")

    def test_method_none_is_control_even_with_t_tag(self):
        self.assertEqual(charts.arm(r3("s3-aaaa-t6-1111", "T6", method="none")), "control")

    def test_pass_rule(self):
        self.assertTrue(charts.passed(r3("s3-aaaa-t6-1111", "T6", score="90")))
        self.assertFalse(charts.passed(r3("s3-aaaa-t3-1111", "T3", score="95")))
        self.assertTrue(charts.passed(r3("s3-aaaa-t3-1111", "T3", score="100")))

    def rows_pair(self, eff_ctl="high", ctl_score="100", model_ctl="m", **flag):
        return [s1("aaaa"), r3("s3-aaaa-t6-1111", "T6", score="95", **flag),
                r3("s3-aaaa-n6-2222", "T6", score=ctl_score, method="none", effort=eff_ctl, model=model_ctl),
                r3("s3-aaaa-t3-3333", "T3", score="100", **flag),
                r3("s3-aaaa-n3-4444", "T3", score="50", method="none", effort=eff_ctl, model=model_ctl)]

    def test_pairs_same_settings(self):
        p = charts.paired(charts.learners(self.rows_pair()))
        c = p["cells"][("m", "high", "T6", False)]
        self.assertEqual((c["pairs"], c["skill"]["pass"], c["control"]["pass"]), (1, 1, 1))
        c3 = p["cells"][("m", "high", "T3", False)]
        self.assertEqual((c3["skill"]["pass"], c3["control"]["fail"]), (1, 1))

    def test_pairs_differing_or_unknown_settings_skipped(self):
        for kw in ({"eff_ctl": "low"}, {"eff_ctl": ""}, {"model_ctl": "other"}):
            p = charts.paired(charts.learners(self.rows_pair(**kw)))
            self.assertEqual((p["cells"], p["skipped"]), ({}, 2), kw)

    def test_effort_not_recorded_pairs_by_model(self):          # ruling R4: Claude Code / Cursor log no effort
        rows = self.rows_pair(eff_ctl="")
        for r in rows:
            if r["stage"] == "3":
                r["effort"] = ""
        p = charts.paired(charts.learners(rows))
        self.assertEqual(p["skipped"], 0)
        self.assertEqual(p["cells"][("m", "", "T6", False)]["pairs"], 1)
        self.assertIn("T6 m (effort not recorded)", charts.pair_spec(charts.learners(rows))["groups"])

    def test_empty_model_never_pairs(self):                       # review MINOR-3
        rows = self.rows_pair(model_ctl="")
        for r in rows:
            r["model"] = ""
        p = charts.paired(charts.learners(rows))
        self.assertEqual((p["cells"], p["skipped"]), ({}, 2))

    def test_repeat_attempts_earliest_kept_and_counted(self):     # review MINOR-4
        rows = self.rows_pair()
        for i, r in enumerate(rows):
            r["start"] = str(100 + i)
        rows.append(r3("s3-aaaa-t6-9999", "T6", score="10", start="999"))
        g = charts.learners(rows)[0]
        self.assertEqual((g["T6"]["run_id"], g["repeats"]), ("s3-aaaa-t6-1111", 1))
        self.assertEqual(charts.t6_pass(rows)["class"], (1, 1))
        self.assertIn("1 repeat attempt not shown", charts.pair_spec(charts.learners(rows))["hint"])
        small = [s for s in charts.chart_specs(rows) if s["id"] == "small"][0]
        self.assertIn("1 repeat attempt not shown", small["hint"])

    def test_unconfirmed_counted_not_flagged(self):              # ruling R9
        rows = self.rows_pair(settings_confirmed="not_asked")
        spec = charts.pair_spec(charts.learners(rows))
        self.assertNotIn("[flagged]", " ".join(spec["groups"]))
        self.assertIn("2 runs: settings not confirmed by the gate", spec["hint"])
        small = [s for s in charts.chart_specs(rows) if s["id"] == "small"][0]
        self.assertIn("1 run: settings not confirmed by the gate", small["hint"])

    def test_missing_partner_counted(self):
        rows = [s1("aaaa"), r3("s3-aaaa-t6-1111", "T6", score="95")]
        p = charts.paired(charts.learners(rows))
        self.assertEqual((p["cells"], p["missing"]), ({}, 1))

    def test_flagged_pairs_apart_and_counted(self):
        spec = charts.pair_spec(charts.learners(self.rows_pair(memory_used="yes")))
        self.assertTrue(all("[flagged]" in g for g in spec["groups"]))
        self.assertIn("Flagged pairs", spec["hint"])
        self.assertIn(": 2, shown apart", spec["hint"])

    def test_flag_reasons(self):
        base = r3("s3-aaaa-t6-1111", "T6", score="100")
        self.assertFalse(charts.flagged(base))
        for kw in ({"memory_used": "yes"}, {"isolation": "detected"}, {"settings_confirmed": "no"},
                   {"overrun": "yes"}):
            self.assertTrue(charts.flagged(dict(base, **kw)), kw)
        for kw in ({"settings_confirmed": ""}, {"settings_confirmed": "not_asked"}):      # unconfirmed: not a flag
            self.assertFalse(charts.flagged(dict(base, **kw)), kw)
        self.assertFalse(charts.flagged(dict(base, isolation="not_detected", overrun="no")))

    def test_t6_counts_flagged_ungraded_missing(self):
        rows = [s1("aaaa"), s1("bbbb"), s1("cccc"), s1("dddd"),
                r3("s3-aaaa-t6-1111", "T6", score="100"),
                r3("s3-bbbb-t6-1111", "T6", score="", grading="ungraded"),
                r3("s3-cccc-t6-1111", "T6", score="100", memory_used="yes")]
        t = charts.t6_pass(rows)
        self.assertEqual(t["class"], (1, 1))
        self.assertEqual((t["counts"]["ungraded"], t["flagged"], t["missing"]), (1, 1, 1))
        small = [s for s in charts.chart_specs(rows) if s["id"] == "small"][0]
        self.assertIn("1 ungraded", small["hint"])
        self.assertIn("1 flagged", small["hint"])
        self.assertIn("1 learner has no T6 row", small["hint"])

    def test_titles(self):
        specs = {s["id"]: s for s in charts.chart_specs([s1("aaaa")])}
        self.assertNotIn("leak", specs)
        self.assertIn("pairs", specs)
        self.assertTrue(specs["money"]["title"].endswith("(not a matched comparison)"))
        self.assertTrue(specs["time"]["title"].endswith("(not a matched comparison)"))
        self.assertIn("10-minute", specs["small"]["title"])

    def test_old_rows_without_new_fields_load(self):
        r = {f: "" for f in charts.FIELDS}
        r.update(run_id="s3-aaaa-t6-1111", stage="3", task="T6", score="100")
        r["_date"] = DAY_A
        charts.chart_specs([r])                          # must not raise


class FlagStageTest(unittest.TestCase):
    """The settings gate and the 10-minute box exist only in stage 3."""

    def row(self, stage, **kw):
        r = {f: "" for f in charts.FIELDS}
        r.update(stage=stage, **kw)
        return r

    def test_stage1_and_2_not_flagged_for_settings_or_time(self):
        for st in ("1", "2"):
            self.assertFalse(charts.flagged(self.row(st, overrun="yes")), st)

    def test_stage3_flags(self):
        self.assertFalse(charts.flagged(self.row("3", settings_confirmed="")))
        self.assertTrue(charts.flagged(self.row("3", settings_confirmed="no")))
        self.assertTrue(charts.flagged(self.row("3", settings_confirmed="yes", overrun="yes")))
        self.assertFalse(charts.flagged(self.row("3", settings_confirmed="yes", overrun="no")))

    def test_memory_and_isolation_flag_every_stage(self):
        self.assertTrue(charts.flagged(self.row("1", memory_used="yes")))
        self.assertTrue(charts.flagged(self.row("2", isolation="detected")))


class PartialGradingTest(unittest.TestCase):
    def test_partial_is_graded(self):
        r = {f: "" for f in charts.FIELDS}
        r.update(stage="3", task="T6", score="95", grading="partial")
        self.assertEqual(charts.outcome(r), "pass")
        r.update(score="40")
        self.assertEqual(charts.outcome(r), "fail")
        r.update(grading="ungraded")
        self.assertEqual(charts.outcome(r), "ungraded")


if __name__ == "__main__":
    unittest.main()
