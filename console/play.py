#!/usr/bin/env python3
"""VESPER-16 pixel console launcher (stdlib only, Python 3.9+).

    python console/play.py solutions/T3.vsa [solutions/T6.vsa] [--vesper PATH] [--no-browser]

Starts `vesper play <program>`, serves console.html on 127.0.0.1 and opens the browser.

Talks to the emulator with public things only:
  - stdin : one line per frame, the held button names (UP DOWN LEFT RIGHT A B SELECT START)
  - stdout: 64*48*3 bytes of RGB per frame
  - stderr: error text, shown as it is
"""
import argparse
import base64
import json
import os
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

W, H = 64, 48
FRAME_BYTES = W * H * 3
BUTTONS = ("UP", "DOWN", "LEFT", "RIGHT", "A", "B", "SELECT", "START")
FPS = 60
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
TITLES = {"T3": "SQUASH", "T6": "NAMEPLATE"}


def default_vesper():
    return ROOT / "bin" / ("vesper.exe" if os.name == "nt" else "vesper")


def cart_label(path):
    stem = Path(path).stem
    name = TITLES.get(stem.upper())
    return f"{stem.upper()} {name}" if name else stem.upper()


class Runner:
    """Owns one `vesper play` process at a time and paces its frames."""

    def __init__(self, programs, vesper, fps=FPS):
        self.programs = [str(p) for p in programs]
        self.vesper = str(vesper)
        self.fps = fps
        self.cond = threading.Condition()
        self.lifecycle = threading.Lock()
        self.closing = False
        self.index = 0
        self.gen = 0
        self.proc = None
        self.held = []
        self.frame = None
        self.frame_no = -1
        self.state = "idle"       # idle | running | error | ended
        self.code = None
        self.error = ""
        self.seq = 0              # bumps on every change
        self.status_seq = 0       # bumps on every status change

    # ---- public API
    def command(self, program):
        cmd = [self.vesper]
        if self.vesper.lower().endswith(".py"):
            cmd = [sys.executable, self.vesper]
        return cmd + ["play", program]

    def set_held(self, names):
        wanted = set(names)
        self.held = [b for b in BUTTONS if b in wanted]

    def status(self):
        with self.cond:
            return self._status_locked()

    def _status_locked(self):
        return {
            "mode": "live",
            "carts": [{"file": os.path.basename(p), "label": cart_label(p)} for p in self.programs],
            "cart": self.index,
            "state": self.state,
            "code": self.code,
            "error": self.error,
            "epoch": self.gen,
        }

    def start(self, index=None):
        with self.lifecycle:
            self._stop_locked()
            if index is not None:
                self.index = index
            self.gen += 1
            gen = self.gen
            with self.cond:
                self.frame = None
                self.frame_no = -1
                self.code = None
                self.error = ""
            try:
                proc = subprocess.Popen(
                    self.command(self.programs[self.index]),
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                )
            except OSError as e:
                self._set_state("error", -1, f"cannot start the emulator: {e}")
                return
            self.proc = proc
            errbuf = bytearray()
            errthread = threading.Thread(target=self._drain, args=(proc, errbuf), daemon=True)
            errthread.start()
            self._set_state("running")
            threading.Thread(target=self._pump, args=(gen, proc, errbuf, errthread), daemon=True).start()

    def restart(self):
        self.start()

    def switch(self, index):
        if not 0 <= index < len(self.programs):
            raise ValueError("no such cartridge")
        self.start(index)

    def stop(self):
        with self.lifecycle:
            self.closing = True
            self._stop_locked()
        with self.cond:
            self.cond.notify_all()

    # ---- internals
    def _stop_locked(self):
        proc, self.proc = self.proc, None
        self.gen += 1          # supersedes the running pump thread
        if proc is None:
            return
        for stream in (proc.stdin,):
            try:
                stream.close()
            except OSError:
                pass
        try:
            proc.kill()
        except OSError:
            pass
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            pass

    @staticmethod
    def _drain(proc, buf):
        try:
            for chunk in iter(lambda: proc.stderr.read(4096), b""):
                buf.extend(chunk)
        except (OSError, ValueError):
            pass
        finally:
            try:
                proc.stderr.close()
            except (OSError, ValueError):
                pass

    def _set_state(self, state, code=None, error=""):
        with self.cond:
            self.state, self.code, self.error = state, code, error
            self.status_seq += 1
            self.seq += 1
            self.cond.notify_all()

    def _publish(self, frame, n):
        with self.cond:
            self.frame, self.frame_no = frame, n
            self.seq += 1
            self.cond.notify_all()

    @staticmethod
    def _read_frame(proc):
        try:
            data = proc.stdout.read(FRAME_BYTES)
        except (OSError, ValueError):
            return None
        return data if data is not None and len(data) == FRAME_BYTES else None

    def _pump(self, gen, proc, errbuf, errthread):
        try:
            self._pump_inner(gen, proc, errbuf, errthread)
        finally:
            try:
                proc.stdout.close()
            except (OSError, ValueError):
                pass

    def _pump_inner(self, gen, proc, errbuf, errthread):
        n = 0
        frame = self._read_frame(proc)             # frame 0 comes before any input
        next_t = time.monotonic()
        while frame is not None and gen == self.gen:
            self._publish(frame, n)
            next_t += 1.0 / self.fps
            delay = next_t - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            elif delay < -0.25:
                next_t = time.monotonic()
            if gen != self.gen:
                return
            line = (" ".join(self.held) + "\n").encode("ascii")
            try:
                proc.stdin.write(line)
                proc.stdin.flush()
            except (OSError, ValueError):
                break
            frame = self._read_frame(proc)
            n += 1
        if gen != self.gen:
            return
        try:
            code = proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
            code = proc.wait()
        errthread.join(timeout=1)
        text = bytes(errbuf).decode("utf-8", "replace").strip()
        if gen != self.gen:
            return
        if code != 0 or text:
            self._set_state("error", code, text or f"the emulator stopped (exit code {code})")
        else:
            self._set_state("ended", code)


