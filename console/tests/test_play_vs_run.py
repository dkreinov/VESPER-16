#!/usr/bin/env python3
"""`vesper-play` must show the same frames as the normal `vesper run`, and fail the same way.

Environment:
  VESPER_BIN          the play binary (console/bin/vesper-play[.exe])
  VESPER_RUN_BIN      the normal kit binary (bin/vesper[.exe]) used as the reference for `run`
  VESPER_KEYS_HELPER  path of the helper that writes test input (kept outside this repo)
  VESPER_OK_DIR       folder with T3.vsa, T4.vsa, T6.vsa (programs that run without errors)
  VESPER_BAD_DIR      folder with broken_syntax.vsa and empty.vsa (assembler errors)
  VESPER_RT_DIR       folder with programs that fail at run time after a few frames (E20-E23)

Frame 0: `play` writes frame 0 before it reads any input line, so frame 0 never sees keys.
The helper makes the key file the same way (no keys at frame 0), so both sides compare equal.
"""
import glob, importlib.util, os, struct, subprocess, sys, tempfile, unittest, zlib

BIN = os.environ.get("VESPER_BIN")
RUN_BIN = os.environ.get("VESPER_RUN_BIN")
HELPER = os.environ.get("VESPER_KEYS_HELPER")
OK_DIR = os.environ.get("VESPER_OK_DIR")
BAD_DIR = os.environ.get("VESPER_BAD_DIR")
RT_DIR = os.environ.get("VESPER_RT_DIR")
W, H = 64, 48
NFRAMES = 90


def decode_png(path):
    """Minimal PNG decoder: 8-bit RGB, filter type 0 only (what the emulator writes). Returns raw RGB bytes."""
    try:
        from PIL import Image
        import numpy as np
        return np.asarray(Image.open(path).convert("RGB"), dtype="uint8").tobytes()
    except ImportError:
        pass
    d = open(path, "rb").read()
    assert d[:8] == b"\x89PNG\r\n\x1a\n"
    pos, idat, w, h = 8, b"", 0, 0
    while pos < len(d):
        n, t = struct.unpack(">I4s", d[pos:pos + 8])
        body = d[pos + 8:pos + 8 + n]
        if t == b"IHDR":
            w, h, bd, ct = struct.unpack(">IIBB", body[:10])
            assert bd == 8 and ct == 2
        elif t == b"IDAT":
            idat += body
        pos += 12 + n
    raw = zlib.decompress(idat)
    row = 1 + w * 3
    out = bytearray()
    for y in range(h):
        assert raw[y * row] == 0, "unsupported PNG filter"
        out += raw[y * row + 1:(y + 1) * row]
    return bytes(out)


def quiet_env(log=None):
    env = dict(os.environ)
    env.pop("VESPER_NO_LOG", None)
    env["VESPER_RUNLOG"] = log or os.devnull
    return env


def run_frames(prog, keyfile, nframes, extra=()):
    with tempfile.TemporaryDirectory() as d:
        p = subprocess.run([RUN_BIN, "run", prog, "--frames", str(nframes), "--input", keyfile, "--out", d, *extra],
                           capture_output=True)
        assert p.returncode == 0, p.stdout
        return [decode_png(os.path.join(d, "frame_%04d.png" % i)) for i in range(nframes)]


def play_frames(prog, lines, extra=()):
    stdin = ("\n".join(lines) + "\n").encode() if lines else b""
    p = subprocess.run([BIN, "play", prog, *extra], input=stdin, capture_output=True, env=quiet_env())
    n = len(p.stdout) // (W * H * 3)
    assert len(p.stdout) % (W * H * 3) == 0, len(p.stdout)
    return [p.stdout[i * W * H * 3:(i + 1) * W * H * 3] for i in range(n)], p


@unittest.skipUnless(BIN and RUN_BIN and HELPER and OK_DIR and BAD_DIR and RT_DIR,
                     "set VESPER_BIN, VESPER_RUN_BIN, VESPER_KEYS_HELPER, VESPER_OK_DIR, VESPER_BAD_DIR, VESPER_RT_DIR")
