#!/usr/bin/env python3
"""charts.py - the debrief charts from the results form export (5 SVGs).

  python charts.py EXPORT [EXPORT ...] [--from YYYY-MM-DD] [--to YYYY-MM-DD] [--out DIR] [--png]
                   [--date-format FMT] [--map "Header text=field" ...]

EXPORT: the Microsoft Forms Excel export (.xlsx), a CSV of it, or the workshop's own results.csv.
--from / --to: keep only rows whose completion date is in [from, to] (one event session each; inclusive).
Writes DIR/charts.html (5 inline SVGs, each with a data table). --png also writes
DIR/chart-<n>.png when matplotlib is installed; without matplotlib only the HTML page is written.
Stdlib only (zipfile + ElementTree read the .xlsx).
"""
import argparse, csv, datetime as dt, html, os, re, statistics, sys, zipfile
import xml.etree.ElementTree as ET

FIELDS = ["alias", "run_id", "stage", "revision", "task", "agent", "model", "method", "skill_has_solution",
          "elapsed_min", "emulator_runs", "tok_uncached", "tok_cache_read", "tok_out", "cost_usd", "score",
          "grading", "measurement", "effort", "memory_used", "settings_confirmed", "isolation", "overrun",
          "stopped", "error_note"]
DATE_HEADERS = ("completion time", "start time", "start")   # Forms columns first; results.csv has "start" (epoch)
# Own copy as numbers; the source of truth is workshop.py T6_BASELINE ("small model, no skill: 0/12 pass in 5 min").
T6_BASELINE = (0, 12)        # small model, no skill: 0/12 pass in 5 min (Haiku 0/6, gpt-6-luna 0/6)
COLORS = ["#2a78d6", "#eb6834", "#1baf7a"]   # categorical slots 1-3 of the validated default palette
NEUTRAL = "#8a8985"
S3_ID = re.compile(r"^s3-([0-9a-f]{4})-([tn]\d)-[0-9a-f]{4}$")
M_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
R_ID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"


# ------------------------------------------------------------------ reading
def _col_index(ref):
    n = 0
    for ch in re.match(r"[A-Z]+", ref).group(0):
        n = n * 26 + ord(ch) - 64
    return n - 1


def read_xlsx(path):
    """The first worksheet as a list of rows (lists of str)."""
    q = lambda tag: "{%s}%s" % (M_NS, tag)
    with zipfile.ZipFile(path) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(q("si")):
                shared.append("".join(t.text or "" for t in si.iter(q("t"))))
        first = ET.fromstring(z.read("xl/workbook.xml")).find("%s/%s" % (q("sheets"), q("sheet"))).get(R_ID)
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        target = [r.get("Target") for r in rels if r.get("Id") == first][0].lstrip("/")
        sheet = ET.fromstring(z.read(target if target.startswith("xl/") else "xl/" + target))
    rows = []
    for r in sheet.iter(q("row")):
        cells = {}
        for c in r.findall(q("c")):
            t = c.get("t", "")
            if t == "inlineStr":
                v = "".join(x.text or "" for x in c.iter(q("t")))
            else:
                ve = c.find(q("v"))
                v = "" if ve is None else (ve.text or "")
                if t == "s" and v:
                    v = shared[int(v)]
            cells[_col_index(c.get("r")) if c.get("r") else len(cells)] = v
        rows.append([cells.get(i, "") for i in range(max(cells) + 1)] if cells else [])
    return rows


def read_table(path):
    if path.lower().endswith(".xlsx"):
        return read_xlsx(path)
    with open(path, newline="", encoding="utf-8-sig") as f:
        return [row for row in csv.reader(f)]


def norm_header(h):
    return re.sub(r"^\s*\d+[.)]\s*", "", str(h)).strip().lower()


def map_columns(header, extra=None):
    """{field: column index} plus "_date". extra: {header text (any case): field}."""
    out, extra = {}, {k.strip().lower(): v for k, v in (extra or {}).items()}
    names = [norm_header(h) for h in header]
    for i, n in enumerate(names):
        f = extra.get(n) or (n if n in FIELDS else re.split(r"[\s:(]", n, 1)[0])
        if f in FIELDS or f == "all_results":
            out.setdefault(f, i)
    for d in DATE_HEADERS:
        if d in names:
            out["_date"] = names.index(d)
            break
    return out


