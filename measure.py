#!/usr/bin/env python3
"""measure.py - time, emulator runs, tokens and estimated cost of one agent attempt.

    python measure.py start --label stage1 [--task T3]   before you give the agent the task
    python measure.py stop [--session ID]                when the agent says it is done (ID from /status)
    python measure.py show                               all your measured attempts (results.csv)
    python measure.py grade                              (re)grade attempts that have no score yet
    python measure.py redo [--session ID] [--since HH:MM] [--until HH:MM]   re-measure the last attempt

Works with any agent. Time and emulator runs are always measured (bin/vesper logs every command
to .vesper-runs.log). Tokens are read from the agent's own session logs on this computer:
Claude Code (~/.claude/projects) and Codex (~/.codex/sessions). For any other agent pass
    python measure.py stop --tokens-in N --tokens-out M
with the numbers from that tool's usage screen. If part 4 is unlocked, `stop` also grades.
Standard library only; Linux, macOS and Windows.
"""
import argparse, csv, datetime as dt, glob, json, os, re, subprocess, sys, time

KIT = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(KIT, ".measure", "state.json")
LAST = os.path.join(KIT, ".measure", "last.json")
RESULTS = os.path.join(KIT, "results.csv")
RUNLOG = os.path.join(KIT, ".vesper-runs.log")
PRICES = os.path.join(KIT, "prices.json")

# USD per million tokens, API list prices as of 2026-10-14 (standard tier, short prompts). Longest matching
# prefix of the model name wins. Override or add models in prices.json next to this script:
#   {"model-name": {"in": 2.0, "cache_read": 0.2, "cache_write": 2.5, "out": 10}}
# Subscription users (ChatGPT, Claude, Cursor plans) don't pay per token: read the cost as "what this
# would cost on the API". Accuracy target for the workshop: +-20%.
#   Claude:  Anthropic API price list (claude-api reference, Oct 2026). Claude Code writes its cache with a
#            1-hour lifetime, billed at 2x input, so cache_write = 2 x in.
#   OpenAI (Codex): openai.com could not be checked directly; GPT-6.1 Sol per OpenAI's launch post as
#            reported by aggregators, the rest from aggregators (OpenRouter, Requesty, CloudZero, ...).
#            GPT-5.6 Sol: $4/$20 is a promotional price (to Nov 21 2026; list $5/$30).
#            GPT-6 Luna: most sources $0.10/$0.50, one says $0.20/$1.20 - unconfirmed.
#   Cursor:  first-party models (Composer, Grok) from Cursor's docs as quoted by third parties; Cursor bills
#            third-party models (Claude, GPT, Gemini) at the provider's list price (+$0.25/M on Teams).
#   Gemini:  aggregators; Gemini 3.1 Pro rises to $4/$18 above 200K-token prompts.
DEFAULT_PRICES = {
    # Anthropic (Claude Code; also selectable in Cursor)
    "claude-fable-5-1":  {"in": 10.0, "cache_read": 0.25, "out": 50.0},
    "claude-fable-5":    {"in": 10.0, "cache_read": 1.00, "out": 50.0},
    "claude-mythos-5":   {"in": 10.0, "cache_read": 0.25, "out": 50.0},
    "claude-opus-5-5":   {"in": 4.0,  "cache_read": 0.20, "out": 20.0},
    "claude-opus-5":     {"in": 5.0,  "cache_read": 0.50, "out": 25.0},
    "claude-opus-4":     {"in": 5.0,  "cache_read": 0.50, "out": 25.0},
    "claude-sonnet-5":   {"in": 2.0,  "cache_read": 0.20, "out": 10.0},
    "claude-sonnet-4":   {"in": 3.0,  "cache_read": 0.30, "out": 15.0},
    "claude-haiku-5":    {"in": 0.10, "cache_read": 0.01, "out": 0.50},
    "claude-haiku-4":    {"in": 1.0,  "cache_read": 0.10, "out": 5.0},
    # OpenAI (Codex; also selectable in Cursor)
    "gpt-6.1-sol":       {"in": 2.0,  "cache_read": 0.10, "cache_write": 2.50, "out": 10.0},
    "gpt-6-astra":       {"in": 10.0, "cache_read": 1.00, "cache_write": 12.50, "out": 50.0},
    "gpt-6-sol":         {"in": 2.0,  "cache_read": 0.20, "out": 10.0},
    "gpt-6-luna":        {"in": 0.10, "cache_read": 0.01, "cache_write": 0.125, "out": 0.50},
    "gpt-5.6-sol":       {"in": 4.0,  "cache_read": 0.40, "out": 20.0},
    "gpt-5.6-terra":     {"in": 2.0,  "cache_read": 0.20, "cache_write": 2.50, "out": 12.0},
    "gpt-5.6-luna":      {"in": 0.20, "cache_read": 0.02, "out": 1.20},
    # Cursor's own models (enter the name with --model, e.g. --model composer-2.5)
    "composer-2.5":      {"in": 0.50, "cache_read": 0.20, "out": 2.50},
    "composer-2.5-fast": {"in": 3.0,  "out": 15.0},
    "grok-4.7":          {"in": 2.0,  "out": 6.0},
    "grok-4.6":          {"in": 2.0,  "cache_read": 0.50, "out": 6.0},
    "grok-4.6-fast":     {"in": 4.0,  "cache_read": 1.00, "out": 12.0},
    "grok-4.5":          {"in": 2.0,  "cache_read": 0.50, "out": 6.0},
    # Google (selectable in Cursor)
    "gemini-3.1-pro":    {"in": 2.0,  "cache_read": 0.20, "out": 12.0},
    "gemini-3.5-flash":  {"in": 1.50, "out": 9.0},
    "gemini-3.1-flash-lite": {"in": 0.25, "out": 1.50},
}


