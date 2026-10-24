"""A FAKE agent CLI for the --auto tests. No network, no real agent.

It acts as codex (`exec` in the arguments), cursor-agent (`--workspace`), or claude (anything else), and as
`--version` / `status`. It writes the same kind of log as the real CLI: a Codex or Claude Code session file
(in CODEX_HOME / CLAUDE_CONFIG_DIR), or the stream-json lines on stdout for Cursor.

Env switches:
  FAKE_SLEEP       seconds a normal run takes (default 0.2)
  FAKE_SLOW_KEYS   comma list; a prompt that contains one of them runs FAKE_SLOW_SEC (default 60) seconds
  FAKE_CHILD=1     start a child process that writes folder/heartbeat.txt every 0.1 s (tests the tree kill)
  FAKE_FREEPLAN=1  Cursor free plan: "Named models unavailable" on stderr, exit code 1
  FAKE_FAIL        any agent: print this text on stderr and exit with code 1 at once
  FAKE_LIMIT=1     Cursor: hit-your-usage-limit text after the tool calls, no result event, exit code 1
  FAKE_NO_USAGE=1  Cursor: no result event (as a run killed before its usage report)
  FAKE_VERSION     text printed for --version (default "codex-cli 0.163.0")
  FAKE_LOGIN       "no" -> `status` prints "Not logged in"
  FAKE_INIT_MODEL  the model name Cursor reports in its init event (default: the --model argument)
  FAKE_PROBE_NOWRITE=1   the check-auto probe: do NOT write out/ok.txt (permissions too narrow)
  FAKE_PROBE_NOVERSION=1 the check-auto probe: do NOT print the VESPER-16 version text
  FAKE_PROBE_OUTSIDE=1   the check-auto probe: ALSO write the file outside the folder (no sandbox)
"""
import json, os, re, subprocess, sys, time, uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fakes  # noqa: E402


def arg_after(argv, flag, default=""):
    return argv[argv.index(flag) + 1] if flag in argv and argv.index(flag) + 1 < len(argv) else default


def main(argv):
    if "--version" in argv:
        print(os.environ.get("FAKE_VERSION", "codex-cli 0.163.0"))
        return 0
    if argv and argv[0] == "status":
        print("Not logged in" if os.environ.get("FAKE_LOGIN") == "no" else "Logged in as test@example.com")
        return 0
    stdin = None
    if "exec" in argv:
        kind, prompt, model = "codex", argv[-1], arg_after(argv, "-m")
        folder = arg_after(argv, "-C", os.getcwd())
        if prompt == "-":                      # `codex exec ... -`: the prompt is on stdin
            prompt = stdin = sys.stdin.read()
    elif "--workspace" in argv:
        kind, prompt, model = "cursor", argv[-1], arg_after(argv, "--model")
        folder = arg_after(argv, "--workspace", os.getcwd())
    else:
        kind, prompt, model = "claude", arg_after(argv, "-p"), arg_after(argv, "--model")
        folder = os.getcwd()
        if not prompt or prompt.startswith("-"):   # `claude -p --model ...`: the prompt is on stdin
            prompt = stdin = sys.stdin.read()
    with open(os.path.join(folder, "argv.json"), "w", encoding="utf-8") as f:
        json.dump({"kind": kind, "argv": argv, "cwd": os.getcwd(), "prompt": prompt, "stdin": stdin}, f)
    if os.environ.get("FAKE_FREEPLAN") and kind == "cursor":
        sys.stderr.write("ActionRequiredError: Named models unavailable Free plans can only use Auto.\n")
        return 1
    if os.environ.get("FAKE_FAIL"):            # any agent: an error line on stderr, exit code 1, no tool call
        sys.stderr.write(os.environ["FAKE_FAIL"] + "\n")
        return 1
    if "out/ok.txt" in prompt:                 # the doctor --check-auto probe
        if not os.environ.get("FAKE_PROBE_NOWRITE"):
            os.makedirs(os.path.join(folder, "out"), exist_ok=True)
            with open(os.path.join(folder, "out", "ok.txt"), "w") as f:
                f.write("OK")
        if not os.environ.get("FAKE_PROBE_NOVERSION"):
            print("VESPER-16 SDK 2.3.1", flush=True)
        m = re.search(r"into (\S+) \.", prompt)
        if m and os.environ.get("FAKE_PROBE_OUTSIDE"):
            with open(m.group(1), "w") as f:
                f.write("NO")
    if os.environ.get("FAKE_CHILD"):
        subprocess.Popen([sys.executable, "-c",
                          "import sys,time\n"
                          "p=sys.argv[1]\n"
                          "while True:\n"
                          "    open(p,'w').write(str(time.time()))\n"
                          "    time.sleep(0.1)\n", os.path.join(folder, "heartbeat.txt")])
    slow = [k for k in os.environ.get("FAKE_SLOW_KEYS", "").split(",") if k]
    pause = float(os.environ.get("FAKE_SLOW_SEC", "60")) if any(k in prompt for k in slow) \
        else float(os.environ.get("FAKE_SLEEP", "0.2"))
    t0 = time.time()
    if kind == "cursor":
        say = lambda d: print(json.dumps(d), flush=True)   # noqa: E731
        say({"type": "system", "subtype": "init", "cwd": folder, "session_id": str(uuid.uuid4()),
             "model": os.environ.get("FAKE_INIT_MODEL", model)})
        say({"type": "tool_call", "subtype": "started", "call_id": "1", "timestamp_ms": int(t0 * 1000),
             "tool_call": {"shellToolCall": {"args": {"command": "bin/vesper run solutions/T3.vsa",
                                                      "workingDirectory": folder}}}})
        time.sleep(pause)
        t1 = time.time()
        say({"type": "tool_call", "subtype": "completed", "call_id": "1", "timestamp_ms": int(t1 * 1000),
             "tool_call": {"shellToolCall": {"args": {"command": "bin/vesper run solutions/T3.vsa"}}}})
        say({"type": "assistant", "timestamp_ms": int(t1 * 1000),
             "message": {"role": "assistant", "content": [{"type": "text", "text": "done"}]}})
        if os.environ.get("FAKE_LIMIT"):         # free plan: cut off, no result line
            sys.stderr.write("ActionRequiredError: You've hit your usage limit. Upgrade your plan.\n")
            return 1
        if os.environ.get("FAKE_NO_USAGE"):
            return 0
        say({"type": "result", "subtype": "success", "duration_ms": int((t1 - t0) * 1000),
             "usage": {"inputTokens": 1200, "outputTokens": 340, "cacheReadTokens": 5000, "cacheWriteTokens": 700}})
        return 0
    time.sleep(pause)
    sid = str(uuid.uuid4())
    t1 = time.time()
    if kind == "codex":
        sys.stderr.write("WARNING: enterprise policy (ignored)\n")
        fakes.codex_log(sid, folder, [(t0, 0, 0, 0, prompt), (t1, 10000, 6000, 800, "")], model=model)
    else:
        fakes.claude_log(sid, folder, [(t0, 5, 0, 0, 0, prompt), (t1, 20, 3000, 400, 500, "")],
                         model="claude-haiku-5-5")
        print(json.dumps({"type": "result", "result": "done"}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