def parse_date(v, fmt=None):
    v = str(v).strip()
    if not v:
        return None
    if fmt:
        return dt.datetime.strptime(v, fmt)
    try:
        f = float(v)
        if f > 1e8:
            return dt.datetime.fromtimestamp(f)                          # epoch seconds (results.csv)
        return dt.datetime(1899, 12, 30) + dt.timedelta(days=f)          # Excel serial date
    except ValueError:
        pass
    for f in ("%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%m/%d/%y %H:%M:%S"):
        try:
            return dt.datetime.strptime(v, f)
        except ValueError:
            continue
    return None


def num(v):
    try:
        return float(str(v).strip().rstrip("%").lstrip("$").replace(",", ""))
    except ValueError:
        return None


def expand_all_results(text):
    """Decode the all_results text (vesper-results v1) into a list of row dicts."""
    from urllib.parse import unquote
    out = []
    for line in str(text).replace("\r\n", "\n").split("\n"):
        line = line.strip()
        if not line or line.startswith("vesper-results"):
            continue
        d = {}
        for part in line.split(";"):
            k, eq, v = part.partition("=")
            if eq and k.strip():
                d[k.strip()] = unquote(v).strip()
        if d:
            out.append(d)
    return out


def load_rows(paths, extra=None, date_format=None):
    rows = []
    for p in paths:
        t = read_table(p)
        if not t:
            continue
        cols = map_columns(t[0], extra)
        for raw in t[1:]:
            if not any(str(x).strip() for x in raw):
                continue
            r = {f: (raw[i].strip() if i < len(raw) else "") for f, i in cols.items() if f != "_date"}
            r["_date"] = parse_date(raw[cols["_date"]], date_format) if "_date" in cols and cols["_date"] < len(raw) else None
            blob = r.pop("all_results", "")
            if blob:
                for d in expand_all_results(blob):
                    x = {f: d.get(f, "") for f in FIELDS}
                    x["alias"] = r.get("alias", "")
                    x["_date"] = r["_date"]
                    rows.append(x)
                continue
            rows.append(r)
    return rows


def dedup(rows):
    """One row per (run_id, stage): the highest revision, then the latest date."""
    best = {}
    for r in rows:
        k = (r.get("run_id", ""), r.get("stage", ""))
        key = (num(r.get("revision")) or 0, r["_date"] or dt.datetime.min)
        if k not in best or key >= best[k][0]:
            best[k] = (key, r)
    return [v[1] for v in best.values()]


def in_range(rows, d_from=None, d_to=None):
    out = []
    for r in rows:
        d = r["_date"].date() if r["_date"] else None
        if (d_from or d_to) and d is None:
            continue
        if (d_from and d < d_from) or (d_to and d > d_to):
            continue
        out.append(r)
    return out


def parent_id(run_id):
    """s3-<parent code>-<task>-<code> -> s1-<parent code>; older ids -> ""."""
    m = S3_ID.match(run_id or "")
    return "s1-" + m.group(1) if m else ""


def arm(r):
    """"control" (no skill) or "skill" for a stage-3 row: the run_id tag (n3/n6) or method "none". Never guess "skill" from the task."""
    m = S3_ID.match(r.get("run_id", "") or "")
    if (m and m.group(2).startswith("n")) or (r.get("method") or "").strip().lower() == "none":
        return "control"
    return "skill"


def row_task(r):
    """T3 or T6: from the run_id tag when it has one, else from the task field."""
    m = S3_ID.match(r.get("run_id", "") or "")
    return "T" + m.group(2)[-1] if m else (r.get("task") or "").upper()


def passed(r):
    """T6 pass = score >= 90; any other task = score 100. Same rule as passed() in workshop.py: keep both in sync."""
    sc = num(r.get("score"))
    return sc is not None and sc >= (90 if row_task(r) == "T6" else 100)


def is_graded(r):
    # "partial" = the grader ran on the solution frozen early (same rule as workshop.py): it counts as graded
    if run_failed(r):
        return False
    return num(r.get("score")) is not None and (r.get("grading") or "graded") in ("graded", "partial")


def run_failed(r):
    """An --auto run whose agent failed at once (auth error, free plan, crash): no data, never a pass or fail."""
    return (r.get("stopped") or "").strip().lower() == "error"