def make_handler(runner, page_path):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def _send(self, code, body, ctype="application/json"):
            if isinstance(body, (dict, list)):
                body = json.dumps(body).encode()
            elif isinstance(body, str):
                body = body.encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _origin_ok(self):
            origin = self.headers.get("Origin")
            return origin is None or origin.split("://", 1)[-1] == self.headers.get("Host")

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path in ("/", "/index.html", "/console.html"):
                try:
                    self._send(200, Path(page_path).read_bytes(), "text/html; charset=utf-8")
                except OSError as e:
                    self._send(500, f"cannot read console.html: {e}", "text/plain")
            elif path == "/api/status":
                self._send(200, runner.status())
            elif path == "/api/events":
                self._events()
            else:
                self._send(404, {"ok": False, "error": "not found"})

        def do_POST(self):
            if not self._origin_ok():
                self._send(403, {"ok": False, "error": "bad origin"})
                return
            n = int(self.headers.get("Content-Length") or 0)
            try:
                body = json.loads(self.rfile.read(n) or b"{}")
                if not isinstance(body, dict):
                    raise ValueError("body must be an object")
            except ValueError as e:
                self._send(400, {"ok": False, "error": str(e)})
                return
            path = self.path.split("?", 1)[0]
            try:
                if path == "/api/keys":
                    held = body.get("held", [])
                    if not isinstance(held, list):
                        raise ValueError("held must be a list")
                    runner.set_held([b for b in held if b in BUTTONS])
                elif path == "/api/restart":
                    runner.restart()
                elif path == "/api/cart":
                    runner.switch(int(body.get("index", -1)))
                else:
                    self._send(404, {"ok": False, "error": "not found"})
                    return
            except (ValueError, TypeError) as e:
                self._send(400, {"ok": False, "error": str(e)})
                return
            self._send(200, {"ok": True})

        def _events(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True
            seen_status, seen_frame = -1, -2
            try:
                while not runner.closing:
                    with runner.cond:
                        runner.cond.wait_for(
                            lambda: runner.closing or runner.status_seq != seen_status
                            or runner.frame_no != seen_frame, timeout=10)
                        status = runner._status_locked()
                        s_seq, frame, f_no = runner.status_seq, runner.frame, runner.frame_no
                    out = b""
                    if s_seq != seen_status:
                        out += b"event: status\ndata: " + json.dumps(status).encode() + b"\n\n"
                        seen_status = s_seq
                    if f_no != seen_frame:
                        seen_frame = f_no
                        if frame is not None:
                            out += (b"event: frame\nid: %d\ndata: " % f_no
                                    + base64.b64encode(frame) + b"\n\n")
                    self.wfile.write(out or b": keepalive\n\n")
                    self.wfile.flush()
            except (OSError, ValueError):
                pass

    return Handler


def main(argv=None):
    ap = argparse.ArgumentParser(description="VESPER-16 pixel console")
    ap.add_argument("programs", nargs="+", help="one or two .vsa programs (keys 1 and 2 switch)")
    ap.add_argument("--vesper", default=None, help="path to the vesper program (default: bin/vesper[.exe])")
    ap.add_argument("--no-browser", action="store_true", help="do not open the browser")
    ap.add_argument("--port", type=int, default=8765, help="port (default: 8765, or any free port if it is busy)")
    args = ap.parse_args(argv)

    for p in args.programs:
        if not os.path.isfile(p):
            ap.error(f"program not found: {p}")
    vesper = Path(args.vesper) if args.vesper else default_vesper()
    if not vesper.is_file():
        print(f"warning: emulator not found: {vesper}", file=sys.stderr)

    runner = Runner(args.programs, vesper)
    try:
        server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(runner, HERE / "console.html"))
    except OSError:
        if args.port == 0:
            raise
        print(f"port {args.port} is busy, using a free port", file=sys.stderr)
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(runner, HERE / "console.html"))
    server.daemon_threads = True
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    runner.start(0)
    print(f"VESPER-16 console: {url}   (Ctrl+C to stop)", flush=True)
    if not args.no_browser:
        threading.Timer(0.3, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        print("\nstopping...", flush=True)
    finally:
        runner.stop()
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
