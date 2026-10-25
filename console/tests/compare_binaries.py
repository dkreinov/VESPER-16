#!/usr/bin/env python3
"""Binary safety check: an old and a new vesper must behave the same for `run` and `asm`.
(The public vesper is the old binary again, so old == current is expected to pass trivially.)

Compares stdout, exit code and every output file (frame PNGs, raw dump, GIF), byte for byte.

  python compare_binaries.py --old OLD --new NEW --keys-helper PATH_TO_HELPER \
      --programs DIR [DIR ...] [--frames 60] [--work DIR] [--log FILE] [--status FILE]

--keys-helper: path of a helper module that writes the test input files (kept outside this repo).
It must provide make_cases(outdir, nframes, seed, count) -> [{"name", "keyfile", "lines"}].
--programs: directories with .vsa files (for example the examples folder).
"""
import argparse, glob, hashlib, importlib.util, json, os, shutil, subprocess, sys, tempfile, time
from concurrent.futures import ThreadPoolExecutor


def load_helper(path):
    spec = importlib.util.spec_from_file_location("keys_helper", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def tree_hash(d):
    out = {}
    for root, _, files in os.walk(d):
        for f in sorted(files):
            p = os.path.join(root, f)
            with open(p, "rb") as fh:
                out[os.path.relpath(p, d).replace("\\", "/")] = hashlib.sha256(fh.read()).hexdigest()
    return out


def run_one(binary, args, work):
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work)
    full = [a.replace("@W", work) for a in args]
    env = dict(os.environ, VESPER_NO_LOG="1")   # never append to the kit's usage log
    p = subprocess.run([binary] + full, capture_output=True, timeout=300, env=env)
    return p.returncode, p.stdout, p.stderr, tree_hash(work)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--old", required=True)
    ap.add_argument("--new", required=True)
    ap.add_argument("--keys-helper", required=True)
    ap.add_argument("--programs", nargs="+", required=True)
    ap.add_argument("--frames", type=int, default=60)
    ap.add_argument("--cases", type=int, default=24)
    ap.add_argument("--work", default=None)
    ap.add_argument("--log", default="compare_binaries.log")
    ap.add_argument("--status", default="compare_binaries.status.json")
    ap.add_argument("--jobs", type=int, default=8)
    a = ap.parse_args()

    work = a.work or tempfile.mkdtemp(prefix="cmpbin_")
    os.makedirs(work, exist_ok=True)
    helper = load_helper(a.keys_helper)
    cases = helper.make_cases(os.path.join(work, "keys"), a.frames, 1, a.cases)
    progs = []
    for d in a.programs:
        progs += sorted(glob.glob(os.path.join(d, "*.vsa")))
    log = open(a.log, "w")

    def say(s):
        log.write(s + "\n"); log.flush()

    jobs = []
    for p in progs:
        for c in cases:
            jobs.append((p, c["name"], ["run", p, "--frames", str(a.frames), "--input", c["keyfile"],
                                         "--out", "@W/png", "--dump", "@W/dump.bin", "--gif", "@W/a.gif"]))
        jobs.append((p, "nokeys_seed", ["run", p, "--frames", "30", "--seed", "7", "--out", "@W/png"]))
        jobs.append((p, "scale", ["run", p, "--frames", "5", "--scale", "3", "--out", "@W/png"]))
        jobs.append((p, "asm", ["asm", p]))
    for i, args in enumerate([[], ["run"], ["run", "x.vsa", "--bogus", "1"], ["frobnicate", "x"],
                              ["run", progs[0], "--frames", "0"], ["--version"]]):
        jobs.append(("-", "misc%d" % i, args))

    fails, n = [], 0

    def check(j):
        prog, name, args = j
        tag = "%s|%s" % (os.path.basename(prog), name)
        safe = hashlib.md5(tag.encode()).hexdigest()[:10]
        o = run_one(a.old, args, os.path.join(work, "o_" + safe))
        w = run_one(a.new, args, os.path.join(work, "n_" + safe))
        shutil.rmtree(os.path.join(work, "o_" + safe), ignore_errors=True)
        shutil.rmtree(os.path.join(work, "n_" + safe), ignore_errors=True)
        diffs = []
        if o[0] != w[0]: diffs.append("exit %s != %s" % (o[0], w[0]))
        if o[1] != w[1]: diffs.append("stdout differs")
        if o[2] != w[2]: diffs.append("stderr differs")
        if o[3] != w[3]: diffs.append("output files differ (%d vs %d files)" % (len(o[3]), len(w[3])))
        return tag, diffs, o[0], len(o[3])

    t0 = time.time()
    frames_cmp = 0
    with ThreadPoolExecutor(a.jobs) as ex:
        for tag, diffs, rc, nf in ex.map(check, jobs):
            n += 1
            frames_cmp += nf
            say("%s %s rc=%s files=%d %s" % ("FAIL" if diffs else "ok  ", tag, rc, nf, "; ".join(diffs)))
            if diffs:
                fails.append({"case": tag, "diffs": diffs})
    status = {"done": True, "ok": not fails, "pairs": n, "failures": len(fails), "files_compared": frames_cmp,
              "programs": len(progs), "key_cases": len(cases), "seconds": round(time.time() - t0, 1),
              "failed": fails[:50]}
    with open(a.status, "w") as fh:
        json.dump(status, fh, indent=1)
    say(json.dumps({k: v for k, v in status.items() if k != "failed"}))
    print(json.dumps({k: v for k, v in status.items() if k != "failed"}))
    shutil.rmtree(work, ignore_errors=True) if not a.work else None
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
