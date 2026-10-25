"""play.py tests with the fake emulator. No browser. Run: python -m unittest console/tests/test_play_py.py"""
import base64
import http.client
import json
import sys
import tempfile
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import play  # noqa: E402

FAKE = str(HERE / "fake_vesper.py")


def wait_for(cond, timeout=8.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.01)
    return False


def dot_center(frame):
    """Centre of the bright 5x5 dot: pixels that differ from the background."""
    xs, ys = [], []
    for i in range(play.W * play.H):
        y, x = divmod(i, play.W)
        if 4 <= y < play.H - 1 and 1 <= x < play.W - 1 and frame[i * 3] > 200 and frame[i * 3 + 1] > 100:
            xs.append(x)
            ys.append(y)
    return (sum(xs) / len(xs), sum(ys) / len(ys)) if xs else None


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def prog(self, name, text="fake program\n"):
        p = Path(self.tmp.name) / name
        p.write_text(text)
        return str(p)

    def runner(self, *progs):
        r = play.Runner(progs, FAKE)
        self.addCleanup(r.stop)
        r.start(0)
        return r


class RunnerTests(Base):
    def test_frame_forward(self):
        r = self.runner(self.prog("T3.vsa"))
        self.assertTrue(wait_for(lambda: r.frame_no >= 5))
        self.assertEqual(len(r.frame), play.FRAME_BYTES)
        self.assertEqual(r.state, "running")

    def test_paces_about_60_fps(self):
        r = self.runner(self.prog("T3.vsa"))
        self.assertTrue(wait_for(lambda: r.frame_no >= 0))
        a, t0 = r.frame_no, time.time()
        time.sleep(3.0)                      # long window: a short stall cannot move the mean much
        rate = (r.frame_no - a) / (time.time() - t0)
        self.assertTrue(35 < rate < 75, rate)

    def test_key_forward(self):
        r = self.runner(self.prog("T3.vsa"))
        self.assertTrue(wait_for(lambda: r.frame_no >= 2))
        x0, y0 = dot_center(r.frame)
        r.set_held(["RIGHT", "DOWN", "NOPE"])
        self.assertEqual(r.held, ["DOWN", "RIGHT"])      # unknown names are dropped
        self.assertTrue(wait_for(lambda: dot_center(r.frame)[0] > x0 + 5 and dot_center(r.frame)[1] > y0 + 5))
        x1, y1 = dot_center(r.frame)
        self.assertGreater(x1, x0 + 5)
        self.assertGreater(y1, y0 + 5)
        r.set_held([])
        time.sleep(0.1)
        a = dot_center(r.frame)
        time.sleep(0.2)
        self.assertEqual(a, dot_center(r.frame))        # held set cleared: dot stops

    def test_held_stays_when_nothing_is_sent(self):
        r = self.runner(self.prog("T3.vsa"))
        self.assertTrue(wait_for(lambda: r.frame_no >= 1))
        r.set_held(["LEFT"])
        time.sleep(0.3)
        x1 = dot_center(r.frame)[0]
        time.sleep(0.3)
        self.assertLess(dot_center(r.frame)[0], x1)

    def test_error_path(self):
        r = self.runner(self.prog("T3.vsa", "FAKE_ERROR_AT=10\n"))
        self.assertTrue(wait_for(lambda: r.state == "error"))
        self.assertEqual(r.code, 3)
        self.assertIn("fake failure", r.error)

    def test_error_before_first_frame(self):
        r = self.runner(self.prog("T3.vsa", "FAKE_BAD\n"))
        self.assertTrue(wait_for(lambda: r.state == "error"))
        self.assertEqual(r.code, 2)
        self.assertIn("assembler", r.error)
        self.assertIsNone(r.frame)

    def test_missing_emulator(self):
        r = play.Runner([self.prog("T3.vsa")], str(Path(self.tmp.name) / "nope.exe"))
        self.addCleanup(r.stop)
        r.start(0)
        self.assertEqual(r.state, "error")
        self.assertIn("cannot start", r.error)

    def test_clean_end_is_not_an_error(self):
        r = self.runner(self.prog("T3.vsa", "FAKE_END_AT=5\n"))
        self.assertTrue(wait_for(lambda: r.state == "ended"))
        self.assertEqual(r.code, 0)

    def test_restart(self):
        r = self.runner(self.prog("T3.vsa", "FAKE_ERROR_AT=300\n"))
        self.assertTrue(wait_for(lambda: r.frame_no >= 1))
        r.set_held(["RIGHT"])
        self.assertTrue(wait_for(lambda: dot_center(r.frame)[0] > 40))
        epoch = r.gen
        r.set_held([])
        r.restart()
        self.assertGreater(r.gen, epoch)
        self.assertTrue(wait_for(lambda: r.frame is not None and r.frame_no < 20))
        self.assertAlmostEqual(dot_center(r.frame)[0], 32, delta=1)
        self.assertEqual(r.state, "running")

    def test_restart_after_error(self):
        r = self.runner(self.prog("T3.vsa", "FAKE_ERROR_AT=3\n"))
        self.assertTrue(wait_for(lambda: r.state == "error"))
        epoch = r.gen
        r.restart()
        self.assertGreater(r.gen, epoch)
        self.assertTrue(wait_for(lambda: r.state == "error" and r.gen > epoch + 1 or r.state == "running"))
        self.assertTrue(wait_for(lambda: r.state == "error" and r.code == 3))

    def test_cartridge_switch(self):
        r = self.runner(self.prog("T3.vsa"), self.prog("T6.vsa"))
        self.assertTrue(wait_for(lambda: r.frame_no >= 1))
        first = bytes(r.frame[:3])
        r.switch(1)
        self.assertEqual(r.index, 1)
        self.assertTrue(wait_for(lambda: r.frame is not None and r.frame_no >= 1))
        self.assertNotEqual(first, bytes(r.frame[:3]))   # the fake tints T6 differently
        with self.assertRaises(ValueError):
            r.switch(2)

    def test_command_for_py_emulator(self):
        r = play.Runner(["x.vsa"], FAKE)
        self.assertEqual(r.command("x.vsa")[1:], [FAKE, "play", "x.vsa"])

    def test_labels(self):
        self.assertEqual(play.cart_label("solutions/T3.vsa"), "T3 SQUASH")
        self.assertEqual(play.cart_label("solutions/T6.vsa"), "T6 NAMEPLATE")
        self.assertEqual(play.cart_label("my_game.vsa"), "MY_GAME")


