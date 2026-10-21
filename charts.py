#!/usr/bin/env python3
"""charts.py - the debrief charts from the results form export (4 topics, 5 SVGs).

  python charts.py EXPORT [EXPORT ...] [--from YYYY-MM-DD] [--to YYYY-MM-DD] [--out DIR] [--png]
                   [--date-format FMT] [--map "Header text=field" ...]

EXPORT: the Microsoft Forms Excel export (.xlsx), a CSV of it, or the workshop's own results.csv.
--from / --to: keep only rows whose completion date is in [from, to] (one event session each; inclusive).
Writes DIR/charts.html (4 topics as 5 inline SVGs, each with a data table). --png also writes
DIR/chart-<n>.png when matplotlib is installed; without matplotlib only the HTML page is written.
Stdlib only (zipfile + ElementTree read the .xlsx).
"""
import argparse, csv, datetime as dt, html, os, re, statistics, sys, zipfile
import xml.etree.ElementTree as ET

FIELDS = ["alias", "run_id", "stage", "revision", "task", "agent", "model", "method", "skill_has_solution",
          "elapsed_min", "emulator_runs", "tok_uncached", "tok_cache_read", "tok_out", "cost_usd", "score",
          "grading", "measurement"]
DATE_HEADERS = ("completion time", "start time", "start")   # Forms columns first; results.csv has "start" (epoch)
PASS = 90                    # score >= PASS = pass (as in the lab runs)
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
        if f in FIELDS:
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


def learners(rows):
    """One dict per stage-1 run: {"label", "s1", "s2", "T6", "T3"} (missing keys = no row)."""
    by = {}
    for r in rows:
        rid, st = r.get("run_id", ""), r.get("stage", "")
        if st in ("1", "2") and rid.startswith("s1-"):
            by.setdefault(rid, {})["s%s" % st] = r
        elif st == "3" and parent_id(rid):
            ctl = r.get("method") == "none" or S3_ID.match(rid).group(2).startswith("n")
            by.setdefault(parent_id(rid), {})["N" + r.get("task", "T3")[-1] if ctl else r.get("task", "").upper()] = r   # N3 / N6 = control
    out = []
    for rid in sorted(by):
        g = by[rid]
        g["label"] = (g.get("s1") or {}).get("alias") or rid
        out.append(g)
    return out


# ------------------------------------------------------------------ chart data (pure)
SERIES3 = ["stage 1: T3, no skill", "stage 3: T6 with skill", "stage 3: T3 again with skill"]


def money_time(groups):
    keys = ("s1", "T6", "T3")
    return {"labels": [g["label"] for g in groups],
            "cost": [[num((g.get(k) or {}).get("cost_usd")) for k in keys] for g in groups],
            "time": [[num((g.get(k) or {}).get("elapsed_min")) for k in keys] for g in groups]}


def leakage(groups):
    """Points: x = stage-1 game % in the skill, y = stage-3 minutes; one point per stage-3 row."""
    pts = []
    for g in groups:
        x = num((g.get("s2") or {}).get("skill_has_solution"))
        if x is None:
            x = num((g.get("T3") or g.get("T6") or {}).get("skill_has_solution"))
        if x is None:
            continue
        for k in ("T6", "T3"):
            r = g.get(k)
            if r and num(r.get("elapsed_min")) is not None:
                pts.append({"x": x, "y": num(r["elapsed_min"]), "series": k, "label": g["label"],
                            "passed": (num(r.get("score")) or 0) >= PASS})
    return pts


def t6_pass(rows):
    t6 = [r for r in rows if r.get("stage") == "3" and r.get("task", "").upper() == "T6" and num(r.get("score")) is not None]
    return {"class": (sum(1 for r in t6 if num(r["score"]) >= PASS), len(t6)), "baseline": T6_BASELINE}


def methods(groups):
    acc = {}
    for g in groups:
        r = g.get("T6")
        m = (g.get("s1") or {}).get("method") or (r or {}).get("method")
        if not r or not m:
            continue
        d = acc.setdefault(m, {"times": [], "passed": 0, "n": 0})
        if num(r.get("elapsed_min")) is not None:
            d["times"].append(num(r["elapsed_min"]))
        d["n"] += 1
        d["passed"] += (num(r.get("score")) or 0) >= PASS
    return {m: {"median_min": statistics.median(d["times"]) if d["times"] else None, "passed": d["passed"], "n": d["n"]}
            for m, d in sorted(acc.items())}


