#!/usr/bin/env python3
"""`vesper play` must show the same frames as `vesper run`, and fail the same way.

Environment (or same-name command line options through unittest is not used):
  VESPER_BIN          binary to test
  VESPER_KEYS_HELPER  path of the helper that writes test input (kept outside this repo)
  VESPER_GRADER_DIR   directory that holds reference/ and mutants/ (.vsa files)
"""
import importlib.util, os, struct, subprocess, sys, tempfile, unittest, zlib

BIN = os.environ.get("VESPER_BIN")
HELPER = os.environ.get("VESPER_KEYS_HELPER")
GRADER = os.environ.get("VESPER_GRADER_DIR")
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


def run_frames(prog, keyfile, nframes, extra=()):
    with tempfile.TemporaryDirectory() as d:
        p = subprocess.run([BIN, "run", prog, "--frames", str(nframes), "--input", keyfile, "--out", d, *extra],
                           capture_output=True)
        assert p.returncode == 0, p.stdout
        return [decode_png(os.path.join(d, "frame_%04d.png" % i)) for i in range(nframes)]


def play_frames(prog, lines, extra=()):
    stdin = ("\n".join(lines) + "\n").encode() if lines else b""
    p = subprocess.run([BIN, "play", prog, *extra], input=stdin, capture_output=True)
    n = len(p.stdout) // (W * H * 3)
    assert len(p.stdout) % (W * H * 3) == 0, len(p.stdout)
    return [p.stdout[i * W * H * 3:(i + 1) * W * H * 3] for i in range(n)], p


@unittest.skipUnless(BIN and HELPER and GRADER, "set VESPER_BIN, VESPER_KEYS_HELPER, VESPER_GRADER_DIR")
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
        return os.path.join(GRADER, "reference", name + ".vsa")

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
                             stderr=subprocess.PIPE)
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
            prog = os.path.join(GRADER, "mutants", name + ".vsa")
            r = subprocess.run([BIN, "run", prog, "--frames", "5"], capture_output=True)
            got, p = play_frames(prog, ["", ""])
            self.assertNotEqual(r.returncode, 0, name)
            self.assertEqual(p.returncode, r.returncode, name)
            self.assertEqual(p.stderr, r.stdout, name)  # run prints the error on stdout, play on stderr
            self.assertEqual(p.stdout, b"", name)

    def test_bad_option_same_code(self):
        r = subprocess.run([BIN, "run", self.ref("T3"), "--bogus", "1"], capture_output=True)
        p = subprocess.run([BIN, "play", self.ref("T3"), "--bogus", "1"], capture_output=True)
        self.assertEqual((p.returncode, p.stderr, p.stdout), (r.returncode, r.stdout, b""))


if __name__ == "__main__":
    unittest.main(verbosity=2)
