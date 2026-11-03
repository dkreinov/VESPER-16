"""Find the agent app and open it on the run folder (semi mode). Standard library only.

Nothing here raises to the caller. A problem gives Opened(ok=False, ...) with manual lines.
Tests: VESPER_LAUNCHER_<AGENT>=<path or "none"> forces the app path.
VESPER_LAUNCHER_DRYRUN=<logfile> starts nothing and logs one JSON line per command.
"""
import json, os, shutil, subprocess, sys, tempfile, time
from typing import NamedTuple, Optional
from urllib.parse import quote

ONE_LINE = "Workshop run: {run_id}. Read PROMPT.txt in this folder and do what it says."
AGENTS = ("codex", "cursor", "claude", "copilot")
WIN = sys.platform == "win32"


def one_line(run_id):
    return ONE_LINE.format(run_id=run_id)


class Found(NamedTuple):
    kind: str
    path: str
    note: str


class Opened(NamedTuple):
    ok: bool
    how: str
    lines: list
    manual: list


# ---------------------------------------------------------------- find

def _which(name):
    try:
        return shutil.which(name)
    except Exception:
        return None


def _first_file(*paths):
    for p in paths:
        try:
            if p and os.path.isfile(p):
                return p
        except Exception:
            pass
    return None


def _codex_app_dir():
    if not WIN:
        return None
    try:
        r = subprocess.run(["powershell.exe", "-NoProfile", "-Command",
                            "(Get-AppxPackage OpenAI.Codex | Select-Object -First 1).InstallLocation"],
                           capture_output=True, text=True, timeout=15)
        p = (r.stdout or "").strip().splitlines()
        p = p[0].strip() if p else ""
        return p if p and os.path.isdir(p) else None
    except Exception:
        return None


def _find_codex(prefer):
    def app():
        d = _codex_app_dir()
        return Found("codex-app", d, "Codex app found.") if d else None

    def cli():
        p = _which("codex") or _first_file(os.path.join(os.environ.get("APPDATA", ""), "npm", "codex.cmd"))
        note = "Codex CLI found." if prefer == "cli" else "Codex CLI found (the app was not found)."
        return Found("codex-cli", p, note) if p else None

    order = (cli, app) if prefer == "cli" else (app, cli)
    for fn in order:
        f = fn()
        if f:
            return f
    return None


def _override(agent):
    v = os.environ.get("VESPER_LAUNCHER_" + agent.upper())
    if v is None or v == "":
        return False, None
    if v.strip().lower() == "none":
        return True, None
    kind = {"cursor": "cursor", "claude": "claude-cli", "copilot": "vscode"}.get(agent)
    if agent == "codex":
        kind = "codex-app" if os.path.isdir(v) else "codex-cli"
    return True, Found(kind, v, "%s found (set by VESPER_LAUNCHER_%s)." % (agent, agent.upper()))


def find_app(agent, prefer=None):
    try:
        if agent not in AGENTS:
            return None
        hit, f = _override(agent)
        if hit:
            return f
        if agent == "codex":
            return _find_codex(prefer)
        la = os.environ.get("LOCALAPPDATA", "")
        if agent == "cursor":
            p = _which("cursor") or _first_file(os.path.join(la, "Programs", "cursor", "resources", "app", "bin", "cursor.cmd"))
            return Found("cursor", p, "Cursor found.") if p else None
        if agent == "claude":
            home = os.path.expanduser("~")
            p = _which("claude") or _first_file(os.path.join(home, ".local", "bin", "claude"),
                                                os.path.join(home, ".local", "bin", "claude.exe"))
            return Found("claude-cli", p, "Claude Code found.") if p else None
        p = _which("code") or _first_file(os.path.join(la, "Programs", "Microsoft VS Code", "bin", "code.cmd"))
        return Found("vscode", p, "VS Code found.") if p else None
    except Exception:
        return None


# ---------------------------------------------------------------- helpers