def cache_write_price(model, pr):
    if "cache_write" in pr:
        return pr["cache_write"]
    return pr["in"] * (2.0 if model.startswith("claude") else 1.25)


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


def path_forms(p):
    p = str(p)
    if p.startswith("\\\\?\\"):                 # Windows long-path prefix
        p = p[4:]
    forms = {os.path.abspath(p)}
    try:
        forms.add(os.path.realpath(p))       # OneDrive / symlinked folders resolve differently
    except OSError:
        pass
    return {os.path.normcase(f).rstrip("\\/") for f in forms}


def relation(cwd):
    """'kit' if the agent ran in this folder (or below it), 'parent' if in a folder above it."""
    if not cwd:
        return None
    sep = ("\\", "/")
    for k in path_forms(KIT):
        for c in path_forms(cwd):
            if c == k or any(c.startswith(k + x) for x in sep):
                return "kit"
            if any(k.startswith(c + x) for x in sep) and os.path.dirname(k) == c:
                return "parent"                  # only the folder directly above the kit
    tail = lambda x: [t for t in os.path.normcase(str(x)).replace("\\", "/").split("/") if t][-2:]
    if tail(cwd) == tail(KIT):               # same last two folder names: same folder via another path
        return "kit"
    return None


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
def claude_home():
    return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")


