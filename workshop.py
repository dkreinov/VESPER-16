#!/usr/bin/env python3
"""workshop.py - run the VESPER-16 skill exercise cleanly and measure it.

  python workshop.py doctor                 check this computer (run it first)
  python workshop.py new s1                 stage 1: clean folder, prints the prompt
  python workshop.py done [run_id]          end stage 1 or 3: measure, grade, form
  python workshop.py skill                  stage 2: prints the skill-writing prompt (same thread)
  python workshop.py harvest                end stage 2: take the skill out, check it
  python workshop.py new s3 --task all      stage 3, four runs in one command (default): T3 with the skill,
                                            T3 without (control), T6 with, T6 without (control)
  python workshop.py new s3 --task both     stage 3, two runs (T6, then T3) in one command
  python workshop.py new s3 --task T6       stage 3, run 1: T6 with your name, a NEW agent thread
  python workshop.py new s3 --task T3       stage 3, run 2: T3 again, a SECOND new agent thread
  python workshop.py new s3 --task all --auto   stage 3, the tool runs the 4 agents itself (about 10 min)
  python workshop.py doctor --check-auto    one tiny agent run: can --auto use the stage-3 model?
  python workshop.py unlock 4 <password from the slide>    grader (only after the agent is done)
  python workshop.py grade | show | cleanup

The tool never talks to an agent: you paste every prompt. It sends nothing over the network; it only
opens the results form in your browser. See README.md (Workshop), MANUAL.md and HOMEWORK.md.
"""
import argparse, csv, difflib, fnmatch, glob, hashlib, io, json, math, os, posixpath, random, re, shutil, subprocess, sys, tempfile, textwrap, time, webbrowser, zipfile
from urllib.parse import urlencode
import urllib.parse

KIT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, KIT)
import measure as M  # noqa: E402  (session readers and prices, same folder)
import t6font as T6F  # noqa: E402  (T6 name font, same folder; locked part 4 has a copy)

_VT = []


def _vt_ok():
    """Windows: switch on ANSI processing once. Any failure means colour off."""
    if not _VT:
        ok = True
        if os.name == "nt":
            try:
                import ctypes
                k = ctypes.windll.kernel32
                h = k.GetStdHandle(-11)
                mode = ctypes.c_uint32()
                ok = bool(k.GetConsoleMode(h, ctypes.byref(mode))) and \
                    bool(k.SetConsoleMode(h, mode.value | 0x0004))
            except Exception:
                ok = False
        _VT.append(ok)
    return _VT[0]


def use_color():
    if os.environ.get("FORCE_COLOR") == "1":
        _vt_ok()  # best effort; forced on even when stdout is a pipe
        return True
    return (sys.stdout.isatty() and "NO_COLOR" not in os.environ
            and os.environ.get("TERM") != "dumb" and _vt_ok())


def _sgr(code, text):
    return "\x1b[%sm%s\x1b[0m" % (code, text) if use_color() else text


def c_banner(t): return _sgr("1;36", t)
def c_next(t): return _sgr("1;33", t)
def c_ok(t): return _sgr("32", t)
def c_err(t): return _sgr("31", t)
def c_prompt(t): return _sgr("35", t)
def c_link(t): return _sgr("4", t)
def c_bold(t): return _sgr("1", t)
def c_good(t): return _sgr("1;32", t)


MAXW = 72                                          # no learner line is longer than this
_ESC_LINE = re.compile(r"^(\x1b\[[0-9;]*m)(.*)(\x1b\[0m)$")
_ATOM = re.compile(r"^\s*(?:[A-Za-z]:[\/]|/|~|\.{1,2}[\/]|python |bin/|https?:)")
import builtins  # noqa: E402
_builtin_print = builtins.print
# all_results data lines are copied by hand when the clipboard fails: never wrap them (a note can hold spaces)
_DATA_LINE = re.compile(r"(vesper-results\b|[a-z_]+=[^ ;]*;)")
_WRAP = [True]                                     # doctor text is copied into help prompts: not wrapped


def wrap_line(line, width=MAXW):
    """Wrap one line at word boundaries, same indent. Boxes, paths and commands stay as they are."""
    m = _ESC_LINE.match(line)
    if m:
        return [m.group(1) + x + m.group(3) for x in wrap_line(m.group(2), width)]
    if len(line) <= width or "\x1b" in line:
        return [line]
    body = line.lstrip(" ")
    if not body or body[0] in "|+=" or " " not in body or _ATOM.match(line) or _DATA_LINE.match(body):
        return [line]
    ind = line[:len(line) - len(body)]
    out, cur = [], ind
    for word in body.split(" "):
        if cur.strip() and len(cur) + 1 + len(word) > width:
            out.append(cur.rstrip())
            cur = ind + word
        else:
            cur = (cur + " " + word) if cur.strip() else cur + word
    out.append(cur.rstrip())
    return out


def print(*args, sep=" ", end="\n", file=None, flush=False):   # noqa: A001  (every learner line goes through here)
    text = sep.join(str(x) for x in args)
    if file is None and sep == " " and _WRAP[0]:
        text = "\n".join(y for x in text.split("\n") for y in wrap_line(x))
    _builtin_print(text, end=end, file=file, flush=flush)


def term_cols():
    return shutil.get_terminal_size().columns


def chunk_lines(chunks, indent=2, gap=3, width=MAXW):
    """Join short chunks with gaps into lines no longer than width."""
    lines, cur = [], ""
    for c in chunks:
        if cur and indent + len(cur) + gap + len(c) > width:
            lines.append(" " * indent + cur)
            cur = c
        else:
            cur = (cur + " " * gap + c) if cur else c
    if cur:
        lines.append(" " * indent + cur)
    return lines


def clear_screen():
    """Clear terminal when sys.stdout.isatty() is true and VESPER_NO_CLEAR is not set."""
    if not sys.stdout.isatty() or os.environ.get("VESPER_NO_CLEAR"):
        return
    if _vt_ok():
        sys.stdout.write("\x1b[2J\x1b[H")
        sys.stdout.flush()
    else:
        os.system("cls")


PRICE_TABLE = "2026-10-14"
METHODS = ["builtin", "superpowers", "plain"]
PART_DEST = {"2": ".wiki", "3": ".prebuilt", "4": ".grader"}
ROW_FIELDS = ["alias", "run_id", "stage", "revision", "parent_run_id", "task", "agent", "model", "method",
              "skill_source", "skill_hash", "skill_has_solution", "elapsed_min", "wall_min", "emulator_runs",
              "tok_uncached", "tok_cache_read", "tok_cache_write", "tok_out", "cost_usd", "price_table",
              "measurement", "score", "grading", "solution_sha", "cutoff", "start", "method_used", "memory_used", "effort",
              "model_switched", "settings_confirmed", "isolation", "isolation_note", "overrun", "stopped",
              "error_note"]
LINE = "-" * 72
T6_PASS = 90


def passed(row):
    """Pass mark: T6 passes with a score of 90 or more; T3 (and every other task) needs 100.
    No score (empty or not a number) is not a pass.
    charts.py has its own copy of this rule: keep both in sync."""
    try:
        sc = float(str((row or {}).get("score", "")).strip())
    except ValueError:
        return False
    return sc >= (T6_PASS if (row or {}).get("task") == "T6" else 100)


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
                reg = cls(json.load(f))
        except (OSError, ValueError):
            reg = cls({"version": 2, "agent": "", "alias": "", "items": [], "runs": {}, "rows": {},
                       "active": None, "active_runs": {}})
        reg._migrate()
        return reg

    def _migrate(self):
        """v1 registries have one 'active' object (or null); v2 keeps all active runs in 'active_runs'."""
        if not isinstance(self.data.get("active_runs"), dict):
            old = self.data.get("active")
            ok = isinstance(old, dict) and isinstance(old.get("run_id"), str)
            self.data["active_runs"] = {old["run_id"]: old} if ok else {}
        self._mirror()

    def _mirror(self):
        """'active' = the latest-started active run, for v1 readers (e2e_agent.py, old tests)."""
        acts = self.actives()
        self.data["active"] = acts[-1] if acts else None

    def actives(self, stage=None):
        acts = sorted(self.data["active_runs"].values(), key=lambda x: float(x["start"]))
        return [x for x in acts if stage is None or x["stage"] == stage]

    def get_active(self, run_id):
        return self.data["active_runs"].get(run_id)

    def start_active(self, run_id, stage, start=None):
        self.data["active_runs"][run_id] = {"run_id": run_id, "stage": stage,
                                            "start": time.time() if start is None else start}
        self._mirror()

    def end_active(self, run_id):
        self.data["active_runs"].pop(run_id, None)
        self._mirror()

    def save(self):
        self._mirror()
        self.data["version"] = 2
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
            w = csv.DictWriter(f, fieldnames=ROW_FIELDS, extrasaction="ignore")
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

SMALL_MODEL = {"claude": "Claude Code: Haiku (type /model haiku in the new thread)",
               "codex": "Codex: gpt-6-luna (choose it in the model menu of the new thread)",
               "cursor": "Cursor: its cheapest model (model menu of the new chat)"}
TIME_BOX_MIN = 10


def overrun_flag(stage, t0, t1):
    """'yes'/'no' for a stage-3 run over the time box; '' for stages 1 and 2 (the writer has 20 minutes).
    t0 is the time of the run's prompt in its log (prompt_time), or the folder-creation start when the log has none."""
    if str(stage) != "3":
        return ""
    return "yes" if t1 - t0 > TIME_BOX_MIN * 60 else "no"
S3_RUN_BUDGET = 6      # also written in prompts/stage3.md


def _codex_roots():
    roots = [os.path.join(user_home(), ".codex")]
    if os.environ.get("CODEX_HOME") and os.environ["CODEX_HOME"] not in roots:
        roots.append(os.environ["CODEX_HOME"])
    return roots


def codex_memories_on(reg=None):
    """True if Codex Memories look ON: config.toml [features] memories = true, a non-empty memories folder,
    or a stage-1/2 row of this learner with memory_used == yes. Read only."""
    for root in _codex_roots():
        try:
            sect = ""
            with open(os.path.join(root, "config.toml"), encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.split("#", 1)[0].strip()
                    if line.startswith("["):
                        sect = line.strip("[] ").lower()
                    elif sect == "features":
                        m = re.match(r"memories\s*=\s*(\w+)\s*$", line, re.I)
                        if m and m.group(1).lower() == "true":
                            return True
        except OSError:
            pass
        for dp, _, fns in os.walk(os.path.join(root, "memories")):
            if fns:
                return True
    if reg is not None:
        return any(r.get("stage") in ("1", "2") and r.get("memory_used") == "yes"
                   for r in reg.data["rows"].values())
    return False


def memories_card(reg):
    """Yellow card before stage 3 when Codex Memories are on. Prints nothing otherwise."""
    if (reg.data.get("agent") or "codex") != "codex" or not codex_memories_on(reg):
        return
    for l in ("Codex Memories are ON on this computer. Stage 3 must be a fresh agent with only the skill:",
              "   1. In EACH new stage-3 thread, type /memories first.",
              "   2. Turn off memories for this chat (do not use existing memories, do not save new ones).",
              "   3. Then paste the prompt.",
              "Your global setting does not change. (Claude Code: nothing to do; its memory is per project.)"):
        print(c_next("  " + l))


SMALL_SHORT = {"claude": "Haiku (/model haiku)", "codex": "gpt-6-luna, effort high",
               "cursor": "its cheapest model"}


def s3_header(reg, a, both, total=None):
    """Compact stage-3 header: title (+ T6 name), one steps paragraph, one wait line."""
    agent = reg.data.get("agent") or ""
    if total == 4:
        title = "STAGE 3 - four NEW agents (T3 and T6, each with and without the skill)"
    elif total == 3:
        title = "STAGE 3 - three NEW agents (T3 with skill, T3 without skill, T6 with skill)"
    else:
        title = "STAGE 3 - %s WITH your skill" % ("two NEW agents" if both else "a NEW agent")
    first = reg.data["runs"][a.s3_first]
    right = ("name on T6: " + first["name"]) if first.get("task") == "T6" and first.get("name") else ""
    print("\n" + c_banner(WIDE))
    if right and len(title) + 4 + len(right) <= 70:
        print(c_banner(("  " + title).ljust(70 - len(right)) + right))
    else:
        print("\n".join(c_banner(x) for x in wrap_line("  " + title, MAXW - 2)))
        if right:
            print(c_banner("  " + right))
    print(c_banner(WIDE))
    model = SMALL_SHORT.get(agent) or "; ".join("%s %s" % (k, v) for k, v in SMALL_SHORT.items())
    mem = codex_memories_on(reg) and agent in ("codex", "")
    chunks = ["new project from the folder", "-> new thread"] + (["-> /memories off"] if mem else []) \
        + ["-> model " + model, "-> paste its prompt.   %d runs each." % S3_RUN_BUDGET]
    lines, cur = [], ("For EACH run:" if both else "For this run:")
    for c in chunks:
        if len(cur) + 1 + len(c) > 70:
            lines.append(cur)
            cur = c
        else:
            cur += " " + c
    lines.append(cur)
    print("\n".join("  " + l for l in lines))
    if mem:
        print("  (Codex Memories are on: turn them off per thread with /memories)")
    if right and getattr(a, "name_from_alias", False):
        print("  (change: --name OTHER)")
    print("  Wait until the agent is done; do not ask it anything else.")
    print("  If an agent asks a question, reply: Make reasonable assumptions and continue.")
    print("  Time box %d min: stop any agent still working at %d min, then run its done line."
          % (TIME_BOX_MIN, TIME_BOX_MIN))


def s3_run_block(n, total, task, folder, prompt, desc=None):
    """One run: its title line with the full folder path, then the prompt between magenta lines."""
    desc = desc or {"T6": "T6 (new task)", "T3": "T3 (same task as stage 1)"}.get(task, task)
    of = " %d of %d" % (n, total) if total > 1 else ""
    num = " %d" % n if total > 1 else ""
    print("\n" + c_bold("  RUN%s  %s" % (of, desc)) + "\n  Folder:\n       " + folder)
    print(c_prompt((" PROMPT%s " % num).center(72, "-")))
    print(prompt.rstrip("\n"))
    print(c_prompt((" END OF PROMPT%s " % num).center(72, "-")))


def gate_on():
    """The confirmation gate runs only in an interactive terminal."""
    return bool(sys.stdout.isatty())


def run_page(reg, rid, head, folder, prompt, model_line, last, extra=None, mem=False):
    """One run as its own page (terminal only). Repeats the steps until the learner answers y."""
    while True:
        clear_screen()
        print("\n" + c_banner(WIDE) + "\n" + c_banner("  " + head) + "\n" + c_banner(WIDE))
        if extra:
            extra()
        print("\n  1. Open this folder as a NEW project in your agent (choose exactly this folder, not a folder above it):\n\n       %s" % folder)
        print("\n     Project name in the app: %s" % os.path.basename(os.path.normpath(folder)))
        print("\n  2. Start a NEW thread.")
        n = 3
        if mem:
            print("\n  3. " + c_next("/memories -> turn memory off for this chat."))
            n = 4
        print("\n  %d. Model: %s" % (n, model_line))
        if ask("\n  Done with these steps? [y/n]: ", "y").lower().startswith("y"):
            break
    reg.data["runs"][rid]["settings_confirmed"] = "yes"
    reg.save()
    prompt_block(prompt)
    print("\n  Paste it and send it.")
    if not last:
        ask("\n  Press Enter for the next run: ", "")


def s3_show(reg, rid, n, total, task, folder, prompt, desc=None, extra=None):
    """Show one stage-3 run: its own page in a terminal, else the plain block."""
    run = reg.data["runs"][rid]
    if run_mode(run) == "auto":                   # a failed --auto run that the learner now does by hand
        run["session"] = None
        for k in ("auto", "auto_model", "stopped", "error_note"):
            run.pop(k, None)
    if run.get("mode") != "manual":
        run["mode"] = "manual"                    # its page is shown: the learner runs it; --auto never relaunches it
        reg.save()
    if not gate_on():
        reg.data["runs"][rid]["settings_confirmed"] = "not_asked"     # no terminal, no gate: unconfirmed, not "no"
        reg.save()
        return s3_run_block(n, total, task, folder, prompt, desc=desc)
    agent = reg.data.get("agent") or ""
    model = SMALL_SHORT.get(agent) or "; ".join("%s %s" % (k, v) for k, v in SMALL_SHORT.items())
    desc = desc or {"T6": "T6 (new task)", "T3": "T3 (same task as stage 1)"}.get(task, task)
    nm = reg.data["runs"][rid].get("name", "")
    head = "STAGE 3 - RUN %d of %d  %s%s" % (n, total, desc, ("   name on T6: " + nm) if nm and task == "T6" else "")
    run_page(reg, rid, head, folder, prompt, model, n >= total, extra=extra,
             mem=codex_memories_on(reg) and agent in ("codex", ""))


def method_notice(method, when):
    """Tell the participant which skill-writing method they got, and that the room is split three ways."""
    print("\n  The room is split into 3 ways to write the skill in stage 2, chosen at random:")
    for m in METHODS:
        ln = "     %s %-12s %s" % ("->" if m == method else "  ", m.upper(), METHOD_DESC[m])
        print(c_bold(ln) if m == method else ln)
    print(c_bold("  You were selected for %s%s." % (method.upper(), when)) + " At the end we compare the three methods.")


def builtin_how(agent, guide):
    return BUILTIN_HOW.get(agent, BUILTIN_HOW["claude"]).replace("{guide}", guide)


def next_cmd(act):
    if act["stage"] == "2":
        return "python workshop.py harvest"
    if act["stage"] == "3":
        return "python workshop.py done " + act["run_id"]
    return "python workshop.py done"


def active_lines(reg):
    return ["Stage %s of %s (%s) is still active. Next:  %s"
            % (x["stage"], x["run_id"], reg.data["runs"].get(x["run_id"], {}).get("task", ""), next_cmd(x))
            for x in reg.actives()]


def choose_active(reg, acts):
    """Several stage-3 runs are active: ask which agent is done (no TTY: name the run)."""
    print("%d stage-3 runs are active:" % len(acts))
    for i, x in enumerate(acts, 1):
        print("  %d) %s  %s" % (i, x["run_id"], reg.data["runs"].get(x["run_id"], {}).get("task", "")))
    n = ask("Which agent is done? Type its number (Enter = cancel): ", "")
    if n.isdigit() and 1 <= int(n) <= len(acts):
        x = acts[int(n) - 1]
        return x["run_id"], x["stage"]
    sys.exit("Nothing finished. Name the run that is done:\n  " + "\n  ".join(next_cmd(x) for x in acts))


def is_control(run):
    return run.get("stage") == "3" and run.get("skill_source") == "none"


def s3_run_id(reg, parent, task):
    """s3-<stage-1 code>-<task>-<new code>: the form's run_id names the stage-1 parent (charts.py links them)."""
    pcode = parent.split("-", 1)[1] if parent.startswith("s1-") else "none"
    while True:
        rid = "s3-%s-%s-%s" % (pcode, task.lower(), new_code())
        if rid not in reg.data["runs"]:
            return rid


PAIR = {"T6": "T3", "T3": "T6"}


def second_s3_hint(reg, rid):
    """The command for the paired stage-3 task of the same parent, when it was not started yet."""
    run = reg.data["runs"][rid]
    other = PAIR.get(run["task"])
    if not other or not run["parent"] or is_control(run):
        return ""
    for r in reg.data["runs"].values():
        if r.get("stage") == "3" and r.get("parent") == run["parent"] and r.get("task") == other \
                and not is_control(r):
            return ""
    return "python workshop.py new s3 --task " + other


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


HELP_PROMPT = "Read doctor-report.txt and help me fix the setup. Do not change files outside this folder."
AGENT_CLIS = ["codex", "claude", "cursor-agent", "cursor"]
SP_SKILLS = ("using-superpowers", "brainstorming", "writing-plans", "subagent-driven-development")
CODEX_SP = re.compile(r'^\[plugins\."(superpowers@[^"]+)"\][^\n]*\n((?:(?!\[)[^\n]*(?:\n|$))*)', re.M)


def doctor_report_path():
    return os.environ.get("VESPER_DOCTOR_REPORT") or os.path.join(KIT, "doctor-report.txt")


def cli_version(name):
    p = shutil.which(name)
    if not p:
        return "not found"
    if os.environ.get("VESPER_DOCTOR_SKIP_CLI"):
        return "skipped"
    try:
        r = subprocess.run([p, "--version"], capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=15)
        text = (r.stdout or r.stderr).strip()
        return text.splitlines()[0] if text else "exit code %d" % r.returncode
    except (OSError, subprocess.TimeoutExpired) as e:
        return "error: %s" % e


def write_doctor_report(path, lines, agent):
    import platform
    out = ["VESPER-16 workshop - doctor report (%s)" % time.strftime("%Y-%m-%d %H:%M:%S"), "",
           "Faults:"] + [ln for ln in lines if ln.strip().startswith("FAIL")] + ["", "All checks:"] + lines
    out += ["", "OS: %s %s (%s)" % (platform.system(), platform.release(), platform.version()),
            "Python: %s at %s" % (sys.version.split()[0], sys.executable),
            "Agent chosen: %s" % (agent or "-"), "Agent CLI versions:"]
    out += ["  %s: %s" % (n, cli_version(n)) for n in AGENT_CLIS]
    out += ["", "Paths:", "  kit folder: " + KIT, "  workshop home: " + ws_home(), "  emulator: " + vesper_bin(),
            "  git: " + (shutil.which("git") or "not found"), "  current folder: " + os.getcwd(),
            "  VESPER_WS_HOME: " + os.environ.get("VESPER_WS_HOME", "(not set)"),
            "  kit folder files: " + ", ".join(sorted(os.listdir(KIT))), "",
            "Help: README.md (Requirements) and MANUAL.md (the workshop by hand) are in the kit folder."]
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out) + "\n")


