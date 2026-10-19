#!/usr/bin/env python3
"""workshop.py - run the VESPER-16 skill exercise cleanly and measure it.

  python workshop.py doctor                 check this computer (run it first)
  python workshop.py new s1                 stage 1: clean folder, prints the prompt
  python workshop.py done                   end stage 1 or 3: measure, grade, form
  python workshop.py skill                  stage 2: prints the skill-writing prompt (same thread)
  python workshop.py harvest                end stage 2: take the skill out, check it
  python workshop.py new s3 --skill own     stage 3: clean folder with your skill
  python workshop.py unlock 4 <password>    grader (only after the agent is done)
  python workshop.py grade | show | cleanup

The tool never talks to an agent: you paste every prompt. It sends nothing over the network; it only
opens the results form in your browser. See README.md (Workshop), MANUAL.md and HOMEWORK.md.
"""
import argparse, csv, hashlib, io, json, os, random, re, shutil, subprocess, sys, tempfile, time, webbrowser, zipfile
from urllib.parse import urlencode

KIT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, KIT)
import measure as M  # noqa: E402  (session readers and prices, same folder)

PRICE_TABLE = "2026-10-14"
METHODS = ["builtin", "superpowers", "plain"]
PART_DEST = {"2": ".wiki", "3": ".prebuilt", "4": ".grader"}
ROW_FIELDS = ["alias", "run_id", "stage", "revision", "parent_run_id", "task", "agent", "model", "method",
              "skill_source", "skill_hash", "skill_has_solution", "elapsed_min", "wall_min", "emulator_runs",
              "tok_uncached", "tok_cache_read", "tok_cache_write", "tok_out", "cost_usd", "price_table",
              "measurement", "score", "grading", "solution_sha", "cutoff", "start"]
LINE = "-" * 72


# ------------------------------------------------------------------ paths and registry
def ws_home(check=False):
    h = os.environ.get("VESPER_WS_HOME")
    if not h:
        base = os.environ.get("LOCALAPPDATA") if os.name == "nt" else os.path.expanduser("~")
        h = os.path.join(base or os.path.expanduser("~"), "vesper-runs")
    if check and "onedrive" in h.lower():
        sys.exit("The workshop home %s is on OneDrive. Set VESPER_WS_HOME to a local folder." % h)
    return h


def user_home():
    return os.environ.get("VESPER_WS_USERHOME") or os.path.expanduser("~")


def replace_file(src, dst, tries=20):
    """os.replace with retries: on Windows, antivirus or the indexer can hold a new file for a moment."""
    for i in range(tries):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if i == tries - 1:
                raise
            time.sleep(0.1 * (i + 1))


def new_code():
    return "%04x" % random.randrange(0x10000)


class Registry:
    def __init__(self, data):
        self.data = data

    @classmethod
    def path(cls):
        return os.path.join(ws_home(), "registry.json")

    @classmethod
    def load(cls):
        try:
            with open(cls.path(), encoding="utf-8") as f:
                return cls(json.load(f))
        except (OSError, ValueError):
            return cls({"version": 1, "agent": "", "alias": "", "items": [], "runs": {}, "rows": {},
                        "active": None})

    def save(self):
        os.makedirs(ws_home(), exist_ok=True)
        tmp = self.path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=1)
        replace_file(tmp, self.path())

    def add_item(self, path, kind):
        if not any(i["path"] == path for i in self.data["items"]):
            self.data["items"].append({"path": path, "kind": kind, "status": "pending"})

    def mark_done(self, path):
        for i in self.data["items"]:
            if i["path"] == path:
                i["status"] = "done"

    def set_row(self, run_id, stage, fields):
        row = self.data["rows"].setdefault("%s|%s" % (run_id, stage), {k: "" for k in ROW_FIELDS})
        row.update({k: ("" if v is None else v) for k, v in fields.items() if k in ROW_FIELDS})
        row["run_id"], row["stage"] = run_id, stage

    def row(self, run_id, stage):
        return self.data["rows"].get("%s|%s" % (run_id, stage))

    def write_csv(self):
        p = os.path.join(ws_home(), "results.csv")
        with open(p + ".tmp", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=ROW_FIELDS)
            w.writeheader()
            for k in sorted(self.data["rows"]):
                w.writerow(self.data["rows"][k])
        replace_file(p + ".tmp", p)


def ask(prompt, default=""):
    if not sys.stdin or not sys.stdin.isatty():
        return default
    try:
        v = input(prompt).strip()
    except EOFError:
        return default
    return v or default


def rmtree(p):
    def onerr(func, path, _):          # git objects are read-only on Windows
        try:
            os.chmod(path, 0o700)
            func(path)
        except OSError:
            pass
    shutil.rmtree(p, onerror=onerr)


# ------------------------------------------------------------------ prompts
class _Keep(dict):
    def __missing__(self, k):
        return "{" + k + "}"


def render_prompt(name, **kw):
    with open(os.path.join(KIT, "prompts", name + ".md"), encoding="utf-8") as f:
        return f.read().format_map(_Keep(kw)).strip() + "\n"


def guides_dir():
    d = os.path.join(ws_home(), ".guides")
    if not os.path.isdir(d):
        shutil.copytree(os.path.join(KIT, "guides"), d)
    return d


# The "builtin" stage-2 method: each agent's own skill creator (fallback: the bundled Anthropic guide).
BUILTIN_HOW = {
    "codex": "use your built-in skill creator: $skill-creator.",
    "claude": ("use the skill-creator skill (the Claude Code plugin skill-creator@claude-plugins-official). "
               "If you do not have it, read and follow the guide at {guide}/anthropic-skill-creator/SKILL.md."),
    "cursor": ("use your built-in skill creator (/create-skill). If you do not have it, read and follow the "
               "guide at {guide}/anthropic-skill-creator/SKILL.md."),
}
BUILTIN_STEP = {
    "codex": "Codex: the prompt calls $skill-creator, Codex's built-in skill creator. Nothing to install.",
    "claude": ("Claude Code: install the built-in skill creator first (once), in the same session:\n"
               "         /plugin install skill-creator@claude-plugins-official\n"
               "     (If you cannot install plugins, the prompt points the agent to the bundled guide.)"),
    "cursor": ("Cursor: type /create-skill at the start of the message, then paste the prompt.\n"
               "     (Older Cursor without /create-skill: the prompt points the agent to the bundled guide.)"),
}