def claude_sessions(t0, t1, sid=None):
    home = claude_home()
    files = glob.glob(os.path.join(home, "projects", "*", "*.jsonl")) + \
        glob.glob(os.path.join(home, "projects", "*", "*", "subagents", "*.jsonl"))
    if sid:   # <session-id>.jsonl, and its helper agents in <session-id>/subagents/
        files = [f for f in files if sid.lower() in f.lower()]
    out = []
    for fp in files:
        if not sid and not recent(fp, t0):
            continue
        per_msg, models, cwd, first, last = {}, set(), None, None, None
        for d in jsonl(fp):
            if d.get("type") != "assistant":
                continue
            ts = parse_ts(d.get("timestamp"))
            if ts is None or ts < t0 or ts > t1:
                continue
            m = d.get("message") or {}
            u = m.get("usage") or {}
            if not u:
                continue
            cwd = cwd or d.get("cwd")
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
            if m.get("model") and not str(m["model"]).startswith("<"):
                models.add(m["model"])
            first = ts if first is None else min(first, ts)
            last = ts if last is None else max(last, ts)
        if not per_msg:
            continue
        tot = dict(i=0, cw=0, cr=0, o=0)
        for r in per_msg.values():
            tot["i"] += r["i"]; tot["cw"] += r["cw"]; tot["cr"] += r["cr"]
            tot["o"] += max(r["o"], r["chars"] // 4)   # hidden thinking is not in the log: a lower bound
        out.append(dict(agent="claude", file=fp, cwd=cwd, tot=tot, models=models, first=first, last=last,
                        sid=os.path.basename(fp)[:-6]))
    return out


# ---------------------------------------------------------------- Cursor (stream-json output file)
_VESPER_RUN = re.compile(r"""vesper(?:\.exe)?["']?\s+run\b""")


def cursor_model(name):
    """Model id as written in the stream-json init event: lower case, no spaces; 'Auto' -> 'auto'."""
    return re.sub(r"\s+", "-", str(name or "").strip().lower())


def cursor_sessions(path):
    """Read the agent-output.jsonl of one `cursor-agent -p --output-format stream-json` run.
    Cursor keeps no token counts locally, so this file is the measurement source. Returns a list with one
    dict (or [] when the file has no init and no result event): tot (i = uncached input, cr, cw, o), models,
    first/last (epoch seconds from timestamp_ms), cwd, session_id, tools (started tool_call events as text),
    emulator_runs (started `vesper run` calls), complete (a result event with usage was seen),
    duration (seconds from the result's duration_ms, or None; never mixed into first/last)."""
    models, cwd, sid, usage, stamps, tools, runs = set(), None, None, None, [], [], 0
    seen_init, duration = False, None
    for d in jsonl(path):
        if not isinstance(d, dict):
            continue
        ms = d.get("timestamp_ms")
        if isinstance(ms, (int, float)):
            stamps.append(ms / 1000.0)
        typ = d.get("type")
        if typ == "system" and d.get("subtype") == "init":
            seen_init = True
            if d.get("model"):
                models.add(cursor_model(d["model"]))
            cwd = d.get("cwd") or cwd
            sid = d.get("session_id") or sid
        elif typ == "tool_call" and d.get("subtype") == "started":
            text = json.dumps(d.get("tool_call"))
            tools.append(text)
            if _VESPER_RUN.search(text.replace("\\\"", '"')):
                runs += 1
        elif typ == "result":
            if isinstance(d.get("usage"), dict):
                usage = d["usage"]
            if isinstance(d.get("duration_ms"), (int, float)):
                duration = d["duration_ms"] / 1000.0          # seconds, not a time stamp
    if not seen_init and usage is None:
        return []
    u = usage or {}
    tot = dict(i=int(u.get("inputTokens", 0) or 0), cr=int(u.get("cacheReadTokens", 0) or 0),
               cw=int(u.get("cacheWriteTokens", 0) or 0), o=int(u.get("outputTokens", 0) or 0))
    return [dict(agent="cursor", file=path, cwd=cwd, tot=tot, models=models, first=min(stamps) if stamps else None,
                 last=max(stamps) if stamps else None, sid=sid or os.path.basename(path), tools=tools,
                 emulator_runs=runs, complete=usage is not None, duration=duration)]


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


def codex_home():
    return os.environ.get("CODEX_HOME") or os.path.join(os.path.expanduser("~"), ".codex")


def recent(fp, t0, days=7):
    """Cheap pre-filter. Windows may not update the modified time of a log the agent keeps open,
    so also accept files whose name (rollout-YYYY-MM-DD...) is from the last few days."""
    try:
        if os.path.getmtime(fp) >= t0 - 86400:
            return True
    except OSError:
        return False
    m = re.search(r"(\d{4}-\d{2}-\d{2})T", os.path.basename(fp))
    if m:
        d = dt.datetime.strptime(m.group(1), "%Y-%m-%d").date()
        return (dt.date.fromtimestamp(t0) - d).days <= days
    return False


def root_of(fp, t0):
    try:
        if not recent(fp, t0):
            return None
        with open(fp, encoding="utf-8", errors="replace") as f:
            p = (json.loads(f.readline()).get("payload") or {})
        return str(p.get("session_id") or p.get("parent_thread_id") or "").lower() or None
    except (OSError, ValueError):
        return None


def codex_sessions(t0, t1, sid=None):
    home = codex_home()
    files = glob.glob(os.path.join(home, "sessions", "**", "*.jsonl"), recursive=True) + \
        glob.glob(os.path.join(home, "archived_sessions", "**", "*.jsonl"), recursive=True)
    if sid:   # rollout-<date>-<session-id>.jsonl, plus helper-agent threads whose root is that session
        files = [f for f in files if sid.lower() in os.path.basename(f).lower() or (root_of(f, t0) or "-").startswith(sid.lower())]
    out = []
    for fp in files:
        if not sid and not recent(fp, t0):
            continue
        cwd, before, during, models, first, last = None, None, None, set(), None, None
        effort, eff_ts = "", None
        for d in jsonl(fp):
            p = d.get("payload") or {}
            typ = d.get("type")
            if typ == "session_meta":
                cwd = p.get("cwd") or (p.get("meta") or {}).get("cwd") or cwd
            elif typ == "turn_context":
                cwd = p.get("cwd") or cwd
                if p.get("model"):
                    models.add(p["model"])
                ets = parse_ts(d.get("timestamp"))
                if p.get("effort") and ets is not None and ets <= t1 and (eff_ts is None or ets >= eff_ts):
                    effort, eff_ts = str(p["effort"]), ets      # last turn_context up to the end of the window
            if typ == "event_msg":
                u = find_total_usage(p)
            elif typ == "token_usage_record":            # newer Codex: per-response record with thread totals
                u = p.get("thread_token_usage") if isinstance(p.get("thread_token_usage"), dict) else None
            else:
                u = None
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
        if during is None:
            continue
        b = before or {}
        g = lambda k: (during.get(k, 0) or 0) - (b.get(k, 0) or 0)
        cached = g("cached_input_tokens")
        tot = dict(i=g("input_tokens") - cached,        # OpenAI input_tokens includes cached ones
                   cr=cached, cw=g("cache_write_input_tokens"),
                   o=g("output_tokens"))                # includes reasoning tokens
        out.append(dict(agent="codex", file=fp, cwd=cwd, tot=tot, models=models, first=first, last=last,
                        effort=effort, eff_ts=eff_ts, sid=os.path.basename(fp)[:-6]))
    return out


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
    cw = cache_write_price(m, pr)
    return (tot["i"] * pr["in"] + tot["cw"] * cw + tot["cr"] * pr.get("cache_read", pr["in"] * 0.1)
            + tot["o"] * pr["out"]) / 1e6


def cost_multi(tot, models):
    # Several models (e.g. a main agent plus helper agents): price everything at the most expensive one.
    table, best, bm = prices(), None, ""
    for m in models:
        keys = [k for k in table if m.startswith(k)]
        if keys:
            pr = table[max(keys, key=len)]
            if best is None or pr["out"] > best["out"]:
                best, bm = pr, m
    if not best:
        return None
    cw = cache_write_price(bm, best)
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


def run_times(t0, t1):
    ts = []
    try:
        for line in open(RUNLOG, encoding="utf-8", errors="replace"):
            parts = line.split()
            if len(parts) >= 2 and t0 <= float(parts[0]) <= t1 + 1:
                ts.append(float(parts[0]))
    except (OSError, ValueError):
        pass
    return ts


def clean_id(x):
    """Accept a bare session ID or a deep link such as codex://threads/<id>."""
    x = (x or "").strip().strip('"').rstrip("/")
    return x.rsplit("/", 1)[-1] if "/" in x else x


def measure(t0, t1, label, task, a):
    note = []
    chosen, agent, models = [], "other", set()
    tot = dict(i=0, cw=0, cr=0, o=0)
    sid = clean_id(a.session)
    if a.tokens_in is None and not sid and sys.stdin.isatty():
        print("\n  Session ID of the agent (Codex: /status -> Session/Thread; Claude Code: /status -> Session ID).")
        sid = clean_id(input("  Paste it (or the codex://threads/... link), or press Enter to skip: "))
    if a.tokens_in is None:
        if sid:
            chosen = claude_sessions(t0, t1, sid) + codex_sessions(t0, t1, sid)
            if not chosen:
                msg = ("session %s: no log with activity in this time window under %s or %s"
                       % (sid, os.path.join(claude_home(), "projects"), os.path.join(codex_home(), "sessions")))
                print("  " + msg)
                note.append(msg)
        else:   # no ID: accept only one unambiguous session started in this folder
            cands = [c for c in claude_sessions(t0, t1) + codex_sessions(t0, t1) if relation(c["cwd"]) == "kit"]
            def root(c):
                if os.path.basename(os.path.dirname(c["file"])) == "subagents":
                    return os.path.basename(os.path.dirname(os.path.dirname(c["file"])))
                return (root_of(c["file"], 0) if c["agent"] == "codex" else None) or c["sid"]
            roots = {root(c) for c in cands}
            if len(roots) == 1:
                chosen = cands
            elif cands:
                note.append("several agent sessions in this folder - rerun with --session <id>")
        for c in chosen:
            print("  using %s session %s (%s)" % (c["agent"], c["sid"], c["cwd"] or "?"))
            for k in tot:
                tot[k] += c["tot"].get(k, 0)
            models |= c["models"]
        agents = sorted({c["agent"] for c in chosen})
        agent = "+".join(agents) if agents else "other"
        if not chosen and sys.stdin.isatty():
            print("  No session log found. Type the numbers from your agent's usage screen (Enter to skip).")
            ti, to = input("  input tokens: ").strip(), input("  output tokens: ").strip()
            if ti or to:
                tot = dict(i=int(ti.replace(",", "") or 0), cw=0, cr=0, o=int(to.replace(",", "") or 0))
    else:
        tot = dict(i=a.tokens_in, cw=0, cr=0, o=a.tokens_out or 0)
    if a.model and (a.tokens_in is not None or not models):
        models = {a.model}
    act = [x for c in chosen for x in (c["first"], c["last"]) if x] + run_times(t0, t1)
    first, last = (min(act), max(act)) if act else (None, None)
    if first and first - t0 > 180:
        note.append("measurement started %.0f min before the agent - use the agent time" % ((first - t0) / 60))
    c = cost(tot, models)
    if c is None and (tot["i"] or tot["o"]):
        note.append("no price for %s - add it to prices.json" % (", ".join(sorted(models)) or "model"))
    if getattr(a, "keep_score", None):
        score, gnote = a.keep_score, ""
    else:
        if os.path.exists(os.path.join(KIT, "unlocked", "part-4", "grader", "grade.py")):
            print("  grading solutions/%s.vsa ..." % task)
        score, gnote = grade(task)
    if gnote:
        note.append(gnote)
    row = {
        "label": label, "task": task, "agent": agent, "models": " ".join(sorted(models)),
        "wall_min": "%.1f" % ((t1 - t0) / 60),
        "agent_active_min": "%.1f" % ((last - first) / 60) if first and last else "",
        "emulator_runs": count_runs(t0, t1),
        "tokens_in": tot["i"], "tokens_cache_write": tot["cw"], "tokens_cache_read": tot["cr"],
        "tokens_out": tot["o"], "cost_usd": "%.2f" % c if c is not None else "",
        "score": score, "started": dt.datetime.fromtimestamp(t0).strftime("%Y-%m-%d %H:%M"),
        "note": "; ".join(note),
    }
    total_in = tot["i"] + tot["cw"] + tot["cr"]
    print("\n  %s  (%s, %s)" % (label, agent, row["models"] or "model unknown"))
    print("  agent time     %s min   (start to stop: %s min)" % (row["agent_active_min"] or "?", row["wall_min"]))
    print("  emulator runs  %s" % row["emulator_runs"])
    print("  tokens         in %s (of which cached %s)  out %s%s" % (fmt_k(total_in), fmt_k(tot["cr"]), fmt_k(tot["o"]),
          "  (Claude Code: output is a lower bound)" if "claude" in agent else ""))
    print("  cost           %s" % ("~$" + row["cost_usd"] + " at API prices" if row["cost_usd"] else "n/a"))
    print("  score          %s" % (score or "not graded yet"))
    if note:
        print("  note           " + "\n                 ".join(note))
    return row


def save_rows(rows):
    with open(RESULTS, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


def load_rows():
    if not os.path.exists(RESULTS):
        return []
    return list(csv.DictReader(open(RESULTS, encoding="utf-8")))


def cmd_stop(a):
    try:
        st = json.load(open(STATE))
    except (OSError, ValueError):
        sys.exit("no measurement running - use: python measure.py start --label <name>")
    st["stop"] = now()
    row = measure(st["start"], st["stop"], st["label"], st["task"], a)
    save_rows(load_rows() + [row])
    json.dump(st, open(LAST, "w"))
    os.remove(STATE)
    print("\n  saved to results.csv - `python measure.py show` lists all attempts\n")


def cmd_redo(a):
    rows = load_rows()
    try:
        st = json.load(open(LAST))
    except (OSError, ValueError):
        if not rows:
            sys.exit("nothing to redo - stop an attempt first")
        r = rows[-1]   # older measure.py: no saved window; use the row's start minute, end now
        t = dt.datetime.strptime(r["started"], "%Y-%m-%d %H:%M").timestamp()
        st = dict(label=r["label"], task=r["task"], start=t,
                  stop=t + (float(r["wall_min"]) + 1) * 60 if r.get("wall_min") else now())
    day = dt.datetime.fromtimestamp(st["start"]).date()
    hm = lambda x: dt.datetime.combine(day, dt.datetime.strptime(x, "%H:%M").time()).timestamp()
    if a.since:
        st["start"] = hm(a.since)
    if a.until:
        st["stop"] = hm(a.until)
    same = rows and rows[-1]["label"] == st["label"]
    a.keep_score = rows[-1]["score"] if same and rows[-1]["score"] else None   # no re-grading on redo
    row = measure(st["start"], st["stop"], st["label"], st["task"], a)
    if same:
        rows[-1] = row
    else:
        rows.append(row)
    save_rows(rows)
    json.dump(st, open(LAST, "w"))
    print("\n  updated the last attempt in results.csv\n")


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
    save_rows(rows)


def cmd_inspect(a):
    """Diagnostics: what the session log looks like, for reporting problems."""
    import collections
    sid = clean_id(a.session)
    files = [f for f in glob.glob(os.path.join(codex_home(), "**", "*.jsonl"), recursive=True) +
             glob.glob(os.path.join(claude_home(), "projects", "**", "*.jsonl"), recursive=True)
             if sid and sid.lower() in f.lower()]
    print("searched %s and %s" % (codex_home(), os.path.join(claude_home(), "projects")))
    if not files:
        print("no file name contains", sid)
    t0 = None
    if a.since:
        t0 = dt.datetime.combine(dt.date.today(), dt.datetime.strptime(a.since, "%H:%M").time()).timestamp()
    for fp in files:
        print("\nfile:", fp, " modified:", dt.datetime.fromtimestamp(os.path.getmtime(fp)).strftime("%Y-%m-%d %H:%M"))
        types, n, first, last, tok = collections.Counter(), 0, None, None, []
        for d in jsonl(fp):
            n += 1
            p = d.get("payload") if isinstance(d.get("payload"), dict) else {}
            key = "%s/%s" % (d.get("type"), p.get("type", "")) if p.get("type") else str(d.get("type"))
            types[key] += 1
            ts = parse_ts(d.get("timestamp"))
            if ts:
                first = ts if first is None else min(first, ts)
                last = ts if last is None else max(last, ts)
            if "token" in key or "usage" in json.dumps(p)[:4000]:
                if len(tok) < 3 or (t0 and ts and ts >= t0 and len(tok) < 6):
                    tok.append((d.get("timestamp"), key, json.dumps(p)[:300]))
        fmt = lambda t: dt.datetime.fromtimestamp(t).strftime("%H:%M:%S") if t else "?"
        print("lines: %d   first: %s   last: %s (local time)" % (n, fmt(first), fmt(last)))
        for k, v in types.most_common(15):
            print("   %5d  %s" % (v, k))
        print("token-like lines (first few):")
        for t in tok:
            print("  ", t[0], t[1], t[2])


def cmd_show(a):
    if not os.path.exists(RESULTS):
        sys.exit("no results yet")
    rows = list(csv.DictReader(open(RESULTS, encoding="utf-8")))
    cols = [("label", 14), ("task", 4), ("agent", 6), ("agent_active_min", 9), ("emulator_runs", 13),
            ("tokens_in", 10), ("tokens_out", 10), ("cost_usd", 8), ("score", 5)]
    heads = {"agent_active_min": "agent_min", "emulator_runs": "emulator_runs"}
    print("  ".join(heads.get(c, c).ljust(w) for c, w in cols))
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
    for name in ("stop", "redo"):
        s = sub.add_parser(name)
        s.add_argument("--tokens-in", type=int, help="for agents other than Claude Code / Codex")
        s.add_argument("--tokens-out", type=int)
        s.add_argument("--model", help="model name for pricing")
        s.add_argument("--session", help="agent session ID from /status (Codex or Claude Code)")
        if name == "redo":
            s.add_argument("--since", help="HH:MM - attempt started at this local time")
            s.add_argument("--until", help="HH:MM - attempt ended at this local time")
    sub.add_parser("show")
    s = sub.add_parser("inspect")
    s.add_argument("--session", required=True)
    s.add_argument("--since")
    s = sub.add_parser("grade")
    s.add_argument("--last", action="store_true", help="regrade the latest attempt")
    a = ap.parse_args()
    {"start": cmd_start, "stop": cmd_stop, "redo": cmd_redo, "show": cmd_show, "inspect": cmd_inspect, "grade": cmd_grade}[a.cmd](a)


if __name__ == "__main__":
    main()
