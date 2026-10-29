"""Manual demo of the `new s3 --auto` live screen: 4 fake agents, about 8 s, no real agent.
Run in a terminal (PowerShell):  python tests/demo_live.py"""
import json, os, shutil, sys, tempfile, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import workshop as w  # noqa: E402

SEC = 8.0
STEPS = [{"type": "command_execution", "command": "cat tasks/T3.md"},
         {"type": "command_execution", "command": "cat skill/SKILL.md"},
         {"type": "agent_message", "text": "plan"},
         {"type": "file_change"},
         {"type": "command_execution", "command": "bin/vesper asm x.vsa"},
         {"type": "command_execution", "command": "bin/vesper run x.vsa"}]


def main():
    tmp = tempfile.mkdtemp(prefix="demo_live_")
    items = []
    for key, label in [("t3", "T3 with skill"), ("n3", "T3 without skill"),
                       ("t6", "T6 with skill"), ("n6", "T6 without skill")]:
        f = os.path.join(tmp, key)
        os.makedirs(os.path.join(f, "solutions"))
        items.append(dict(folder=f, key=key, label=label, state="running", t0=time.time(), end=None,
                          sol_task="T3", rc=None, live_step=""))
    live = w.LiveView(items, SEC, "demo-model")
    live.header()
    t_start = time.time()
    try:
        while time.time() - t_start < SEC + 0.5:
            el = time.time() - t_start
            for i, it in enumerate(items):
                if it["state"] != "running":
                    continue
                n = min(int(el / SEC * (len(STEPS) + 1) + i * 0.4), len(STEPS))
                if n:
                    ev = STEPS[n - 1]
                    with open(os.path.join(it["folder"], "agent-output.jsonl"), "a") as fh:
                        fh.write(json.dumps({"type": "item.completed", "item": ev}) + "\n")
                    if "vesper run" in ev.get("command", ""):
                        with open(os.path.join(it["folder"], ".vesper-runs.log"), "a") as fh:
                            fh.write("%.0f run x\n" % time.time())
                    if n >= 4:
                        open(os.path.join(it["folder"], "solutions", "T3.vsa"), "w").close()
                if i == 0 and el > SEC * 0.5:
                    it["state"], it["end"] = "done", time.time()
                if i == 3 and el > SEC * 0.7:
                    it["state"], it["end"], it["err"] = "failed", time.time(), "demo error"
            live.draw()
            time.sleep(1.0)
    finally:
        for it in items:
            if it["state"] == "running":
                it["state"], it["end"] = "stopped", time.time()
        live.draw()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
