"""End-to-end check of workshop.py with a real agent (headless `claude -p` or `codex exec`).

Plays the participant: new s1 -> agent -> done -> skill -> same session -> harvest -> stage 3 -> done.
  default: one stage-3 run (T3).
  --v2: two stage-3 runs AT THE SAME TIME (T6 with --name, and T3), each a new agent, then `done <run_id>` for each.
  --sandbox (Linux + bwrap, --out under /tmp; --sandbox-check tests it with no agent): each agent sees only its run folder and its own config home (no neighbour folders,
  no organiser CLAUDE.md or skills; --out must be outside your home folder). Claude needs a token in ~/.claude-eval-token (`claude setup-token`);
  Codex gets a fresh CODEX_HOME with a copy of ~/.codex/auth.json and plugins off.
Writes e2e.log, status.json and DONE into --out. The workshop home is <out>/home (not your normal one).

  python tests/e2e_agent.py --agent claude|codex --out <dir> [--model M] [--s3-model M] [--method plain]
                            [--v2 --name MIRA] [--sandbox]
Spends real tokens. The part-4 password is read only from the environment variable VESPER_PART4_PW and never logged.
"""
import argparse, concurrent.futures, json, os, shutil, subprocess, sys, threading, time

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, KIT)
import t6font  # noqa: E402


def sandbox_env(out, agent):
    """An isolated HOME and agent config under <out>/agent-home."""
    h = os.path.join(out, "agent-home")
    env = {"HOME": h}
    if agent == "claude":
        cfg = os.path.join(h, ".claude")
        os.makedirs(cfg, exist_ok=True)
        tokf = os.path.join(os.path.expanduser("~"), ".claude-eval-token")
        if not os.path.exists(tokf):
            raise SystemExit("--sandbox with claude needs ~/.claude-eval-token (make it with: claude setup-token)")
        for p in (os.path.join(h, ".claude.json"), os.path.join(cfg, ".claude.json")):
            with open(p, "w") as fj:
                json.dump({"hasCompletedOnboarding": True}, fj)
        with open(tokf) as f:
            env.update(CLAUDE_CONFIG_DIR=cfg, CLAUDE_CODE_DISABLE_AUTO_MEMORY="1", CLAUDE_CODE_OAUTH_TOKEN=f.read().strip())
    else:
        cfg = os.path.join(h, ".codex")
        os.makedirs(cfg, exist_ok=True)
        shutil.copy(os.path.join(os.path.expanduser("~"), ".codex", "auth.json"), os.path.join(cfg, "auth.json"))
        with open(os.path.join(cfg, "config.toml"), "w") as f:
            f.write("[features]\nplugins = false\nremote_plugins = false\n")
        env["CODEX_HOME"] = cfg
    return env


def require_sandbox(out):
    """Fail fast: --sandbox needs Linux, bwrap, and --out under /tmp (the sandbox hides everything else)."""
    if sys.platform == "win32" or not sys.platform.startswith("linux") or not shutil.which("bwrap"):
        raise SystemExit("--sandbox needs Linux with bwrap")
    real = os.path.realpath(out)
    if not real.startswith("/tmp/"):
        raise SystemExit("--sandbox: --out must be a folder under /tmp (the agent sees only its run folder; got %s)" % real)


def bwrap_args(cmd, run_folder, env, extra_ro=(), real_home=None):
    """Same idea as the lab harness sandbox(): / read-only, /tmp, /homes and the home parent are EMPTY tmpfs,
    then only the tool installs (read-only) and the run folder + agent home (read-write) are bound back.
    So <out>, <out>/home/registry.json, e2e.log and the other run folders are invisible to the agent."""
    real_home = real_home or os.path.realpath(os.path.expanduser("~"))
    ro = [os.path.join(real_home, ".local"), os.path.join(real_home, ".nvm")]
    for tool in ("claude", "codex", "node", "git", "python3"):
        pth = shutil.which(tool, path=env.get("PATH"))
        if pth:
            ro += [os.path.dirname(pth), os.path.dirname(os.path.realpath(pth))]
    ro += list(extra_ro)
    parent = os.path.dirname(real_home)
    masks = ["/tmp", "/homes", parent if parent not in ("/", "/tmp") else real_home]
    masks = sorted(set(masks), key=len)
    args = ["bwrap", "--ro-bind", "/", "/"]
    for m in masks:
        args += ["--tmpfs", m]
    args += ["--dev", "/dev", "--proc", "/proc"]
    rw = sorted({run_folder, env["HOME"]}, key=len)
    under = lambda d, roots: any(d == r or d.startswith(r + os.sep) for r in roots)
    for d in sorted(set(ro), key=len):
        if os.path.exists(d) and under(d, masks) and not under(d, rw):
            args += ["--ro-bind", d, d]
    for d in rw:
        args += ["--bind", d, d]
    return args + ["--chdir", run_folder, "--die-with-parent", "--"] + list(cmd)


