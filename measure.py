#!/usr/bin/env python3
"""measure.py - time, emulator runs, tokens and estimated cost of one agent attempt.

    python measure.py start --label stage1 [--task T3]   before you give the agent the task
    python measure.py stop                               when the agent says it is done
    python measure.py show                               all your measured attempts (results.csv)
    python measure.py grade                              (re)grade attempts that have no score yet

Works with any agent. Time and emulator runs are always measured (bin/vesper logs every command
to .vesper-runs.log). Tokens are read from the agent's own session logs on this computer:
Claude Code (~/.claude/projects) and Codex (~/.codex/sessions). For any other agent pass
    python measure.py stop --tokens-in N --tokens-out M
with the numbers from that tool's usage screen. If part 4 is unlocked, `stop` also grades.
Standard library only; Linux, macOS and Windows.
"""
import argparse, csv, datetime as dt, glob, json, os, subprocess, sys, time

KIT = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(KIT, ".measure", "state.json")
RESULTS = os.path.join(KIT, "results.csv")
RUNLOG = os.path.join(KIT, ".vesper-runs.log")
PRICES = os.path.join(KIT, "prices.json")

# USD per million tokens. API list prices (Claude: Anthropic first-party API, Oct 2026).
# Subscription users don't pay per token - read cost as "what this would cost on the API".
# Add your models (e.g. the OpenAI model Codex uses) to prices.json next to this script:
#   {"gpt-x": {"in": 1.25, "cache_read": 0.125, "out": 10}}   (longest matching prefix wins)
DEFAULT_PRICES = {
    "claude-fable-5":  {"in": 10.0, "cache_read": 1.00, "out": 50.0},
    "claude-opus-5-5": {"in": 4.0,  "cache_read": 0.20, "out": 20.0},
    "claude-opus-5":   {"in": 5.0,  "cache_read": 0.50, "out": 25.0},
    "claude-opus-4":   {"in": 5.0,  "cache_read": 0.50, "out": 25.0},
    "claude-sonnet-5": {"in": 2.0,  "cache_read": 0.20, "out": 10.0},
    "claude-sonnet-4": {"in": 3.0,  "cache_read": 0.30, "out": 15.0},
    "claude-haiku-5":  {"in": 0.10, "cache_read": 0.01, "out": 0.50},
    "claude-haiku-4":  {"in": 1.0,  "cache_read": 0.10, "out": 5.0},
}
FIELDS = ["label", "task", "agent", "models", "wall_min", "agent_active_min", "emulator_runs",
          "tokens_in", "tokens_cache_write", "tokens_cache_read", "tokens_out", "cost_usd", "score",
          "started", "note"]


def now():
    return time.time()


def parse_ts(s):
    if isinstance(s, (int, float)):
        return float(s)
    try:
        return dt.datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def norm(p):
    return os.path.normcase(os.path.realpath(p))


def inside_kit(cwd):
    if not cwd:
        return False
    k, c = norm(KIT), norm(cwd)
    return c == k or c.startswith(k.rstrip(os.sep) + os.sep)