def codex_link(folder, prompt_text):
    if not prompt_text:                      # path only: the thread opens with an empty box
        return "codex://new?path=%s" % quote(folder, safe="")
    return "codex://new?path=%s&prompt=%s" % (quote(folder, safe=""), quote(prompt_text, safe=""))


def _toml(s):
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def write_run_config(agent, folder, model, effort):
    if agent != "codex":
        return []
    try:
        rows = []
        if model:
            rows.append("model = %s" % _toml(model))
        if effort:
            rows.append("model_reasoning_effort = %s" % _toml(effort))
        if not rows:
            return []
        d = os.path.join(folder, ".codex")
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, "config.toml")
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(rows) + "\n")
        return [p]
    except Exception:
        return []


def _clip(text):
    try:
        if WIN:
            cmd, data = ["clip"], text.encode("utf-16-le")
        elif sys.platform == "darwin":
            cmd, data = ["pbcopy"], text.encode("utf-8")
        else:
            cmd = next((c for c in (["wl-copy"], ["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"])
                        if _which(c[0])), None)
            data = text.encode("utf-8")
            if not cmd:
                return False
        return subprocess.run(cmd, input=data, timeout=10).returncode == 0
    except Exception:
        return False


def _dry_log(agent, argv, env, launch=None):
    """Append one JSON line to the dry-run log. Returns True when dry run is on."""
    path = os.environ.get("VESPER_LAUNCHER_DRYRUN")
    if not path:
        return False
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"agent": agent, "argv": list(argv), "env": dict(env or {}),
                                "launch": list(launch or argv)}) + "\n")
    except Exception:
        pass
    return True


def _terminal_available():
    return WIN or sys.platform == "darwin"


def _cmd_quote(s):
    return '"' + str(s).replace("%", "%%").replace('"', '""') + '"'


def _write_script(folder, env, argv):
    """Write a .cmd script to the system temp folder (never the run folder). Returns its path."""
    lines = ["chcp 65001 >nul", "@echo off", "cd /d %s" % _cmd_quote(folder)]
    for k, v in (env or {}).items():
        lines.append("set %s=%s" % (k, str(v).replace("%", "%%")))
    lines.append(" ".join(_cmd_quote(a) for a in argv))
    fd, p = tempfile.mkstemp(prefix="vesper_run_", suffix=".cmd")
    with os.fdopen(fd, "w", encoding="utf-8", newline="\r\n") as f:
        f.write("\r\n".join(lines) + "\r\n")
    return p


def _ps_quote(s):
    return "'" + str(s).replace("'", "''") + "'"


def _popen(argv, **kw):
    flags = 0
    if WIN:
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=flags, **kw) if WIN else subprocess.Popen(
        argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True, **kw)


def _open_terminal(agent, folder, env, argv):
    """Start argv in a new terminal window in the folder. Returns True or False."""
    if _dry_log(agent, argv, env, ["terminal"]):
        return True
    if not _terminal_available():
        return False
    script = _write_script(folder, env, argv)
    if WIN:
        arg = "'/k','\"%s\"'" % script.replace("'", "''")
        subprocess.run(["powershell.exe", "-NoProfile", "-Command",
                        "Start-Process cmd.exe -WorkingDirectory %s -ArgumentList %s" % (_ps_quote(folder), arg)],
                       timeout=30, check=True,
                       capture_output=True)
    else:
        subprocess.run(["open", "-a", "Terminal", script], timeout=30, check=True, capture_output=True)
    return True


# ---------------------------------------------------------------- open

def _manual(folder, agent, run_id):
    return ["Folder: %s" % folder,
            "Open %s on this folder by hand." % agent,
            "The prompt is in PROMPT.txt in the folder. It is also on this page.",
            "Send this message in the chat: %s" % one_line(run_id)]


def _launcher_ok(found):
    return found.kind == "codex-app" or bool(_which(found.path)) or os.path.isfile(found.path)