def outcome(r):
    """"pass", "fail" or "ungraded"."""
    return "ungraded" if not is_graded(r) else ("pass" if passed(r) else "fail")


def flag_reasons(r):
    out = []
    if run_failed(r):
        out.append("run failed")
    if r.get("memory_used") == "yes":
        out.append("memory used")
    if r.get("isolation") == "detected":
        out.append("isolation")
    # The settings gate and the 10-minute box exist only in stage 3 (the stage-1 writer has 20 minutes, no gate).
    s3 = str(r.get("stage", "")) == "3"
    # Only an explicit "no" is flagged; "" or "not_asked" (no gate, e.g. no terminal) is unconfirmed: counted, not flagged.
    if s3 and r.get("settings_confirmed") == "no":
        out.append("settings not confirmed")
    if s3 and r.get("overrun") == "yes":
        out.append("over time box")
    return out


def flagged(r):
    return bool(flag_reasons(r))


def unconfirmed(r):
    """A stage-3 row whose settings the gate did not confirm ("" or "not_asked"). Not a flag."""
    return str(r.get("stage", "")) == "3" and r.get("settings_confirmed") not in ("yes", "no", "auto")


def plural(n, one, many):
    return "%d %s" % (n, one if n == 1 else many)


def counts(rs):
    """{"pass", "fail", "ungraded", "n"} over rows."""
    c = {"pass": 0, "fail": 0, "ungraded": 0}
    for r in rs:
        c[outcome(r)] += 1
    c["n"] = len(rs)
    return c


def learners(rows):
    """One dict per stage-1 run: {"label", "s1", "s2", "T6", "T3", "N6", "N3"} (missing keys = no row).
    T3/T6 are with-skill rows only; N3/N6 are the no-skill controls."""
    by, repeats = {}, {}
    for r in sorted(rows, key=lambda r: num(r.get("start")) or 0):       # repeat attempts: the earliest one is kept
        rid, st = r.get("run_id", ""), r.get("stage", "")
        if st in ("1", "2") and rid.startswith("s1-"):
            by.setdefault(rid, {})["s%s" % st] = r
        elif st == "3" and parent_id(rid):
            t = row_task(r)
            g, k = by.setdefault(parent_id(rid), {}), ("N" + t[-1:]) if arm(r) == "control" else t
            if k in g and g[k].get("run_id") != rid:
                repeats[parent_id(rid)] = repeats.get(parent_id(rid), 0) + 1
            else:
                g[k] = r
    out = []
    for rid in sorted(by):
        g = by[rid]
        g["label"] = (g.get("s1") or {}).get("alias") or rid
        g["repeats"] = repeats.get(rid, 0)
        out.append(g)
    return out


def skill_rows(rows, task="T6"):
    """Stage-3 rows of one task that used the skill (never a control)."""
    return [r for r in rows if r.get("stage") == "3" and row_task(r) == task and arm(r) == "skill"]


def split_flagged(rs):
    return [r for r in rs if not flagged(r)], [r for r in rs if flagged(r)]


# ------------------------------------------------------------------ chart data (pure)
SERIES3 = ["stage 1: T3, no skill", "stage 3: T6 with skill", "stage 3: T3 again with skill"]


def money_time(groups):
    keys = ("s1", "T6", "T3")
    return {"labels": [g["label"] for g in groups],
            "cost": [[num((g.get(k) or {}).get("cost_usd")) for k in keys] for g in groups],
            "time": [[num((g.get(k) or {}).get("elapsed_min")) for k in keys] for g in groups]}


def t6_pass(rows):
    """Class T6 pass count, with-skill rows only, unflagged only, plus the other counts (nothing dropped silently)."""
    groups = learners(rows)
    t6 = [g["T6"] for g in groups if "T6" in g]               # one with-skill T6 row per learner (repeats not counted)
    clean, bad = split_flagged(t6)
    c = counts(clean)
    return {"class": (c["pass"], c["pass"] + c["fail"]), "baseline": T6_BASELINE, "counts": c, "flagged": len(bad),
            "missing": sum(1 for g in groups if "s1" in g and "T6" not in g),
            "repeats": sum(g.get("repeats", 0) for g in groups),
            "unconfirmed": sum(1 for r in t6 if unconfirmed(r))}