def _read_json(p):
    try:
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _sp_skill_dirs(dirs):
    return [os.path.join(d, n) for d in dirs for n in SP_SKILLS if os.path.isfile(os.path.join(d, n, "SKILL.md"))]


def superpowers_evidence(agent):
    """Where the superpowers plugin/skills are active for this agent (empty list = not found)."""
    h, ev = user_home(), []
    if agent == "claude":
        ch = M.claude_home()
        en = _read_json(os.path.join(ch, "settings.json")).get("enabledPlugins") or {}
        ev += ["settings.json enables " + k for k, v in sorted(en.items()) if k.startswith("superpowers@") and v is True]
        inst = _read_json(os.path.join(ch, "plugins", "installed_plugins.json")).get("plugins") or {}
        ev += ["installed plugin " + k for k in sorted(inst) if k.startswith("superpowers@") and k not in en]
        ev += _sp_skill_dirs([os.path.join(ch, "skills")])
    elif agent == "codex":
        xh = M.codex_home()
        try:
            with open(os.path.join(xh, "config.toml"), encoding="utf-8", errors="replace") as f:
                toml = f.read()
        except OSError:
            toml = ""
        ev += ["config.toml enables " + m.group(1) for m in CODEX_SP.finditer(toml)
               if re.search(r"^\s*enabled\s*=\s*true\b", m.group(2), re.M)]
        if os.path.isdir(os.path.join(xh, "superpowers")):
            ev.append(os.path.join(xh, "superpowers"))
        ev += _sp_skill_dirs([os.path.join(xh, "skills"), os.path.join(h, ".agents", "skills")])
    elif agent == "cursor":
        root = os.path.join(h, ".cursor", "plugins")
        for dp, dns, _ in os.walk(root):
            rel = os.path.relpath(dp, root)
            depth = 0 if rel == "." else rel.count(os.sep) + 1
            if "superpowers" in dns:
                ev.append(os.path.join(dp, "superpowers"))
            if depth >= 2:
                dns[:] = []
        ev += _sp_skill_dirs([os.path.join(h, ".cursor", "skills"), os.path.join(h, ".agents", "skills")])
    return ev


MEMORY_WARN = ("Codex Memories hold VESPER notes from earlier sessions. In every new workshop thread type /memories "
               "and turn memory off for that chat (or turn Memories off in Settings > Personalization).")


def codex_memories_have_vesper():
    """True if a file under ~/.codex/memories mentions vesper. Read only."""
    roots = {os.path.join(user_home(), ".codex", "memories")}
    if os.environ.get("CODEX_HOME"):
        roots.add(os.path.join(os.environ["CODEX_HOME"], "memories"))
    for root in roots:
        for dp, _, fns in os.walk(root):
            for fn in fns:
                try:
                    with open(os.path.join(dp, fn), encoding="utf-8", errors="replace") as f:
                        if "vesper" in f.read(2000000).lower():
                            return True
                except OSError:
                    pass
    return False


def cmd_doctor(a):
    _WRAP[0] = False
    try:
        return _cmd_doctor(a)
    finally:
        _WRAP[0] = True


def _cmd_doctor(a):
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
    agent = (a.agent or reg.data.get("agent") or ask("Which agent do you use (codex/claude/cursor)? [codex] ", "codex")).lower()
    alias = a.alias if a.alias is not None else (
        reg.data.get("alias") or ask("Alias for the shared chart (Enter = anonymous): ", ""))
    sp = superpowers_evidence(agent)
    if sp:
        note(1, "WARN", "superpowers is active for %s (%s). Your agent may stop to ask for approval; "
                        "answer 'go on'." % (agent, "; ".join(sp)))
    if agent == "codex" and codex_memories_have_vesper():
        note(1, "WARN", MEMORY_WARN)
    al, ready = doctor_auto_lines(agent, getattr(a, "check_auto", False))
    for x in al:
        if x.startswith("  WARN"):
            level = max(level, 1)
    lines += al
    reg.data.update(agent=agent, alias=alias, doctor={"level": level, "time": time.time()}, auto_ready=ready)
    reg.add_item(h, "dir")
    reg.mark_done(h)
    reg.save()
    print("\n".join(c_ok(l) if l.startswith("  OK ") else c_err(l) if l.startswith("  FAIL")
                     else c_next(l) if l.startswith("  WARN") else l for l in lines))
    print([c_good("GREEN: all good."), "YELLOW: it works - read the warnings.",
           c_err("RED: follow MANUAL.md or work with a neighbour.")][level])
    rp = doctor_report_path()
    if level == 2:
        write_doctor_report(rp, lines, agent)
        print("\n  The setup has a fault. A report for help is in:\n    %s" % rp)
        print("  Paste this prompt into any LLM (an agent opened in this kit folder reads the file;")
        print("  in a chat window, attach doctor-report.txt):")
        prompt_block(HELP_PROMPT)
    elif os.path.exists(rp):
        os.remove(rp)
    return level if level == 2 else 0


# ------------------------------------------------------------------ run folders
AGENTS_MD = "# Workshop run {run_id}\nThis folder is one isolated VESPER-16 workshop run.\n"
SKILL_NOTE = ("Skills are in .agents/skills/ (copies in .claude/skills/ and .cursor/skills/). "
              "Read vesper16/SKILL.md before you start.\n")


def git(folder, *args):
    subprocess.run(["git", "-c", "user.name=vesper", "-c", "user.email=vesper@local", "-c", "core.autocrlf=false"]
                   + list(args), cwd=folder, capture_output=True, check=True)


