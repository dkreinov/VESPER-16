import datetime as dt, importlib, json, os, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def fresh_ws():
    home = tempfile.mkdtemp(prefix="vws_")
    os.environ["VESPER_WS_HOME"] = os.path.join(home, "vesper-runs")
    os.environ["VESPER_WS_USERHOME"] = os.path.join(home, "user")
    os.environ["CLAUDE_CONFIG_DIR"] = os.path.join(home, "claude")
    os.environ["CODEX_HOME"] = os.path.join(home, "codex")
    os.environ["VESPER_DOCTOR_REPORT"] = os.path.join(home, "doctor-report.txt")   # never in the kit folder
    os.environ["VESPER_DOCTOR_SKIP_CLI"] = "1"                                   # no slow agent --version calls
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    import workshop
    importlib.reload(workshop)
    return workshop, home


def run(w, *argv):
    a = w.parse(list(argv))
    return a.func(a)


def iso(t):
    return dt.datetime.fromtimestamp(t, dt.timezone.utc).isoformat().replace("+00:00", "Z")


def codex_log(sid, cwd, events, model="gpt-6.1-sol"):
    """events: list of (t, input, cached, output, text)."""
    d = os.path.join(os.environ["CODEX_HOME"], "sessions", "2026", "10", "18")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, "rollout-2026-10-18T10-00-00-%s.jsonl" % sid)
    t0 = events[0][0]
    with open(p, "w") as f:
        f.write(json.dumps({"timestamp": iso(t0), "type": "session_meta",
                            "payload": {"id": sid, "session_id": sid, "cwd": cwd}}) + "\n")
        f.write(json.dumps({"timestamp": iso(t0), "type": "turn_context",
                            "payload": {"cwd": cwd, "model": model}}) + "\n")
        for t, i, c, o, text in events:
            if text:
                f.write(json.dumps({"timestamp": iso(t), "type": "response_item", "payload": {
                    "type": "message", "content": [{"type": "input_text", "text": text}]}}) + "\n")
            f.write(json.dumps({"timestamp": iso(t), "type": "event_msg", "payload": {
                "type": "token_count", "info": {"total_token_usage": {
                    "input_tokens": i, "cached_input_tokens": c, "output_tokens": o}}}}) + "\n")
    return p


def claude_log(sid, cwd, events, model="claude-haiku-5-5"):
    """events: list of (t, uncached, cache_read, cache_write, output, text)."""
    d = os.path.join(os.environ["CLAUDE_CONFIG_DIR"], "projects", "-proj")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, sid + ".jsonl")
    with open(p, "w") as f:
        for k, (t, i, cr, cw, o, text) in enumerate(events):
            if text:
                f.write(json.dumps({"type": "user", "timestamp": iso(t), "cwd": cwd,
                                    "message": {"role": "user", "content": text}}) + "\n")
            f.write(json.dumps({"type": "assistant", "timestamp": iso(t), "cwd": cwd, "message": {
                "id": "m%d" % k, "model": model, "content": [],
                "usage": {"input_tokens": i, "cache_read_input_tokens": cr,
                          "cache_creation_input_tokens": cw, "output_tokens": o}}}) + "\n")
    return p


FAKE_GRADER = ('import json, sys\n'
               'a = sys.argv\n'
               'name = a[a.index("--name") + 1] if "--name" in a else ""\n'
               'print(json.dumps({"score": 100 if name == "MIRA" else 1}))\n')


def install_fake_grader(w):
    """A grader that scores 100 only when it gets --name MIRA (checks that T6 passes the name)."""
    p = w.grader_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        f.write(FAKE_GRADER)


def ready_for_s3(w, method="plain"):
    """doctor -> new s1 -> done -> skill -> harvest, with no agent. Returns (s1 run id, harvest stdout)."""
    import contextlib, io
    run(w, "doctor", "--agent", "codex", "--alias", "t")
    run(w, "new", "s1", "--method", method)
    reg = w.Registry.load()
    rid = reg.data["active"]["run_id"]
    f = reg.data["runs"][rid]["folder"]
    run(w, "done", "--no-form")
    run(w, "skill")
    sk = os.path.join(f, "skill-out", "vesper16")
    os.makedirs(sk)
    with open(os.path.join(sk, "SKILL.md"), "w") as fh:
        fh.write("---\nname: vesper16\ndescription: VESPER-16 games\n---\nUse bin/vesper.\n")
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        run(w, "harvest", "--no-form")
    return rid, out.getvalue()