def sandbox_selfcheck(out, run_folder, env, run=subprocess.run):
    """No agent: from inside the sandbox, <out> and <out>/home/registry.json must be invisible."""
    reg_file = os.path.join(out, "home", "registry.json")
    cmd = bwrap_args(["bash", "-c", "ls %s; cat %s" % (out, reg_file)], run_folder, env)
    r = run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=60)
    seen = (r.stdout or "") + (r.stderr or "")
    if r.returncode == 0 or "e2e.log" in seen or "registry.json" in (r.stdout or "") or '"runs"' in seen:
        raise SystemExit("sandbox leak: the agent can see %s (rc=%s): %s" % (out, r.returncode, seen[-300:]))
    return seen


ALLOW = ("PATH", "LANG", "LANGUAGE", "TERM", "TMPDIR", "TZ", "HOME", "VESPER_WS_HOME", "CLAUDE_CODE_OAUTH_TOKEN",
         "CLAUDE_CONFIG_DIR", "CLAUDE_CODE_DISABLE_AUTO_MEMORY", "CODEX_HOME")
ALLOW_WIN = ("SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "APPDATA", "LOCALAPPDATA", "USERPROFILE", "HOMEDRIVE", "HOMEPATH",
             "TEMP", "TMP", "PATHEXT", "COMSPEC", "PROGRAMFILES", "PROGRAMFILES(X86)", "PROGRAMDATA", "USERNAME")
ALLOW_AUTH = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN")   # without --sandbox the agent logs in as you


