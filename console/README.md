# VESPER-16 pixel console

A pixel handheld in your browser. It shows your program live, or plays back saved frames.
You need Python 3.9 or newer. You need no other package.

## Live: play your program

1. Open a terminal in the `vesper-16` folder.
2. Run: `python console/play.py solutions/T3.vsa`
3. The browser opens. Click the page once, then use the keys below.

Give two programs to switch between them with the keys 1 and 2:

    python console/play.py solutions/T3.vsa solutions/T6.vsa

The console runs the play emulator `console/bin/vesper-play` (`vesper-play.exe` on Windows). It is a separate file from `bin/vesper`.

Options: `--vesper PATH` (use another play emulator file), `--no-browser` (only print the address), `--port N` (default 8765).
Press Ctrl+C in the terminal to stop.

If your program has an error, the console shows a red light and a dark screen.
The error text from the emulator shows under the console. Fix the file, then press R.

## Replay: look at saved frames

1. Open `console/console.html` in the browser (double-click the file).
2. Drop a folder of `frame_NNNN.png` files on the page, or drop a `.gif` file.
   You can also use the "Open folder" and "Open PNG files / GIF" buttons.
3. Press Space to pause or play. Use the left and right arrows to step.

In replay the buttons on the console do not move. Replay never reads your key file.
When the page is served by `play.py`, you can still drop frames. Press L to go back to live.

## Keys

| Key | Action |
| --- | --- |
| Arrow keys | D-pad |
| Z / X | A / B |
| Enter | START |
| Shift | SELECT |
| 1 / 2 | Change cartridge |
| R | Restart (live) or go to frame 0 (replay) |
| Space | Play / pause (replay) |
| M | Motion off (no slide, splash or pulse) |
| F | Full screen |
| B | Blank screen |
| G | All LCD effects on or off (grid, glow, afterglow) |
| + / = and - / _ (also numpad) | Speed 30, 60, 90 or 120 fps (live and replay). The status line shows it when it is not 60. |
| L | Back to live (when served by `play.py`) |

Afterglow: each screen pixel fades from its old colour over about 100 ms (6 emulator frames), so a one-frame touch shows as a short flash. It follows the emulator frames, not the clock. When paused, stepping or scrubbing, the page shows the exact frame. Static pixels keep their exact colour.

## Files

- `play.py` - the launcher and small web server.
- `bin/` - the play emulator for Windows and Linux (x86-64).
- `console.html` - the page (one file, works offline). Built from `console.src.html`.
- `build_console.py` - rebuilds `console.html` with the background picture from `assets/workbench.webp`.
- `tests/` - tests and a fake emulator for them.

## For the presenter

`python console/build_console.py --deck DIR` builds `DIR/VESPER-Console.html` from recorded frames and button lines listed in `DIR/demos.json`. It writes only into DIR. See the docstring in `build_console.py`.