def write_task(dst_dir, task, name=""):
    """Copy tasks/<task>.md into a run folder; T6 is a template filled with the learner's name."""
    src = os.path.join(KIT, "tasks", task + ".md")
    if task != "T6":
        shutil.copy2(src, dst_dir)
        return
    with open(src, encoding="utf-8") as fh:
        tpl = fh.read()
    with open(os.path.join(dst_dir, "T6.md"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(T6F.task_md(tpl, name))


def make_run_folder(reg, run_id, task, skill_dir=None, name=""):
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
        write_task(os.path.join(f, "tasks"), task, name)
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
    lines = wrap_line("  " + title, MAXW - 2) if len(title) > MAXW - 4 else ["  " + title]
    print("\n" + c_banner(WIDE) + "\n" + "\n".join(c_banner(x) for x in lines) + "\n" + c_banner(WIDE))


def prompt_block(prompt):
    print("\n" + c_prompt("-" * 30 + " PROMPT " + "-" * 34))
    print(prompt.rstrip("\n"))
    print(c_prompt("-" * 27 + " END OF PROMPT " + "-" * 30))


def next_box(cmd, when):
    cmds = [cmd] if isinstance(cmd, str) else list(cmd)
    w = max([70] + [len(x) + 10 for x in cmds])
    wl = textwrap.wrap(when, w - 10) or [""]
    print("\n" + c_next("+" + "-" * w + "+"))
    print(c_next("|  NEXT: " + wl[0].ljust(w - 8) + "|"))
    for extra in wl[1:]:
        print(c_next("|        " + extra.ljust(w - 8) + "|"))
    for c in cmds:
        print(c_next("|        " + c.ljust(w - 8) + "|"))
    print(c_next("+" + "-" * w + "+") + "\n")


def print_prompt(folder, prompt, then, cmd="python workshop.py done", mem=False):
    print("\n  1. Open this folder as a NEW project in your agent (choose exactly this folder, not a folder above it):")
    print("\n       %s" % folder)
    print("\n     Project name in the app: %s" % os.path.basename(os.path.normpath(folder)))
    print("\n  2. Start a NEW thread.")
    if mem:
        print("\n  3. " + c_next("Type /memories first and turn off memory for this chat."))
    print("\n  %d. Copy everything between the PROMPT lines and send it." % (4 if mem else 3))
    prompt_block(prompt)
    print("\n  %d. Wait until the agent says it is done. Do not ask it anything else in this thread."
          % (5 if mem else 4))
    print("     If it asks a question, reply: Make reasonable assumptions and continue.")
    if cmd:
        next_box(cmd, then)


def create_s3_run(reg, a, task, name=None, control=False):
    """Create one stage-3 run (registry row, folder, active). Returns (run_id, folder, prompt).
    On failure the registry row and active entry are removed, so no half state stays."""
    src, parent, sh, shs = resolve_skill(reg, a.skill)
    if task == "T6" and name is None:
        if a.name is not None:
            raw = a.name
        elif reg.data.get("alias"):
            raw = reg.data["alias"]
            a.name_from_alias = True
        else:
            raw = ask("Your name for the T6 nameplate (up to 8 letters A-Z; Enter = VESPER): ", "")
        name = T6F.normalise(raw)
    name = name or ""
    rid = s3_run_id(reg, parent, ("n" + task[-1]) if control else task)
    if control:       # control run: same folder, no skill, no skill sentences in the prompt
        reg.data["runs"][rid] = dict(folder="", task=task, method="none", code=rid.rsplit("-", 1)[1], stage="3",
                                     parent=parent, skill_source="none", skill_hash="", skill_has_solution="",
                                     session=None, name=name)
    else:
        reg.data["runs"][rid] = dict(folder="", task=task, method=reg.data["runs"].get(parent, {}).get("method", ""),
                                     code=rid.rsplit("-", 1)[1], stage="3", parent=parent,
                                     skill_source=a.skill if a.skill in ("own", "wiki") else "path",
                                     skill_hash=sh, skill_has_solution=shs, session=None, name=name)
    try:
        f = make_run_folder(reg, rid, task, skill_dir=None if control else src, name=name)
        prompt = render_prompt("stage3-noskill" if control else "stage3", task=task, run_id=rid)
        with open(os.path.join(f, "PROMPT.txt"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(prompt)                    # a lost window is never fatal: the prompt stays in the run folder
    except BaseException:
        reg.data["runs"].pop(rid, None)
        reg.save()
        raise
    reg.data["runs"][rid]["folder"] = f
    reg.start_active(rid, "3")
    reg.save()
    return rid, f, prompt


def new_s3_both(reg, a):
    """new s3 --task both: the T6 run, then the T3 run, in one process and one terminal."""
    auto = getattr(a, "auto", False)
    r1, f1, p1 = create_s3_run(reg, a, "T6")
    a.s3_first = r1
    if not auto:
        if not gate_on():
            s3_header(reg, a, True)
        s3_show(reg, r1, 1, 2, "T6", f1, p1)
    try:
        r2, f2, p2 = create_s3_run(reg, a, "T3")
    except Exception as e:
        print(c_err("\n  The T3 run could not be created: %s" % e))
        print("  The T6 run %s is valid. Start the T3 run later with:  python workshop.py new s3 --task T3" % r1)
        if auto:
            return run_auto(reg, a, [auto_item(reg, a, r1, f1, p1)]) or 1
        next_box("python workshop.py done " + r1, "when the T6 agent says it is done, run:")
        return 1
    if auto:
        return run_auto(reg, a, [auto_item(reg, a, r1, f1, p1), auto_item(reg, a, r2, f2, p2)])
    s3_show(reg, r2, 2, 2, "T3", f2, p2)
    next_box(["python workshop.py done %s   (T6)" % r1, "python workshop.py done %s   (T3)" % r2],
             "when an agent is done, run its line:")
    return 0


ALL_DESC = {"t3": "T3 WITH the skill",
            "n3": "T3 WITHOUT the skill (control: stop it at 10 min)",
            "t6": "T6 WITH the skill (a different task that shares components with T3)",
            "n6": "T6 WITHOUT the skill (control: stop it at 10 min)"}
ALL_LABEL = {"t3": "(T3 with skill)", "n3": "(T3 without skill)", "t6": "(T6 with skill)", "n6": "(T6 without skill)"}
ALL_ORDER = ("t3", "n3", "t6", "n6")
AFTER_ALL = "After ALL your stage-3 agents are done"


def run_label(reg, rid):
    """'(T3 with skill)' style label of a stage-3 run."""
    run = reg.data["runs"].get(rid, {})
    task = run.get("task", "")
    return "(%s %s skill)" % (task, "without" if is_control(run) else "with")


def still_working_box(reg, left):
    """NEXT box listing every still-active stage-3 run, one line each, with its label."""
    left = sorted(left, key=lambda x: float(x.get("start") or 0))
    lines = ["%s   %s" % (next_cmd(x), run_label(reg, x["run_id"])) for x in left]
    if len(left) == 1:
        head = "1 agent is still working. When it is done (or at 15 min), run its line:"
    else:
        head = ("%d agents are still working. When each one is done (or at 15 min), run its line:"
                % len(left))
    next_box(lines, head)


def start_order(seed):
    """Order to start the four stage-3 threads. Per task, WITH or WITHOUT goes first; random per stage-1 run."""
    rng = random.Random(str(seed))
    order = []
    for t in ("T3", "T6"):
        pair = ["%s with skill" % t, "%s without skill" % t]
        if rng.random() < 0.5:
            pair.reverse()
        order += pair
    return order


ORDER_KEY = {"T3 with skill": "t3", "T3 without skill": "n3", "T6 with skill": "t6", "T6 without skill": "n6"}


def start_order_keys(seed):
    """start_order as ALL_ORDER keys (t3, n3, t6, n6)."""
    return [ORDER_KEY[x] for x in start_order(seed)]


BENCH_LINE = ("  Together, these 4 runs are a small benchmark of your skill: the same task and a different task,"
              " each with and without it.")


def start_order_line(seed):
    return "  Start in this order: " + " ".join("%d. %s" % (i, x) for i, x in enumerate(start_order(seed), 1))


def new_s3_all(reg, a):
    """new s3 --task all: T3 and T6, each with the skill and without it (control); one terminal."""
    made = {}
    try:
        made["t6"] = create_s3_run(reg, a, "T6")          # first: it asks for the T6 name
        nm = reg.data["runs"][made["t6"][0]].get("name", "")
        made["t3"] = create_s3_run(reg, a, "T3")
        made["n3"] = create_s3_run(reg, a, "T3", control=True)
        made["n6"] = create_s3_run(reg, a, "T6", name=nm, control=True)   # same name as the T6 skill run
    except Exception as e:
        print(c_err("\n  A run could not be created: %s" % e))
        print("  Runs already created stay valid; start the missing ones later with --task T6 or T3.")
    if not made:
        return 1
    a.s3_first = made["t6"][0] if "t6" in made else next(iter(made.values()))[0]
    seed = reg.data["runs"][next(iter(made.values()))[0]].get("parent", "")
    if getattr(a, "auto", False):
        order = [k for k in start_order_keys(seed) if k in made]
        rc = run_auto(reg, a, [auto_item(reg, a, made[k][0], made[k][1], made[k][2]) for k in order])
        return rc or (0 if len(made) == 4 else 1)
    if not gate_on():
        s3_header(reg, a, True, total=4)
    s3_pages(reg, a, made, seed, total=4)         # the start order line comes before the pages
    return 0 if len(made) == 4 else 1


def cmd_new(a):
    ws_home(check=True)
    clear_screen()
    reg = Registry.load()
    d = reg.data.get("doctor")
    if not d or (a.stage == "s1" and d.get("level") == 2):
        print("Checking this computer first (doctor).\n")
        if cmd_doctor(argparse.Namespace(agent=None, alias=None)):
            sys.exit("\nFix the FAIL lines first (see doctor-report.txt and the help prompt above), "
                     "then run this command again.")
        reg = Registry.load()
    task = a.task
    if task in ("both", "all") and a.stage != "s3":
        sys.exit("--task %s is for stage 3 only:  python workshop.py new s3 --task all" % task)
    acts = reg.actives()
    blocking = acts if a.stage == "s1" else [x for x in acts if x["stage"] != "3"]
    if blocking:
        sys.exit("\n".join(active_lines(reg)))
    if a.stage == "s3":
        same = [x for x in acts if reg.data["runs"].get(x["run_id"], {}).get("task") in
                (("T6", "T3") if task in ("both", "all") else (task,))
                and (task == "all" or not is_control(reg.data["runs"].get(x["run_id"], {})))]
    else:
        same = []
    if getattr(a, "auto", False) and a.stage != "s3":
        sys.exit("--auto is for stage 3 only:  python workshop.py new s3 --task all --auto")
    if a.stage == "s1":
        if task == "T6":
            sys.exit("T6 is a stage-3 task. Stage 1 uses T3:  python workshop.py new s1")
        method = a.method if a.method != "random" else random.choice(METHODS)
        code = new_code()
        rid = "s1-" + code
        reg.data["runs"][rid] = dict(folder="", task=task, method=method, code=code, stage="1", parent="",
                                     skill_source="none", skill_hash="", skill_has_solution="", session=None, name="")
        f = make_run_folder(reg, rid, task)
        prompt = render_prompt("stage1", task=task, run_id=rid)
        if not gate_on():
            banner("STAGE 1 - the agent with NO skill        run %s" % rid)
            method_notice(method, " (used in stage 2)")
        done_cmd = "python workshop.py done"
    else:
        g = find_global_vesper_skills()
        if g:
            sys.exit("A VESPER skill is in a global folder, so stage 3 would not be clean:\n  " + "\n  ".join(g)
                     + "\nMove it away (or run harvest / cleanup), then run this command again.")
        if getattr(a, "auto", False):
            auto_setup(reg, a)
            if not same and not auto_confirm(a, {"all": 4, "both": 2}.get(task, 1)):
                return 1                          # nothing is created: the learner can choose the manual flow
        try:
            if same:
                return resume_s3(reg, a, same)
            if task == "all":
                return new_s3_all(reg, a)
            if task == "both":
                return new_s3_both(reg, a)
            rid, f, prompt = create_s3_run(reg, a, task)
            a.s3_first = rid
            if getattr(a, "auto", False):
                return run_auto(reg, a, [auto_item(reg, a, rid, f, prompt)])
            if not gate_on():
                s3_header(reg, a, False)
            s3_show(reg, rid, 1, 1, task, f, prompt)
            next_box("python workshop.py done " + rid, "when the agent is done, run:")
            hint = second_s3_hint(reg, rid)
            if hint:
                print("  Now start the second stage-3 run (here), and open it in a SECOND new agent thread:")
                print("      %s\n" % hint)
            return 0
        except KeyboardInterrupt:
            print("\n" + S3_STOPPED)
            return 130
    reg.data["runs"][rid]["folder"] = f
    reg.start_active(rid, "1" if a.stage == "s1" else "3")
    reg.save()
    mem = (reg.data.get("agent") or "") in ("codex", "") and codex_memories_on(reg)
    if gate_on():
        run_page(reg, rid, "STAGE 1 - the agent with NO skill        run %s" % rid, f, prompt, "your default model",
                 True, extra=lambda: method_notice(method, " (used in stage 2)"), mem=mem)
        next_box(done_cmd, "when the agent says it is done, run:")
        return 0
    print_prompt(f, prompt, "when the agent says it is done, run:", done_cmd, mem=mem)
    return 0


# ------------------------------------------------------------------ measurement
def _log_files():
    out = []
    for root in (os.path.join(M.codex_home(), "sessions"), os.path.join(M.codex_home(), "archived_sessions"),
                 os.path.join(M.claude_home(), "projects")):
        for dp, _, fs in os.walk(root):
            out += [os.path.join(dp, n) for n in fs if n.endswith(".jsonl")]
    return out


CHUNK = 8 * 2 ** 20


def _file_has(p, key):
    """True if the bytes key occur in file p. Reads in chunks (overlap len(key)); stops at the first hit."""
    keep = b""
    with open(p, "rb") as f:
        while True:
            buf = f.read(CHUNK)
            if not buf:
                return False
            if key in keep + buf:
                return True
            keep = buf[-(len(key) - 1):] if len(key) > 1 else b""


def find_sessions(run_id, since=None):
    """Agent logs that contain the run id. With since (epoch seconds), a log whose last write is more than
    120 s before since is skipped unread (it cannot hold this run). Older big logs (> 200 MB) are skipped
    only when since is not given; a log written during the run is always searched."""
    key, seen, out = run_id.encode(), set(), []
    codex_root = os.path.abspath(M.codex_home())
    for p in _log_files():
        try:
            if since is not None:
                if os.path.getmtime(p) < since - 120:
                    continue
            elif os.path.getsize(p) > 200 * 2 ** 20:
                continue
            if not _file_has(p, key):
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
    return _join_threads(out)


_UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def _join_threads(found):
    """Codex continues one thread in a new file rollout-<time>-<PARENT>_<CHILD>.jsonl when the model changes.
    Files of one thread become ONE session: sid = the first file's thread id, paths = all its files."""
    cx = [x for x in found if x["agent"] == "codex"]
    if len(cx) < 2:
        return found
    names = [os.path.basename(x["path"]).lower() for x in cx]
    own = [(_UUID_RE.findall(n) or [""])[-1] for n in names]
    grp = list(range(len(cx)))

    def top(i):
        while grp[i] != i:
            i = grp[i]
        return i
    for i in range(len(cx)):
        for j in range(len(cx)):
            if i != j and own[j] and own[j] + "_" in names[i]:
                grp[top(i)] = top(j)
    groups = {}
    for i in range(len(cx)):
        groups.setdefault(top(i), []).append(i)
    if all(len(v) == 1 for v in groups.values()):
        return found
    joined = {}
    for idx in groups.values():
        idx.sort(key=lambda i: names[i])
        first = cx[idx[0]]
        ids = _UUID_RE.findall(names[idx[0]])
        sid = ids[0] if ids and len(idx) > 1 else first["sid"]
        joined[id(first)] = dict(first, sid=sid, paths=[cx[i]["path"] for i in idx])
        for i in idx[1:]:
            joined[id(cx[i])] = None
    out = []
    for x in found:
        if x["agent"] != "codex":
            out.append(x)
        elif joined.get(id(x)):
            out.append(joined[id(x)])
    return out


def session_paths(session):
    """All log files of a stored session (a split Codex thread has several)."""
    s = session or {}
    paths = list(s.get("paths") or [])
    p = s.get("path")
    if p and p not in paths:
        paths.insert(0, p)
    if len(paths) == 1 and s.get("agent") == "codex":      # a session stored before the join: look for its siblings
        ids = _UUID_RE.findall(os.path.basename(p).lower())
        if ids:
            for q in sorted(glob.glob(os.path.join(M.codex_home(), "sessions", "**", "*%s*.jsonl" % ids[0]), recursive=True)):
                if q not in paths:
                    paths.append(q)
    return paths


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


def _tool_evidence(d):
    """The tool calls and tool results of one log line, as text. Prose, prompts and skill lists give ''."""
    t = d.get("type")
    if t in ("user", "assistant"):
        c = (d.get("message") or {}).get("content")
        if not isinstance(c, list):
            return ""
        return " ".join(json.dumps(b) for b in c
                        if isinstance(b, dict) and b.get("type") in ("tool_use", "tool_result"))
    p = d.get("payload")
    if t == "response_item" and isinstance(p, dict) and p.get("type") not in (
            "message", "reasoning", None):
        return json.dumps(p)
    return ""


_USE_RE = re.compile(r"(skill-creator|writing-skills)(?:/|\\\\|\\)SKILL\.md|\$(skill-creator|writing-skills)\b"
                     r"|\"name\": \"Skill\".{0,80}?\"skill\": \"(?:[\w.-]+:)?(skill-creator|writing-skills)\"")


def detect_method_used(path, t0, t1):
    """Which skill-writing help the agent really used: 'skill-creator', 'writing-skills', 'none', or '' (no log).
    path may be a list of log files (one split thread)."""
    if isinstance(path, (list, tuple)):
        res = [_method_used_one(p, t0, t1) for p in path]
        for name in ("skill-creator", "writing-skills", "none"):
            if name in res:
                return name
        return ""
    return _method_used_one(path, t0, t1)


def _method_used_one(path, t0, t1):
    if not path or not os.path.exists(path):
        return ""
    lines = []
    try:
        for d in M.jsonl(path):
            if isinstance(d, dict):
                lines.append((M.parse_ts(d.get("timestamp")), _tool_evidence(d)))
    except Exception:
        return ""
    if any(ts is not None for ts, _ in lines):
        lines = [x for x in lines if x[0] is not None and t0 - 1 <= x[0] <= t1 + 1]
    found = set()
    for _, text in lines:
        for m in _USE_RE.finditer(text):
            found.add(next(g for g in m.groups() if g))
    for name in ("skill-creator", "writing-skills"):
        if name in found:
            return name
    return "none"


_MEM_PATH_RE = re.compile(r"\.codex(?:/|\\+)memories", re.I)


def _message_text(d):
    """Text of a developer/system message of one log line, else ''."""
    p = d.get("payload")
    if d.get("type") == "response_item" and isinstance(p, dict) and p.get("type") == "message"             and p.get("role") in ("developer", "system"):
        c = p.get("content")
    elif d.get("type") == "system":
        c = d.get("content") if "content" in d else (d.get("message") or {}).get("content")
    else:
        return ""
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return " ".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in c)
    return ""


def detect_memory_used(path, t0, t1):
    """Did Codex Memories reach the agent? 'yes', 'no', or '' (no log). path may be a list of files."""
    if isinstance(path, (list, tuple)):
        res = [_memory_used_one(p, t0, t1) for p in path]
        return "yes" if "yes" in res else ("no" if "no" in res else "")
    return _memory_used_one(path, t0, t1)


def _memory_used_one(path, t0, t1):
    """
    yes = a developer/system message has a '## Memory' section that names VESPER (the session start
    may lie before t0, so these are not time-filtered), or a tool call/result in the window reads .codex/memories."""
    if not path or not os.path.exists(path):
        return ""
    try:
        for d in M.jsonl(path):
            if not isinstance(d, dict):
                continue
            txt = _message_text(d)
            i = txt.find("## Memory")
            if i >= 0 and "vesper" in txt[i:].lower():
                return "yes"
    except Exception:
        return ""
    lines = []
    try:
        for d in M.jsonl(path):
            if isinstance(d, dict):
                lines.append((M.parse_ts(d.get("timestamp")), _tool_evidence(d)))
    except Exception:
        return ""
    if any(ts is not None for ts, _ in lines):
        lines = [x for x in lines if x[0] is not None and t0 - 1 <= x[0] <= t1 + 1]
    return "yes" if any(_MEM_PATH_RE.search(t) for _, t in lines) else "no"


def _user_text(d):
    """Text of a user prompt in one log line (Codex user message / user_message event, Claude user text),
    else None. Tool results are not prompts."""
    t, p = d.get("type"), d.get("payload")
    if t == "response_item" and isinstance(p, dict) and p.get("type") == "message" and p.get("role") in (None, "user"):
        c = p.get("content")
    elif t == "event_msg" and isinstance(p, dict) and p.get("type") == "user_message":
        c = p.get("message")
    elif t == "user":
        c = (d.get("message") or {}).get("content")
        if isinstance(c, list):
            c = [b for b in c if isinstance(b, dict) and b.get("type") == "text"]
            if not c:
                return None
    else:
        return None
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return " ".join(str(b.get("text", "")) if isinstance(b, dict) else str(b) for b in c)
    return None


def prompt_time(paths, run_id, t0, t1):
    """When the learner sent the run's prompt: the 'Workshop run: <id>' user message in [t0, t1], else the
    first user message in [t0, t1]. None when the log has no such time."""
    key = ("workshop run: %s" % run_id).lower()
    first_key = first_user = None
    for path in paths or []:
        if not path or not os.path.exists(path):
            continue
        try:
            for d in M.jsonl(path):
                if not isinstance(d, dict):
                    continue
                ts = M.parse_ts(d.get("timestamp"))
                if ts is None or not t0 - 1 <= ts <= t1 + 1:
                    continue
                txt = _user_text(d)
                if txt is None:
                    continue
                first_user = ts if first_user is None else min(first_user, ts)
                if key in txt.lower():
                    first_key = ts if first_key is None else min(first_key, ts)
        except Exception:
            continue
    return first_key if first_key is not None else first_user


def memory_line(row):
    return "  Agent memory in context: %s (Codex Memories; see the debrief)" % (row.get("memory_used") or "unknown")


_SKIP_KEYS = ("content", "new_string", "old_string", "text", "new_source")
_PATH_END = r"\s\"'`|;&()<>,{}\[\]="                 # characters that end a path token
_TOKEN = re.compile(r"[^%s]+" % _PATH_END)
_RUN_ID = re.compile(r"^s[123]-[0-9a-f]{4}(?:-[tn][36]-[0-9a-f]{4})?$")
_HOME_STORES = (".skills", ".grader", ".snapshots", ".prebuilt", ".guides")   # in the runs home, never for a run
_PATCH = re.compile(r"\*\*\* begin patch(.*?)(?:\*\*\* end patch|$)", re.I | re.S)
_WORKDIR = re.compile(r"[\"']?(?:workdir|cwd)[\"']?\s*:\s*[\"']([^\"']+)[\"']", re.I)
_WRITER_T6 = re.compile(r"t6\.md|t6font", re.I)
_MEM_TOK = re.compile(r"\.codex/memories(?:/|$)|/projects/[^/]+/memory(?:/|$)", re.I)   # used per token: linear
_GLOB_CH = re.compile(r"[*?\[]")
_PWD_MARK = "@pwd@"                                   # the current folder ($PWD, %CD%, ...), resolved per command
_CD_CMDS = ("cd", "pushd", "set-location", "sl", "chdir")
# a recursive listing or search: find/tree, -r/-R/-rn/-Recurse/--recursive, dir /s, rg --files, a ** glob
_RECURSIVE = re.compile(r"(?:^|[\s;&|(])(?:find|tree)(?=\s|$)|(?:^|\s)(?:-[a-qs-z]?r[a-qs-z]{0,2}|-recurse|--recursive"
                        r"|--files|/s)(?=\s|$)|\*\*", re.I)


def _strings(v, out):
    if isinstance(v, str):
        out.append(v)
    elif isinstance(v, dict):
        for k, x in v.items():
            if k not in _SKIP_KEYS:
                _strings(x, out)
    elif isinstance(v, list):
        for x in v:
            _strings(x, out)


def _cwd_args(v, out):
    """A workdir/cwd argument (Codex shell_command) as 'workdir:"..."' text, so the scan resolves '..' from it."""
    if isinstance(v, dict):
        for k in ("workdir", "cwd"):
            if isinstance(v.get(k), str) and v[k]:
                out.append('workdir:"%s"' % v[k])


def _ev_ts(d):
    """Event time in epoch seconds: 'timestamp' (Codex, Claude Code) or 'timestamp_ms' (Cursor stream-json)."""
    ts = M.parse_ts(d.get("timestamp"))
    if ts is None and isinstance(d.get("timestamp_ms"), (int, float)):
        ts = d["timestamp_ms"] / 1000.0
    return ts


def _call_text(d):
    """The arguments of one agent tool call (Codex function_call / custom_tool_call, Claude tool_use), else ''."""
    parts = []
    p = d.get("payload")
    if d.get("type") == "response_item" and isinstance(p, dict) and p.get("type") in ("function_call", "custom_tool_call"):
        raw = p.get("arguments") if p.get("type") == "function_call" else p.get("input")
        if p.get("name") == "apply_patch" and isinstance(raw, str):
            return "\n".join(l for l in raw.splitlines() if l.startswith("*** "))
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except ValueError:
                pass
        _cwd_args(raw, parts)
        _strings(raw, parts)
    elif d.get("type") == "tool_call" and d.get("subtype") == "started":      # Cursor stream-json
        _strings(d.get("tool_call"), parts)
    elif d.get("type") == "assistant":
        c = (d.get("message") or {}).get("content")
        if isinstance(c, list):
            for b in c:
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    inp = b.get("input")
                    if b.get("name") == "Glob" and isinstance(inp, dict) and inp.get("path") and inp.get("pattern"):
                        parts.append(inp["path"].rstrip("/\\") + "/" + inp["pattern"])    # the pattern is under path
                    _strings(inp, parts)
    return "\n".join(parts)


_WIN = os.name == "nt"


def _fold(s):
    """One spelling for path text: '/' separators, lower case on Windows."""
    s = re.sub(r"\\+", "/", s)
    return s.lower() if _WIN else s


def _npath(p):
    """A normalised absolute or relative path ('/' separators, Git Bash /c/ -> c:/, no '..')."""
    p = _fold(p)
    if _WIN:
        p = re.sub(r"^/([a-z])(?=/|$)", r"\1:", p)
    p = posixpath.normpath(p) if p else p
    return p + "/" if re.match(r"^[a-z]:$", p, re.I) else p


def _is_abs(p):
    return p.startswith("/") or bool(re.match(r"^[a-z]:", p, re.I))


def _within(q, root):
    return bool(root) and (q == root or q.startswith(root.rstrip("/") + "/"))


def _kit_roots():
    """The kit folder; also the current folder if it is a kit copy (a learner may run another clone)."""
    roots = [KIT]
    cwd = os.getcwd()
    if os.path.isfile(os.path.join(cwd, "workshop.py")) and os.path.isdir(os.path.join(cwd, "tasks")):
        roots.append(cwd)
    return list(dict.fromkeys(_npath(os.path.abspath(r)) for r in roots))


def _iso_roots(folder):
    own = _npath(os.path.abspath(folder))
    runs = list(dict.fromkeys([_npath(os.path.abspath(ws_home())), posixpath.dirname(own.rstrip("/"))]))
    return {"own": own, "runs": runs, "kits": _kit_roots(),
            "codex_mem": _npath(os.path.join(os.path.abspath(M.codex_home()), "memories")),
            "claude": _npath(os.path.abspath(M.claude_home()))}


def _env_path(m):
    """$env:NAME, ${env:NAME}, %NAME%, $NAME, ${NAME} -> the value when it is one absolute path; else unchanged."""
    name = next(g for g in m.groups() if g)
    v = os.environ.get(name) or os.environ.get(name.upper()) or ""
    if v and os.path.isabs(v) and os.pathsep not in v:
        return _npath(os.path.abspath(v))
    return m.group(0)


def _norm_call_text(text):
    """Unescape JSON/JS string text, drop patch bodies (written text, not reads), fold case,
    expand home and environment variables, mark the current folder ($PWD, %CD%, ...) and
    turn Git Bash drive paths into c:/ paths."""
    if "\\\\" in text:                     # escaped strings: \\ is a separator, \n a line break
        text = re.sub(r"\\{2,}", "/", text)
        text = re.sub(r"\\[nr]", "\n", text)
        text = re.sub(r"\\t", " ", text)
        text = re.sub(r"\\([\"'])", r"\1", text)
    text = _PATCH.sub(lambda m: "\n".join(l for l in m.group(1).splitlines() if l.lstrip().startswith("*** ")), text)
    text = _fold(text)
    home = _npath(os.path.abspath(user_home()))
    subs = [(r"\$\{?pwd\}?(?!\w)|\$\(pwd\)|%cd%|\$?\(get-location\)(?:\.path)?", _PWD_MARK),
            (r"\$env:userprofile(?!\w)|\$\{env:(?:userprofile|home)\}|\$env:home(?!\w)|%userprofile%"
             r"|\$\{home\}|\$home(?!\w)", home),
            (r"(?<![\w~.$-])~(?=/|$|[%s])" % _PATH_END, home)]
    for var in ("localappdata", "appdata"):
        if os.environ.get(var.upper()):
            subs.append((r"\$env:%s(?!\w)|\$\{env:%s\}|%%%s%%" % (var, var, var),
                         _npath(os.path.abspath(os.environ[var.upper()]))))
    for rx, val in subs:
        text = re.sub(rx, lambda m, v=val: v, text, flags=re.I)
    text = re.sub(r"\$\{env:(\w+)\}|\$env:(\w+)|%(\w+)%|\$\{([a-z_]\w*)\}|\$([a-z_]\w*)", _env_path, text, flags=re.I)
    if _WIN:
        text = re.sub(r"(?<![\w/.:~-])/([a-z])(?=/)", r"\1:", text)
    return text


def _glob_reaches(q, root):
    """True when the glob pattern q can match a path below root (another run folder, a store, ...)."""
    qc, rc = q.rstrip("/").split("/"), root.rstrip("/").split("/")
    for i, part in enumerate(rc):
        if i >= len(qc):
            return False
        if qc[i] == "**":
            return True
        if not fnmatch.fnmatchcase(part, qc[i]):
            return False
    return len(qc) > len(rc)


def _classify(q, roots):
    """A short hit for one normalised path, or None when the path is allowed or not of interest."""
    if _within(q, roots["own"]):
        return None
    if _within(q, roots["codex_mem"]) or re.search(r"(^|/)\.codex/memories(/|$)", q):
        return "memory " + q[q.find("memories"):][:60]
    if (_within(q, roots["claude"]) or "/.claude/" in q) and re.search(r"/projects/[^/]+/memory(/|$)", q):
        return "memory (claude project memory)"       # the project slug holds the user's path: not in the note
    if _GLOB_CH.search(q):                              # a pattern: can it reach another run, a store or the kit?
        for r in roots["runs"]:
            if _glob_reaches(q, r):
                return "runs home glob " + (q[len(r):].strip("/") if _within(q, r) else q)
        for r in roots["kits"]:
            if _glob_reaches(q, r) or _within(q, r):
                return "kit glob " + (q[len(r):].strip("/") if _within(q, r) else q)
    for r in roots["runs"]:
        if _within(q, r):
            rel = q[len(r):].strip("/")
            first = rel.split("/")[0]
            if not rel:
                return "runs home listed"
            if _RUN_ID.match(first):
                return "other run " + rel
            if first in _HOME_STORES:
                return "runs home " + rel
            return "runs home " + rel if os.path.exists(q) else None
    for r in roots["kits"]:
        if _within(q, r):
            return "kit " + (q[len(r):].strip("/") or "folder")
    return None


def _resolve(tok, cwd):
    tok = tok.replace(_PWD_MARK, cwd)
    return _npath(tok) if _is_abs(tok) else posixpath.normpath(posixpath.join(cwd, tok))


def _scan_text(text, roots, writer):
    """Hits (short strings) for reads of guarded knowledge in the text of one tool call."""
    text = _norm_call_text(text)
    own = roots["own"]
    found = []
    for r in sorted(set(roots["runs"] + roots["kits"] + [roots["codex_mem"]]), key=len, reverse=True):
        rx = r"(?<![\w.-])%s(?=$|/|[%s])[^%s]*" % (re.escape(r.rstrip("/")), _PATH_END, _PATH_END)
        found += [_npath(m.group(0).rstrip(".:")) for m in re.finditer(rx, text)]
    cwds = []
    for m in _WORKDIR.finditer(text):
        cwds.append(_resolve(m.group(1), own))
    cwds = cwds or [own]
    rec = bool(_RECURSIVE.search(text))
    searched = list(cwds) if rec else []         # folders a recursive command may start from
    prev = ""
    for tok in _TOKEN.findall(text):
        low = tok.lower()
        if _MEM_TOK.search(tok):
            found.append(_npath(tok.replace(_PWD_MARK, cwds[0])))
        if prev in _CD_CMDS and low != "/d":     # cd X: X is read (listed) and the next tokens resolve from it
            cwds = [_resolve(tok, c) for c in cwds]
            found += cwds
            if rec:
                searched += cwds
        elif _PWD_MARK in tok or _is_abs(tok):
            q = [_resolve(tok, c) for c in cwds]
            found += q
            if rec:
                searched += q
        elif ".." in tok.split("/") or any(not _within(c, own) for c in cwds):
            q = [_resolve(tok, c) for c in cwds]
            if not any(_within(x, own) for x in q):     # a '..' that stays in the own folder from any cwd is fine
                found += q
                if rec:
                    searched += q
        if not (prev == "cd" and low == "/d"):
            prev = low
    hits = []
    for q in found:
        h = _classify(q, roots)
        if h and h not in hits:
            hits.append(h)
    for q in searched:                           # a recursive search from an ancestor of the runs home
        base = q.split("*")[0].split("?")[0].rstrip("/") if _GLOB_CH.search(q) else q.rstrip("/")
        if not base or base == "/":
            continue
        for r in roots["runs"]:
            if base != r.rstrip("/") and _within(r, base):
                h = "recursive search over " + base
                if h not in hits:
                    hits.append(h)
    if writer and _WRITER_T6.search(text):
        hits.append("writer reads T6 (%s)" % _WRITER_T6.search(text).group(0))
    return hits


def _private(note):
    """No home folder or user name in a note that goes into the results: the home folder becomes '~'."""
    homes = {_npath(os.path.abspath(user_home())).rstrip("/"), _npath(os.path.expanduser("~")).rstrip("/")}
    for h in sorted(homes, key=len, reverse=True):
        if len(h) > 3:
            note = re.sub(re.escape(h) + r"(?=/|$|[^\w.-])", "~", note, flags=re.I)
    users = {os.path.basename(os.path.expanduser("~")), os.environ.get("USERNAME", ""), os.environ.get("USER", "")}
    for u in users:
        if len(u) >= 3:
            note = re.sub(r"(?<![a-z0-9])%s(?![a-z0-9])" % re.escape(u), "<user>", note, flags=re.I)
    return note


def detect_outside_reads(paths, t0, t1, folder, writer=False):
    """Targeted scan of the agent's tool calls in [t0, t1] for reads of knowledge a run must not have:
    another run folder or a store in the runs home (.skills, .grader, ...), also by a glob pattern or a
    recursive search from an ancestor of the runs home, the kit folder (tasks, solutions, guides, ...: a run
    folder has its own copies), agent memory files, and for the stage-1/2 writer (writer=True) any T6.md /
    t6font reference. Other paths are ignored. '..' resolves from the own folder, a workdir argument, or a
    'cd X' earlier in the same command.
    Returns (status, note): 'detected' (note = first 3 hits, no home path or user name), 'not_detected',
    or 'unknown' (no log). A scan finds some outside reads; it is not proof."""
    if isinstance(paths, str):
        paths = [paths]
    paths = [p for p in (paths or []) if p and os.path.exists(p)]
    if not paths:
        return "unknown", ""
    roots = _iso_roots(folder)
    hits = []
    for path in paths:
        calls = []
        try:
            for d in M.jsonl(path):
                if isinstance(d, dict):
                    calls.append((_ev_ts(d), _call_text(d)))
        except Exception:
            continue
        if any(ts is not None for ts, _ in calls):
            calls = [x for x in calls if x[0] is not None and t0 - 1 <= x[0] <= t1 + 1]
        for _, text in calls:
            if text:
                for h in _scan_text(text, roots, writer):
                    if h not in hits:
                        hits.append(h)
    if not hits:
        return "not_detected", ""
    return "detected", _private("; ".join(hits[:3]))[:200]


_CWD_KEYS = ("cwd", "workdir", "workingDirectory")


def _cwd_norm(v):
    """A working folder as written in a log (plain path or file URL) -> normalised path, or ''."""
    v = v.strip()
    if v[:7].lower() == "file://":
        v = urllib.parse.unquote(v[7:])
        if re.match(r"^/[A-Za-z]:", v):
            v = v[1:]
    if not _is_abs(v):
        return ""
    return _npath(v).rstrip("/") if len(_npath(v)) > 3 else _npath(v)


def _walk_cwds(o, out, depth=0):
    if depth > 8:
        return
    if isinstance(o, dict):
        for k, v in o.items():
            if k in _CWD_KEYS and isinstance(v, str):
                n = _cwd_norm(v)
                if n:
                    out.add(n)
            elif isinstance(v, (dict, list)):
                _walk_cwds(v, out, depth + 1)
    elif isinstance(o, list):
        for x in o:
            _walk_cwds(x, out, depth + 1)


def session_workdirs(paths, t0, t1):
    """Normalised working folders ('cwd' / 'workdir' fields of Codex and Claude Code log events)
    that the agent used in [t0, t1]."""
    if isinstance(paths, str):
        paths = [paths]
    out = set()
    for path in [p for p in (paths or []) if p and os.path.exists(p)]:
        evs = [d for d in M.jsonl(path) if isinstance(d, dict)]
        stamped = [(_ev_ts(d), d) for d in evs]
        use_ts = any(ts is not None for ts, _ in stamped)
        for ts, d in stamped:
            if use_ts and (ts is None or not (t0 - 1 <= ts <= t1 + 1)) and not (
                    ts is None and d.get("type") == "system" and d.get("subtype") == "init"):    # Cursor init: no time
                continue
            _walk_cwds(d, out)
    return out


def outside_workdirs(paths, t0, t1, folder):
    """Sorted working folders of the run window that are not inside the run folder."""
    own = _npath(os.path.abspath(folder))
    return sorted(w for w in session_workdirs(paths, t0, t1) if not _within(w, own))


def wrong_folder_block(outside, folder, harvest=False):
    """Attention text (list of lines) for a learner whose agent worked outside the run folder."""
    first = outside[0]
    lines = ["  WRONG FOLDER: your agent worked in %s, not in the run folder." % first,
             "  Its files are not where the tool looks. Fix: in your agent, open exactly this folder as the project "
             "(not a folder above it):",
             "       %s" % folder,
             "  Then ask the agent to write the skill there, and run harvest again." if harvest
             else "  Then ask the agent to redo the step there."]
    return [c_err(x) for x in lines]


def print_wrong_folder(run, row, harvest=False):
    try:
        out = outside_workdirs(session_paths(run.get("session")), float(row["start"]), float(row["cutoff"]), run["folder"])
    except (ValueError, TypeError, KeyError):
        return []
    if out:
        print("\n" + "\n".join(wrong_folder_block(out, run["folder"], harvest)) + "\n")
    return out


def skill_in_outside(outside):
    """A skill-out/vesper16/SKILL.md inside one of the outside working folders, or ''."""
    for d in outside:
        p = os.path.join(d, "skill-out", "vesper16", "SKILL.md")
        if os.path.isfile(p):
            return p
    return ""


def isolation_with_workdirs(iso, note, outside):
    if not outside:
        return iso, note
    n = "worked outside the run folder: " + _private(outside[0])
    if iso == "detected" and note:
        n += "; " + note
    return "detected", n[:200]


def isolation_lines(row):
    st = row.get("isolation") or "unknown"
    out = "  Isolation check: %s." % st
    if st == "not_detected":
        out += " (A scan finds some outside reads; not proof.)"
    if st == "detected" and row.get("isolation_note"):
        out += "\n    " + row["isolation_note"]
    return out


def count_runs(folder, t0, t1):
    t = _runlog_times(folder, t0, t1, True)
    return None if t is None else len(t)


def measure_stage(run, t0, t1):
    s = run.get("session") or {}
    res = {"agent": s.get("agent", ""), "model": "", "effort": "", "model_switched": "", "tok_uncached": "", "tok_cache_read": "",
           "tok_cache_write": "", "tok_out": "", "cost_usd": "", "measurement": ""}
    found = []
    if s.get("agent") == "codex":
        found = M.codex_sessions(t0, t1, s["sid"])
    elif s.get("agent") == "claude":
        found = M.claude_sessions(t0, t1, s["sid"])
    elif s.get("agent") == "cursor":
        found = M.cursor_sessions(s.get("path") or "")
    acts = _runlog_times(run["folder"], t0, t1, False) or []
    if found:
        tot = {"i": 0, "cr": 0, "cw": 0, "o": 0}
        models, eff = set(), (-1, "")
        for c in found:
            if c.get("effort"):
                eff = max(eff, (c.get("eff_ts") or 0, c["effort"]))
            for k in tot:
                tot[k] += c["tot"].get(k, 0)
            models |= c["models"]
            acts += [x for x in (c["first"], c["last"]) if x]
        c = M.cost(tot, models)
        if s["agent"] == "codex" and len(found) > 1:
            # one split thread: price each file with its own model; model/effort = the file with most output
            parts = [M.cost(x["tot"], x["models"]) for x in found]
            c = None if any(v is None for v in parts) else sum(parts)
            top = max(found, key=lambda x: x["tot"].get("o", 0))
            models = top["models"] or models
            eff = (0, top.get("effort") or eff[1])
            res["model_switched"] = "yes" if len({frozenset(x["models"]) for x in found}) > 1 else "no"
        res.update(model=" ".join(sorted(models)), effort=eff[1], tok_uncached=tot["i"], tok_cache_read=tot["cr"],
                   tok_cache_write=tot["cw"], tok_out=tot["o"], cost_usd=("%.2f" % c) if c is not None else "",
                   measurement={"codex": "log", "cursor": "log" if all(x.get("complete") for x in found)
                                else "log, stopped before the usage report"}.get(s["agent"], "log, output lower bound"))
        if s["agent"] == "cursor" and not all(x.get("complete") for x in found):
            # no usage report (the run was killed): the tokens and the cost are unknown, never 0
            res.update(tok_uncached="", tok_cache_read="", tok_cache_write="", tok_out="", cost_usd="")
        if s["agent"] == "cursor" and len(acts) < 2:
            dur = sum(x.get("duration") or 0 for x in found)
            if 0 < dur <= (t1 - t0) + 1:          # a duration longer than the wall time is wrong: ignore it
                acts = [t1 - dur, t1]
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


def pick_session(run_id, folder=None, since=None):
    s = find_sessions(run_id, since)
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


def form_link(rows, cfg=None):
    """One prefilled link: alias + all_results (v1 lines for `rows`). A single dict is accepted as one row."""
    cfg = cfg or load_config()
    fid = cfg.get("all_results_field")
    if not cfg.get("form_url") or not fid:
        return None
    if isinstance(rows, dict):
        rows = [rows]
    vals = {}
    if "alias" in cfg.get("fields", {}):
        vals[cfg["fields"]["alias"]] = rows[0].get("alias", "") if rows else ""
    vals[fid] = all_results_text(rows)
    return cfg["form_url"] + ("&" if "?" in cfg["form_url"] else "?") + urlencode(vals)


def alias_link(alias, cfg=None):
    """Form link with only the alias filled in. It is always short, so the Microsoft sign-in redirect accepts it."""
    cfg = cfg or load_config()
    fid = cfg.get("fields", {}).get("alias")
    if not cfg.get("form_url"):
        return None
    if not fid:
        return cfg["form_url"]
    return cfg["form_url"] + ("&" if "?" in cfg["form_url"] else "?") + urlencode({fid: alias})


def copy_to_clipboard(text):
    """Put text on the system clipboard. Returns True on success. VESPER_NO_CLIPBOARD=1 turns it off (tests)."""
    if os.environ.get("VESPER_NO_CLIPBOARD"):
        return False
    if os.name == "nt":
        cmds = [["clip"]]
    elif sys.platform == "darwin":
        cmds = [["pbcopy"]]
    else:
        cmds = [["wl-copy"], ["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"]]
    for c in cmds:
        if not shutil.which(c[0]):
            continue
        try:
            # clip.exe reads UTF-16-LE (no BOM: a BOM is pasted as an extra character)
            data = text.encode("utf-16-le") if c[0] == "clip" else text.encode("utf-8")
            if subprocess.run(c, input=data, timeout=10).returncode == 0:
                return True
        except (OSError, subprocess.SubprocessError):
            pass
    return False


def submit(row, a, confirm=False):
    """Show one row for the form: short URL, the v1 line that is sent, and (unless --no-form) open the link.
    With confirm=True on a TTY, ask for Enter after the browser step; returns True when the learner confirmed."""
    cfg = load_config()
    if not cfg.get("form_url"):
        print("\nRow for the shared sheet (tab-separated):\n" + "\t".join(str(row.get(k, "")) for k in ROW_FIELDS))
        return False
    short = cfg.get("short_url") or cfg["form_url"]
    print("\n  RESULTS FORM:  %s" % c_link(short))
    print("  Fields: alias = %s, all_results = these lines:\n" % row.get("alias", ""))
    print(all_results_text([row]))
    if getattr(a, "no_form", False):
        return False
    again = "python workshop.py form %s %s" % (row.get("run_id", ""), row.get("stage", ""))
    if webbrowser.open(form_link([row], cfg)):
        print("\n  The form opens in a NEW browser window, with these values filled in.")
        print("  Check them and click Submit.")
    else:
        print("\n  The browser did not open. Open the form URL, type the alias, paste the lines above into all_results, and click Submit.")
    print("  Window closed by mistake? Open it again:  %s" % again)
    if confirm and sys.stdout.isatty() and sys.stdin and sys.stdin.isatty():
        return ask("\n  Click Submit in the browser, then press Enter (s = skip this one): ", "").lower() != "s"
    return False


SUBMIT_CMD = "python workshop.py submit"
SAVED_LINE = "Saved. You submit all results at the end:  python workshop.py submit"


def all_done_box(reg, show=True):
    """The ordered last steps when no agent is working: unlock (once), grade, show, submit."""
    steps = []
    if not os.path.exists(grader_path()):
        steps.append("python workshop.py unlock 4 <password from the slide>")
    if any(r["stage"] in ("1", "3") and r["grading"] == "ungraded" for r in reg.data["rows"].values()):
        steps.append("python workshop.py grade")
    if show:
        steps.append("python workshop.py show")
    steps.append(SUBMIT_CMD)
    next_box(["%d. %s" % (i, x) for i, x in enumerate(steps, 1)], "all agents are done. Now:")


def mark_submitted(reg, row):
    r = reg.row(row["run_id"], row["stage"])
    r["submitted_rev"] = int(r.get("revision") or 1)
    reg.save()


def needs_submit(r):
    sr = r.get("submitted_rev")
    return sr in (None, "") or int(r.get("revision") or 1) > int(sr)


RESULTS_HEADER = "vesper-results v1"
# `submit` never puts results in the link: Microsoft sign-in copies the whole link (base64) into its redirect
# and rejects form links above ~2,300 characters (AADSTS90015, measured 2026-10-21). The results go to the
# clipboard and the learner pastes them into all_results: ONE window and ONE response.
MAX_TEXT = 3800                    # a Forms long answer holds 4,000 characters; about 8 results fit
LINE_SKIP = ("alias",)             # the alias has its own form field
SHA_LEN = 12
LOCKED_MSG = "Unlock the grader first:  python workshop.py unlock 4 <password from the slide>  (then run submit again)"


def esc_value(v):
    v = str(v)
    for ch, code in (("%", "%25"), (";", "%3B"), ("=", "%3D"), ("\r", "%0D"), ("\n", "%0A")):
        v = v.replace(ch, code)
    return v


def all_results_text(rows):
    """One line per row; empty fields are left out (the reader treats a missing key as empty)."""
    lines = [RESULTS_HEADER]
    for r in rows:
        parts = []
        for k in ROW_FIELDS:
            v = "" if r.get(k) is None else str(r.get(k))
            if k in LINE_SKIP or v == "":
                continue
            if k == "solution_sha":
                v = v[:SHA_LEN]
            parts.append("%s=%s" % (k, esc_value(v)))
        lines.append(";".join(parts))
    return "\n".join(lines)


def grade_ungraded(reg):
    """Grade every ungraded row (the code of `grade`, short lines)."""
    for r in [r for r in reg.data["rows"].values() if r["grading"] == "ungraded"]:
        snap = snap_path(r["run_id"], r["stage"])
        name = reg.data["runs"].get(r["run_id"], {}).get("name", "")
        score, status = grade_snapshot(r["task"], snap if os.path.exists(snap) else None, name)
        reg.set_row(r["run_id"], r["stage"], {"score": score, "grading": status,
                                              "revision": int(r["revision"] or 1) + 1})
        reg.save()
        reg.write_csv()
        print("%s stage %s: score %s" % (r["run_id"], r["stage"], score))


def cmd_submit(a):
    reg = Registry.load()
    if not [r for r in reg.data["rows"].values() if needs_submit(r)]:
        print("Nothing to submit. All results are submitted.")
        return 0
    if any(r["stage"] in ("1", "3") and r["grading"] == "ungraded" for r in reg.data["rows"].values()):
        if not os.path.exists(grader_path()):
            print(LOCKED_MSG)
            return 1
        print("Grading first:")
        grade_ungraded(reg)
        reg = Registry.load()
    rows = sorted([r for r in reg.data["rows"].values() if needs_submit(r)],
                  key=lambda r: (str(r["stage"]), float(r["start"] or 0)))
    tty = sys.stdout.isatty() and bool(sys.stdin) and sys.stdin.isatty() and not getattr(a, "no_form", False)
    if not tty:
        a.no_form = True               # print only: no browser, nothing marked
    cfg = load_config()
    if not cfg.get("form_url") or not cfg.get("all_results_field"):
        for r in rows:
            submit(r, a)
        return 0
    link = alias_link(rows[0].get("alias", ""), cfg)
    paste = "Cmd+V" if sys.platform == "darwin" else "Ctrl+V"
    parts = split_text(rows)
    n = len(parts)
    print("\n  RESULTS FORM:  %s" % c_link(cfg.get("short_url") or cfg["form_url"]))
    print("  %d results to submit, in %s." % (len(rows), "ONE form response" if n == 1 else "%d form responses" % n))
    done = 0
    for i, g in enumerate(parts, 1):
        text = all_results_text(g)
        part = "" if n == 1 else " (response %d of %d)" % (i, n)
        if not tty:
            print("\n  Form link (alias filled in)%s:\n%s\n\n  Paste these lines into all_results:\n%s" % (part, link, text))
            continue
        copied = copy_to_clipboard(text)
        opened = webbrowser.open(link)
        print("\n  1. %s" % ("The form opens in your browser, with your alias filled in%s." % part if opened else
                             "Open this link%s (the browser did not open):\n     %s" % (part, link)))
        print("     If Forms asks 'Use previous draft or New draft?', click New draft.")
        if copied:
            print("  2. Click the all_results field and press %s. Your results are on the clipboard." % paste)
        else:
            print("  2. Copy ALL the lines between the two marks below and paste them into the all_results field.")
        print("  3. Click Submit, then press Enter here.")
        print("\n  ----- all_results (%d lines) -----\n%s\n  ----- end -----" % (len(g) + 1, text))
        if ask("\n  Press Enter when submitted (s = skip, mark nothing): ", "").lower() == "s":
            print("\nNothing marked%s. Run submit again when you are ready." % part)
            continue
        for r in g:
            mark_submitted(reg, r)
        done += len(g)
    if tty:
        print("\nAll %d results submitted" % done if done == len(rows) else
              "\n%d of %d results submitted (run submit again for the rest)" % (done, len(rows)))
    return 0


def split_text(rows):
    """Groups of rows whose all_results text fits one Forms answer (MAX_TEXT). Nearly always one group."""
    groups, cur = [], []
    for r in rows:
        if cur and len(all_results_text(cur + [r])) > MAX_TEXT:
            groups.append(cur)
            cur = []
        cur.append(r)
    if cur:
        groups.append(cur)
    return groups


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


def grade_snapshot(task, path, name=""):
    if not os.path.exists(grader_path()):
        return "", "ungraded"
    if not path:
        return "0", "graded"
    cmd = [sys.executable, grader_path(), task, path, "--bin", vesper_bin()]
    if task == "T6":
        cmd += ["--name", T6F.normalise(name)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300,
                           env=dict(os.environ, VESPER_NO_LOG="1"))
        return str(json.loads(r.stdout)["score"]), "graded"
    except Exception as e:  # noqa: BLE001
        print("grading failed: %s" % e)
        return "", "ungraded"


def _half_ok():
    """Half blocks need a console that can encode them; a TTY is switched to utf-8 when it cannot."""
    try:
        if sys.stdout.isatty() and "utf" not in (sys.stdout.encoding or "").lower():
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    try:
        "█▀▄".encode(sys.stdout.encoding or "ascii")
        return True
    except Exception:  # noqa: BLE001
        return False


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
        on = lambda x, y: bool(fr[y * 64 + x])
        if _half_ok():
            ch = {(1, 1): "█", (1, 0): "▀", (0, 1): "▄", (0, 0): " "}
            rows = ["".join(ch[(on(x, y), on(x, y + 1))] for x in range(64)) for y in range(0, 48, 2)]
        else:
            rows = ["".join("#" if (on(x, y) or on(x, y + 1)) else " " for x in range(64))
                    for y in range(0, 48, 2)]
        return "Frame %d of your game:\n+%s+\n%s\n+%s+" % (
            frame, "-" * 64, "\n".join("|" + r + "|" for r in rows), "-" * 64)
    except Exception:  # noqa: BLE001
        return ""
    finally:
        shutil.rmtree(d, ignore_errors=True)


COST_NOTE = "  Estimated cost under the kit's price assumptions."
OBSERVED_NOTE = "  Observed results: one attempt per condition. Check pass/fail before time or cost; reliability is unknown."
UNMATCHED_NOTE = "  Settings differ: this is not a matched comparison."
FAILED_NOTE = "  At least one attempt failed. Costs describe attempts, not equal-quality savings."


SHOW_COLS = [("run_id", 16), ("stage", 5), ("task", 4), ("model", 20), ("elapsed_min", 7), ("emulator_runs", 6),
             ("tok_in", 9), ("tok_out", 8), ("cost_usd", 7), ("score", 9), ("grading", 9)]
SHOW_NAMES = {"elapsed_min": "time min", "emulator_runs": "runs", "tok_in": "tokens in", "tok_out": "tokens out",
              "cost_usd": "cost USD", "run_id": "run"}


def run_summary(row, stage=None):
    """One summary line per run (wrapped to the width), plus a score line for graded stages."""
    el, cost = _val(row, "elapsed_min"), _val(row, "cost_usd")
    mem = {"yes": "ON", "no": "off"}.get(row.get("memory_used") or "", "unknown")
    iso = {"not_detected": "OK", "detected": "CHECK (detected)"}.get(row.get("isolation") or "", "unknown")
    chunks = ["Time %s" % ("unknown" if el is None else "%.1f min" % el),
              "Cost %s" % ("unknown" if cost is None else "$%.2f (estimate)" % cost),
              "Memory " + mem, "Isolation " + iso]
    out = chunk_lines(chunks)
    stage = stage or row.get("stage")
    if stage in ("1", "3"):
        sc = ("%s %s" % (row.get("score", ""), verdict(row))).strip() if _val(row, "score") is not None else "not graded"
        sl = ["Score " + sc]
        if str(row.get("emulator_runs", "")).strip() not in ("", "unknown"):
            sl.append("Runs %s" % row["emulator_runs"])
        out += chunk_lines(sl)
    return "\n".join(out)


def run_warnings(row):
    """Lines only when something is wrong: memory ON, isolation detected, overrun."""
    out = []
    if row.get("memory_used") == "yes":
        out.append("  WARNING: memory was ON. The agent could read earlier sessions (see the debrief).")
    if row.get("isolation") == "detected":
        out.append("  CHECK: the agent may have read outside the run folder.")
        if row.get("isolation_note"):
            out.append("    " + row["isolation_note"])
    if row.get("overrun") == "yes":
        out.append("  Over the 10-minute time box: flagged in the results.")
    return out


def show_rows(rows, note=True):
    """Results: a table when the terminal fits it, else one short key: value block per row."""
    cols = SHOW_COLS
    table = sum(w for _, w in cols) + 2 * (len(cols) - 1) <= min(term_cols(), MAXW)
    if table:
        print("  ".join(n.ljust(w) for n, w in cols))
    for r in rows:
        tin = sum(int(r.get(k) or 0) for k in ("tok_uncached", "tok_cache_read", "tok_cache_write")
                  if str(r.get(k, "")).isdigit())
        mdl = r.get("model", "")
        if mdl and r.get("effort"):
            mdl = "%s/%s" % (mdl, r["effort"])
        sc = ("%s %s" % (r.get("score", ""), verdict(r))).strip()
        v = dict(r, model=mdl, score=sc, tok_in=M.fmt_k(tin) if tin else "", tok_out=M.fmt_k(int(r["tok_out"])) if str(r.get("tok_out", "")).isdigit() else "")
        if table:
            print("  ".join(str(v.get(n, ""))[:w].ljust(w) for n, w in cols))
            continue
        print("\n  %s" % v.get("run_id", ""))
        for n, _ in cols[1:]:
            if str(v.get(n, "")).strip():
                print("    %s: %s" % (SHOW_NAMES.get(n, n), v[n]))
    if note and any(str(r.get("cost_usd", "")).strip() for r in rows):
        print(COST_NOTE)


def _val(r, *keys):
    """Sum of the fields, or None when all of them are empty."""
    vals = [str((r or {}).get(k, "")).strip() for k in keys]
    vals = [v for v in vals if v]
    try:
        return sum(float(v) for v in vals) if vals else None
    except ValueError:
        return None


COMPARE = [("Time (min)", ("elapsed_min",), "%.1f"),
           ("Emulator runs", ("emulator_runs",), "%d"),
           ("Tokens in", ("tok_uncached", "tok_cache_read", "tok_cache_write"), "k"),
           ("Tokens out", ("tok_out",), "k"),
           ("Cost (USD)", ("cost_usd",), "%.2f"),
           ("Score", ("score",), "%d")]


# Lab detail, not printed: Haiku 0/6, gpt-6-luna 0/6.
T6_BASELINE = "small model, no skill: 0/12 pass in 5 min"


def color_change(ch):
    """Pad to 10, then colour: real savings green, real increases red, zero plain."""
    chc = ch.rjust(10)
    if ch in ("+0%", "-0%"):
        return chc
    if ch.startswith("-"):
        return c_ok(chc)
    if ch.startswith("+"):
        return c_err(chc)
    return chc


def tasks_word(n):
    return "task" if n == 1 else "tasks"


def settings_match(rw, rc):
    """'same': same non-empty model and same non-empty effort. 'no_effort': same non-empty model and BOTH
    efforts empty (Claude Code and Cursor do not log effort). '' otherwise: models differ or are unknown,
    efforts differ, or only one effort is known."""
    g = lambda r, k: str((r or {}).get(k, "")).strip()
    if not g(rw, "model") or g(rw, "model") != g(rc, "model"):
        return ""
    ew, ec = g(rw, "effort"), g(rc, "effort")
    if not ew and not ec:
        return "no_effort"
    return "same" if ew and ew == ec else ""


def same_settings(rw, rc):
    """True when the pair is a matched comparison (see settings_match)."""
    return bool(settings_match(rw, rc))


SAME_LABEL = {"same": " (same model)", "no_effort": " (same model; effort not recorded)"}


def verdict(row):
    """'PASS' or 'FAIL' next to a score; '' while the row has no score."""
    if _val(row, "score") is None:
        return ""
    return "PASS" if passed(row) else "FAIL"


def compare_control(reg, rw, rc, task="T3", note=""):
    """Task WITH the skill (rw) vs WITHOUT the skill (rc, control), same parent."""
    match = settings_match(rw, rc)
    if match:
        banner("%s: WITH vs WITHOUT the skill%s%s" % (task, SAME_LABEL[match], note))
    else:
        banner("%s: WITH vs WITHOUT the skill%s" % (task, note))
        print(UNMATCHED_NOTE)
    print("\n" + c_bold("  %-15s %16s %16s %10s" % ("", "without", "with skill", "change")))
    print("  %-15s %16s %16s %10s" % ("", rc["run_id"], rw["run_id"], ""))
    print("  " + "-" * 60)
    failed = "FAIL" in (verdict(rc), verdict(rw))
    for name, keys, f in COMPARE:
        a, b = _val(rc, *keys), _val(rw, *keys)
        fmt = lambda x: "-" if x is None else (M.fmt_k(int(x)) if f == "k" else f % x)
        ca, cb = fmt(a), fmt(b)
        if name == "Score":
            ca, cb = ("%s %s" % (ca, verdict(rc))).strip(), ("%s %s" % (cb, verdict(rw))).strip()
        ch = "%+d%%" % round((b - a) / a * 100) if a and b is not None and name != "Score" and not failed else ""
        print("  %-15s %16s %16s %s" % (name, ca, cb, color_change(ch)))
    if failed:
        print("\n" + FAILED_NOTE)
    if _val(rc, "score") is None or _val(rw, "score") is None:
        print("\n  Score not graded yet. Run:\n  python workshop.py unlock 4 <password from the slide>\n"
              "  python workshop.py grade")


T6_NOTE = " - different task; shares components with T3"


def _gain(rw, rc):
    """Score points of the skill run over its control; None when a score is missing."""
    sw, sc = _val(rw, "score"), _val(rc, "score")
    if sw is None or sc is None:
        return None
    return sw - sc


def leakage_line(reg, parent):
    """Observed score gains, when both pairs (T3 and T6, skill vs control) are graded. No verdict."""
    g = {}
    for r in sorted(reg.data["rows"].values(), key=lambda r: float(r["start"] or 0)):   # earliest attempt
        run = reg.data["runs"].get(r["run_id"], {})
        if r["stage"] == "3" and run.get("parent") == parent:
            g.setdefault((r["task"], is_control(run) or r.get("method") == "none"), r)
    gains = [_gain(g.get((t, False)), g.get((t, True))) if (t, False) in g and (t, True) in g else None
             for t in ("T3", "T6")]
    if None in gains:
        return ""
    return ("  Leakage check: Observed score gains: T3 %+d; T6 %+d. "
            "These results neither identify nor rule out answer reuse." % (round(gains[0]), round(gains[1])))


def payback(reg, r1, r2, r3, t6=False, shown_table=False):
    """What writing the skill cost (stage-2 row). No break-even number."""
    s1s, s3s_ = _val(r1, "score"), _val(r3, "score")
    if r2:
        mins, cost = _val(r2, "elapsed_min"), _val(r2, "cost_usd")
        print("\n  Skill creation: %s min, %s estimated. Break-even not established."
              % ("unknown" if mins is None else "%.1f" % mins, "unknown" if cost is None else "$%.2f" % cost))
    if (s1s is None or s3s_ is None) and shown_table:
        print("\n  Score not graded yet. %s, run:\n  python workshop.py unlock 4 <password from the slide>\n"
              "  python workshop.py grade" % (AFTER_ALL if reg.actives("3") else "Now"))


def show_compare(reg, s3_id=None, cost_note=True):
    """Real pairs only: the same task on the same model, WITH vs WITHOUT the skill (T3 and T6).
    The stage-1 writer (large model) is never put in a table; it appears in one cost line."""
    rows3 = [r for r in reg.data["rows"].values() if r["stage"] == "3"]
    runs = reg.data["runs"]
    pick = [r for r in rows3 if not s3_id or r["run_id"] == s3_id]
    parents = []
    for r in sorted(pick, key=lambda r: float(r["start"] or 0)):
        p = runs.get(r["run_id"], {}).get("parent", "")
        if p not in parents:
            parents.append(p)
    want_task = {r["task"] for r in pick} if s3_id else {"T3", "T6"}
    printed_ll = set()
    if not pick:
        return
    print("\n" + OBSERVED_NOTE)
    if cost_note and any(str(r.get("cost_usd", "")).strip() for r in rows3):
        print(COST_NOTE)
    for parent in parents:
        mine = [r for r in rows3 if runs.get(r["run_id"], {}).get("parent") == parent]
        g = {}
        for r in sorted(mine, key=lambda r: float(r["start"] or 0)):    # repeat attempts: the earliest one
            run = runs.get(r["run_id"], {})
            g.setdefault((r["task"], is_control(run) or r.get("method") == "none"), r)
        reg_ctl = {run["task"] for run in runs.values()
                   if run.get("parent") == parent and is_control(run)}
        if not any(k[1] for k in g) and not reg_ctl:
            show_rows(mine, note=False)
            print("\n  No control runs: run python workshop.py new s3 --task all for a fair comparison.")
            continue
        shown_t3 = None
        for t in ("T3", "T6"):
            if t not in want_task:
                continue
            w, ctl = g.get((t, False)), g.get((t, True))
            if w and ctl:
                compare_control(reg, w, ctl, t, T6_NOTE if t == "T6" else "")
                if t == "T3":
                    shown_t3 = w
            elif w:
                if t in reg_ctl:
                    print("\n  %s: waiting for its control run (%s without skill)" % (t, t))
                else:
                    print("\n  %s: no control run" % t)
            elif ctl:
                print("\n  %s: waiting for the run WITH the skill (%s with skill)" % (t, t))
        ll = leakage_line(reg, parent)
        if ll and ll not in printed_ll:
            printed_ll.add(ll)
            print("\n" + ll)
        r1, r2 = reg.row(parent, "1"), reg.row(parent, "2")
        if r1 and r2:
            payback(reg, r1, r2, shown_t3 or {}, t6=shown_t3 is None)


def finish_stage(reg, rid, stage, a, grade=True):
    run = reg.data["runs"][rid]
    act = reg.get_active(rid)
    first = bool(act and act["stage"] == stage)
    row = reg.row(rid, stage)
    if first:
        t0, t1 = act["start"], time.time()
    else:
        t0, t1 = float(row["start"]), float(row["cutoff"])
    if not run.get("session"):
        run["session"] = pick_session(rid, run["folder"], t0)
    m = measure_stage(run, t0, t1)
    if not m["measurement"]:
        prev = row or {}
        if prev.get("measurement") == "manual":
            m.update({k: prev[k] for k in ("model", "tok_uncached", "tok_out", "cost_usd", "measurement")})
        elif run.get("auto"):
            m["measurement"] = "none"             # --auto never asks: the tool started the agent itself
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
    if runs is None and run.get("auto"):
        runs = next((x.get("emulator_runs") for x in M.cursor_sessions(
            (run.get("session") or {}).get("path") or "") if (run.get("session") or {}).get("agent") == "cursor"), None)
    fields.update(alias=reg.data.get("alias", ""), task=run["task"], agent=agent, method=run["method"],
                  parent_run_id=run["parent"], skill_source=run["skill_source"], skill_hash=run["skill_hash"],
                  skill_has_solution=run["skill_has_solution"], price_table=PRICE_TABLE,
                  start="%.0f" % t0, cutoff="%.0f" % t1, wall_min="%.1f" % ((t1 - t0) / 60),
                  emulator_runs="unknown" if runs is None else runs)
    if first:
        # 1, or one more than a failed --auto row of this run (that row may be submitted already)
        fields["revision"] = int(row.get("revision") or 0) + 1 if row and row.get("stopped") == "error" else 1
        if grade:
            snap, sha = snapshot_solution(rid, run, stage)
            fields["solution_sha"] = sha
            score, status = grade_snapshot(run["task"], snap, run.get("name", ""))
            fields.update(score=score, grading="partial" if getattr(a, "partial", False) else status)
        else:
            fields.update(score="", grading="none")
        reg.end_active(rid)
    else:
        fields["revision"] = int(row.get("revision") or 1) + 1
    fields["memory_used"] = detect_memory_used(session_paths(run.get("session")), t0, t1)
    iso, iso_note = detect_outside_reads(session_paths(run.get("session")), t0, t1, run["folder"],
                                         writer=stage in ("1", "2"))
    outside = outside_workdirs(session_paths(run.get("session")), t0, t1, run["folder"])
    fields["isolation"], fields["isolation_note"] = isolation_with_workdirs(iso, iso_note, outside)
    p0 = prompt_time(session_paths(run.get("session")), rid, t0, t1) if stage == "3" and not run.get("auto") else None
    fields["overrun"] = overrun_flag(stage, t0 if p0 is None else p0, t1)   # 10 min from the prompt, not the set-up
    if run.get("auto") and stage == "3":
        fields["overrun"] = "no"           # --auto: the start is the launch and the tool stops the run at the box
    fields["stopped"] = run.get("stopped", "")
    fields["error_note"] = run.get("error_note", "")
    fields["settings_confirmed"] = run.get("settings_confirmed", "")
    reg.set_row(rid, stage, fields)
    reg.save()
    reg.write_csv()
    return reg.row(rid, stage)


def cmd_done(a):
    reg = Registry.load()
    want = getattr(a, "run_id", None)
    if want:
        act = reg.get_active(want)
        if act and act["stage"] == "2":
            sys.exit("Stage 2 ends with:  python workshop.py harvest")
        if act:
            rid, stage = want, act["stage"]
        else:
            done = [r for r in reg.data["rows"].values() if r["run_id"] == want and r["stage"] in ("1", "3")]
            if not done:
                sys.exit("No active or finished stage 1 or 3 is called %s. See:  python workshop.py show" % want)
            rid, stage = want, done[0]["stage"]
            print("Updating the finished stage %s of %s (same cutoff, same frozen solution)." % (stage, rid))
    else:
        acts = [x for x in reg.actives() if x["stage"] in ("1", "3")]
        if not acts and reg.actives("2"):
            sys.exit("Stage 2 ends with:  python workshop.py harvest")
        if len(acts) == 1:
            rid, stage = acts[0]["run_id"], acts[0]["stage"]
        elif acts:
            rid, stage = choose_active(reg, acts)
        else:
            rows = [r for r in reg.data["rows"].values() if r["stage"] in ("1", "3")]
            if not rows:
                sys.exit("No stage is active. Start with:  python workshop.py new s1")
            last = max(rows, key=lambda r: float(r["cutoff"] or 0))
            rid, stage = last["run_id"], last["stage"]
            print("Updating the finished stage %s of %s (same cutoff, same frozen solution)." % (stage, rid))
    row = finish_stage(reg, rid, stage, a)
    clear_screen()
    print_wrong_folder(reg.data["runs"][rid], row)
    banner("STAGE %s FINISHED   run %s" % (stage, rid))
    print()
    print(run_summary(row, stage))
    warn = run_warnings(row)
    if warn:
        print("\n" + "\n".join(warn))
    fr = ascii_frame(snap_path(rid, stage))
    if fr:
        print("\n" + fr)
    if row["grading"] == "ungraded" and stage == "3":   # stages 1-2: grading is at the end (the last NEXT box says how)
        who = AFTER_ALL if stage == "3" and reg.actives("3") else "After the agent is done"
        print("\nNot graded yet. %s, run:\n  python workshop.py unlock 4 <password from the slide>\n"
              "  python workshop.py grade" % who)
    print("\n" + SAVED_LINE)
    if stage == "1":
        next_box("python workshop.py skill", "stage 2 (the SAME agent thread writes a skill), run:")
    else:
        show_compare(reg, rid)
        left = reg.actives("3")
        if left:
            still_working_box(reg, left)
        else:
            all_done_box(reg)
    return 0


def cmd_grade(a):
    reg = Registry.load()
    todo = [r for r in reg.data["rows"].values() if r["grading"] == "ungraded"]
    if not todo:
        print("Nothing to grade.")
        return 0
    if not os.path.exists(grader_path()):
        sys.exit("The grader is locked:  python workshop.py unlock 4 <password from the slide>")
    clear_screen()
    grade_ungraded(reg)
    print("\n" + SAVED_LINE)
    show_compare(reg)
    all_done_box(reg)
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


MIN_BLOCK = 5      # a match counts only when this many lines in a row are the same
_REG_RE = re.compile(r"\br\d{1,2}\b")
_LABEL_DEF = re.compile(r"^\s*([A-Za-z_.][\w.]*)\s*:")
_EQU_DEF = re.compile(r"^\s*\.(?:equ|define|set)\s+([A-Za-z_]\w*)", re.I)


def _norm_lines(text):
    """[(line number, normalised text)] without blank lines. Comments go; labels and registers become
    placeholders, so a renamed label or register still matches."""
    raw = [(i, re.sub(r"\s+", " ", ln.split(";", 1)[0].strip().lower())) for i, ln in enumerate(text.splitlines(), 1)]
    raw = [(i, ln) for i, ln in raw if ln]
    names = set()
    for _, ln in raw:
        m = _LABEL_DEF.match(ln) or _EQU_DEF.match(ln)
        if m:
            names.add(m.group(1))
    out = []
    for i, ln in raw:
        if names:
            ln = re.sub(r"(?<![\w.])(%s)(?![\w])" % "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True)), "LBL", ln)
        ln = _REG_RE.sub("REG", ln)
        out.append((i, re.sub(r"\s+", " ", ln)))
    return out


def _kit_lines():
    """Normalised lines of the kit's generic code (examples and guides): they do not count as the learner's."""
    kit = set()
    for sub in ("examples", "guides"):
        for dp, _, fs in os.walk(os.path.join(KIT, sub)):
            for n in fs:
                try:
                    with open(os.path.join(dp, n), encoding="utf-8", errors="replace") as f:
                        kit |= {t for _, t in _norm_lines(f.read())}
                except OSError:
                    pass
    return kit


GAME_SHARE = 0.5   # the skill holds at least this part of the stage-1 game -> "the finished game"


def solution_blocks(skill_dir, snapshot):
    """Return (blocks, share). A block is a dict: rel, a, b (skill lines), c, d (solution lines), n.
    share: part of the stage-1 solution lines (kit lines left out) covered by blocks of >= MIN_BLOCK lines."""
    if not (snapshot and os.path.exists(snapshot)):
        return [], 0.0
    with open(snapshot, encoding="utf-8", errors="replace") as f:
        sol = _norm_lines(f.read())
    kit = _kit_lines()
    # kit lines may sit inside a block (they bridge it), but they never count toward the block or the share
    sol_keys = [t for _, t in sol]
    countable = {k for k, (_, t) in enumerate(sol) if t not in kit}
    blocks, covered = [], set()
    for dp, dns, fs in os.walk(skill_dir):
        dns.sort()
        for n in sorted(fs):
            p = os.path.join(dp, n)
            try:
                with open(p, encoding="utf-8", errors="replace") as f:
                    lines = _norm_lines(f.read())
            except OSError:
                continue
            if not lines:
                continue
            sm = difflib.SequenceMatcher(None, [t for _, t in lines], sol_keys, autojunk=False)
            for m in sm.get_matching_blocks():
                idx = [k for k in range(m.b, m.b + m.size) if k in countable]
                if m.size < MIN_BLOCK or len(idx) < MIN_BLOCK:
                    continue
                lo, hi = idx[0] - m.b, idx[-1] - m.b          # a block starts and ends on a line of yours
                covered.update(idx)
                blocks.append({"rel": os.path.relpath(p, skill_dir).replace("\\", "/"),
                               "a": lines[m.a + lo][0], "b": lines[m.a + hi][0],
                               "c": sol[m.b + lo][0], "d": sol[m.b + hi][0], "n": hi - lo + 1})
    return blocks, (len(covered) / len(countable) if countable else 0.0)


def detect_solution(skill_dir, snapshot):
    """Return (found, share). found: [(rel, reason)], one per skill file with a block.
    share: part of the stage-1 solution lines (kit lines left out) that sit in blocks of the skill."""
    blocks, share = solution_blocks(skill_dir, snapshot)
    per = {}
    for b in blocks:
        per[b["rel"]] = per.get(b["rel"], 0) + b["n"]
    return [(rel, "%d lines in blocks of your T3 solution" % k) for rel, k in per.items()], share


REPEAT_NOTE = [
    "  Why stage 3 also runs a DIFFERENT task (T6):",
    "  A new agent can pass T3 again with your skill without real knowledge:",
    "    1. Memory: the agent remembers the earlier session.",
    "       (This is why memory is off in stage 3.)",
    "    2. The skill holds parts of the T3 answer itself.",
    "  So a T3 pass alone proves little. T6 is a different task: a gain",
    "  there shows knowledge that transfers.",
]


def harvest_note(share):
    """What the learner reads after harvest: no code, only the measured share and why T6 exists."""
    if share:
        head = ("  Your skill shares %d%% of its code with your T3 solution (a line match: "
                "it cannot tell a useful helper from the answer)." % round(share * 100))
    else:
        head = ("  No copied block of your T3 solution was found in your skill "
                "(a line match; it cannot see the answer in other words).")
    return [head] + REPEAT_NOTE


def block_lines(skill_dir, blocks):
    """The lines harvest prints for the blocks (see the W8 step)."""
    if not blocks:
        return ["  No block of your T3 solution was found in your skill "
                "(line match; it cannot see knowledge in your own words)."]
    out = []
    for b in blocks[:6]:
        out.append("  %s lines %d-%d = your T3 solution lines %d-%d (%d lines)" % (b["rel"], b["a"], b["b"], b["c"], b["d"], b["n"]))
        try:
            with open(os.path.join(skill_dir, b["rel"]), encoding="utf-8", errors="replace") as f:
                src = f.read().splitlines()
        except OSError:
            src = []
        shown = 0
        for ln in src[b["a"] - 1:b["b"]]:
            if ln.split(";", 1)[0].strip() and shown < 3:
                out.append("      " + ln.rstrip()[:100])
                shown += 1
    if len(blocks) > 6:
        out.append("  ... and %d more blocks" % (len(blocks) - 6))
    out.append("  These blocks in your skill come from your T3 solution. Knowledge or the answer? "
               "You will see this again in the leakage check.")
    return out


def cmd_skill(a):
    reg = Registry.load()
    acts2 = reg.actives("2")
    again = bool(acts2)                # run again during stage 2: show the prompt again
    if reg.actives() and not again:
        sys.exit("\n".join(active_lines(reg)))
    s1 = [r for r in reg.data["rows"].values() if r["stage"] == "1"]
    if not s1:
        sys.exit("Do stage 1 first:  python workshop.py new s1")
    rid = acts2[0]["run_id"] if again else max(s1, key=lambda r: float(r["cutoff"] or 0))["run_id"]
    if reg.row(rid, "2"):
        sys.exit("Stage 2 of %s is already done. Next:  python workshop.py new s3 --task all" % rid)
    run = reg.data["runs"][rid]
    clear_screen()
    if again:
        print("\n  Stage 2 is already running (the clock started at the first 'skill'). Here is the prompt again.")
    else:
        reg.start_active(rid, "2")
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
    acts2 = reg.actives("2")
    if not acts2:
        done2 = [r for r in reg.data["rows"].values() if r["stage"] == "2"]
        if done2:
            rid = max(done2, key=lambda r: float(r["cutoff"] or 0))["run_id"]
            acts = reg.actives()
            sys.exit("Stage 2 of %s is already harvested.\n"
                     "  Form again:  python workshop.py form %s 2\n"
                     "  Next:        %s" % (rid, rid, next_cmd(acts[-1]) if acts else "python workshop.py new s3 --task all"))
        sys.exit("harvest ends stage 2. Start stage 2 with:  python workshop.py skill")
    rid = acts2[0]["run_id"]
    run = reg.data["runs"][rid]
    src = os.path.join(run["folder"], "skill-out", "vesper16")
    if not os.path.exists(os.path.join(src, "SKILL.md")):
        g = find_global_vesper_skills()
        try:
            outside = outside_workdirs(session_paths(run.get("session")), float(acts2[0]["start"]), time.time(), run["folder"])
        except (ValueError, TypeError, KeyError):
            outside = []
        if outside:
            print("\n" + "\n".join(wrong_folder_block(outside, run["folder"], True)) + "\n")
            sk = skill_in_outside(outside)
            if sk:
                print("  A skill was written here instead: %s\n" % sk)
        sys.exit("No skill at %s\n%sAsk the agent to write it there, then run harvest again."
                 % (os.path.join(src, "SKILL.md"), ("It may be in a global folder: %s\n" % ", ".join(g)) if g else ""))
    base = os.path.join(ws_home(), ".skills", rid)
    dst = os.path.join(base, "vesper16")
    reg.add_item(base, "dir")
    reg.save()
    if os.path.exists(dst):
        rmtree(dst)
    shutil.copytree(src, dst)
    clear_screen()
    found, share = detect_solution(dst, snap_path(rid, "1"))
    blocks, _ = solution_blocks(dst, snap_path(rid, "1"))
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
    used = detect_method_used(session_paths(run.get("session")), float(row["start"]), float(row["cutoff"]))
    reg.set_row(rid, "2", {"method_used": used})
    reg.save()
    reg.write_csv()
    row = reg.row(rid, "2")
    g = find_global_vesper_skills()
    if g:
        banner("CHECK - a VESPER skill is in a global folder")
        print("\n  It would leak into stage 3:\n\n    " + "\n    ".join(g) + "\n")
        if a.remove_global or ask("  Remove these global copies? [y/N] ", "n").lower() == "y":
            for p in g:
                if not os.path.islink(p):
                    rmtree(p)
    print_wrong_folder(run, row, True)
    banner("STAGE 2 DONE: skill saved   run %s" % rid)
    print()
    print(run_summary(row, "2"))
    warn = run_warnings(row)
    if warn:
        print("\n" + "\n".join(warn))
    if status == "removed":
        print("  Shared T3 code: moved aside by the instructor (--move-aside)")
    print()
    print("\n".join(harvest_note(share)))
    print("\n  Optional (2 min): python workshop.py judge")
    if getattr(a, "blocks", False):      # instructor view: where the shared code is
        print("\n".join(block_lines(dst, blocks)))
    s3_choice_box(reg, "stage 3: FOUR new agents (T3, T3 control, T6, T6 control). Choose one:")
    return 0


def latest_harvested(reg):
    """Run id of the newest stage-1 run that has a harvested skill, or None."""
    rows = [r for r in reg.data["rows"].values() if r["stage"] == "1"
            and os.path.isfile(os.path.join(ws_home(), ".skills", r["run_id"], "vesper16", "SKILL.md"))]
    return max(rows, key=lambda r: float(r["cutoff"] or 0))["run_id"] if rows else None


def cmd_judge(a):
    """Build a read-only folder for an independent judge thread; print and copy the prompt."""
    reg = Registry.load()
    rid = a.run_id or latest_harvested(reg)
    if not rid:
        sys.exit("No harvested skill yet. Do stage 2:  python workshop.py skill  then  harvest")
    skill = os.path.join(ws_home(), ".skills", rid, "vesper16")
    if not os.path.isfile(os.path.join(skill, "SKILL.md")):
        sys.exit("Run %s has no harvested skill. Do stage 2 for it:  python workshop.py skill  then  harvest" % rid)
    snap = snap_path(rid, "1")
    if not os.path.isfile(snap):
        sys.exit("No T3 solution snapshot for run %s (%s). The judge needs it." % (rid, snap))
    folder = os.path.join(ws_home(), "judge-" + rid)
    reg.add_item(folder, "dir")
    reg.save()
    if os.path.exists(folder):
        rmtree(folder)
    os.makedirs(os.path.join(folder, "tasks"))
    shutil.copytree(skill, os.path.join(folder, "skill"))
    shutil.copy2(snap, os.path.join(folder, "t3-solution.vsa"))
    shutil.copy2(os.path.join(KIT, "tasks", "T3.md"), os.path.join(folder, "tasks", "T3.md"))
    shutil.copytree(os.path.join(KIT, "examples"), os.path.join(folder, "kit-examples"))
    prompt = render_prompt("judge", run_id=rid)
    banner("JUDGE - does your skill hold the T3 answer?        run %s" % rid)
    print("\n  A fresh thread judges the skill. The thread that wrote it would judge its own work,")
    print("  and it remembers its T3 solution.")
    print("\n  Folder for the judge:\n\n       %s" % folder)
    prompt_block(prompt)
    ok = copy_to_clipboard(prompt)
    if ok:
        print("\n  Open a NEW thread (any model; memory off) in the folder above, paste the prompt (it is on the")
        print("  clipboard), and read the answer. About 2 minutes. Nothing is graded or sent.")
    else:
        print("\n  Open a NEW thread (any model; memory off) in the folder above, copy the prompt between the")
        print("  PROMPT lines, paste it, and read the answer. About 2 minutes. Nothing is graded or sent.")
    s3_choice_box(reg, "when you have read the answer, go on to stage 3. Choose one:")
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
            sys.exit("The wiki skill is in locked part 3:  python workshop.py unlock 3 <password from the slide>")
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
    acts = reg.actives()
    if acts and a.part == "4":
        print("Warning: %s still active. Unlock the grader only after the agents are done."
              % ", ".join("stage %s of %s" % (x["stage"], x["run_id"]) for x in acts))
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
    clear_screen()
    if not rows:
        print("No results yet.")
    else:
        show_rows(rows)
        show_compare(reg, cost_note=False)          # show_rows printed the cost note: once per output
        if not reg.actives() and any(needs_submit(r) for r in rows):
            all_done_box(reg, show=False)
    for x in reg.actives():
        print("\nActive: stage %s of %s (%s). Next:  %s"
              % (x["stage"], x["run_id"], reg.data["runs"].get(x["run_id"], {}).get("task", ""), next_cmd(x)))
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
    if submit(row, a, confirm=True):
        mark_submitted(reg, row)
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
                                 session=None, name="")
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
    reg.start_active(rid, a.stage[1] + "s", t0)
    row = finish_stage(reg, rid, a.stage[1] + "s", a)
    show_rows([row])
    return 0


# ------------------------------------------------------------------ stage 3 --auto
# `new s3 --auto`: the tool starts the stage-3 agents itself (headless), stops each at the time box,
# and then finishes each run like `done <run_id>`. The manual flow is unchanged.
AUTO_TICK = 30             # seconds between two status blocks
AUTO_POLL = 0.5            # seconds between two checks of the processes
AUTO_BOX_SEC = None        # tests only: the time box in seconds (default: TIME_BOX_MIN minutes)
AUTO_CHECK_SEC = 180       # doctor --check-auto: the tiny run must end within this time
AUTO_MODEL = {"codex": "gpt-6-luna", "claude": "haiku", "cursor": "gpt-5.6-luna-high"}
AUTO_AGENTS = tuple(AUTO_MODEL)
CODEX_MIN = (0, 163)       # the npm `codex` 0.154 rejects gpt-6-luna on a ChatGPT account
FREE_PLAN_RE = re.compile(r"Named models unavailable|Free plans can only use Auto", re.I)
FREE_PLAN_MSG = "free plan: only Auto"
_sleep = time.sleep
AUTO_LABEL = {"t3": "T3 with skill", "n3": "T3 without skill", "t6": "T6 with skill", "n6": "T6 without skill"}


def _as_argv(path):
    return [sys.executable, path] if str(path).lower().endswith(".py") else [path]


def _exe_override(agent):
    p = os.environ.get("VESPER_%s_EXE" % agent.upper())
    return _as_argv(p) if p else None


def _version_tuple(text):
    m = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", text or "")
    return tuple(int(x or 0) for x in m.groups()) if m else None


def _run_text(argv, timeout=20):
    """Output (stdout + stderr) of a short CLI call, or '' when it cannot run or does not end in time."""
    try:
        rc, text = run_capture(argv, timeout)
    except OSError:
        return ""
    return "" if rc is None else text.strip()


def anon(text):
    """The text with the home folder written as ~ (error notes go to the shared sheet)."""
    text = str(text or "")
    for h in {user_home(), os.path.expanduser("~")}:
        if h and len(h) > 3:
            for v in {h, h.replace("\\", "/"), h.replace("/", "\\")}:
                text = re.sub(re.escape(v), "~", text, flags=re.I)
    return text


def _exe_version(argv):
    if os.environ.get("VESPER_DOCTOR_SKIP_CLI"):
        return "skipped"
    out = _run_text(argv + ["--version"])
    return out.splitlines()[0].strip() if out else ""


def find_cli(agent):
    """(argv, '') for the CLI that --auto starts, or (None, why). Codex = the Codex app's own codex.exe
    (newest); the npm codex only when it is 0.163 or newer. Env VESPER_<AGENT>_EXE overrides (tests)."""
    ov = _exe_override(agent)
    if ov:
        return ov, ""
    lad = os.environ.get("LOCALAPPDATA", "")
    if agent == "codex":
        found = glob.glob(os.path.join(lad, "OpenAI", "Codex", "bin", "*", "codex.exe")) if lad else []
        if found:
            return [max(found, key=os.path.getmtime)], ""
        p = shutil.which("codex")
        if not p:
            return None, "codex was not found"
        argv = _as_argv(p)
        v = _exe_version(argv)
        if v == "skipped" or (_version_tuple(v) or (0, 0)) >= CODEX_MIN:
            return argv, ""
        return None, "codex on PATH is too old (%s); it needs 0.163 or newer" % (v or "version unknown")
    if agent == "cursor":
        p = os.path.join(lad, "cursor-agent", "cursor-agent.cmd") if lad else ""
        if p and os.path.isfile(p):
            return [p], ""
        p = shutil.which("cursor-agent") or shutil.which("agent")
        return (_as_argv(p), "") if p else (None, "cursor-agent was not found")
    p = shutil.which("claude")
    return (_as_argv(p), "") if p else (None, "claude was not found")


def install_help(agent):
    """How to get the CLI, in the form that works in the learner's shell (no %VAR% syntax)."""
    if agent == "cursor":
        if os.name == "nt":
            return ["Install (PowerShell):",
                    "  irm 'https://cursor.com/install?win32=true' | iex",
                    "Then open a NEW PowerShell window (it needs the new PATH) and log in:",
                    "  agent login   (it opens the browser)"]
        return ["Install:  curl https://cursor.com/install -fsS | bash", "Then log in:  agent login"]
    if agent == "codex":
        return ["Install the Codex app (it contains codex.exe 0.163 or newer), or update the codex CLI."]
    return ["Install Claude Code:  npm install -g @anthropic-ai/claude-code"]


def cursor_logged_in(argv):
    """True / False from `status` ('Logged in as ...' / 'Not logged in'), None when unknown."""
    out = _run_text(argv + ["status"])
    if re.search(r"not logged in", out, re.I):
        return False
    return True if re.search(r"logged in", out, re.I) else None


def auto_ready(agent):
    """(ok, text, fix_lines): can `--auto` start this agent? Never makes a model call."""
    if agent not in AUTO_AGENTS:
        return False, "not available for this agent (codex, claude or cursor only)", []
    argv, why = find_cli(agent)
    if not argv:
        return False, why, install_help(agent)
    ver = _exe_version(argv)
    if agent == "cursor" and not os.environ.get("VESPER_DOCTOR_SKIP_CLI"):
        li = cursor_logged_in(argv)
        if li is False:
            return False, "Cursor is not logged in", ["Log in:  agent login   (it opens the browser)"]
        if li is None:
            ver = (ver + ", login unknown").strip(", ")
    return True, "ready (%s)" % (ver if ver and ver != "skipped" else "CLI found"), []


def cursor_rules_note():
    """(always_on, text): alwaysApply rules in ~/.cursor/rules, else a one-line reminder."""
    d = os.path.join(user_home(), ".cursor", "rules")
    for dp, _, fns in os.walk(d):
        for fn in fns:
            try:
                with open(os.path.join(dp, fn), encoding="utf-8", errors="replace") as f:
                    if re.search(r"alwaysApply\s*:\s*true", f.read(4000), re.I):
                        return True, ("Cursor has alwaysApply rules in %s. --auto runs load them: "
                                      "turn them off for a clean run." % d)
            except OSError:
                pass
    return False, ("Cursor loads User Rules and alwaysApply rules in every run (Settings > Rules). "
                   "Turn them off for a clean --auto run.")


def _cmd_script(argv):
    return os.name == "nt" and bool(argv) and str(argv[0]).lower().endswith((".cmd", ".bat"))


CMD_MAX = 8000             # cmd.exe cuts a command line at 8191 characters
# Claude Code (dontAsk = every tool that is not in this list is refused): run the emulator, read, edit and
# write only below the run folder. "./**" is relative to the working folder (the run folder).
CLAUDE_TOOLS = ["Bash(bin/vesper:*)", "Bash(./bin/vesper:*)", "Bash(bin/vesper.exe:*)", "Bash(./bin/vesper.exe:*)",
                "Read", "Glob", "Grep", "Edit(./**)", "Write(./**)", "Skill"]


class LaunchError(Exception):
    """--auto cannot start this agent in a safe way (for example the command line is too long)."""


def build_auto_cmd(agent, argv, model, folder, prompt):
    """(command line, stdin text) of one headless stage-3 run (flags tested on 2026-10-23).
    The prompt is never an argument of a .cmd/.bat launcher for Codex and Claude: cmd.exe cuts an argument at
    the first new line and drops every later flag. They read the prompt from stdin. Cursor has only a .cmd
    on Windows: its prompt is flattened to one line, and a command line above CMD_MAX is refused."""
    script = _cmd_script(argv)
    if agent == "codex":
        eff = "model_reasoning_effort=high" if script else 'model_reasoning_effort="high"'   # cmd.exe breaks \"
        return argv + ["exec", "-m", model, "-c", eff, "-c", "features.memories=false", "-s", "workspace-write",
                       "--skip-git-repo-check", "-C", folder, "-"], prompt
    if agent == "cursor":
        if script:                    # a .cmd file cannot take new lines or double quotes in an argument
            prompt = " ".join(prompt.split()).replace('"', "'")
            if "%" in prompt or "!" in prompt:      # cursor-agent.cmd uses enabledelayedexpansion
                raise LaunchError("the prompt has %% or ! (cursor-agent.cmd cannot pass them)")
        cmd = argv + ["-p", "--model", model, "--output-format", "stream-json", "--force", "--sandbox", "enabled",
                      "--trust", "--workspace", folder, prompt]
        if script and len(subprocess.list2cmdline(cmd)) > CMD_MAX:
            raise LaunchError("the command line is too long for cursor-agent.cmd (%d characters)"
                              % len(subprocess.list2cmdline(cmd)))
        return cmd, None
    return argv + ["-p", "--model", model, "--output-format", "json", "--permission-mode", "dontAsk",
                   "--setting-sources", "project", "--allowedTools"] + CLAUDE_TOOLS, prompt


def start_agent(cmd, folder, out_path, stdin_text=None):
    """Start the agent in the background; stdout and stderr go to out_path; stdin_text (if any) is its stdin.
    Windows: the agent goes into its own Job Object, so every process it starts dies with it (and with
    this tool). Returns the Popen."""
    kw = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
    src = None
    if stdin_text is not None:
        src = tempfile.TemporaryFile()
        src.write(stdin_text.encode("utf-8"))
        src.seek(0)
    try:
        with open(out_path, "wb") as out:
            proc = subprocess.Popen(cmd, cwd=folder, stdin=src if src else subprocess.DEVNULL, stdout=out,
                                    stderr=subprocess.STDOUT, **kw)
    finally:
        if src:
            src.close()
    proc._vesper_job = _job_for(proc)
    return proc


_K32 = []


def _k32():
    """kernel32 with the argument types this file uses (Windows only)."""
    if not _K32:
        import ctypes
        from ctypes import wintypes
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.CreateJobObjectW.restype = wintypes.HANDLE
        k.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        k.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        k.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        k.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        k.CloseHandle.argtypes = [wintypes.HANDLE]
        k.OpenProcess.restype = wintypes.HANDLE
        k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        k.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        k.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(ctypes.c_uint64)] * 4
        _K32.append(k)
    return _K32[0]


def _job_for(proc):
    """Windows: put proc in a new Job Object with KILL_ON_JOB_CLOSE (its children join the job too).
    Closing the handle (kill_tree, or this tool ends in any way) kills every process in the job.
    Returns the job handle, or None (POSIX, VESPER_NO_JOB=1, or the call failed: taskkill is the fallback)."""
    if os.name != "nt" or os.environ.get("VESPER_NO_JOB"):
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class Basic(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                        ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                        ("SchedulingClass", wintypes.DWORD)]

        class Extended(ctypes.Structure):
            _fields_ = [("Basic", Basic), ("Io", ctypes.c_uint64 * 6), ("ProcessMemoryLimit", ctypes.c_size_t),
                        ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                        ("PeakJobMemoryUsed", ctypes.c_size_t)]
        k = _k32()
        job = k.CreateJobObjectW(None, None)
        if not job:
            return None
        info = Extended()
        info.Basic.LimitFlags = 0x2000                  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if k.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)) and \
                k.AssignProcessToJobObject(job, int(proc._handle)):
            return job
        k.CloseHandle(job)
    except Exception:  # noqa: BLE001  (no job: taskkill /T is the fallback)
        pass
    return None


