"""GitHub Copilot (VS Code Copilot Chat) - PARTIAL support, kept apart from the rest of the kit.

What works: the manual flow (new s1 / skill / new s3 / done / grade / show / submit) with Copilot Chat in VS Code.
What does not: --auto (no headless Copilot run here), input tokens and cost, the Copilot CLI, the Copilot app.
Everything Copilot-specific lives in this file. workshop.py only calls the small functions below, and only when
the learner chose the agent "copilot". If this file has a fault, no other agent is affected.

Measurement: VS Code keeps every chat in a local file (workspaceStorage/<id>/chatSessions/<chat>.jsonl). The file of
the CURRENT chat is found by the run id in the first message. It gives the model, the time and the output tokens.
It gives no input tokens, so there is no cost. Any problem with the file gives None, never an error.
"""
import glob, json, os, sys

NAME = "copilot"
PARTIAL_TITLE = "GitHub Copilot: PARTIAL SUPPORT (experimental)"

# What the learner must know the moment they pick Copilot (doctor, new s1, new s3).
LIMITS = [
    "Copilot works here in manual mode only: VS Code, Copilot Chat, agent mode.",
    "NOT supported: --auto, the Copilot CLI and the Copilot app.",
    "From the chat the kit reads: model, time and output tokens. Input tokens and cost are not available.",
    "This path is less tested than Codex or Claude Code. If something looks wrong, tell the instructor.",
]

SETUP = [
    "Before you start (once, 3 minutes):",
    "  1. VS Code: File > Preferences > Profiles > Create Profile. Name it vesper-clean.",
    "     Use this profile for the workshop. Your normal profile and memories stay as they are.",
    "  2. In that profile: Settings (Ctrl+,), search \"memory\", turn OFF chat.copilot.memory.enabled.",
    "  3. Open the run folder in VS Code (File > Open Folder). Use Copilot Chat in Agent mode.",
    "  4. Pick the model from the model picker. Never leave it on Auto.",
    "  5. Start a NEW chat for every run (the + button in the chat panel).",
]

BUILTIN_HOW = ("use your built-in skill creator (/create-skill in Copilot Chat). If you do not have it, "
               "read and follow the guide at {guide}/anthropic-skill-creator/SKILL.md.")
BUILTIN_STEP = ("Copilot Chat: in the SAME chat, type /create-skill at the start of the message, then paste the prompt.\n"
                "     (If /create-skill is missing, the prompt points the agent to the bundled guide.)")

LARGE = "a large model from the model picker (not Auto)"
SMALL = "a small model from the model picker: Claude Haiku 5.5 or GPT-6 Luna (not Auto)"

APP_LINE = "  Tokens and cost: input tokens are not available in Copilot Chat, so there is no cost."


def doctor_lines():
    """Lines for `doctor` when the learner picked Copilot. The first is a WARN, so the result is never plain green."""
    out = ["  WARN  %s" % PARTIAL_TITLE]
    out += ["          " + x for x in LIMITS]
    out += ["          " + x for x in SETUP]
    return out


def banner_lines():
    """Short reminder, printed on the stage pages."""
    return ["", "  *** %s ***" % PARTIAL_TITLE] + ["  - " + x for x in LIMITS[:3]]


def stage3_lines(total=4):
    return ["  Model: %s in %s." % (SMALL, "all %d chats" % total if total > 1 else "this chat"),
            "  New chat for each run. Memory off (profile vesper-clean). Agent mode.",
            "  Tokens and cost: not shown by Copilot Chat. The kit reads model, time and output tokens."]


# ---------------------------------------------------------------- reading the chat file
def chat_files(root=None):
    """Session files of VS Code / VS Code Insiders. VESPER_COPILOT_CHATS (a folder) overrides, for tests."""
    root = root or os.environ.get("VESPER_COPILOT_CHATS")
    if root:
        return glob.glob(os.path.join(root, "*.jsonl")) + glob.glob(os.path.join(root, "*.json"))
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Roaming")
    elif sys.platform == "darwin":
        base = os.path.join(os.path.expanduser("~"), "Library", "Application Support")
    else:
        base = os.path.join(os.path.expanduser("~"), ".config")
    out = []
    for app in ("Code", "Code - Insiders"):
        w = os.path.join(base, app, "User", "workspaceStorage", "*", "chatSessions")
        out += glob.glob(os.path.join(w, "*.jsonl")) + glob.glob(os.path.join(w, "*.json"))
    return out


def _set(state, path, value):
    cur = state
    for p in path[:-1]:
        cur = cur[p]
    cur[path[-1]] = value


def load_session(path):
    """The chat as a dict. .jsonl = a first snapshot (kind 0) then patches: kind 1 sets a path, kind 2 adds to a list."""
    with open(path, encoding="utf-8", errors="replace") as f:
        text = f.read()
    if path.endswith(".json"):
        return json.loads(text)
    state = None
    for line in text.splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        kind = d.get("kind")
        if kind == 0:
            state = d.get("v")
        elif state is None:
            continue
        elif kind == 1:
            _set(state, d["k"], d.get("v"))
        elif kind == 2:
            cur = state
            for p in d["k"]:
                cur = cur[p]
            if isinstance(d.get("i"), int):
                cur[d["i"]:d["i"]] = d.get("v") or []
            else:
                cur.extend(d.get("v") or [])
    return state


def _num(x):
    return x if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def chat_summary(state):
    """{model, first, last, out_tokens, requests} of a loaded chat, or None."""
    reqs = [r for r in (state or {}).get("requests") or [] if isinstance(r, dict)]
    if not reqs:
        return None
    models, firsts, lasts, out = [], [], [], 0
    for r in reqs:
        m = str(r.get("modelId") or "").strip()
        m = m.split("/", 1)[1] if m.startswith("copilot/") else m
        if m and m not in models:
            models.append(m)
        ts = _num(r.get("timestamp"))
        if ts is not None:
            firsts.append(ts / 1000.0)
            el = _num(r.get("elapsedMs")) or _num(((r.get("result") or {}).get("timings") or {}).get("totalElapsed"))
            done = _num((r.get("modelState") or {}).get("completedAt"))
            lasts.append(done / 1000.0 if done else ts / 1000.0 + (el or 0) / 1000.0)
        out += int(_num(r.get("completionTokens")) or 0)
    if not firsts:
        return None
    return dict(model=models[0] if len(models) == 1 else ("mixed: " + ", ".join(models) if models else ""),
                first=min(firsts), last=max(lasts), out_tokens=out, requests=len(reqs))


def copilot_app_chat(run_id, root=None):
    """The newest chat whose text holds the run id, summarised. None if not found or anything fails."""
    if not run_id:
        return None
    try:
        needle = str(run_id).encode()
        hits = []
        for p in chat_files(root):
            try:
                with open(p, "rb") as f:
                    if needle in f.read():
                        hits.append(p)
            except OSError:
                continue
        for p in sorted(hits, key=os.path.getmtime, reverse=True):
            s = chat_summary(load_session(p))
            if s:
                return s
    except Exception:  # noqa: BLE001  (never crash a `done` because of VS Code's private data)
        return None
    return None
