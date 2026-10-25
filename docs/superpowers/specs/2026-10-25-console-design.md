# VESPER-16 pixel console — design (2026-10-25)

Goal: a good-looking pixel handheld VESPER-16 in the browser. Any user runs their own T3 or T6
program on it, live (keyboard) or as a replay of `vesper run` output. The deck uses the same page.

## Hard rule: no leak

The exercise ("there is no manual") must stay intact. No new file that ships to participants may
show the key-file format, the instruction set, registers, memory, the screen memory layout, or any
other machine detail. Python and HTML know only the public button names
(UP DOWN LEFT RIGHT A B SELECT START, already in the task files) and finished RGB pixels.

## Parts

1. **`vesper play <prog> [--frames N] [--seed N]`** — new mode in the C emulator
   (source: `../agents-skills-workshop/experiments/04-blackbox-console/private/src/vesper.c`).
   - stdin: one text line per frame: space-separated public button names held in that frame
     (empty line = none). EOF = stop.
   - stdout: for every frame, exactly 64*48*3 = 9216 bytes RGB, row 0 first. Frame 0 is sent
     before the first stdin line is read (same frame-0 semantics as `run`).
   - On assembler or runtime error: print the SAME error text that `run` prints to stderr, exit
     with the same code. Never print machine state.
   - `run` and `asm` code paths unchanged. Windows: stdin/stdout in binary mode, flush every frame.
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
     light), background = workbench art (`effective-skills/vesper-directions/assets/pixel.png`,
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
4. **Deck copy** — `presentations/effective-skills/vesper-console/`: built `console.html` with two
   embedded reference replays (T3 and T6, recorded with `vesper run` using a hand-made key file
   that shows the games well; T6 name "VESPER"). Only new files in a new folder; nothing existing
   is edited.

## Tests (must pass before anything ships)

1. Binary safety: old vs new binary, `vesper run` on examples + `private/grader/reference/*.vsa`
   + `private/grader/mutants/*.vsa` with ≥ 20 key files (random, long holds, empty, all buttons):
   stdout, exit code and every frame byte-identical. Script: `console/tests/compare_binaries.py`.
2. `play` vs `run`: same program + keys → identical frames (from PNG decode) for T3, T4, T6
   references. Error programs → same text and code.
3. `play.py` unit test with a fake emulator: key forward, frame forward, error path, restart.
4. Browser screenshots 1280×720: boot, T3 live, T6 replay, error screen, motion off.
5. Leak review by an independent agent over every shipped new file.

## Delivery

Branch `console` in `vesper-16` and in `agents-skills-workshop`. New binaries go into
`vesper-16/bin/` on the branch only. Nothing is pushed or merged until the user says so.