def agent_env(env, sandbox):
    """Allowlisted environment for an agent process: no password, no other credentials."""
    keys = list(ALLOW)
    if not sandbox:
        keys += list(ALLOW_AUTH)
        if os.name == "nt":
            keys += list(ALLOW_WIN)
    return {k: v for k, v in env.items() if k in keys or k.startswith("LC_") or (os.name == "nt" and k.upper() in keys)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--agent", default="claude", choices=["claude", "codex"])
    ap.add_argument("--model", default="")
    ap.add_argument("--s3-model", default="", help="stage-3 model (the small one); default: --model")
    ap.add_argument("--method", default="plain")
    ap.add_argument("--v2", action="store_true", help="stage 3 = T6 and T3 at the same time")
    ap.add_argument("--name", default="MIRA", help="T6 name (--v2)")
    ap.add_argument("--sandbox", action="store_true")
    ap.add_argument("--sandbox-check", action="store_true", help="only test the sandbox (no agent, no tokens), then exit")
    ap.add_argument("--timeout", type=int, default=30, help="minutes per agent turn")
    a = ap.parse_args()
    a.out = os.path.abspath(a.out)
    if a.sandbox_check:
        a.sandbox = True
    if a.sandbox:
        require_sandbox(a.out)
    os.makedirs(a.out, exist_ok=True)
    secret = os.environ.pop("VESPER_PART4_PW", "")     # read once; no child process inherits it
    env = dict(os.environ, VESPER_WS_HOME=os.path.join(a.out, "home"))
    if a.sandbox:
        env.update(sandbox_env(a.out, a.agent))
    if a.sandbox_check:
        os.makedirs(os.path.join(a.out, "home"), exist_ok=True)
        with open(os.path.join(a.out, "home", "registry.json"), "w") as f:
            f.write('{"runs": {}}')
        open(os.path.join(a.out, "e2e.log"), "a").close()
        run_dir = os.path.join(a.out, "home", "runs", "probe")
        os.makedirs(run_dir, exist_ok=True)
        print("sandbox ok:", sandbox_selfcheck(a.out, run_dir, env).strip()[:200])
        return

    def scrub(text):
        return str(text).replace(secret, "<password>") if secret else str(text)
    lock = threading.Lock()
    log = open(os.path.join(a.out, "e2e.log"), "a", encoding="utf-8")
    status = {"step": "", "claude_cost": {}, "ok": None}

    def put(**kw):
        with lock:
            status.update(kw)
            with open(os.path.join(a.out, "status.json"), "w") as f:
                json.dump(status, f, indent=1)

    def logw(text):
        with lock:
            log.write(text)
            log.flush()

    def ws(*args):
        r = subprocess.run([sys.executable, os.path.join(KIT, "workshop.py")] + list(args),
                           env=dict(env, PYTHONIOENCODING="utf-8"), capture_output=True, text=True, encoding="utf-8",
                           errors="replace", stdin=subprocess.DEVNULL)
        logw(scrub("$ workshop.py %s\n%s%s\n" % (" ".join(args), r.stdout, r.stderr)))
        if r.returncode:
            raise SystemExit(scrub("workshop.py %s failed: %s" % (args[0], r.stderr[-500:])))
        return scrub(r.stdout)

    def reg():
        with open(os.path.join(env["VESPER_WS_HOME"], "registry.json"), encoding="utf-8") as f:
            return json.load(f)

    def prompt_of(out):
        lines = out.splitlines()
        i = [k for k, l in enumerate(lines) if l.startswith("-" * 20)]
        return "\n".join(lines[i[0] + 1:i[1]])

    def agent(folder, prompt, resume=None, label="", model=""):
        if a.agent == "claude":
            cmd = ["claude", "-p", "--output-format", "json", "--permission-mode", "bypassPermissions"]
            cmd += ["--model", model] if model else []
            cmd += ["--resume", resume] if resume else []
            cmd += [prompt]
        else:
            m = ["-m", model] if model else []
            if resume:
                cmd = ["codex", "exec", "resume", resume, "--json", "--approve-for-me", "--skip-git-repo-check"] + m + [prompt]
            else:
                cmd = ["codex", "exec", "--json", "--approve-for-me", "--skip-git-repo-check", "-C", folder] + m + [prompt]
        if a.sandbox:
            cmd = bwrap_args(cmd, folder, env, extra_ro=[os.path.join(env["VESPER_WS_HOME"], ".guides")])
        put(step="agent " + label)
        t = time.time()
        r = subprocess.run(cmd, cwd=folder, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=a.timeout * 60, stdin=subprocess.DEVNULL, env=agent_env(env, a.sandbox))
        logw(scrub("[agent %s] %.0fs rc=%d\n%s\n%s\n" % (label, time.time() - t, r.returncode, r.stdout[-1500:], r.stderr[-800:])))
        if r.returncode:
            raise SystemExit("agent %s failed (rc=%d), see e2e.log" % (label, r.returncode))
        if a.agent == "claude":
            j = json.loads(r.stdout)
            with lock:
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
            with lock:
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
        if a.sandbox:
            sandbox_selfcheck(a.out, f1, env)
        sid = agent(f1, prompt_of(out), label="stage1", model=a.model)
        ws("done", "--no-form")
        out = ws("skill")
        agent(f1, prompt_of(out), resume=sid, label="stage2", model=a.model)
        ws("harvest", "--no-form", "--move-aside", "--remove-global")
        s3_model = a.s3_model or a.model
        if a.v2:
            jobs = []
            for task, extra in (("T6", ["--name", a.name]), ("T3", [])):
                out = ws("new", "s3", "--task", task, *extra)
                r = reg()
                rid3 = [x for x in r["active_runs"] if r["runs"][x]["task"] == task][0]
                jobs.append((task, rid3, r["runs"][rid3]["folder"], prompt_of(out)))
            with concurrent.futures.ThreadPoolExecutor(2) as ex:
                futs = [ex.submit(agent, f, p, None, "stage3-" + t, s3_model) for t, _, f, p in jobs]
                for fu in futs:
                    fu.result()
            for _, rid3, _, _ in jobs:
                ws("done", rid3, "--no-form")
            if reg()["runs"][jobs[0][1]].get("name") != t6font.normalise(a.name):
                raise SystemExit("the T6 run did not store the name %s" % t6font.normalise(a.name))
        else:
            out = ws("new", "s3", "--skill", "own")
            r = reg()
            s3 = r["active"]["run_id"]
            agent(r["runs"][s3]["folder"], prompt_of(out), label="stage3", model=s3_model)
            ws("done", "--no-form")
        if secret:
            ws("unlock", "4", secret)
            ws("grade", "--no-form")
        rows = list(reg()["rows"].values())
        if a.v2 and len(rows) != 4:
            raise SystemExit("expected 4 rows (stage 1, 2, 3 T6, 3 T3), got %d" % len(rows))
        put(step="finished", ok=True, rows=rows)
        logw(ws("show"))
    except BaseException as e:  # noqa: BLE001  (SystemExit too)
        put(ok=False, error=scrub(e))
        raise
    finally:
        open(os.path.join(a.out, "DONE"), "w").close()


if __name__ == "__main__":
    main()