def paired(groups):
    """T3/T6 with vs without the skill, per learner, only for matched pairs: the same non-empty model and the same
    effort, or BOTH efforts empty (Claude Code and Cursor do not log effort; the cell's effort is then "").
    Same rule as settings_match() in workshop.py: keep both in sync.
    Returns {"cells": {(model, effort, task, flagged): {"skill": counts, "control": counts, "pairs": n}},
             "skipped": pairs with different or unknown settings, "missing": runs with no partner}."""
    cells, skipped, missing = {}, 0, 0
    for g in groups:
        for t in ("3", "6"):
            w, c = g.get("T" + t), g.get("N" + t)
            if not w and not c:
                continue
            if not (w and c):
                missing += 1
                continue
            ew, ec = (w.get("effort") or "").strip(), (c.get("effort") or "").strip()
            same = bool(w.get("model")) and w.get("model") == c.get("model") and ew == ec
            if not same:
                skipped += 1
                continue
            key = (w["model"], ew, "T" + t, flagged(w) or flagged(c))
            cell = cells.setdefault(key, {"skill": [], "control": []})
            cell["skill"].append(w)
            cell["control"].append(c)
    out = {k: {"skill": counts(v["skill"]), "control": counts(v["control"]), "pairs": len(v["skill"])} for k, v in cells.items()}
    return {"cells": out, "skipped": skipped, "missing": missing}


def methods(groups):
    acc = {}
    for g in groups:
        r = g.get("T6")
        m = (g.get("s1") or {}).get("method") or (r or {}).get("method")
        if not r or not m or flagged(r):
            continue
        d = acc.setdefault(m, {"times": [], "passed": 0, "n": 0})
        if num(r.get("elapsed_min")) is not None:
            d["times"].append(num(r["elapsed_min"]))
        d["n"] += 1
        d["passed"] += outcome(r) == "pass"
    return {m: {"median_min": statistics.median(d["times"]) if d["times"] else None, "passed": d["passed"], "n": d["n"]}
            for m, d in sorted(acc.items())}


def pair_spec(groups):
    p = paired(groups)
    keys = sorted(p["cells"], key=lambda k: (k[3], k[2], k[0], k[1]))
    labels, values, notes = [], [], []
    for k in keys:
        c = p["cells"][k]
        labels.append("%s %s%s%s" % (k[2], k[0], ("/" + k[1]) if k[1] else " (effort not recorded)", " [flagged]" if k[3] else ""))
        values.append([c["skill"]["pass"], c["control"]["pass"]])
        notes.append(["%dP %dF %dU of %d" % (c[a]["pass"], c[a]["fail"], c[a]["ungraded"], c["pairs"]) for a in ("skill", "control")])
    nf = sum(c["pairs"] for k, c in p["cells"].items() if k[3])
    rs = [g[k] for g in groups for k in ("T3", "T6", "N3", "N6") if k in g]
    hint = ("Pairs: %d (same model and effort; for Claude Code and Cursor, which do not record effort, the same model). "
            "P = pass, F = fail, U = ungraded. Flagged pairs (memory used, isolation found, "
            "settings answered no, or over the time box): %d, shown apart. Left out: %s with different or unknown settings; "
            "%s with no partner. %s: settings not confirmed by the gate. %s not shown."
            % (sum(c["pairs"] for c in p["cells"].values()), nf, plural(p["skipped"], "pair", "pairs"),
               plural(p["missing"], "run", "runs"), plural(sum(1 for r in rs if unconfirmed(r)), "run", "runs"),
               plural(sum(g.get("repeats", 0) for g in groups), "repeat attempt", "repeat attempts")))
    return {"id": "pairs", "kind": "bars", "title": "2. With skill vs without skill: pass count per pair (T3 and T6)",
            "groups": labels, "series": ["with skill", "without skill"], "values": values, "unit": "pass", "notes": notes, "hint": hint}


