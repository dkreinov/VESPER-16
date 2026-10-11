# VESPER-16 development kit

Write the game described in [tasks/T3.md](tasks/T3.md) for the VESPER-16 handheld console.
The kit contains the console's assembler + emulator and two tiny example programs.
There is no manual — working out how the console behaves is part of the exercise.

<p align="center"><img src="media/t3-squash.gif" alt="T3 squash running on VESPER-16: the paddle returns the ball, the green score bar grows, a miss resets the game" width="384"></p>
<p align="center"><sub>What a finished T3 looks like (12 s from a real solution, frames 600–960, scaled 6×):
the paddle returns the ball and the green score bar grows; a miss resets the score and relaunches the ball.</sub></p>

**Bonus:** [tasks/T4.md](tasks/T4.md) is a second game, Breakout, for anyone who finishes early or wants
to try a skill on a game it was not written for.

<p align="center"><img src="media/t4-breakout.gif" alt="T4 Breakout running on VESPER-16: the ball breaks the last bricks, the wall refills and the ball waits on the paddle" width="384"></p>
<p align="center"><sub>What a finished T4 looks like (12 s from a real solution, frames 600–960, scaled 6×):
the last bricks break, the full wall comes back and the ball rests on the paddle until A is pressed.</sub></p>

## Design concepts

These illustrations show a possible physical design for the VESPER-16 processor and handheld
console. They are design concepts; the development kit runs the machine in an emulator.

![VESPER-16 processor package concept](media/vesper16-processor-concept.png)

*Processor package concept.*

![VESPER-16 exploded handheld console concept](media/vesper16-console-concept.png)

*Exploded handheld console concept, showing the display, controls, board and V16 processor.*

## Requirements

- **Linux x86-64** (`bin/vesper`) or **Windows x64** (`bin/vesper.exe`). Both are self-contained
  executables and behave identically. macOS: use a Linux VM or container.
- A web browser for the frame viewer (`player.html`).
- Python 3 — only for `unlock.py` (and the grader, which also needs numpy), used later in the workshop.

## Start

Linux:
```sh
git clone https://github.com/dkreinov/VESPER-16.git
cd VESPER-16
chmod +x bin/vesper
bin/vesper run examples/fill.vsa --frames 30 --out out/fill
```

Windows (PowerShell):
```powershell
git clone https://github.com/dkreinov/VESPER-16.git
cd VESPER-16
.\bin\vesper.exe run examples\fill.vsa --frames 30 --out out\fill
```

Both print `OK 30 frames` and write `out/fill/frame_0000.png …`. Open `player.html` in a browser
and drop the output folder (or a `--gif` file) onto it to watch the frames.

Where the task files write `bin/vesper`, Windows users run `.\bin\vesper.exe`.
Save your program as `solutions/T3.vsa` (bonus: `solutions/T4.vsa`).

## Rules for the exercise

- Leave `bin/`, `examples/` and `tasks/` unchanged.
- This kit imposes no limit on emulator runs. If your presenter announces a run budget for a stage,
  count your `vesper run` calls yourself (`vesper asm` is free).
- Some later parts of the workshop are in `locked/`. Your presenter gives the password for each part
  when it starts; then run `python unlock.py <part> <password>` (it extracts into `unlocked/part-<n>/`).
  Don't try to open them earlier.

## Files

```text
bin/vesper          assembler + emulator (Linux x86-64)
bin/vesper.exe      assembler + emulator (Windows x64)
examples/fill.vsa   small sample program
examples/pixel.vsa  small sample program
tasks/T3.md         the game task
tasks/T4.md         bonus game (Breakout)
player.html         offline viewer for --out folders and --gif files
media/              the demo GIFs and design concept images above
solutions/          save your game here
locked/             later workshop parts (password-protected)
unlock.py           opens a locked part into unlocked/part-<n>/
```