def pid_alive(pid, since=None):
    """True when process pid runs (and, on Windows, was created before `since`, so a reused pid is not alive)."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if os.name != "nt":
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except OSError:
            return True
        return True
    try:
        import ctypes
        from ctypes import wintypes
        k = _k32()
        h = k.OpenProcess(0x1000, False, pid)            # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return ctypes.get_last_error() == 5           # access denied: it exists
        try:
            code = wintypes.DWORD()
            if not k.GetExitCodeProcess(h, ctypes.byref(code)) or code.value != 259:   # STILL_ACTIVE
                return False
            if since:
                t = [ctypes.c_uint64() for _ in range(4)]
                if k.GetProcessTimes(h, *[ctypes.byref(x) for x in t]):
                    created = t[0].value / 1e7 - 11644473600     # FILETIME (1601, 100 ns) -> epoch seconds
                    if created > float(since) + 2:
                        return False
            return True
        finally:
            k.CloseHandle(h)
    except Exception:  # noqa: BLE001
        return False


def kill_tree(proc):
    """Kill the agent and every process it started, also after the agent itself has ended (its orphans).
    Windows: terminate its Job Object, then taskkill /T /F as the fallback; POSIX: the process group."""
    job = getattr(proc, "_vesper_job", None)
    if job:
        proc._vesper_job = None
        try:
            _k32().TerminateJobObject(job, 1)
            _k32().CloseHandle(job)
        except Exception:  # noqa: BLE001
            pass
    try:
        if os.name == "nt":
            if proc.poll() is None:
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True, timeout=30)
        else:
            import signal
            os.killpg(proc.pid, signal.SIGKILL)       # the group lives on while an orphan is in it
    except (OSError, subprocess.TimeoutExpired):
        pass
    if proc.poll() is None:
        try:
            proc.kill()
        except OSError:
            pass
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        pass


def run_capture(cmd, timeout, cwd=None, stdin_text=None):
    """(exit code or None at the timeout, output text) of a short CLI call. The output goes to a temp file and
    the whole process tree is killed at the timeout, so a grandchild that holds a pipe cannot hang the tool."""
    fd, out = tempfile.mkstemp(prefix="vesper-cli-", suffix=".txt")
    os.close(fd)
    try:
        proc = start_agent(cmd, cwd or os.getcwd(), out, stdin_text)
        try:
            rc = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            rc = None
        kill_tree(proc)
        with open(out, encoding="utf-8", errors="replace") as f:
            return rc, f.read()
    finally:
        try:
            os.remove(out)
        except OSError:
            pass


def check_auto_run(agent):
    """doctor --check-auto: ONE tiny run ("Reply OK") with the stage-3 model. Returns (ok, text)."""
    argv, why = find_cli(agent)
    if not argv:
        return False, "error: " + why
    tmp = tempfile.mkdtemp(prefix="vesper-auto-check-")
    try:
        try:
            cmd, stdin_text = build_auto_cmd(agent, argv, AUTO_MODEL[agent], tmp, "Reply OK")
            rc, text = run_capture(cmd, AUTO_CHECK_SEC, cwd=tmp, stdin_text=stdin_text)
        except (OSError, LaunchError) as e:
            return False, "error: %s" % e
        if rc is None:
            return False, "error: no answer in %d s" % AUTO_CHECK_SEC
        if FREE_PLAN_RE.search(text):
            return False, FREE_PLAN_MSG
        if rc == 0:
            return True, "OK (model %s answered)" % AUTO_MODEL[agent]
        lines = [x.strip() for x in text.splitlines() if x.strip() and "warn" not in x.lower()]
        return False, "error: " + (anon(lines[-1])[:50] if lines else "exit code %d" % rc)
    finally:
        rmtree(tmp)


def _doctor_wrap(lines):
    """Doctor is not wrapped by print (its text goes into help prompts): keep its --auto lines <= 72."""
    out = []
    for x in lines:
        body = x.lstrip(" ")
        ind = " " * (len(x) - len(body))
        sub = ind if not re.match(r"(OK|INFO|WARN|FAIL)\s", body) else ind + "      "
        out += textwrap.wrap(body, MAXW, initial_indent=ind, subsequent_indent=sub,
                             break_long_words=False, break_on_hyphens=False) or [x]
    return out


def doctor_auto_lines(agent, check=False):
    """Doctor lines about --auto for the learner's agent only (no other CLI is started);
    returns (lines, ready{agent: bool})."""
    lines, ready = [], {}
    if agent not in AUTO_AGENTS:
        return lines, ready
    ok, text, fix = auto_ready(agent)
    ready[agent] = ok
    lines.append("  INFO  --auto %s: %s" % (agent, text if ok else "NOT ready - " + text))
    if not ok:
        lines += ["          " + x for x in fix]
    if check:
        ok, text = check_auto_run(agent)
        lines.append("  %-5s --check-auto %s (%s): %s" % ("OK" if ok else "WARN", agent, AUTO_MODEL[agent], text))
        if text == FREE_PLAN_MSG:
            lines.append("          Named models need a paid plan.")
            lines.append("          Use the manual flow, or upgrade the plan.")
        ready[agent] = ready[agent] and ok
    if agent == "cursor":
        always, text = cursor_rules_note()
        lines.append("  %-5s %s" % ("WARN" if always else "INFO", text))
    return _doctor_wrap(lines), ready


def auto_setup(reg, a):
    """Check that --auto can start the learner's agent; set a.auto_agent / auto_argv / auto_model. Exits if not."""
    agent = reg.data.get("agent") or ""
    ok, text, fix = auto_ready(agent)
    if not ok:
        sys.exit("--auto is not ready for %s: %s\n%s\nOr run the manual flow without --auto."
                 % (agent or "your agent", text, "\n".join("  " + x for x in fix)))
    a.auto_agent = agent
    a.auto_argv = find_cli(agent)[0]
    a.auto_model = getattr(a, "model", None) or AUTO_MODEL[agent]