def chart_specs(rows):
    g = learners(rows)
    mt, pts, tp, me = money_time(g), leakage(g), t6_pass(rows), methods(g)
    pc = lambda p, n: 100.0 * p / n if n else None
    return [
        {"id": "money", "kind": "bars", "title": "1a. Money per learner: stage 1 vs stage 3 (USD, API list price)",
         "groups": mt["labels"], "series": SERIES3, "values": mt["cost"], "unit": "USD"},
        {"id": "time", "kind": "bars", "title": "1b. Time per learner: stage 1 vs stage 3 (minutes)",
         "groups": mt["labels"], "series": SERIES3, "values": mt["time"], "unit": "min"},
        {"id": "leak", "kind": "scatter", "title": "2. Leakage gap: T3 again vs T6, by the game share in the skill",
         "points": pts, "series": ["T6", "T3"], "xlabel": "stage-1 game in the skill (%)", "ylabel": "stage-3 minutes",
         "hint": "Hollow = score below %d. A skill that holds the T3 game makes T3-again fast; T6 shows what it teaches." % PASS},
        {"id": "small", "kind": "bars", "title": "3. The small model can now do it: T6 pass rate (%)",
         "groups": ["baseline: no skill (lab)", "this class: with skill"], "series": ["T6 pass rate (%)"],
         "values": [[pc(*tp["baseline"])], [pc(*tp["class"])]], "unit": "%",
         "notes": [["%d/%d" % tp["baseline"]], ["%d/%d" % tp["class"]]]},
        {"id": "methods", "kind": "bars", "title": "4. Side quest: T6 median minutes by skill-writing method",
         "groups": list(me), "series": ["median T6 minutes"], "values": [[me[m]["median_min"]] for m in me], "unit": "min",
         "notes": [["%d/%d pass" % (me[m]["passed"], me[m]["n"])] for m in me],
         "hint": "Small groups: this is a hint, not proof."},
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
        p.append('<text class="tick" x="%.1f" y="%d" text-anchor="middle">%s</text>' % (L + gi * gw + gw / 2, T + ph + 16, esc(str(lab)[:22])))
    if ns > 1:
        for si, s in enumerate(series):
            x = L + si * 210
            p.append('<rect x="%d" y="%d" width="10" height="10" rx="2" fill="%s"/><text class="tick" x="%d" y="%d">%s</text>'
                     % (x, H - 18, COLORS[si], x + 14, H - 9, esc(s)))
    p.append("</svg>")
    return "".join(p)


def svg_scatter(spec, W=680, H=320):
    L, R, T, B = 56, 16, 16, 64
    pts = spec["points"]
    pw, ph = W - L - R, H - T - B
    ymax = max([q["y"] for q in pts] or [0]) or 1.0
    sx = lambda x: L + pw * min(max(x, 0), 100) / 100
    sy = lambda y: T + ph - ph * y / ymax
    p = ['<svg viewBox="0 0 %d %d" width="100%%" role="img" aria-label="%s">' % (W, H, esc(spec["title"]))]
    for k in range(5):
        y = T + ph - ph * k / 4
        p.append('<line class="grid" x1="%d" x2="%d" y1="%.1f" y2="%.1f"/>' % (L, W - R, y, y))
        p.append('<text class="tick" x="%d" y="%.1f" text-anchor="end">%s</text>' % (L - 6, y + 4, fmt(ymax * k / 4)))
        p.append('<text class="tick" x="%.1f" y="%d" text-anchor="middle">%d</text>' % (sx(25 * k), T + ph + 16, 25 * k))
    p.append('<text class="tick" x="%.1f" y="%d" text-anchor="middle">%s</text>' % (L + pw / 2, T + ph + 34, esc(spec["xlabel"])))
    for q in pts:
        c = COLORS[spec["series"].index(q["series"]) % len(COLORS)]
        p.append('<circle cx="%.1f" cy="%.1f" r="6" fill="%s" stroke="%s" stroke-width="2"><title>%s %s: %s%% game in skill, %s min%s</title></circle>'
                 % (sx(q["x"]), sy(q["y"]), c if q["passed"] else "var(--surface)", c, esc(q["label"]), q["series"],
                    fmt(q["x"]), fmt(q["y"]), "" if q["passed"] else ", score below %d" % PASS))
    for si, s in enumerate(spec["series"]):
        x = L + si * 160
        p.append('<circle cx="%d" cy="%d" r="5" fill="%s"/><text class="tick" x="%d" y="%d">%s</text>'
                 % (x + 5, H - 13, COLORS[si], x + 14, H - 9, "T6" if s == "T6" else "T3 again"))
    p.append("</svg>")
    return "".join(p)


def html_table(spec):
    if spec["kind"] == "scatter":
        head = ["learner", "task", spec["xlabel"], spec["ylabel"], "pass"]
        body = [[q["label"], q["series"], fmt(q["x"]), fmt(q["y"]), "yes" if q["passed"] else "no"] for q in spec["points"]]
    else:
        head = [""] + spec["series"] + (["note"] if spec.get("notes") else [])
        body = [[g] + [fmt(v) for v in spec["values"][i]] + ([" ".join(n or "" for n in spec["notes"][i])] if spec.get("notes") else [])
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
        parts.append(svg_scatter(s) if s["kind"] == "scatter" else svg_bars(s))
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
        if s["kind"] == "scatter":
            for si, name in enumerate(s["series"]):
                q = [p for p in s["points"] if p["series"] == name]
                ax.scatter([p["x"] for p in q], [p["y"] for p in q], s=50, edgecolors=COLORS[si], linewidths=2,
                           facecolors=[COLORS[si] if p["passed"] else "none" for p in q], label=name)
            ax.set_xlabel(s["xlabel"])
            ax.set_ylabel(s["ylabel"])
        else:
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