def jsonl(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    yield json.loads(line)
                except ValueError:
                    pass
    except OSError:
        return


# ---------------------------------------------------------------- Claude Code
def claude_usage(t0, t1, kit_only=True):
    home = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
    files = glob.glob(os.path.join(home, "projects", "*", "*.jsonl")) + \
        glob.glob(os.path.join(home, "projects", "*", "*", "subagents", "*.jsonl"))
    seen, tot, models, first, last = set(), dict(i=0, cw=0, cr=0, o=0), set(), None, None
    per_msg = {}
    for fp in files:
        try:
            if os.path.getmtime(fp) < t0:
                continue
        except OSError:
            continue
        for d in jsonl(fp):
            if d.get("type") != "assistant":
                continue
            ts = parse_ts(d.get("timestamp"))
            if ts is None or ts < t0 or ts > t1:
                continue
            if kit_only and not inside_kit(d.get("cwd")):
                continue
            m = d.get("message") or {}
            u = m.get("usage") or {}
            if not u:
                continue
            # One API response is logged once per content block, all with the same id. Input/cache
            # counts are final on every line; output_tokens is often a streaming partial, so keep
            # the largest value and also estimate from the text actually written (~4 chars/token).
            key = m.get("id") or d.get("requestId") or d.get("uuid")
            r = per_msg.setdefault(key, dict(i=0, cw=0, cr=0, o=0, chars=0))
            r["i"] = max(r["i"], u.get("input_tokens", 0) or 0)
            r["cw"] = max(r["cw"], u.get("cache_creation_input_tokens", 0) or 0)
            r["cr"] = max(r["cr"], u.get("cache_read_input_tokens", 0) or 0)
            r["o"] = max(r["o"], u.get("output_tokens", 0) or 0)
            for c in m.get("content") or []:
                if isinstance(c, dict):
                    r["chars"] += len(c.get("text") or c.get("thinking") or "") + \
                        (len(json.dumps(c["input"])) if "input" in c else 0)
            seen.add(key)
            if m.get("model") and not str(m["model"]).startswith("<"):
                models.add(m["model"])
            first = ts if first is None else min(first, ts)
            last = ts if last is None else max(last, ts)
    for r in per_msg.values():
        tot["i"] += r["i"]; tot["cw"] += r["cw"]; tot["cr"] += r["cr"]
        tot["o"] += max(r["o"], r["chars"] // 4)   # hidden thinking is not in the log: a lower bound
    tot["approx_out"] = True
    return (tot, models, first, last) if seen else None


# ---------------------------------------------------------------- Codex
def find_total_usage(obj):
    if isinstance(obj, dict):
        if isinstance(obj.get("total_token_usage"), dict):
            return obj["total_token_usage"]
        for v in obj.values():
            r = find_total_usage(v)
            if r:
                return r
    return None


def codex_usage(t0, t1, kit_only=True):
    home = os.environ.get("CODEX_HOME") or os.path.join(os.path.expanduser("~"), ".codex")
    files = glob.glob(os.path.join(home, "sessions", "**", "rollout-*.jsonl"), recursive=True)
    tot, models, first, last, found = dict(i=0, cw=0, cr=0, o=0), set(), None, None, False
    for fp in files:
        try:
            if os.path.getmtime(fp) < t0:
                continue
        except OSError:
            continue
        cwd, before, during = None, None, None
        for d in jsonl(fp):
            p = d.get("payload") or {}
            typ = d.get("type")
            if typ == "session_meta":
                cwd = p.get("cwd") or (p.get("meta") or {}).get("cwd")
            elif typ == "turn_context":
                cwd = cwd or p.get("cwd")
                if p.get("model"):
                    models.add(p["model"])
            u = find_total_usage(p) if typ == "event_msg" else None
            if not u:
                continue
            ts = parse_ts(d.get("timestamp"))
            if ts is None:
                continue
            if ts < t0:
                before = u
            elif ts <= t1:
                during = u
                first = ts if first is None else min(first, ts)
                last = ts if last is None else max(last, ts)
        if during is None or (kit_only and not inside_kit(cwd)):
            continue
        found = True
        b = before or {}
        g = lambda k: (during.get(k, 0) or 0) - (b.get(k, 0) or 0)
        cached = g("cached_input_tokens")
        tot["i"] += g("input_tokens") - cached          # OpenAI input_tokens includes cached ones
        tot["cr"] += cached
        tot["cw"] += g("cache_write_input_tokens")
        tot["o"] += g("output_tokens")                  # includes reasoning tokens
    return (tot, models, first, last) if found else None


# ---------------------------------------------------------------- helpers
def prices():
    p = dict(DEFAULT_PRICES)
    if os.path.exists(PRICES):
        try:
            p.update(json.load(open(PRICES, encoding="utf-8")))
        except ValueError as e:
            print("warning: prices.json ignored (%s)" % e)
    return p


def cost(tot, models):
    if len(models) != 1:
        return None if not models else cost_multi(tot, models)
    table = prices()
    m = next(iter(models))
    keys = [k for k in table if m.startswith(k)]
    if not keys:
        return None
    pr = table[max(keys, key=len)]
    cw = pr.get("cache_write", pr["in"] * 1.25)
    return (tot["i"] * pr["in"] + tot["cw"] * cw + tot["cr"] * pr.get("cache_read", pr["in"] * 0.1)
            + tot["o"] * pr["out"]) / 1e6


def cost_multi(tot, models):
    # Several models (e.g. a main agent plus helper agents): price everything at the most expensive one.
    table, best = prices(), None
    for m in models:
        keys = [k for k in table if m.startswith(k)]
        if keys:
            pr = table[max(keys, key=len)]
            best = pr if best is None or pr["out"] > best["out"] else best
    if not best:
        return None
    cw = best.get("cache_write", best["in"] * 1.25)
    return (tot["i"] * best["in"] + tot["cw"] * cw + tot["cr"] * best.get("cache_read", best["in"] * 0.1)
            + tot["o"] * best["out"]) / 1e6


def count_runs(t0, t1):
    n = 0
    try:
        for line in open(RUNLOG, encoding="utf-8", errors="replace"):
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "run" and t0 <= float(parts[0]) <= t1 + 1:
                n += 1
    except (OSError, ValueError):
        pass
    return n


def grade(task):
    g = os.path.join(KIT, "unlocked", "part-4", "grader", "grade.py")
    sol = os.path.join(KIT, "solutions", task + ".vsa")
    if not os.path.exists(g):
        return "", "not graded yet (grader locked): unlock part 4 after the run, then `python measure.py grade`"
    if not os.path.exists(sol):
        return "0", "no solutions/%s.vsa" % task
    exe = os.path.join(KIT, "bin", "vesper.exe" if os.name == "nt" else "vesper")
    env = dict(os.environ, VESPER_NO_LOG="1")           # grading runs are not the agent's runs
    try:
        r = subprocess.run([sys.executable, g, task, sol, "--bin", exe], capture_output=True,
                           text=True, timeout=300, env=env)
        return str(json.loads(r.stdout)["score"]), ""
    except Exception as e:  # noqa: BLE001
        return "", "grading failed: %s" % e


def fmt_k(n):
    return "%.1fM" % (n / 1e6) if n >= 1e6 else "%dk" % round(n / 1e3)


# ---------------------------------------------------------------- commands
def cmd_start(a):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    sols = [f for f in glob.glob(os.path.join(KIT, "solutions", "*.vsa"))]
    if sols:
        print("warning: solutions/ already has %s - for a fresh attempt delete it (and out/) first"
              % ", ".join(os.path.basename(s) for s in sols))
    json.dump({"label": a.label, "task": a.task, "start": now()}, open(STATE, "w"))
    print("started '%s' (%s) at %s - now give the agent the task." %
          (a.label, a.task, dt.datetime.now().strftime("%H:%M:%S")))


def cmd_stop(a):
    try:
        st = json.load(open(STATE))
    except (OSError, ValueError):
        sys.exit("no measurement running - use: python measure.py start --label <name>")
    t0, t1 = st["start"], now()
    note = []
    agent, res = "other", None
    if a.tokens_in is None:
        for name, fn in (("claude", claude_usage), ("codex", codex_usage)):
            res = fn(t0, t1)
            if res:
                agent = name
                break
        if not res:
            for name, fn in (("claude", claude_usage), ("codex", codex_usage)):
                res = fn(t0, t1, kit_only=False)
                if res:
                    agent = name
                    note.append("matched by time only (agent not started inside this folder)")
                    break
    tot, models, first, last = res if res else (dict(i=0, cw=0, cr=0, o=0), set(), None, None)
    if a.tokens_in is not None:
        tot = dict(i=a.tokens_in, cw=0, cr=0, o=a.tokens_out or 0)
        if a.model:
            models = {a.model}
    if a.model and not models:
        models = {a.model}
    if not res and a.tokens_in is None:
        note.append("no Claude Code / Codex session found - pass --tokens-in/--tokens-out")
    c = cost(tot, models)
    if c is None and (tot["i"] or tot["o"]):
        note.append("no price for %s - add it to prices.json" % (", ".join(sorted(models)) or "model"))
    score, gnote = grade(st["task"])
    if gnote:
        note.append(gnote)
    row = {
        "label": st["label"], "task": st["task"], "agent": agent, "models": " ".join(sorted(models)),
        "wall_min": "%.1f" % ((t1 - t0) / 60),
        "agent_active_min": "%.1f" % ((last - first) / 60) if first and last else "",
        "emulator_runs": count_runs(t0, t1),
        "tokens_in": tot["i"], "tokens_cache_write": tot["cw"], "tokens_cache_read": tot["cr"],
        "tokens_out": tot["o"], "cost_usd": "%.2f" % c if c is not None else "",
        "score": score, "started": dt.datetime.fromtimestamp(t0).strftime("%Y-%m-%d %H:%M"),
        "note": "; ".join(note),
    }
    new = not os.path.exists(RESULTS)
    with open(RESULTS, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerow(row)
    os.remove(STATE)
    total_in = tot["i"] + tot["cw"] + tot["cr"]
    print("\n  %s  (%s, %s)" % (row["label"], agent, row["models"] or "model unknown"))
    print("  time           %s min (agent active %s min)" % (row["wall_min"], row["agent_active_min"] or "?"))
    print("  emulator runs  %s" % row["emulator_runs"])
    print("  tokens         in %s (of which cached %s)  out %s%s" % (fmt_k(total_in), fmt_k(tot["cr"]), fmt_k(tot["o"]),
          "  (Claude Code: output is a lower bound, hidden thinking is not logged)" if tot.get("approx_out") else ""))
    print("  cost           %s" % ("~$" + row["cost_usd"] + " at API prices" if row["cost_usd"] else "n/a"))
    print("  score          %s" % (score or "n/a (unlock part 4 to grade)"))
    if note:
        print("  note           " + "; ".join(note))
    print("\n  saved to results.csv - `python measure.py show` lists all attempts\n")


def cmd_grade(a):
    # Unlock part 4 only after the agent has finished (it must not see the grader), then run this.
    if not os.path.exists(RESULTS):
        sys.exit("no results yet")
    rows = list(csv.DictReader(open(RESULTS, encoding="utf-8")))
    todo = [r for r in rows if not r["score"]] or ([rows[-1]] if a.last else [])
    if not todo:
        print("every attempt already has a score (use --last to regrade the latest)")
    for r in todo:
        score, gnote = grade(r["task"])
        r["score"] = score
        print("%s: %s %s" % (r["label"], score or "-", gnote))
        if score:
            print("   (grades the current solutions/%s.vsa)" % r["task"])
    with open(RESULTS, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


def cmd_show(a):
    if not os.path.exists(RESULTS):
        sys.exit("no results yet")
    rows = list(csv.DictReader(open(RESULTS, encoding="utf-8")))
    cols = [("label", 14), ("task", 4), ("agent", 6), ("wall_min", 8), ("emulator_runs", 13),
            ("tokens_in", 10), ("tokens_out", 10), ("cost_usd", 8), ("score", 5)]
    print("  ".join(c.ljust(w) for c, w in cols))
    for r in rows:
        tin = int(r["tokens_in"] or 0) + int(r["tokens_cache_write"] or 0) + int(r["tokens_cache_read"] or 0)
        vals = dict(r, tokens_in=fmt_k(tin), tokens_out=fmt_k(int(r["tokens_out"] or 0)))
        print("  ".join(str(vals[c])[:w].ljust(w) for c, w in cols))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("start")
    s.add_argument("--label", default="attempt")
    s.add_argument("--task", default="T3")
    s = sub.add_parser("stop")
    s.add_argument("--tokens-in", type=int, help="for agents other than Claude Code / Codex")
    s.add_argument("--tokens-out", type=int)
    s.add_argument("--model", help="model name for pricing (with --tokens-in)")
    sub.add_parser("show")
    s = sub.add_parser("grade")
    s.add_argument("--last", action="store_true", help="regrade the latest attempt")
    a = ap.parse_args()
    {"start": cmd_start, "stop": cmd_stop, "show": cmd_show, "grade": cmd_grade}[a.cmd](a)


if __name__ == "__main__":
    main()