def chart_specs(rows):
    g = learners(rows)
    mt, tp, me = money_time(g), t6_pass(rows), methods(g)
    pc = lambda p, n: 100.0 * p / n if n else None
    c = tp["counts"]
    small_hint = ("With-skill T6 rows: %d pass, %d fail, %d ungraded; %s no T6 row; %s not in the bar. "
                  "%s: settings not confirmed by the gate. %s not shown. "
                  "The lab baseline used a 5-minute limit; the class used a 10-minute box."
                  % (c["pass"], c["fail"], c["ungraded"], plural(tp["missing"], "learner has", "learners have"),
                     plural(tp["flagged"], "flagged row is", "flagged rows are"),
                     plural(tp["unconfirmed"], "run", "runs"), plural(tp["repeats"], "repeat attempt", "repeat attempts")))
    return [
        {"id": "money", "kind": "bars", "title": "1a. Money per learner: stage 1 vs stage 3 (USD, API list price) (not a matched comparison)",
         "groups": mt["labels"], "series": SERIES3, "values": mt["cost"], "unit": "USD"},
        {"id": "time", "kind": "bars", "title": "1b. Time per learner: stage 1 vs stage 3 (minutes) (not a matched comparison)",
         "groups": mt["labels"], "series": SERIES3, "values": mt["time"], "unit": "min"},
        pair_spec(g),
        {"id": "small", "kind": "bars", "title": "3. T6 pass rate with skill: class (10-minute box) vs lab baseline (5 minutes)",
         "groups": ["baseline: no skill (lab)", "this class: with skill"], "series": ["T6 pass rate (%)"],
         "values": [[pc(*tp["baseline"])], [pc(*tp["class"])]], "unit": "%",
         "notes": [["%d/%d" % tp["baseline"]], ["%d/%d" % tp["class"]]], "hint": small_hint},
        {"id": "methods", "kind": "bars", "title": "4. Side quest: T6 median minutes by skill-writing method",
         "groups": list(me), "series": ["median T6 minutes"], "values": [[me[m]["median_min"]] for m in me], "unit": "min",
         "notes": [["%d/%d pass" % (me[m]["passed"], me[m]["n"])] for m in me],
         "hint": "Small groups: this is a hint, not proof. Flagged rows are left out."},
    ]


# ------------------------------------------------------------------ SVG / HTML
def esc(s):
    return html.escape(str(s), quote=True)


def fmt(v):
    return "-" if v is None else ("%.2f" % v if abs(v) < 10 and v != int(v) else "%d" % round(v))


def svg_bars(spec, W=680, H=320):
    L, R, T, B = 56, 16, 16, 64
    groups, series, values = spec["groups"], spec["series"], spec["values"]
    notes = spec.get("notes")
    pw, ph = W - L - R, H - T - B
    vmax = max([v for row in values for v in row if v is not None] or [0]) or 1.0
    ng, ns = max(len(groups), 1), len(series)
    gw = pw / ng
    bw = max(4.0, min(28.0, (gw - 12) / ns - 2))
    p = ['<svg viewBox="0 0 %d %d" width="100%%" role="img" aria-label="%s">' % (W, H, esc(spec["title"]))]
    for k in range(5):
        y = T + ph - ph * k / 4
        p.append('<line class="grid" x1="%d" x2="%d" y1="%.1f" y2="%.1f"/>' % (L, W - R, y, y))
        p.append('<text class="tick" x="%d" y="%.1f" text-anchor="end">%s</text>' % (L - 6, y + 4, fmt(vmax * k / 4)))
    for gi, lab in enumerate(groups):
        x0 = L + gi * gw + (gw - ns * (bw + 2)) / 2
        for si in range(ns):
            v = values[gi][si]
            if v is None:
                continue
            h = max(ph * v / vmax, 1.0)
            x, y = x0 + si * (bw + 2), T + ph - h
            p.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="2" fill="%s"><title>%s - %s: %s %s</title></rect>'
                     % (x, y, bw, h, NEUTRAL if (spec["id"] == "small" and gi == 0) else COLORS[si % len(COLORS)],
                        esc(lab), esc(series[si]), fmt(v), esc(spec["unit"])))
            if notes and notes[gi][si]:
                p.append('<text class="note" x="%.1f" y="%.1f" text-anchor="middle">%s</text>' % (x + bw / 2, y - 4, esc(notes[gi][si])))
        p.append('<text class="tick" x="%.1f" y="%d" text-anchor="middle">%s</text>' % (L + gi * gw + gw / 2, T + ph + 16, esc(str(lab)[:30])))
    if ns > 1:
        for si, s in enumerate(series):
            x = L + si * 210
            p.append('<rect x="%d" y="%d" width="10" height="10" rx="2" fill="%s"/><text class="tick" x="%d" y="%d">%s</text>'
                     % (x, H - 18, COLORS[si], x + 14, H - 9, esc(s)))
    p.append("</svg>")
    return "".join(p)


