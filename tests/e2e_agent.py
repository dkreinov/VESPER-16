"""End-to-end check of workshop.py with a real agent (headless `claude -p` or `codex exec`).

Plays the participant: new s1 -> agent -> done -> skill -> same session -> harvest -> new s3 -> new agent -> done.
Writes a log and status.json into --out. Compares workshop.py's token cost with Claude's own total_cost_usd.

  python tests/e2e_agent.py --agent claude|codex --out <dir> [--model M] [--method plain] [--password <pw>]
Spends real tokens. The workshop home is <out>/home (not your normal one).
"""
import argparse, json, os, subprocess, sys, time

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--agent", default="claude", choices=["claude", "codex"])
    ap.add_argument("--model", default="")
    ap.add_argument("--method", default="plain")
    ap.add_argument("--password", default="")
    ap.add_argument("--timeout", type=int, default=30, help="minutes per agent turn")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    env = dict(os.environ, VESPER_WS_HOME=os.path.join(a.out, "home"))
    log = open(os.path.join(a.out, "e2e.log"), "a", encoding="utf-8")
    status = {"step": "", "claude_cost": {}, "ok": None}

    def put(**kw):
        status.update(kw)
        with open(os.path.join(a.out, "status.json"), "w") as f:
            json.dump(status, f, indent=1)

    def ws(*args):
        r = subprocess.run([sys.executable, os.path.join(KIT, "workshop.py")] + list(args), env=dict(env, PYTHONIOENCODING="utf-8"),
                           capture_output=True, text=True, encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL)
        log.write("$ workshop.py %s\n%s%s\n" % (" ".join(args), r.stdout, r.stderr))
        log.flush()
        if r.returncode:
            raise SystemExit("workshop.py %s failed: %s" % (args[0], r.stderr[-500:]))
        return r.stdout

    def reg():
        with open(os.path.join(env["VESPER_WS_HOME"], "registry.json"), encoding="utf-8") as f:
            return json.load(f)

    def prompt_of(out):
        lines = out.splitlines()
        i = [k for k, l in enumerate(lines) if l.startswith("-" * 20)]
        return "\n".join(lines[i[0] + 1:i[1]])

    def agent(folder, prompt, resume=None, label=""):
        if a.agent == "claude":
            cmd = ["claude", "-p", "--output-format", "json", "--permission-mode", "bypassPermissions"]
            cmd += ["--model", a.model] if a.model else []
            cmd += ["--resume", resume] if resume else []
            cmd += [prompt]
        else:
            m = ["-m", a.model] if a.model else []
            if resume:
                cmd = ["codex", "exec", "resume", resume, "--json", "--full-auto", "--skip-git-repo-check"] + m + [prompt]
            else:
                cmd = ["codex", "exec", "--json", "--full-auto", "--skip-git-repo-check", "-C", folder] + m + [prompt]
        put(step="agent " + label)
        t = time.time()
        r = subprocess.run(cmd, cwd=folder, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=a.timeout * 60,
                           stdin=subprocess.DEVNULL)
        log.write("[agent %s] %.0fs rc=%d\n%s\n%s\n" % (label, time.time() - t, r.returncode, r.stdout[-1500:],
                                                          r.stderr[-800:]))
        log.flush()
        if a.agent == "claude":
            j = json.loads(r.stdout)
            status["claude_cost"][label] = j.get("total_cost_usd")
            sid = j["session_id"]
        else:
            sid, usage = resume, {}
            for line in r.stdout.splitlines():
                try:
                    ev = json.loads(line)
                except ValueError:
                    continue
                if ev.get("type") == "thread.started":
                    sid = ev.get("thread_id")
                if ev.get("type") == "turn.completed":
                    usage = ev.get("usage", {})
            status["claude_cost"][label] = usage      # Codex reports usage, not cost
        put()
        return sid

    try:
        put(step="doctor")
        ws("doctor", "--agent", a.agent, "--alias", "e2e")
        out = ws("new", "s1", "--method", a.method)
        r = reg()
        rid = r["active"]["run_id"]
        f1 = r["runs"][rid]["folder"]
        sid = agent(f1, prompt_of(out), label="stage1")
        ws("done", "--no-form")
        out = ws("skill")
        agent(f1, prompt_of(out), resume=sid, label="stage2")
        ws("harvest", "--no-form", "--move-aside", "--remove-global")
        out = ws("new", "s3", "--skill", "own")
        r = reg()
        s3 = r["active"]["run_id"]
        agent(r["runs"][s3]["folder"], prompt_of(out), label="stage3")
        ws("done", "--no-form")
        if a.password:
            ws("unlock", "4", a.password)
            ws("grade", "--no-form")
        put(step="finished", ok=True, rows=list(reg()["rows"].values()))
        log.write(ws("show"))
    except Exception as e:  # noqa: BLE001
        put(ok=False, error=str(e))
        raise
    finally:
        open(os.path.join(a.out, "DONE"), "w").close()


if __name__ == "__main__":
    main()