# What the agent may do in an --auto run (one line of at most 72 characters each; shown before the start).
AUTO_SAFETY = {"codex": "Codex runs in a sandbox: it can change files only in its run folder.",
               "claude": "Claude may only run bin/vesper and edit files in its run folder.",
               "cursor": "Cursor runs in Cursor's sandbox (--sandbox enabled)."}


def auto_confirm(a, n):
    """The warning screen before --auto starts n agents. Default No; without a terminal only --yes starts."""
    word = "the agent" if n == 1 else "the %d agents" % n
    print("\n  --auto starts %s with no window. What they may do:" % word)
    print("  " + AUTO_SAFETY.get(a.auto_agent, ""))
    print("  The tool stops each agent at %d min. Ctrl+C stops all of them." % TIME_BOX_MIN)
    if getattr(a, "yes", False):
        return True
    if not (sys.stdin and sys.stdin.isatty()):
        print("  Not started: no terminal to answer. Add --yes to start them.")
        return False
    if ask("  Start %s? [y/N] " % word, "n").strip().lower() in ("y", "yes"):
        return True
    print("  Not started.")
    return False


def auto_item(reg, a, rid, folder, prompt):
    """Mark a run as an --auto run and return its item for run_auto."""
    run = reg.data["runs"][rid]
    run.update(auto=True, mode="auto", auto_model=a.auto_model, settings_confirmed="auto")
    reg.save()
    key = ("n" if is_control(run) else "t") + run["task"][-1]
    return dict(rid=rid, folder=folder, prompt=prompt, key=key, label=AUTO_LABEL.get(key, run["task"]),
                state="waiting", t0=0.0, end=None, proc=None, rc=None, agent=a.auto_agent,
                task=getattr(a, "task", "all"))