class HttpTests(Base):
    def setUp(self):
        super().setUp()
        self.page = self.prog("console.html", "<html>page</html>")
        self.r = self.runner(self.prog("T3.vsa"), self.prog("T6.vsa"))
        self.srv = play.Server(("127.0.0.1", 0), play.make_handler(self.r, self.page))
        self.srv.daemon_threads = True
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)
        self.port = self.srv.server_address[1]

    def call(self, method, path, body=None, headers=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        c.request(method, path, json.dumps(body) if body is not None else None, headers or {})
        resp = c.getresponse()
        data = resp.read()
        c.close()
        return resp.status, data

    def test_page_and_status(self):
        st, data = self.call("GET", "/")
        self.assertEqual((st, data), (200, b"<html>page</html>"))
        st, data = self.call("GET", "/api/status")
        info = json.loads(data)
        self.assertEqual(info["mode"], "live")
        self.assertEqual([c["label"] for c in info["carts"]], ["T3 SQUASH", "T6 NAMEPLATE"])

    def test_keys_restart_cart_over_http(self):
        self.assertEqual(self.call("POST", "/api/keys", {"held": ["UP", "A"]})[0], 200)
        self.assertEqual(self.r.held, ["UP", "A"])
        self.assertEqual(self.call("POST", "/api/keys", {"held": "UP"})[0], 400)
        self.assertEqual(self.call("POST", "/api/cart", {"index": 1})[0], 200)
        self.assertEqual(self.r.index, 1)
        self.assertEqual(self.call("POST", "/api/cart", {"index": 9})[0], 400)
        epoch = self.r.gen
        self.assertEqual(self.call("POST", "/api/restart", {})[0], 200)
        self.assertGreater(self.r.gen, epoch)
        self.assertEqual(self.call("POST", "/api/nothing", {})[0], 404)
        self.assertEqual(self.call("POST", "/api/restart", {}, {"Origin": "http://evil.example"})[0], 403)

    def test_host_header_must_be_local(self):
        for path in ("/", "/api/status", "/api/events"):
            self.assertEqual(self.call("GET", path, None, {"Host": "evil.example:8765"})[0], 403, path)
        self.assertEqual(self.call("POST", "/api/restart", {}, {"Host": "evil.example"})[0], 403)
        self.assertEqual(self.call("GET", "/api/status", None, {"Host": "localhost:%d" % self.port})[0], 200)

    def test_events_reject_foreign_origin(self):
        st, _ = self.call("GET", "/api/events", None, {"Origin": "http://evil.example"})
        self.assertEqual(st, 403)

    def test_bad_content_length_is_400(self):
        for value in ("abc", "-5", "99999999"):
            c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
            c.putrequest("POST", "/api/keys")
            c.putheader("Content-Length", value)
            c.endheaders()
            self.assertEqual(c.getresponse().status, 400, value)
            c.close()


    def test_event_stream_carries_frames_and_status(self):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        c.request("GET", "/api/events")
        resp = c.getresponse()
        self.assertEqual(resp.getheader("Content-Type"), "text/event-stream")
        events = {}
        while "frame" not in events or "status" not in events:
            name = resp.fp.readline().decode().strip()
            if not name.startswith("event:"):
                continue
            kind = name.split(":", 1)[1].strip()
            lines = []
            while True:
                ln = resp.fp.readline().decode().rstrip("\n")
                if ln == "":
                    break
                lines.append(ln)
            events[kind] = [x for x in lines if x.startswith("data:")][0][5:].strip()
        c.close()
        self.assertEqual(len(base64.b64decode(events["frame"])), play.FRAME_BYTES)
        self.assertEqual(json.loads(events["status"])["state"], "running")

    def test_error_reaches_status(self):
        self.r.programs[0] = self.prog("bad.vsa", "FAKE_BAD\n")
        self.call("POST", "/api/restart", {})
        self.assertTrue(wait_for(lambda: json.loads(self.call("GET", "/api/status")[1])["state"] == "error"))
        info = json.loads(self.call("GET", "/api/status")[1])
        self.assertEqual(info["code"], 2)
        self.assertIn("assembler", info["error"])


class PortTests(unittest.TestCase):
    def test_busy_port_makes_bind_fail(self):
        import socket
        for reuse in (False, True):
            blocker = socket.socket()
            if reuse:
                blocker.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            blocker.bind(("127.0.0.1", 0))
            blocker.listen()
            port = blocker.getsockname()[1]
            try:
                with self.assertRaises(OSError):
                    play.Server(("127.0.0.1", port), play.make_handler(None, "x"))
            finally:
                blocker.close()

    def test_main_falls_back_to_free_port(self):
        import socket
        import subprocess
        blocker = socket.socket()
        blocker.bind(("127.0.0.1", 0))
        blocker.listen()
        port = blocker.getsockname()[1]
        prog = Path(tempfile.mkdtemp()) / "T3.vsa"
        prog.write_text("x")
        p = subprocess.Popen([sys.executable, "-u", str(HERE.parent / "play.py"), str(prog), "--no-browser",
                              "--vesper", FAKE, "--port", str(port)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            line = p.stdout.readline()
            self.assertIn("http://127.0.0.1:", line)
            self.assertNotIn(":%d/" % port, line)
        finally:
            p.terminate()
            p.wait(timeout=5)
            p.stdout.close()
            p.stderr.close()
            blocker.close()


if __name__ == "__main__":
    unittest.main()