def html_table(spec):
    head = [""] + spec["series"] + (["note"] if spec.get("notes") else [])
    body = [[g] + [fmt(v) for v in spec["values"][i]] + ([" | ".join(n or "" for n in spec["notes"][i])] if spec.get("notes") else [])
            for i, g in enumerate(spec["groups"])]
    rows = "".join("<tr>%s</tr>" % "".join("<td>%s</td>" % esc(c) for c in r) for r in body)
    return "<table><tr>%s</tr>%s</table>" % ("".join("<th>%s</th>" % esc(h) for h in head), rows)


CSS = """:root{--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--grid:#e4e3df}
@media (prefers-color-scheme: dark){:root{--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--grid:#383835;color-scheme:dark}}
body{background:var(--surface);color:var(--ink);font:14px system-ui,sans-serif;max-width:760px;margin:0 auto;padding:16px}
.grid{stroke:var(--grid)}.tick{fill:var(--ink2);font-size:11px}.note{fill:var(--ink);font-size:11px}
table{border-collapse:collapse;font-size:12px;margin:6px 0 28px}td,th{border-bottom:1px solid var(--grid);padding:2px 8px;text-align:left}
.hint{color:var(--ink2)}"""


def render_html(specs, subtitle):
    parts = ["<!doctype html><meta charset='utf-8'><title>Workshop charts</title><style>%s</style>" % CSS,
             "<h1>Workshop charts</h1><p class='hint'>%s</p>" % esc(subtitle)]
    for s in specs:
        parts.append("<h2>%s</h2>" % esc(s["title"]))
        parts.append(svg_bars(s))
        if s.get("hint"):
            parts.append("<p class='hint'>%s</p>" % esc(s["hint"]))
        parts.append(html_table(s))
    return "\n".join(parts)


def write_pngs(specs, out):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib is not installed: only charts.html is written.")
        return []
    files = []
    for n, s in enumerate(specs, 1):
        fig, ax = plt.subplots(figsize=(7, 3.4))
        ns = len(s["series"])
        for si, name in enumerate(s["series"]):
            xs = [gi + (si - (ns - 1) / 2) * 0.8 / ns for gi in range(len(s["groups"]))]
            ax.bar(xs, [s["values"][gi][si] or 0 for gi in range(len(s["groups"]))], width=0.8 / ns,
                   color=COLORS[si], label=name)
        ax.set_xticks(range(len(s["groups"])))
        ax.set_xticklabels(s["groups"], fontsize=8)
        if len(s["series"]) > 1:
            ax.legend(fontsize=8)
        ax.set_title(s["title"], fontsize=10)
        fig.tight_layout()
        p = os.path.join(out, "chart-%d.png" % n)
        fig.savefig(p, dpi=120)
        plt.close(fig)
        files.append(p)
    return files


def main(argv=None):
    ap = argparse.ArgumentParser(prog="charts.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("exports", nargs="+")
    ap.add_argument("--from", dest="d_from")
    ap.add_argument("--to", dest="d_to")
    ap.add_argument("--out", default="charts-out")
    ap.add_argument("--png", action="store_true")
    ap.add_argument("--date-format", help="strptime format of the date column, e.g. %%d/%%m/%%Y %%H:%%M:%%S")
    ap.add_argument("--map", action="append", default=[], help='"Header text=field" for a renamed question')
    a = ap.parse_args(argv)
    day = lambda s: dt.datetime.strptime(s, "%Y-%m-%d").date() if s else None
    extra = dict(m.split("=", 1) for m in a.map)
    rows = in_range(dedup(load_rows(a.exports, extra, a.date_format)), day(a.d_from), day(a.d_to))
    if not rows:
        sys.exit("No rows in %s for that date range." % ", ".join(a.exports))
    os.makedirs(a.out, exist_ok=True)
    specs = chart_specs(rows)
    sub = "%d rows, %d learners; dates %s to %s" % (len(rows), len(learners(rows)), a.d_from or "any", a.d_to or "any")
    page = os.path.join(a.out, "charts.html")
    with open(page, "w", encoding="utf-8") as f:
        f.write(render_html(specs, sub))
    print("Wrote %s (%s)" % (page, sub))
    if a.png:
        for p in write_pngs(specs, a.out):
            print("Wrote " + p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