def fmt_mss(sec):
    return "%d:%02d" % divmod(int(max(sec, 0)), 60)


def status_block(items, now=None):
    """One line per run: '  T3 with skill     running 3:20' (at most 72 characters)."""
    now = time.time() if now is None else now
    out = []
    for it in items:
        el = ((it["end"] or now) - it["t0"]) if it["state"] != "waiting" else 0
        out.append("  %-17s %-7s %s" % (it["label"], it["state"], fmt_mss(el)))
    return "\n".join(out)


AUTO_LOCK = ".agent.lock"
AUTO_MIN_SEC = 60          # an agent that ends sooner than this did not do the task: the run failed
AUTO_ERROR_RE = re.compile(r"Named models unavailable|Free plans can only use Auto|Authentication required"
                           r"|not supported when using Codex with a ChatGPT account|Not logged in", re.I)
_ERROR_LINE = re.compile(r"error|failed|denied|unauthori[sz]ed|invalid|not found|cannot|can't", re.I)


def read_lock(folder):
    """The .agent.lock of a run folder as a dict (pid, start, mode), or None."""
    try:
        with open(os.path.join(folder, AUTO_LOCK), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def lock_live(folder):
    """True when another `--auto` process (alive, not this one) holds the lock of this run folder."""
    lk = read_lock(folder)
    return bool(lk and lk.get("mode") == "auto" and str(lk.get("pid")) != str(os.getpid())
                and pid_alive(lk.get("pid"), lk.get("start")))


def write_lock(folder, proc):
    try:
        with open(os.path.join(folder, AUTO_LOCK), "w", encoding="utf-8") as f:
            json.dump({"pid": os.getpid(), "agent_pid": proc.pid, "start": time.time(), "mode": "auto"}, f)
    except OSError:
        pass


def auto_launch(reg, a, it):
    rid = it["rid"]
    run = reg.data["runs"][rid]
    out = os.path.join(it["folder"], "agent-output.jsonl")
    if a.auto_agent == "cursor":      # Cursor keeps no token counts: this file is the measurement source
        run["session"] = {"agent": "cursor", "sid": rid, "path": out}
    else:
        run["session"] = None         # a relaunch finds its new session by the run id
    for k in ("stopped", "error_note"):
        run.pop(k, None)              # a relaunch after a failed run starts clean
    it["t0"] = time.time()
    act = reg.get_active(rid)
    if act:
        act["start"] = it["t0"]       # the start is the launch time
    reg.save()
    try:
        cmd, stdin_text = build_auto_cmd(a.auto_agent, a.auto_argv, a.auto_model, it["folder"], it["prompt"])
        it["proc"] = start_agent(cmd, it["folder"], out, stdin_text)
        write_lock(it["folder"], it["proc"])
        it["state"] = "running"
    except (OSError, LaunchError) as e:
        it["state"], it["end"] = "failed", it["t0"]
        it["error"] = "could not start: %s" % e
        print(c_err("  %s could not start: %s" % (it["label"], e)))


def _output_text(folder, limit=400000):
    try:
        with open(os.path.join(folder, "agent-output.jsonl"), encoding="utf-8", errors="replace") as f:
            return f.read(limit)
    except OSError:
        return ""


def _agent_worked(it):
    """Did the agent do anything? Cursor: a tool call in its stream; others: a solution or an emulator run."""
    if it.get("agent") == "cursor":
        return any(c.get("tools") for c in M.cursor_sessions(os.path.join(it["folder"], "agent-output.jsonl")))
    task = it.get("run_task") or ""
    if task and os.path.isfile(os.path.join(it["folder"], "solutions", task + ".vsa")):
        return True
    return bool(count_runs(it["folder"], it["t0"] - 1, time.time() + 1))


def agent_error(it):
    """Why an agent that ended by itself failed ('' when it looks like a real run): it ended within
    AUTO_MIN_SEC, or with a non-zero exit code and no tool calls, or it printed a known error text."""
    if it.get("error"):
        return it["error"]
    lines = [x.strip() for x in _output_text(it["folder"]).splitlines() if x.strip()]
    plain, first_err = [], ""
    for x in lines:
        if x.startswith("{"):
            try:
                d = json.loads(x)
            except ValueError:
                d = None
            if isinstance(d, dict) and d.get("is_error") and d.get("result"):
                plain.append(str(d["result"]).strip())        # Claude: {"type": "result", "is_error": true}
            continue
        plain.append(x)
    for x in plain:
        if AUTO_ERROR_RE.search(x):
            return x
        if not first_err and _ERROR_LINE.search(x) and "warn" not in x.lower():
            first_err = x
    el = (it["end"] or time.time()) - it["t0"]
    if el < AUTO_MIN_SEC:
        return first_err or "the agent ended after %d s (exit code %s)" % (el, it["rc"])
    if it["rc"] and not _agent_worked(it):
        return first_err or "exit code %s and no tool calls" % it["rc"]
    return ""


def auto_error(reg, it, reason):
    """A failed --auto run: record stopped=error and the first error line, do NOT grade, keep the run active
    (the learner does it by hand). Returns the row."""
    rid = it["rid"]
    run = reg.data["runs"][rid]
    note = " ".join(anon(reason).split())[:200]
    run.update(stopped="error", error_note=note)
    prev = reg.row(rid, "3")
    t1 = it["end"] or time.time()
    reg.set_row(rid, "3", dict(
        alias=reg.data.get("alias", ""), task=run["task"], agent=it.get("agent", ""), model=run.get("auto_model", ""),
        method=run["method"], parent_run_id=run["parent"], skill_source=run["skill_source"],
        skill_hash=run["skill_hash"], skill_has_solution=run["skill_has_solution"], price_table=PRICE_TABLE,
        start="%.0f" % it["t0"], cutoff="%.0f" % t1, wall_min="%.1f" % ((t1 - it["t0"]) / 60), score="",
        grading="none", measurement="none", settings_confirmed="auto", stopped="error", error_note=note,
        revision=int((prev or {}).get("revision") or 0) + 1))
    reg.save()
    reg.write_csv()
    print("\n" + c_err("  RUN FAILED  %s" % it["label"]))
    print(c_err("  RUN FAILED: %s. Do this run by hand: python workshop.py new s3 --task %s (shows its page)"
                % (note.rstrip(". "), it.get("task") or "all")))
    return reg.row(rid, "3")


def auto_finish(reg, it):
    """The normal finish of one run (like `done <run_id>`), without clearing the screen.
    A failed run (agent_error) is not finished: it stays active with stopped=error."""
    rid = it["rid"]
    run = reg.data["runs"][rid]
    it["run_task"] = run.get("task", "")
    if it["state"] in ("done", "failed"):
        why = agent_error(it)
        if why:
            it["state"] = "failed"
            return auto_error(reg, it, why)
    if it["state"] in ("stopped", "killed"):
        run["stopped"] = "time" if it["state"] == "stopped" else "ctrl-c"
        reg.save()
    try:
        row = finish_stage(reg, rid, "3", argparse.Namespace(partial=it["state"] in ("stopped", "killed"), auto=True))
    except Exception as e:  # noqa: BLE001  (one run must not stop the others)
        print(c_err("  %s: the finish failed (%s). Later:  python workshop.py done %s" % (it["label"], e, rid)))
        return None
    print("\n" + c_bold("  FINISHED  %s   (%s)" % (it["label"], it["state"])))
    if it["state"] == "done" and it["rc"]:
        print(c_err("  The agent ended with exit code %s; see agent-output.jsonl in the run folder." % it["rc"]))
    print_wrong_folder(run, row)
    print(run_summary(row, "3"))
    warn = run_warnings(row)
    if warn:
        print("\n".join(warn))
    return row


def auto_start_screen(a, items):
    print("\n" + c_banner(WIDE))
    print(c_banner("  STAGE 3 --auto - the tool runs %s for you"
                   % ("the %d agents" % len(items) if len(items) > 1 else "the agent")))
    print(c_banner(WIDE))
    eff = ", effort high" if a.auto_agent == "codex" else ""
    print("  Agent: %s   Model: %s%s" % (a.auto_agent, a.auto_model, eff))
    print("  " + AUTO_SAFETY.get(a.auto_agent, ""))
    print("  Time box %d min: the tool stops any agent still working." % TIME_BOX_MIN)
    print("  Do not type in these folders. Ctrl+C stops all agents.")
    print("  Start order:")
    print("\n".join(chunk_lines(["%d. %s" % (i, it["label"]) for i, it in enumerate(items, 1)], indent=4)))


def run_auto(reg, a, items):
    """Start the agents in order, print a status block every AUTO_TICK seconds, stop each at the time box,
    finish each run when it ends. Ctrl+C: kill all, keep the finished results."""
    box = AUTO_BOX_SEC if AUTO_BOX_SEC is not None else TIME_BOX_MIN * 60
    auto_start_screen(a, items)
    try:
        for it in items:
            auto_launch(reg, a, it)
            if it["state"] == "failed":
                auto_finish(reg, it)
        print("\n" + status_block(items))
        last = time.time()
        while any(it["state"] == "running" for it in items):
            _sleep(AUTO_POLL)
            now = time.time()
            for it in items:
                if it["state"] != "running":
                    continue
                rc = it["proc"].poll()
                if rc is None and now - it["t0"] < box:
                    continue
                kill_tree(it["proc"])         # also when it ended: its orphans (emulator, servers) die too
                it["state"], it["end"], it["rc"] = ("done" if rc is not None else "stopped"), now, rc
                auto_finish(reg, it)
                print("\n" + status_block(items))
                last = now
            if now - last >= AUTO_TICK:
                print("\n" + status_block(items))
                last = now
    except KeyboardInterrupt:
        return auto_ctrl_c(reg, items)
    return auto_end_screen(reg, items)


def auto_ctrl_c(reg, items):
    """Ctrl+C: ignore a second Ctrl+C, kill every agent (the Job Objects make sure), then finish each killed
    run as partial with stopped=ctrl-c (graded --partial, like the time box)."""
    import signal
    old = signal.getsignal(signal.SIGINT)
    try:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
    except (ValueError, OSError):        # not the main thread
        old = None
    try:
        now = time.time()
        for it in items:
            if it["state"] == "running":
                kill_tree(it["proc"])
                it["state"], it["end"] = "killed", now
        print(c_err("\n  Stopped with Ctrl+C. All agents are killed."))
        print(c_err("  Each stopped run is saved as partial work."))
        for it in items:
            if it["state"] == "killed":
                auto_finish(reg, it)
        auto_end_screen(reg, items, show=False)
    finally:
        if old is not None:
            signal.signal(signal.SIGINT, old)
    return 1


def auto_end_screen(reg, items, show=True):
    """The NEXT box after --auto: failed runs (by hand), runs still active elsewhere, or the last steps."""
    if show:
        print("\n" + SAVED_LINE)
        show_compare(reg, items[0]["rid"] if len(items) == 1 else None)
    failed = [it for it in items if it["state"] == "failed"]
    ours = {it["rid"] for it in items}
    left = [x for x in reg.actives("3") if x["run_id"] not in ours]
    if failed:
        task = failed[0].get("task") or "all"
        next_box(["python workshop.py new s3 --task %s" % task, "   shows the page of each failed run"],
                 "1 run failed. Do it by hand:" if len(failed) == 1
                 else "%d runs failed. Do them by hand:" % len(failed))
    elif left:
        still_working_box(reg, left)
    else:
        all_done_box(reg)
    return 0 if not failed else 1


def s3_choice_box(reg, when):
    """The NEXT box with both ways to run stage 3. --auto goes first only when doctor said it is ready."""
    agent = reg.data.get("agent") or ""
    auto = ["python workshop.py new s3 --task all --auto", "   the tool runs the 4 agents, about 10 min"]
    manual = ["python workshop.py new s3 --task all", "   you open 4 threads in your agent app"]
    if agent and agent not in AUTO_AGENTS:
        next_box(manual, when)
    elif (reg.data.get("auto_ready") or {}).get(agent):
        next_box(auto + manual, when)
    else:
        next_box(manual + auto, when)


# ------------------------------------------------------------------ stage 3 pages and resume
S3_STOPPED = "Stopped. Run the same command again to see the pages."


def s3_pages(reg, a, entries, seed, total=None):
    """Show the stage-3 run pages for entries {key: (rid, folder, prompt)} in the printed start order,
    then the NEXT box with one done line per run."""
    order = [k for k in start_order_keys(seed) if k in entries]
    total = total or len(order)
    labels = [x for x in start_order(seed) if ORDER_KEY[x] in entries]
    print("  Start in this order: " + " ".join("%d. %s" % (i, x) for i, x in enumerate(labels, 1)))
    print(BENCH_LINE)
    for i, k in enumerate(order, 1):
        rid, f, p = entries[k]
        s3_show(reg, rid, i, total, "T6" if k[1] == "6" else "T3", f, p, desc=ALL_DESC[k],
                extra=(lambda: print("  Start in this order: " + " ".join(
                    "%d. %s" % (j, x) for j, x in enumerate(labels, 1)))) if gate_on() else None)
    next_box(["python workshop.py done %s   %s" % (entries[k][0], ALL_LABEL[k]) for k in order],
             "when an agent is done (or at 10 min), run its line:")
    return order


def run_mode(run):
    """'auto' (created or launched by --auto) or 'manual' (its page was shown: the learner runs it)."""
    return run.get("mode") or ("auto" if run.get("auto") else "manual")


def has_partial_work(run):
    f = run.get("folder") or ""
    return os.path.isfile(os.path.join(f, "solutions", run.get("task", "") + ".vsa")) or \
        bool(count_runs(f, 0, time.time() + 1))


def auto_resume_pick(reg, entries, order):
    """The runs that a resume with --auto may start: created or launched by --auto, not done, and no live
    agent on them. A stale lock with partial work: ask first (default No)."""
    keep = []
    for k in order:
        rid, folder, _ = entries[k]
        run = reg.data["runs"][rid]
        lab = ALL_LABEL.get(k, run.get("task", ""))
        if run_mode(run) != "auto":
            print("  %s: you run it by hand. When it is done:" % lab)
            print("      python workshop.py done %s" % rid)
            continue
        if lock_live(folder):
            print("  %s: an agent still works on it in another window." % lab)
            continue
        if read_lock(folder) and has_partial_work(run):
            q = "  %s has work from an earlier agent. Start a new agent there? [y/N] " % lab
            if ask(q, "n").strip().lower() not in ("y", "yes"):
                print("      Not started. To end it:  python workshop.py done %s --partial" % rid)
                continue
        keep.append(k)
    return keep


def resume_s3(reg, a, same):
    """Stage 3 is already set up (for example the learner pressed Ctrl+C in the page gate): show the pages of
    the runs that are still active again, in the start order. Prompts are rebuilt as create_s3_run builds them.
    With --auto: ask, then start only the runs that are not done."""
    runs = reg.data["runs"]
    print("Stage 3 is already set up. Showing its pages again.")
    parent = runs[same[0]["run_id"]].get("parent")
    multi = a.task in ("both", "all")
    acts = [x for x in reg.actives("3") if runs[x["run_id"]].get("parent") == parent] if multi else same
    entries = {}
    for x in acts:
        rid, run = x["run_id"], runs[x["run_id"]]
        ctl = is_control(run)
        entries[("n" if ctl else "t") + run["task"][-1]] = (
            rid, run["folder"], render_prompt("stage3-noskill" if ctl else "stage3", task=run["task"], run_id=rid))
    if multi:
        for r in sorted(reg.data["rows"].values(), key=lambda r: float(r.get("start") or 0)):
            if r["stage"] == "3" and runs.get(r["run_id"], {}).get("parent") == parent \
                    and not reg.get_active(r["run_id"]):
                print("  Already done: %s %s" % (run_label(reg, r["run_id"]), r["run_id"]))
    first = next(iter(entries.values()))[0]
    a.s3_first = first
    seed = parent or ""
    if getattr(a, "auto", False):
        order = auto_resume_pick(reg, entries, [k for k in start_order_keys(seed) if k in entries])
        if not order:
            print("  No run can be started by --auto now.")
            return 1
        if not auto_confirm(a, len(order)):
            return 1
        return run_auto(reg, a, [auto_item(reg, a, entries[k][0], entries[k][1], entries[k][2]) for k in order])
    for k in list(entries):
        if lock_live(entries[k][1]):                   # another terminal runs this agent with --auto
            print("  %s: an --auto agent works on it in another window." % ALL_LABEL[k])
            entries.pop(k)
    if not entries:
        return 1
    if not gate_on():
        s3_header(reg, a, len(entries) > 1, total=len(entries) if len(entries) in (3, 4) else None)
    s3_pages(reg, a, entries, seed)
    return 0


# ------------------------------------------------------------------ CLI
def parse(argv):
    ap = argparse.ArgumentParser(prog="workshop.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("doctor")
    s.add_argument("--agent", choices=["codex", "claude", "cursor", "other"])
    s.add_argument("--alias")
    s.add_argument("--check-auto", action="store_true",
                   help="ONE tiny agent run (Reply OK) with the stage-3 model: can --auto use it?")
    s.set_defaults(func=cmd_doctor)
    s = sub.add_parser("new")
    s.add_argument("stage", choices=["s1", "s3"])
    s.add_argument("--task", default="T3", choices=["T3", "T4", "T6", "both", "all"],
                   help="stage 3: use all (recommended) = T3 with skill, T3 without skill (control), T6")
    s.add_argument("--name", help="T6 (or both) only: your name on the screen (up to 8 letters A-Z; default: asked)")
    s.add_argument("--method", default="random", choices=["random"] + METHODS)
    s.add_argument("--skill", default="own", help="own | wiki | <folder with SKILL.md>")
    s.add_argument("--auto", action="store_true",
                   help="stage 3: the tool starts the agents itself (headless) and stops each at 10 min")
    s.add_argument("--model", help="with --auto: the model (default: the stage-3 model of your agent)")
    s.add_argument("--yes", action="store_true", help="with --auto: start the agents without the question")
    s.set_defaults(func=cmd_new)
    s = sub.add_parser("done")
    s.add_argument("run_id", nargs="?", help="the run to end (needed when two stage-3 runs are active)")
    s.add_argument("--partial", action="store_true", help="the agent did not finish; grade what exists")
    s.add_argument("--no-form", action="store_true")
    s.set_defaults(func=cmd_done)
    s = sub.add_parser("skill")
    s.set_defaults(func=cmd_skill)
    s = sub.add_parser("harvest")
    s.add_argument("--no-form", action="store_true")
    s.add_argument("--move-aside", action="store_true")
    s.add_argument("--blocks", action="store_true", help="instructor: list where the shared T3 code is in the skill")
    s.add_argument("--remove-global", action="store_true")
    s.set_defaults(func=cmd_harvest)
    s = sub.add_parser("judge", help="check your skill with an independent judge thread (optional)")
    s.add_argument("run_id", nargs="?", help="default: the latest run with a harvested skill")
    s.set_defaults(func=cmd_judge)
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
    s = sub.add_parser("submit", help="send all results that are not yet submitted to the results form")
    s.add_argument("--no-form", action="store_true", help="print the links and answers only; mark nothing")
    s.set_defaults(func=cmd_submit)
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