def open_project(agent, folder, run_id, *, model=None, effort=None, mode_hint="", clip=None, defer_message=False):
    manual = _manual(folder, agent, run_id)
    msg = one_line(run_id)
    try:
        found = find_app(agent)
        if not found:
            return Opened(False, "", ["The kit did not find the %s app on this PC." % agent,
                                      "Open it by hand (see below)."], manual)
        dry = bool(os.environ.get("VESPER_LAUNCHER_DRYRUN"))
        if not dry and not _launcher_ok(found):
            return Opened(False, "", ["The %s launcher does not exist: %s" % (agent, found.path),
                                      "Open the app by hand (see below)."], manual)
        if agent == "codex" and found.kind == "codex-app":
            write_run_config(agent, folder, model, effort)
            link = codex_link(folder, "" if defer_message else msg)
            ps = ["powershell.exe", "-NoProfile", "-Command", 'Start-Process "%s"' % link]
            if not _dry_log(agent, ["Start-Process", link], {}, ps):
                if not WIN:
                    return Opened(False, "", ["The Codex app link needs Windows."], manual)
                subprocess.run(ps, timeout=30, check=True, capture_output=True)
            if defer_message:
                return Opened(True, "codex-link", [
                    "The Codex app opens on the run folder. The box is empty on purpose.",
                    "Type /memories in the new thread and turn memory off first."], manual)
            return Opened(True, "codex-link", [
                "The Codex app opens on the run folder.",
                "The message is in the box. Do not send it yet.",
                "Type /memories and turn memory off. Then send the message."], manual)
        if agent == "codex":
            argv = ([found.path, "-C", folder] + (["-m", model] if model else [])
                    + (["-c", "model_reasoning_effort=%s" % effort] if effort else []))
            if not _open_terminal(agent, folder, {}, argv):
                return Opened(False, "", ["The kit cannot open a terminal window on this system."], manual)
            if defer_message:
                return Opened(True, "codex-terminal", [
                    "A new terminal window runs Codex on the run folder.",
                    "Type /memories first and turn memory off."], manual)
            copied = (clip or _clip)(msg)
            return Opened(True, "codex-terminal", [
                "A new terminal window runs Codex on the run folder.",
                "Turn memory off first. Then paste the message and send it." if copied
                else "Turn memory off first. Then type this message and send it: %s" % msg], manual)
        if agent == "claude":
            env = {"CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1"}
            argv = [found.path] + (["--model", model] if model else []) + [msg]
            if not _open_terminal(agent, folder, env, argv):
                return Opened(False, "", ["The kit cannot open a terminal window on this system."], manual)
            return Opened(True, "claude-terminal", [
                "A new terminal window runs Claude Code on the run folder.",
                "Memory is off. The kit set it. The message is sent as the first prompt."], manual)
        if agent == "cursor":
            argv = [found.path, "-n", folder]
            if not _dry_log(agent, argv, {}):
                _popen(argv)
            copied = (clip or _clip)(msg)
            lines = ["Cursor opens on the run folder."]
            lines.append("The message is on the clipboard. Paste it in the chat." if copied
                         else "The clipboard did not work. Type this message in the chat: %s" % msg)
            lines.append("The full prompt is in PROMPT.txt in the folder.")
            return Opened(True, "cursor-folder", lines, manual)
        if agent == "copilot":
            a1 = [found.path, "-n", folder, "--profile", "vesper-clean"]
            a2 = [found.path, "chat", "-r", "-m", "agent", "--profile", "vesper-clean", msg]
            if _dry_log(agent, a1, {}):
                _dry_log(agent, a2, {})
            else:
                _popen(a1)
                time.sleep(3)
                _popen(a2)
            return Opened(True, "vscode-chat", [
                "VS Code opens on the run folder.",
                "The message is in the chat box. Do not send it before you turn memory off."], manual)
        return Opened(False, "", ["Unknown agent: %s" % agent], manual)
    except Exception as e:
        return Opened(False, "", ["The kit could not open the app (%s)." % type(e).__name__,
                                  "Open the app by hand (see below)."], manual)