METHOD_DESC = {
    "builtin": "your agent's own built-in skill creator",
    "superpowers": "the superpowers 'writing-skills' guide",
    "plain": "a plain prompt, no guide",
}


def method_notice(method, when):
    """Tell the participant which skill-writing method they got, and that the room is split three ways."""
    print("\n  The room is split into 3 ways to write the skill in stage 2, chosen at random:")
    for m in METHODS:
        print("     %s %-12s %s" % ("->" if m == method else "  ", m.upper(), METHOD_DESC[m]))
    print("  You were selected for %s%s. At the end we compare the three methods." % (method.upper(), when))


def builtin_how(agent, guide):
    return BUILTIN_HOW.get(agent, BUILTIN_HOW["claude"]).replace("{guide}", guide)


def next_cmd(act):
    return {"1": "python workshop.py done", "2": "python workshop.py harvest",
            "3": "python workshop.py done"}[act["stage"]]


# ------------------------------------------------------------------ doctor
def vesper_bin():
    return os.path.join(KIT, "bin", "vesper.exe" if os.name == "nt" else "vesper")


def global_skill_dirs():
    h = user_home()
    return [os.path.join(h, ".codex", "skills"), os.path.join(h, ".agents", "skills"),
            os.path.join(h, ".claude", "skills"), os.path.join(h, ".cursor", "skills")]


def find_global_vesper_skills():
    out = []
    for d in global_skill_dirs():
        if not os.path.isdir(d):
            continue
        for n in sorted(os.listdir(d)):
            p = os.path.join(d, n)
            text = ""
            try:
                with open(os.path.join(p, "SKILL.md"), encoding="utf-8", errors="replace") as f:
                    text = f.read(4000).lower()
            except OSError:
                pass
            if "vesper" in n.lower() or "vesper-16" in text or "name: vesper" in text:
                out.append(p)
    return out


