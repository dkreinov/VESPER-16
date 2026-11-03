"""Capture the printed text of the OLD flows (manual with no launcher, and --auto with fake agents), normalized,
so a change can be compared with an earlier state. Used by tests/test_golden_old_flows.py.

  python tests/golden_capture.py <outdir>     writes <outdir>/<name>.txt for every captured page
"""
import contextlib, io, os, re, sys, tempfile
from unittest import mock
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fakes  # noqa: E402
from fakes import fresh_ws, run, install_fake_grader  # noqa: E402

FAKE = os.path.join(HERE, "fake_agent.py")
AGENTS = ("codex", "claude", "cursor", "copilot")
AUTO_AGENTS = ("codex", "claude", "cursor")
ENV_KEYS = ("VESPER_CODEX_EXE", "VESPER_CURSOR_EXE", "VESPER_CLAUDE_EXE", "FAKE_SLEEP", "LOCALAPPDATA")


def cap(w, *argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        try:
            rc = run(w, *argv)
        except SystemExit as e:
            rc = "exit: %s" % e.code
    return out.getvalue() + "\n[rc=%s]\n" % rc


class Norm:
    """Replace ids, times and paths by stable tokens (the first id seen is <ID1>, and so on)."""
    def __init__(self, home):
        self.home = home
        self.ids = {}

    def __call__(self, text):
        text = text.replace(self.home, "<HOME>").replace(self.home.replace("\\", "/"), "<HOME>")
        text = re.sub(r"[A-Za-z]:[\\/][^\s\"']*?vws_\w+", "<HOME>", text)

        def sub_id(m):
            return self.ids.setdefault(m.group(0), "<ID%d>" % (len(self.ids) + 1))
        text = re.sub(r"\bs[13]-[0-9a-f]{4}(?:-[tn][36]-[0-9a-f]{4})?\b", sub_id, text)
        text = re.sub(r"\b\d\d:\d\d:\d\d\b", "<TIME>", text)
        text = re.sub(r"\b\d+\.\d+ min\b", "<N> min", text)
        text = re.sub(r"\b\d+(\.\d+)?s\b", "<S>", text)
        text = re.sub(r"\r\n", "\n", text)
        text = re.sub(r"Python \d+\.\d+\.\d+", "Python <V>", text)
        return text


def counter():
    n = [0]

    def new_code():
        n[0] += 1
        return "%04x" % n[0]
    return new_code


def capture_all():
    """Returns {name: text}. Every agent: doctor, stage 1, done, skill, harvest, stage 3 (all and T3), done."""
    out = {}
    saved = {k: os.environ.get(k) for k in ENV_KEYS}
    try:
        for agent in AGENTS:
            w, home = fresh_ws()
            for a in AGENTS:
                os.environ["VESPER_LAUNCHER_" + a.upper()] = "none"
            os.environ.pop("VESPER_LAUNCHER_DRYRUN", None)
            norm = Norm(home)
            with mock.patch.object(w, "new_code", counter()):
                install_fake_grader(w)
                out["%s-doctor" % agent] = norm(cap(w, "doctor", "--agent", agent, "--alias", "t"))
                out["%s-new-s1" % agent] = norm(cap(w, "new", "s1", "--method", "plain"))
                reg = w.Registry.load()
                rid = reg.data["active"]["run_id"]
                f = reg.data["runs"][rid]["folder"]
                out["%s-done-s1" % agent] = norm(cap(w, "done", "--no-form"))
                out["%s-skill" % agent] = norm(cap(w, "skill"))
                sk = os.path.join(f, "skill-out", "vesper16")
                os.makedirs(sk, exist_ok=True)
                with open(os.path.join(sk, "SKILL.md"), "w") as fh:
                    fh.write("---\nname: vesper16\ndescription: VESPER-16 games\n---\nUse bin/vesper.\n")
                out["%s-harvest" % agent] = norm(cap(w, "harvest", "--no-form"))
                out["%s-new-s3-all" % agent] = norm(cap(w, "new", "s3", "--task", "all", "--name", "MIRA"))
                reg = w.Registry.load()
                for r in sorted(reg.actives("3"), key=lambda x: x["run_id"]):
                    out["%s-done-%s" % (agent, r["run_id"].split("-", 2)[2][:2])] = norm(
                        cap(w, "done", r["run_id"], "--no-form"))
                out["%s-new-s3-T3-again" % agent] = norm(cap(w, "new", "s3", "--task", "T3", "--yes"))
        for agent in AUTO_AGENTS:
            w, home = fresh_ws()
            for a in AGENTS:
                os.environ["VESPER_LAUNCHER_" + a.upper()] = "none"
            os.environ["LOCALAPPDATA"] = os.path.join(home, "localappdata")
            for k in ("VESPER_CODEX_EXE", "VESPER_CURSOR_EXE", "VESPER_CLAUDE_EXE"):
                os.environ[k] = FAKE
            os.environ["FAKE_SLEEP"] = "0.2"
            norm = Norm(home)
            with mock.patch.object(w, "new_code", counter()):
                fakes.ready_for_s3(w)
                reg = w.Registry.load()
                reg.data["agent"] = agent
                reg.save()
                w.AUTO_TICK, w.AUTO_POLL, w.AUTO_BOX_SEC, w.AUTO_MIN_SEC = 0.3, 0.05, 30, 0
                text = cap(w, "new", "s3", "--task", "T3", "--auto", "--yes")
                out["%s-auto-T3" % agent] = norm(text)
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    return out


if __name__ == "__main__":
    dest = sys.argv[1]
    os.makedirs(dest, exist_ok=True)
    for name, text in capture_all().items():
        with open(os.path.join(dest, name + ".txt"), "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    print("wrote", len(os.listdir(dest)), "files to", dest)