class PlayVsRun(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("keys_helper", HELPER)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        cls.tmp = tempfile.TemporaryDirectory()
        cls.cases = mod.make_cases(cls.tmp.name, NFRAMES, 5, 24)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def ref(self, name):
        return os.path.join(OK_DIR, name + ".vsa")

    def test_frames_equal(self):
        count = 0
        for t in ("T3", "T4", "T6"):
            for c in self.cases:
                want = run_frames(self.ref(t), c["keyfile"], NFRAMES)
                got, p = play_frames(self.ref(t), c["lines"])  # EOF ends the stream
                self.assertEqual(p.returncode, 0, (t, c["name"]))
                self.assertEqual(len(got), NFRAMES, (t, c["name"]))
                for i in range(NFRAMES):
                    self.assertEqual(got[i], want[i], "%s %s frame %d" % (t, c["name"], i))
                    count += 1
        print("compared %d frames" % count)

    def test_frames_limit_and_seed(self):
        c = self.cases[-1]
        for seed in ("7", "0x1234"):
            want = run_frames(self.ref("T3"), c["keyfile"], 40, ("--seed", seed))
            got, p = play_frames(self.ref("T3"), c["lines"], ("--frames", "40", "--seed", seed))
            self.assertEqual(got, want)
            self.assertEqual(p.returncode, 0)

    def test_frame0_before_first_line(self):
        p = subprocess.Popen([BIN, "play", self.ref("T3")], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, env=quiet_env())
        try:
            f0 = p.stdout.read(W * H * 3)  # nothing was written to stdin yet
            self.assertEqual(len(f0), W * H * 3)
            p.stdin.write(b"\n"); p.stdin.flush()
            self.assertEqual(len(p.stdout.read(W * H * 3)), W * H * 3)
        finally:
            p.stdin.close(); p.wait(timeout=10)
        self.assertEqual(p.returncode, 0)

    def test_errors_same_text_and_code(self):
        for name in ("broken_syntax", "empty"):
            prog = os.path.join(BAD_DIR, name + ".vsa")
            r = subprocess.run([RUN_BIN, "run", prog, "--frames", "5"], capture_output=True)
            got, p = play_frames(prog, ["", ""])
            self.assertNotEqual(r.returncode, 0, name)
            self.assertEqual(p.returncode, r.returncode, name)
            self.assertEqual(p.stderr, r.stdout, name)  # run prints the error on stdout, play on stderr
            self.assertEqual(p.stdout, b"", name)

    def test_runtime_errors_same_text_code_and_frames(self):
        """E20-E23 happen after 3 frames: play must send those frames, then the same error and exit code."""
        progs = sorted(glob.glob(os.path.join(RT_DIR, "*.vsa")))
        self.assertGreaterEqual(len(progs), 3)
        for prog in progs:
            name = os.path.basename(prog)
            with tempfile.TemporaryDirectory() as d:
                r = subprocess.run([RUN_BIN, "run", prog, "--frames", "20", "--out", d], capture_output=True)
                want = [decode_png(os.path.join(d, f)) for f in sorted(os.listdir(d))]
            got, p = play_frames(prog, [""] * 30)
            self.assertEqual(r.returncode, 2, name)
            self.assertEqual(p.returncode, r.returncode, name)
            self.assertEqual(p.stderr, r.stdout, name)
            self.assertEqual(got, want, name)
            self.assertGreaterEqual(len(got), 1, name)

    def test_long_line_is_one_frame(self):
        """A key line longer than 1 KB is still one frame (it must not be cut into two)."""
        long_line = "UP" + " " * 3000
        got, p = play_frames(self.ref("T3"), [long_line] * 3)
        base, _ = play_frames(self.ref("T3"), ["UP"] * 3)
        self.assertEqual(len(got), 4)
        self.assertEqual(got, base)

    def test_no_log_and_version(self):
        with tempfile.TemporaryDirectory() as d:
            log = os.path.join(d, "runs.log")
            subprocess.run([BIN, "play", self.ref("T3")], input=b"\n\n", capture_output=True, env=quiet_env(log))
            self.assertFalse(os.path.exists(log), "play must not write a usage log line")
        v = subprocess.run([BIN, "--version"], capture_output=True, env=quiet_env()).stdout.decode().strip()
        self.assertTrue(v.endswith("+play"), v)

    def test_bad_option_same_code(self):
        r = subprocess.run([RUN_BIN, "run", self.ref("T3"), "--bogus", "1"], capture_output=True)
        p = subprocess.run([BIN, "play", self.ref("T3"), "--bogus", "1"], capture_output=True, env=quiet_env())
        self.assertEqual((p.returncode, p.stderr, p.stdout), (r.returncode, r.stdout, b""))


if __name__ == "__main__":
    unittest.main(verbosity=2)