def cmd_doctor(a):
    reg = Registry.load()
    level, lines = 0, []

    def note(lvl, tag, msg):
        nonlocal level
        level = max(level, lvl)
        lines.append("  %-5s %s" % (tag, msg))
    if sys.version_info >= (3, 9):
        note(0, "OK", "Python %s" % sys.version.split()[0])
    else:
        note(2, "FAIL", "Python 3.9 or newer is needed")
    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True)
        note(0, "OK", "git")
    except (OSError, subprocess.CalledProcessError):
        note(2, "FAIL", "git is missing (install Git for Windows / your distribution's git)")
    try:
        r = subprocess.run([vesper_bin(), "--version"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20,
                           env=dict(os.environ, VESPER_NO_LOG="1"))
        if r.returncode == 0:
            note(0, "OK", "emulator: " + r.stdout.strip())
        else:
            note(2, "FAIL", "the emulator does not run")
    except (OSError, subprocess.TimeoutExpired) as e:
        note(2, "FAIL", "the emulator does not run (%s). Antivirus? See MANUAL.md" % e)
    h = ws_home()
    if "onedrive" in h.lower():
        note(2, "FAIL", "the workshop home is on OneDrive: %s (set VESPER_WS_HOME)" % h)
    else:
        note(0, "OK", "workshop home " + h)
    if "onedrive" in KIT.lower():
        note(1, "WARN", "the kit is on OneDrive; it works, but a local folder is faster")
    g = find_global_vesper_skills()
    if g:
        note(1, "WARN", "a VESPER skill is in a global folder (stage 3 would not be clean): " + ", ".join(g))
    else:
        note(0, "OK", "no VESPER skill in global skill folders")
    agent = a.agent or reg.data.get("agent") or ask("Which agent do you use (codex/claude/cursor)? [codex] ", "codex")
    alias = a.alias if a.alias is not None else (
        reg.data.get("alias") or ask("Alias for the shared chart (Enter = anonymous): ", ""))
    reg.data.update(agent=agent.lower(), alias=alias, doctor={"level": level, "time": time.time()})
    reg.add_item(h, "dir")
    reg.mark_done(h)
    reg.save()
    print("\n".join(lines))
    print(["GREEN: all good.", "YELLOW: it works - read the warnings.",
           "RED: follow MANUAL.md or work with a neighbour."][level])
    return level if level == 2 else 0


# ------------------------------------------------------------------ run folders
AGENTS_MD = "# Workshop run {run_id}\nThis folder is one isolated VESPER-16 workshop run.\n"
SKILL_NOTE = ("Skills are in .agents/skills/ (copies in .claude/skills/ and .cursor/skills/). "
              "Read vesper16/SKILL.md before you start.\n")


def git(folder, *args):
    subprocess.run(["git", "-c", "user.name=vesper", "-c", "user.email=vesper@local", "-c", "core.autocrlf=false"]
                   + list(args), cwd=folder, capture_output=True, check=True)


def make_run_folder(reg, run_id, task, skill_dir=None):
    f = os.path.join(ws_home(), run_id)
    reg.add_item(f, "dir")
    reg.save()
    if not os.path.isdir(os.path.join(f, ".git")):
        if os.path.isdir(f):
            rmtree(f)
        os.makedirs(os.path.join(f, "tasks"))
        shutil.copytree(os.path.join(KIT, "examples"), os.path.join(f, "examples"))
        # Only this system's binary: on Windows, Git Bash treats bin/vesper and bin/vesper.exe as one file,
        # so with vesper.exe alone `bin/vesper` works in Git Bash, PowerShell and cmd.
        os.makedirs(os.path.join(f, "bin"))
        shutil.copy2(vesper_bin(), os.path.join(f, "bin"))
        shutil.copy2(os.path.join(KIT, "player.html"), f)
        shutil.copy2(os.path.join(KIT, "tasks", task + ".md"), os.path.join(f, "tasks"))
        os.makedirs(os.path.join(f, "solutions"))
        open(os.path.join(f, "solutions", ".gitkeep"), "w").close()
        open(os.path.join(f, ".vesper-runs.log"), "w").close()
        note = AGENTS_MD.format(run_id=run_id) + (SKILL_NOTE if skill_dir else "")
        for n in ("AGENTS.md", "CLAUDE.md"):
            with open(os.path.join(f, n), "w", encoding="utf-8") as fh:
                fh.write(note)
        if skill_dir:
            for sub in (".agents", ".claude", ".cursor"):     # Codex, Claude Code, Cursor
                shutil.copytree(skill_dir, os.path.join(f, sub, "skills", "vesper16"))
        with open(os.path.join(f, ".gitignore"), "w") as fh:
            fh.write(".vesper-runs.log\nout/\n")
        git(f, "init", "-q")
        git(f, "add", "-A")
        git(f, "commit", "-q", "-m", "workshop run " + run_id)
    reg.mark_done(f)
    reg.save()
    return f


WIDE = "=" * 72


def banner(title):
    print("\n" + WIDE + "\n  " + title + "\n" + WIDE)


def prompt_block(prompt):
    print("\n" + "-" * 30 + " PROMPT " + "-" * 34)
    print(prompt.rstrip("\n"))
    print("-" * 27 + " END OF PROMPT " + "-" * 30)


def next_box(cmd, when):
    print("\n+" + "-" * 70 + "+")
    print("|  NEXT: " + when.ljust(62) + "|")
    print("|        " + cmd.ljust(62) + "|")
    print("+" + "-" * 70 + "+\n")


def print_prompt(folder, prompt, then):
    print("\n  1. Open this folder as a NEW project in your agent (nothing else):")
    print("\n       %s" % folder)
    print("\n  2. Start a NEW thread. Copy everything between the PROMPT lines and send it.")
    prompt_block(prompt)
    print("\n  3. Wait until the agent says it is done. Do not ask it anything else in this thread.")
    next_box("python workshop.py done", then)


def cmd_new(a):
    ws_home(check=True)
    reg = Registry.load()
    if not reg.data.get("doctor"):
        print("doctor was not run - running it now.\n")
        if cmd_doctor(argparse.Namespace(agent=None, alias=None)):
            sys.exit("Fix the FAIL lines first, or follow MANUAL.md.")
        reg = Registry.load()
    act = reg.data.get("active")
    if act:
        sys.exit("Stage %s of %s is still active. Next:  %s" % (act["stage"], act["run_id"], next_cmd(act)))
    task = a.task
    if a.stage == "s1":
        method = a.method if a.method != "random" else random.choice(METHODS)
        code = new_code()
        rid = "s1-" + code
        reg.data["runs"][rid] = dict(folder="", task=task, method=method, code=code, stage="1", parent="",
                                     skill_source="none", skill_hash="", skill_has_solution="", session=None)
        f = make_run_folder(reg, rid, task)
        prompt = render_prompt("stage1", task=task, run_id=rid)
        banner("STAGE 1 - the agent with NO skill        run %s" % rid)
        method_notice(method, " (used in stage 2)")
    else:
        g = find_global_vesper_skills()
        if g:
            sys.exit("A VESPER skill is in a global folder, so stage 3 would not be clean:\n  " + "\n  ".join(g)
                     + "\nMove it away (or run harvest / cleanup), then run this command again.")
        src, parent, sh, shs = resolve_skill(reg, a.skill)
        code = new_code()
        rid = "s3-" + code
        reg.data["runs"][rid] = dict(folder="", task=task, method=reg.data["runs"].get(parent, {}).get("method", ""), code=code, stage="3",
                                     parent=parent,
                                     skill_source=a.skill if a.skill in ("own", "wiki") else "path",
                                     skill_hash=sh, skill_has_solution=shs, session=None)
        f = make_run_folder(reg, rid, task, skill_dir=src)
        prompt = render_prompt("stage3", task=task, run_id=rid)
        banner("STAGE 3 - a NEW agent WITH the skill (%s)        run %s" % (a.skill, rid))
    reg.data["runs"][rid]["folder"] = f
    reg.data["active"] = {"run_id": rid, "stage": "1" if a.stage == "s1" else "3", "start": time.time()}
    reg.save()
    print_prompt(f, prompt, "when the agent says it is done, run:")
    return 0


# ------------------------------------------------------------------ measurement
def _log_files():
    out = []
    for root in (os.path.join(M.codex_home(), "sessions"), os.path.join(M.codex_home(), "archived_sessions"),
                 os.path.join(M.claude_home(), "projects")):
        for dp, _, fs in os.walk(root):
            out += [os.path.join(dp, n) for n in fs if n.endswith(".jsonl")]
    return out


def find_sessions(run_id):
    key, seen, out = run_id.encode(), set(), []
    codex_root = os.path.abspath(M.codex_home())
    for p in _log_files():
        try:
            if os.path.getsize(p) > 200 * 2 ** 20:
                continue
            with open(p, "rb") as f:
                if key not in f.read():
                    continue
        except OSError:
            continue
        if os.path.abspath(p).startswith(codex_root):
            m = re.search(r"([0-9a-f]{4,}(?:-[0-9a-f]{4,})+)\.jsonl$", os.path.basename(p))
            agent, sid = "codex", (m.group(1) if m else os.path.basename(p)[:-6])
        else:
            agent = "claude"
            parent = os.path.dirname(p)
            sid = (os.path.basename(os.path.dirname(parent)) if os.path.basename(parent) == "subagents"
                   else os.path.basename(p)[:-6])
        if (agent, sid) not in seen:
            seen.add((agent, sid))
            out.append({"agent": agent, "sid": sid, "path": p})
    return out


def _runlog_times(folder, t0, t1, only_run):
    out = []
    try:
        with open(os.path.join(folder, ".vesper-runs.log"), encoding="utf-8", errors="replace") as f:
            for line in f:
                parts = line.split()
                try:
                    ts = float(parts[0])
                except (ValueError, IndexError):
                    continue
                if int(t0) <= ts <= t1 + 1 and (not only_run or (len(parts) > 1 and parts[1] == "run")):
                    out.append(ts)
    except OSError:
        return None
    return out


def count_runs(folder, t0, t1):
    t = _runlog_times(folder, t0, t1, True)
    return None if t is None else len(t)


def measure_stage(run, t0, t1):
    s = run.get("session") or {}
    res = {"agent": s.get("agent", ""), "model": "", "tok_uncached": "", "tok_cache_read": "",
           "tok_cache_write": "", "tok_out": "", "cost_usd": "", "measurement": ""}
    found = []
    if s.get("agent") == "codex":
        found = M.codex_sessions(t0, t1, s["sid"])
    elif s.get("agent") == "claude":
        found = M.claude_sessions(t0, t1, s["sid"])
    acts = _runlog_times(run["folder"], t0, t1, False) or []
    if found:
        tot = {"i": 0, "cr": 0, "cw": 0, "o": 0}
        models = set()
        for c in found:
            for k in tot:
                tot[k] += c["tot"].get(k, 0)
            models |= c["models"]
            acts += [x for x in (c["first"], c["last"]) if x]
        c = M.cost(tot, models)
        res.update(model=" ".join(sorted(models)), tok_uncached=tot["i"], tok_cache_read=tot["cr"],
                   tok_cache_write=tot["cw"], tok_out=tot["o"], cost_usd=("%.2f" % c) if c is not None else "",
                   measurement="log" if s["agent"] == "codex" else "log, output lower bound")
    res["elapsed_min"] = ("%.1f" % ((max(acts) - min(acts)) / 60)) if len(acts) >= 2 else ""
    return res


def session_cwd(path):
    """The working folder recorded in an agent log (Codex session_meta / Claude message lines)."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f):
                if i > 400:
                    break
                if '"cwd"' not in line:
                    continue
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                c = d.get("cwd") or (d.get("payload") or {}).get("cwd")
                if c:
                    return c
    except OSError:
        pass
    return ""


def _same_dir(a, b):
    return bool(a and b) and os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def pick_session(run_id, folder=None):
    s = find_sessions(run_id)
    if len(s) > 1 and folder:                     # a pasted run code elsewhere must not count
        own = [x for x in s if _same_dir(session_cwd(x["path"]), folder)]
        if own:
            s = own
    if len(s) == 1:
        return s[0]
    if len(s) > 1:
        print("Several agent sessions contain %s:" % run_id)
        for i, x in enumerate(s):
            print("  %d) %s %s  %s" % (i + 1, x["agent"], x["sid"], x["path"]))
        n = ask("Which one is this run? [1]: ", "1")
        try:
            return s[int(n) - 1]
        except (ValueError, IndexError):
            return s[0]
    return None


# ------------------------------------------------------------------ grading, form, frames
def load_config():
    try:
        with open(os.path.join(KIT, "workshop_config.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"form_url": "", "fields": {}}


def form_link(row, cfg=None):
    cfg = cfg or load_config()
    if not cfg.get("form_url"):
        return None
    q = urlencode({fid: row.get(k, "") for k, fid in cfg.get("fields", {}).items()})
    return cfg["form_url"] + ("&" if "?" in cfg["form_url"] else "?") + q


def submit(row, a):
    cfg = load_config()
    fields = list(cfg.get("fields", {}))
    if not cfg.get("form_url"):
        print("\nRow for the shared sheet (tab-separated):\n" + "\t".join(str(row.get(k, "")) for k in ROW_FIELDS))
        return
    short = cfg.get("short_url") or cfg["form_url"]
    print("\n  RESULTS FORM:  %s" % short)
    print("  Answers (question number. name: value):\n")
    for i, k in enumerate(fields, 1):
        print("  %2d. %-19s %s" % (i, k + ":", row.get(k, "")))
    if getattr(a, "no_form", False):
        return
    again = "python workshop.py form %s %s" % (row.get("run_id", ""), row.get("stage", ""))
    if webbrowser.open(form_link(row, cfg)):
        print("\n  The form opens in a NEW browser window, with these values filled in.")
        print("  Check them and click Submit.")
    else:
        print("\n  The browser did not open. Open the link above, type the values, and click Submit.")
    print("  Window closed by mistake? Open it again:  %s" % again)


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def snap_path(run_id, stage):
    return os.path.join(ws_home(), ".snapshots", "%s-%s.vsa" % (run_id, stage))


def snapshot_solution(run_id, run, stage):
    src = os.path.join(run["folder"], "solutions", run["task"] + ".vsa")
    if not os.path.exists(src):
        return None, ""
    dst = snap_path(run_id, stage)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)
    return dst, sha256_file(dst)


def grader_path():
    return os.path.join(ws_home(), ".grader", "grader", "grade.py")


def grade_snapshot(task, path):
    if not os.path.exists(grader_path()):
        return "", "ungraded"
    if not path:
        return "0", "graded"
    try:
        r = subprocess.run([sys.executable, grader_path(), task, path, "--bin", vesper_bin()],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300, env=dict(os.environ, VESPER_NO_LOG="1"))
        return str(json.loads(r.stdout)["score"]), "graded"
    except Exception as e:  # noqa: BLE001
        print("grading failed: %s" % e)
        return "", "ungraded"


def ascii_frame(path, frame=300):
    if not path or not os.path.exists(path):
        return ""
    d = tempfile.mkdtemp()
    dump = os.path.join(d, "f.raw")
    try:
        subprocess.run([vesper_bin(), "run", path, "--frames", str(frame + 1), "--dump", dump],
                       capture_output=True, timeout=60, env=dict(os.environ, VESPER_NO_LOG="1"))
        with open(dump, "rb") as f:
            fr = f.read()[-3072:]
        if len(fr) < 3072:
            return ""
        rows = ["".join("#" if (fr[y * 64 + x] or fr[(y + 1) * 64 + x]) else " " for x in range(64))
                for y in range(0, 48, 2)]
        return "Frame %d of your game:\n+%s+\n%s\n+%s+" % (
            frame, "-" * 64, "\n".join("|" + r + "|" for r in rows), "-" * 64)
    except Exception:  # noqa: BLE001
        return ""
    finally:
        shutil.rmtree(d, ignore_errors=True)


def show_rows(rows):
    cols = [("run_id", 9), ("stage", 5), ("task", 4), ("model", 18), ("elapsed_min", 7), ("emulator_runs", 6),
            ("tok_in", 9), ("tok_out", 8), ("cost_usd", 7), ("score", 6), ("grading", 9)]
    print("  ".join(n.ljust(w) for n, w in cols))
    for r in rows:
        tin = sum(int(r.get(k) or 0) for k in ("tok_uncached", "tok_cache_read", "tok_cache_write")
                  if str(r.get(k, "")).isdigit())
        v = dict(r, tok_in=M.fmt_k(tin) if tin else "", tok_out=M.fmt_k(int(r["tok_out"])) if str(r.get("tok_out", "")).isdigit() else "")
        print("  ".join(str(v.get(n, ""))[:w].ljust(w) for n, w in cols))


def finish_stage(reg, rid, stage, a, grade=True):
    run = reg.data["runs"][rid]
    act = reg.data.get("active")
    first = bool(act and act["run_id"] == rid and act["stage"] == stage)
    row = reg.row(rid, stage)
    if first:
        t0, t1 = act["start"], time.time()
    else:
        t0, t1 = float(row["start"]), float(row["cutoff"])
    if not run.get("session"):
        run["session"] = pick_session(rid, run["folder"])
    m = measure_stage(run, t0, t1)
    if not m["measurement"]:
        prev = row or {}
        if prev.get("measurement") == "manual":
            m.update({k: prev[k] for k in ("model", "tok_uncached", "tok_out", "cost_usd", "measurement")})
        else:
            print("No agent log contains %s (Cursor or another agent?). "
                  "Type the numbers from the agent's usage screen (Enter = skip)." % rid)
            ti = ask("  input tokens: ", "").replace(",", "")
            to = ask("  output tokens: ", "").replace(",", "")
            model = ask("  model: ", "")
            if ti or to:
                tot = {"i": int(ti or 0), "cr": 0, "cw": 0, "o": int(to or 0)}
                c = M.cost(tot, {model} if model else set())
                m.update(tok_uncached=tot["i"], tok_out=tot["o"], model=model, measurement="manual",
                         cost_usd=("%.2f" % c) if c is not None else "")
            else:
                m["measurement"] = "none"
    agent = m.pop("agent") or reg.data.get("agent", "")
    fields = dict(m)
    runs = count_runs(run["folder"], t0, t1)
    fields.update(alias=reg.data.get("alias", ""), task=run["task"], agent=agent, method=run["method"],
                  parent_run_id=run["parent"], skill_source=run["skill_source"], skill_hash=run["skill_hash"],
                  skill_has_solution=run["skill_has_solution"], price_table=PRICE_TABLE,
                  start="%.0f" % t0, cutoff="%.0f" % t1, wall_min="%.1f" % ((t1 - t0) / 60),
                  emulator_runs="unknown" if runs is None else runs)
    if first:
        fields["revision"] = 1
        if grade:
            snap, sha = snapshot_solution(rid, run, stage)
            fields["solution_sha"] = sha
            score, status = grade_snapshot(run["task"], snap)
            fields.update(score=score, grading="partial" if getattr(a, "partial", False) else status)
        else:
            fields.update(score="", grading="none")
        reg.data["active"] = None
    else:
        fields["revision"] = int(row.get("revision") or 1) + 1
    reg.set_row(rid, stage, fields)
    reg.save()
    reg.write_csv()
    return reg.row(rid, stage)


def cmd_done(a):
    reg = Registry.load()
    act = reg.data.get("active")
    if act and act["stage"] == "2":
        sys.exit("Stage 2 ends with:  python workshop.py harvest")
    if act:
        rid, stage = act["run_id"], act["stage"]
    else:
        rows = [r for r in reg.data["rows"].values() if r["stage"] in ("1", "3")]
        if not rows:
            sys.exit("No stage is active. Start with:  python workshop.py new s1")
        last = max(rows, key=lambda r: float(r["cutoff"] or 0))
        rid, stage = last["run_id"], last["stage"]
        print("Updating the finished stage %s of %s (same cutoff, same frozen solution)." % (stage, rid))
    row = finish_stage(reg, rid, stage, a)
    banner("STAGE %s FINISHED        run %s" % (stage, rid))
    print()
    show_rows([row])
    print(ascii_frame(snap_path(rid, stage)))
    if row["grading"] == "ungraded":
        print("\nNot graded yet. After the agent is done:  python workshop.py unlock 4 <password>  "
              "then  python workshop.py grade")
    submit(row, a)
    if stage == "1":
        next_box("python workshop.py skill", "stage 2 (the SAME agent thread writes a skill), run:")
    return 0


def cmd_grade(a):
    reg = Registry.load()
    todo = [r for r in reg.data["rows"].values() if r["grading"] == "ungraded"]
    if not todo:
        print("Nothing to grade.")
        return 0
    if not os.path.exists(grader_path()):
        sys.exit("The grader is locked:  python workshop.py unlock 4 <password>")
    for r in todo:
        snap = snap_path(r["run_id"], r["stage"])
        score, status = grade_snapshot(r["task"], snap if os.path.exists(snap) else None)
        reg.set_row(r["run_id"], r["stage"], {"score": score, "grading": status,
                                              "revision": int(r["revision"] or 1) + 1})
        reg.save()
        reg.write_csv()
        print("%s stage %s: score %s" % (r["run_id"], r["stage"], score))
        submit(reg.row(r["run_id"], r["stage"]), a)
    return 0


# ------------------------------------------------------------------ stage 2: skill and harvest
def skill_hash(d):
    h = hashlib.sha256()
    for dp, dns, fs in sorted(os.walk(d)):
        dns.sort()
        for n in sorted(fs):
            p = os.path.join(dp, n)
            h.update(os.path.relpath(p, d).replace("\\", "/").encode() + b"\0")
            with open(p, "rb") as f:
                h.update(f.read())
    return h.hexdigest()[:16]


def _norm_lines(text):
    return {re.sub(r"\s+", " ", ln.strip()) for ln in text.splitlines() if ln.strip()}


GAME_SHARE = 0.5   # the skill holds at least this part of the stage-1 game -> "the finished game"


def detect_solution(skill_dir, snapshot):
    """Return (found, share). found: [(rel, reason)]. share: part of the stage-1 game lines in the skill."""
    found, sol, seen = [], set(), set()
    if snapshot and os.path.exists(snapshot):
        with open(snapshot, encoding="utf-8", errors="replace") as f:
            sol = _norm_lines(f.read())
    for dp, _, fs in os.walk(skill_dir):
        for n in sorted(fs):
            p = os.path.join(dp, n)
            rel = os.path.relpath(p, skill_dir)
            try:
                with open(p, encoding="utf-8", errors="replace") as f:
                    text = f.read()
            except OSError:
                continue
            lines = _norm_lines(text)
            common = lines & sol
            seen |= common
            why = []
            if n.lower().endswith(".vsa"):
                why.append("assembly program (.vsa)")
            else:
                for block in re.findall(r"```[^\n]*\n(.*?)```", text, re.S):
                    k = len(block.strip().splitlines())
                    if k > 15:
                        why.append("code block of %d lines" % k)
                        break
            if sol and lines and len(common) / len(lines | sol) >= 0.25:
                why.append("overlaps the stage-1 solution")
            if why:
                if sol:
                    why.append("%d of its %d lines are in your game" % (len(common), len(lines)))
                found.append((rel, ", ".join(why)))
    return found, (len(seen) / len(sol) if sol else 0.0)


def cmd_skill(a):
    reg = Registry.load()
    act = reg.data.get("active")
    again = bool(act and act["stage"] == "2")      # run again during stage 2: show the prompt again
    if act and not again:
        sys.exit("Stage %s of %s is still active. Next:  %s" % (act["stage"], act["run_id"], next_cmd(act)))
    s1 = [r for r in reg.data["rows"].values() if r["stage"] == "1"]
    if not s1:
        sys.exit("Do stage 1 first:  python workshop.py new s1")
    rid = act["run_id"] if again else max(s1, key=lambda r: float(r["cutoff"] or 0))["run_id"]
    if reg.row(rid, "2"):
        sys.exit("Stage 2 of %s is already done. Next:  python workshop.py new s3 --skill own" % rid)
    run = reg.data["runs"][rid]
    if again:
        print("\n  Stage 2 is already running (the clock started at the first 'skill'). Here is the prompt again.")
    else:
        reg.data["active"] = {"run_id": rid, "stage": "2", "start": time.time()}
        reg.save()
    guide = guides_dir().replace("\\", "/")
    prompt = render_prompt("stage2-" + run["method"], run_id=rid, guide=guide,
                           builtin_how=builtin_how(reg.data.get("agent", ""), guide))
    banner("STAGE 2 - the SAME agent writes a skill        run %s" % rid)
    method_notice(run["method"], "")
    print("\n  1. Go back to the SAME thread as stage 1 (project %s)." % os.path.basename(run["folder"]))
    if run["method"] == "builtin":
        print("\n  2. " + BUILTIN_STEP.get(reg.data.get("agent", ""), BUILTIN_STEP["claude"]))
    else:
        print("\n  2. The prompt names the guide the agent must follow (%s)." % run["method"])
    print("\n  3. Copy everything between the PROMPT lines and send it.")
    prompt_block(prompt)
    print("\n  4. Wait until the agent says the skill is written.")
    next_box("python workshop.py harvest", "when the skill is written, run:")
    return 0


def cmd_harvest(a):
    reg = Registry.load()
    act = reg.data.get("active")
    if not act or act["stage"] != "2":
        done2 = [r for r in reg.data["rows"].values() if r["stage"] == "2"]
        if done2:
            rid = max(done2, key=lambda r: float(r["cutoff"] or 0))["run_id"]
            sys.exit("Stage 2 of %s is already harvested.\n"
                     "  Form again:  python workshop.py form %s 2\n"
                     "  Next:        %s" % (rid, rid, next_cmd(act) if act else "python workshop.py new s3 --skill own"))
        sys.exit("harvest ends stage 2. Start stage 2 with:  python workshop.py skill")
    rid = act["run_id"]
    run = reg.data["runs"][rid]
    src = os.path.join(run["folder"], "skill-out", "vesper16")
    if not os.path.exists(os.path.join(src, "SKILL.md")):
        g = find_global_vesper_skills()
        sys.exit("No skill at %s\n%sAsk the agent to write it there, then run harvest again."
                 % (os.path.join(src, "SKILL.md"), ("It may be in a global folder: %s\n" % ", ".join(g)) if g else ""))
    base = os.path.join(ws_home(), ".skills", rid)
    dst = os.path.join(base, "vesper16")
    reg.add_item(base, "dir")
    reg.save()
    if os.path.exists(dst):
        rmtree(dst)
    shutil.copytree(src, dst)
    found, share = detect_solution(dst, snap_path(rid, "1"))
    # Record only: line overlap cannot tell a helper from a cached answer, so the learner is not asked.
    # The percentage goes to the form for the debrief; --move-aside is for the instructor.
    status = "%d%%" % round(share * 100)
    if found:
        if a.move_aside:
            rem = os.path.join(base, "removed")
            for rel, _ in found:
                p = os.path.join(dst, rel)
                if os.path.exists(p):
                    os.makedirs(os.path.dirname(os.path.join(rem, rel)), exist_ok=True)
                    shutil.move(p, os.path.join(rem, rel))
            status = "removed"
            print("\n  Moved aside to: %s" % rem)
    run["skill_hash"] = skill_hash(dst)
    run["skill_has_solution"] = status
    reg.mark_done(base)
    row = finish_stage(reg, rid, "2", a, grade=False)
    g = find_global_vesper_skills()
    if g:
        banner("CHECK - a VESPER skill is in a global folder")
        print("\n  It would leak into stage 3:\n\n    " + "\n    ".join(g) + "\n")
        if a.remove_global or ask("  Remove these global copies? [y/N] ", "n").lower() == "y":
            for p in g:
                if not os.path.islink(p):
                    rmtree(p)
    banner("STAGE 2 FINISHED - skill harvested        run %s" % rid)
    print()
    show_rows([row])
    print("\n  Skill:                    %s" % dst)
    print("  Stage-1 game code in skill: %s  (recorded for the debrief, nothing to do)" % status)
    submit(row, a)
    next_box("python workshop.py new s3 --skill own", "stage 3 (a NEW agent, NEW project), run:")
    return 0


def resolve_skill(reg, name):
    if name == "own":
        rows = [r for r in reg.data["rows"].values() if r["stage"] == "2"]
        if not rows:
            sys.exit("No harvested skill yet. Do stage 2:  python workshop.py skill  then  harvest")
        rid = max(rows, key=lambda r: float(r["cutoff"] or 0))["run_id"]
        run = reg.data["runs"][rid]
        return os.path.join(ws_home(), ".skills", rid, "vesper16"), rid, run["skill_hash"], run["skill_has_solution"]
    if name == "wiki":
        d = os.path.join(ws_home(), ".prebuilt", "skills", "M4-distill")
        if not os.path.isdir(d):
            sys.exit("The wiki skill is in locked part 3:  python workshop.py unlock 3 <password>")
        return d, "", skill_hash(d), "no"
    if not os.path.exists(os.path.join(name, "SKILL.md")):
        sys.exit("No SKILL.md in " + name)
    return os.path.abspath(name), "", skill_hash(name), ""


# ------------------------------------------------------------------ unlock, show, cleanup, shadow
def cmd_unlock(a):
    src = os.path.join(KIT, "locked", "part-%s.zip" % a.part)
    if a.part not in PART_DEST or not os.path.exists(src):
        sys.exit("There is no locked part %s." % a.part)
    try:
        with zipfile.ZipFile(src) as z:
            payload = z.read("payload.zip", pwd=a.password.encode())
    except (RuntimeError, zipfile.BadZipFile, KeyError):
        print("Wrong password.")
        sys.exit(2)
    reg = Registry.load()
    act = reg.data.get("active")
    if act and a.part == "4":
        print("Warning: stage %s is still active. Unlock the grader only after the agent is done." % act["stage"])
        if ask("Unlock anyway? [y/N] ", "n").lower() != "y":
            return 1
    dst = os.path.join(ws_home(), PART_DEST[a.part])
    reg.add_item(dst, "dir")
    reg.save()
    with zipfile.ZipFile(io.BytesIO(payload)) as z:
        z.extractall(dst)
    reg.mark_done(dst)
    reg.save()
    print("Unlocked part %s into %s (outside every run folder)." % (a.part, dst))
    return 0


def cmd_show(a):
    reg = Registry.load()
    rows = sorted(reg.data["rows"].values(), key=lambda r: (float(r["start"] or 0), r["stage"]))
    if not rows:
        print("No results yet.")
    else:
        show_rows(rows)
    act = reg.data.get("active")
    if act:
        print("\nActive: stage %s of %s. Next:  %s" % (act["stage"], act["run_id"], next_cmd(act)))
    print("\nWorkshop home: %s   results: %s" % (ws_home(), os.path.join(ws_home(), "results.csv")))
    return 0


def cmd_form(a):
    reg = Registry.load()
    rows = [r for r in reg.data["rows"].values()
            if (not a.run_id or r["run_id"] == a.run_id) and (not a.stage or r["stage"] == a.stage)]
    if not rows:
        sys.exit("No finished stage%s. See:  python workshop.py show"
                 % (" for %s %s" % (a.run_id, a.stage or "") if a.run_id else ""))
    row = max(rows, key=lambda r: float(r["cutoff"] or 0))
    print("\n  Form for run %s, stage %s:" % (row["run_id"], row["stage"]))
    submit(row, a)
    return 0


def _remove(p):
    if os.path.isdir(p):
        rmtree(p)
    elif os.path.exists(p):
        os.remove(p)


def cmd_cleanup(a):
    reg = Registry.load()
    home = os.path.abspath(ws_home())
    items = [i for i in reg.data["items"] if os.path.abspath(i["path"]) != home]
    print("workshop.py made these items:")
    for i in items:
        print("  [%s] %s" % (i["status"], i["path"]))
    print("  and its own files in %s" % home)
    if not a.no_copy and os.path.exists(os.path.join(home, "results.csv")):
        if a.yes or ask("Copy results.csv to %s first? [Y/n] " % os.getcwd(), "y").lower() != "n":
            shutil.copy2(os.path.join(home, "results.csv"), os.path.join(os.getcwd(), "vesper-results.csv"))
            print("Saved vesper-results.csv")
    if not (a.yes or ask("Delete all of these? [y/N] ", "n").lower() == "y"):
        print("Nothing deleted.")
        return 0
    for i in items:
        p = os.path.abspath(i["path"])
        if not p.startswith(home + os.sep) or os.path.islink(p):
            print("  skipped (outside the workshop home, or a link): " + p)
            continue
        _remove(p)
    for n in ("registry.json", "registry.json.tmp", "results.csv", ".snapshots", ".guides"):
        _remove(os.path.join(home, n))
    try:
        os.rmdir(home)
    except OSError:
        if os.path.isdir(home):
            print("Left in %s (not made by workshop.py): %s" % (home, ", ".join(os.listdir(home))))
    g = find_global_vesper_skills()
    if g:
        print("VESPER skills in global folders (not made by workshop.py - an agent put them there?):\n  "
              + "\n  ".join(g))
        if a.yes or ask("Remove them too? [y/N] ", "n").lower() == "y":
            for p in g:
                if not os.path.islink(p):
                    rmtree(p)
    print("Cleanup done.")
    return 0


def cmd_shadow(a):
    """Presenter / home: run the same prompt headless with a (small) model. Starts a networked agent."""
    reg = Registry.load()
    agent = a.agent or reg.data.get("agent") or "claude"
    print("shadow starts %s with model %s, without a window. It uses your quota and the network." % (agent, a.model))
    if not (a.yes or ask("Continue? [y/N] ", "n").lower() == "y"):
        return 1
    code = new_code()
    rid = "%s-%s-shadow" % (a.stage, code)
    skill = resolve_skill(reg, "own")[0] if a.stage == "s3" else None
    reg.data["runs"][rid] = dict(folder="", task=a.task, method="", code=code, stage=a.stage[1], parent="",
                                 skill_source="own" if skill else "none", skill_hash="", skill_has_solution="",
                                 session=None)
    f = make_run_folder(reg, rid, a.task, skill_dir=skill)
    reg.data["runs"][rid]["folder"] = f
    prompt = render_prompt("stage3" if skill else "stage1", task=a.task, run_id=rid)
    if agent == "codex":
        cmd = ["codex", "exec", "--model", a.model, "--json", "--approve-for-me", "--skip-git-repo-check", "-C", f, prompt]
    else:
        cmd = ["claude", "-p", "--model", a.model, "--output-format", "json", "--permission-mode",
               "acceptEdits", "--allowedTools", "Bash,Read,Write,Edit,Glob,Grep", prompt]
    t0 = time.time()
    with open(os.path.join(f, "shadow.log"), "w", encoding="utf-8") as log:
        try:
            subprocess.run(cmd, cwd=f, stdout=log, stderr=subprocess.STDOUT, timeout=a.timeout * 60)
        except subprocess.TimeoutExpired:
            print("time limit reached")
        except OSError as e:
            sys.exit("cannot start %s: %s" % (cmd[0], e))
    reg.data["active"] = {"run_id": rid, "stage": a.stage[1] + "s", "start": t0}
    row = finish_stage(reg, rid, a.stage[1] + "s", a)
    show_rows([row])
    return 0


# ------------------------------------------------------------------ CLI
def parse(argv):
    ap = argparse.ArgumentParser(prog="workshop.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("doctor")
    s.add_argument("--agent", choices=["codex", "claude", "cursor", "other"])
    s.add_argument("--alias")
    s.set_defaults(func=cmd_doctor)
    s = sub.add_parser("new")
    s.add_argument("stage", choices=["s1", "s3"])
    s.add_argument("--task", default="T3", choices=["T3", "T4"])
    s.add_argument("--method", default="random", choices=["random"] + METHODS)
    s.add_argument("--skill", default="own", help="own | wiki | <folder with SKILL.md>")
    s.set_defaults(func=cmd_new)
    s = sub.add_parser("done")
    s.add_argument("--partial", action="store_true", help="the agent did not finish; grade what exists")
    s.add_argument("--no-form", action="store_true")
    s.set_defaults(func=cmd_done)
    s = sub.add_parser("skill")
    s.set_defaults(func=cmd_skill)
    s = sub.add_parser("harvest")
    s.add_argument("--no-form", action="store_true")
    s.add_argument("--move-aside", action="store_true")
    s.add_argument("--remove-global", action="store_true")
    s.set_defaults(func=cmd_harvest)
    s = sub.add_parser("grade")
    s.add_argument("--no-form", action="store_true")
    s.set_defaults(func=cmd_grade)
    s = sub.add_parser("unlock")
    s.add_argument("part")
    s.add_argument("password")
    s.set_defaults(func=cmd_unlock)
    s = sub.add_parser("show")
    s.set_defaults(func=cmd_show)
    s = sub.add_parser("form", help="open the results form again for a finished stage")
    s.add_argument("run_id", nargs="?", help="default: the last finished stage")
    s.add_argument("stage", nargs="?", choices=["1", "2", "3"])
    s.add_argument("--no-form", action="store_true")
    s.set_defaults(func=cmd_form)
    s = sub.add_parser("cleanup")
    s.add_argument("--yes", action="store_true")
    s.add_argument("--no-copy", action="store_true")
    s.set_defaults(func=cmd_cleanup)
    s = sub.add_parser("shadow")
    s.add_argument("--model", required=True)
    s.add_argument("--agent", choices=["codex", "claude"])
    s.add_argument("--stage", default="s1", choices=["s1", "s3"])
    s.add_argument("--task", default="T3", choices=["T3", "T4"])
    s.add_argument("--timeout", type=int, default=25, help="minutes")
    s.add_argument("--yes", action="store_true")
    s.add_argument("--no-form", action="store_true", default=True)
    s.set_defaults(func=cmd_shadow)
    return ap.parse_args(argv)


def main(argv=None):
    a = parse(sys.argv[1:] if argv is None else argv)
    sys.exit(a.func(a) or 0)


if __name__ == "__main__":
    main()
