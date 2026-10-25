# VESPER-16 pixel console — design (2026-10-25)

Goal: a good-looking pixel handheld VESPER-16 in the browser. Any user runs their own T3 or T6
program on it, live (keyboard) or as a replay of `vesper run` output. The deck uses the same page.

## Hard rule: no leak

The exercise ("there is no manual") must stay intact. No new file that ships to participants may
show the key-file format, the instruction set, registers, memory, the screen memory layout, or any
other machine detail. Python and HTML know only the public button names
(UP DOWN LEFT RIGHT A B SELECT START, already in the task files) and finished RGB pixels.

## Parts

1. **`vesper-play <prog>` (`vesper-play play <prog> [--frames N] [--seed N]`)** — a separate emulator
   binary with a `play` mode, built from the emulator source with a build switch. The public
   `bin/vesper` and `bin/vesper.exe` are the original binaries and are not changed; workshop run
   folders get only those, never the play binary. The play binary lives in `console/bin/`.
   - stdin: one text line per frame: space-separated public button names held in that frame
     (empty line = none). EOF = stop.
   - stdout: for every frame, exactly 64*48*3 = 9216 bytes RGB, row 0 first. Frame 0 is sent
     before the first stdin line is read (same frame-0 semantics as `run`).
   - On assembler or runtime error: print the SAME error text that `run` prints to stderr, exit
     with the same code. Never print machine state.
   - `run` and `asm` code paths unchanged. `play` writes no usage-log line; `--version` ends with
     `+play`. A key line of any length is one frame. Windows: stdin/stdout in binary mode, flush every frame.
2. **`console/play.py <prog.vsa> [--vesper PATH]`** — Python 3.9+, stdlib only.
   Starts `vesper play`, serves `console.html` on 127.0.0.1 (free port), opens the browser.
   Browser → server: held buttons (WebSocket-free: simple long-poll or SSE + POST is fine).
   Server → browser: frames at 60 fps, plus error text and exit status. Paces frames itself.
   Endpoint to restart (R) and to switch program (1/2 when two programs are given:
   `play.py solutions/T3.vsa solutions/T6.vsa`).
3. **`console/console.html`** — one offline file, no external libraries.
   - LIVE mode when served by play.py; REPLAY mode when opened as a file (drop an `out/` folder of
     `frame_*.png` or a `--gif` file, like `player.html`).
   - Look: re-drawn pixel console in the deck style (grey body, stepped pixel edges, orange rim
     light), background = workbench art (`console/assets/workbench.webp`,
     dimmed, blurred, embedded as data URI, compressed ≤ 400 KB). Screen exactly 4:3, integer pixel
     scale, `image-rendering: pixelated`. Subtle LCD grid + glow, toggle G.
   - D-pad, A, B, SELECT, START press down 2 px and glow orange while held, only
     in LIVE mode. REPLAY mode does not read key files (that would need the format), so the
     buttons stay still there.
   - Cartridge label on top edge: "T3 SQUASH" / "T6 NAMEPLATE" (or the file name). Keys 1/2 slide
     one cartridge out and the other in (~0.6 s), then boot splash "VESPER-16".
   - Status line: LIVE / REPLAY, frame number.
   - One error screen for every failure: LED red, screen dims, the vesper error text shows under
     the console. R restarts.
   - Keys: arrows = D-pad, Z = A, X = B, Enter = START, Shift = SELECT. Deck keys: Space
     play/pause (replay), R restart, M motion off (no slide/splash/pulse), F fullscreen,
     B blank, G LCD effect, 1/2 cartridge, L try live (when served).
4. **Deck copy** — a folder outside this repository: built `console.html` with two embedded
   replays (T3 and T6, recorded with `vesper-play`). Recordings and screenshots of finished
   solutions stay in that folder and never enter this repository.

## Tests (must pass before anything ships)

1. Binary safety: the public `bin/vesper(.exe)` must equal the original binaries (sha256 against
   the commit before the console work). `console/tests/compare_binaries.py` compares two
   binaries on any program folders and key files (stdout, exit code, every output file).
2. `play` vs `run`: same program + keys → identical frames (from PNG decode) for T3, T4, T6.
   Assembler errors and run-time errors → same text and code, and the frames before the error.
   Long key line = one frame; no usage-log line. Script: `console/tests/test_play_vs_run.py`.
3. `play.py` unit test with a fake emulator: key forward, frame forward, error path, restart,
   port fallback, Host/Origin checks, bad Content-Length.
4. Browser screenshots 1280×720: boot, T3 live, T6 replay, error screen, motion off.
5. Leak review by an independent reviewer over every shipped new file.

## Delivery

Branch `console`. The play binaries go into `console/bin/` on the branch only; `bin/` is unchanged.
Nothing is pushed or merged until the user says so.
