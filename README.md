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
- Python 3.9+ and git — for `workshop.py` (the grader also needs numpy: `pip install numpy`).

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

## Workshop

`workshop.py` runs the exercise in three stages and measures each one: agent time, emulator runs,
tokens, estimated API cost and score.

```sh
python workshop.py new s1                 # stage 1: checks this computer (doctor), then a clean folder + the prompt
python workshop.py done                   # the agent is done: measure and save (grade)
python workshop.py skill                  # stage 2: the prompt that asks the SAME agent to write a skill
python workshop.py harvest                # stage 2 is done: take the skill out and check it
python workshop.py new s3 --task all      # stage 3, four runs (T3 and T6, each with and without the skill): the default way
python workshop.py new s3 --task both     # stage 3, two runs (T6, then T3)
python workshop.py new s3 --task T6       # alternative: stage 3, run 1: T6 with YOUR name (it asks), a NEW agent thread
python workshop.py new s3 --task T3       # stage 3, run 2: T3 again, a SECOND new agent thread (same time)
python workshop.py done <run_id>          # end one stage-3 run (plain `done` asks which one)
python workshop.py unlock 4 <password>    # the grader - only after your agents are done
python workshop.py grade                  # scores the stages that are not graded yet
python workshop.py show                   # your table and the active runs
python workshop.py submit                 # LAST STEP: send all results to the form, one by one
python workshop.py form                   # open the form again for one stage (last stage; or: form <run_id> <stage>)
python workshop.py cleanup                # removes everything workshop.py made
python workshop.py doctor                 # the setup check alone (new s1 runs it for you)
```

Open each run folder that `new` prints as its own project in your agent (Codex, Claude Code or Cursor),
in a new thread, and paste the prompt. Stage 2 uses the same thread as stage 1.
Codex: if Memories are on, type /memories first in each new workshop thread and turn memory off for that chat.

**Stage 3 runs four agents at the same time.** `new s3 --task all` (the default way; `--name` works with it)
makes four runs in one command: (1) T3 WITH your skill, (2) T3 WITHOUT the skill (the control: same model, same
task, no skill in the folder, and a prompt without the skill sentences; stop it at 10 min),
(3) T6 WITH your skill (a new task: the real test), and (4) T6 WITHOUT the skill (control, same name on the
nameplate; stop it at 10 min). Runs 2 and 4 show what the skill really adds; `show` compares each pair and
prints a leakage check (skill gain on T3 against T6). `--task both` (T6 and T3 with the skill) still works. You can start the runs one by one instead:
`new s3 --task T6` asks for your name (up to 8 letters A-Z) and
writes it into `tasks/T6.md`; T6 is a new task that your skill has never seen. `new s3 --task T3` repeats the
stage-1 game. Open each folder in its own new thread and choose the small model there (Claude Code: Haiku;
Codex: gpt-6-luna; Cursor: its cheapest model). The prompt gives a budget of 6 emulator runs; the time box is
10 minutes (the tool records the time; it does not stop the agent). End each run with the `done <run_id>`
command that `new` printed.

**When `doctor` finds a fault** it writes `doctor-report.txt` into this folder and prints a short prompt.
Paste that prompt into any LLM (an agent opened in this folder can read the file; in a chat, attach the file).

**What workshop.py does:** copies the kit into run folders under `%LOCALAPPDATA%\vesper-runs`
(Windows) or `~/vesper-runs`, runs `git init` there, runs the emulator and the grader, reads your agent's
local session logs to count tokens (it finds them by the `Workshop run:` line in the prompt). At the end,
`submit` opens the results form in your browser.
**What it does not do:** it never starts or talks to an agent (you paste every prompt; the optional
`shadow` command is the only exception), it sends nothing over the network, and it changes nothing
outside its own folder unless you confirm.

- The prompts are plain files in `prompts/`; read them before you paste them.
- Cost is an estimate at API list prices (table at the top of `measure.py`); subscription users do not pay
  per token. For Cursor, type the numbers from Cursor's usage screen when `done` asks.
- **Results form:** https://forms.cloud.microsoft/r/xdtPcwF24a (Mobileye sign-in). `done`, `harvest` and
  `grade` only save the numbers. At the end run `python workshop.py submit`: for each result it opens the form
  with your values filled in, prints the values with their question numbers, and waits for you to click Submit
  and press Enter. If the browser does not open, open the link and type the values.
- If `doctor` shows RED, follow [MANUAL.md](MANUAL.md). More exercises: [HOMEWORK.md](HOMEWORK.md).

## Rules for the exercise

- Leave `bin/`, `examples/` and `tasks/` unchanged.
- Stage 1 allows 20 emulator runs and stage 3 allows 6 (the prompts say so). `vesper asm` is free.
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
tasks/T6.md         stage-3 task template (your name is filled in by workshop.py)
player.html         offline viewer for --out folders and --gif files
media/              the demo GIFs and design concept images above
solutions/          save your game here
locked/             later workshop parts (password-protected)
unlock.py           opens a locked part into unlocked/part-<n>/
workshop.py         runs and measures the workshop stages (uses measure.py)
t6font.py           the T6 name font (python t6font.py <name> prints your nameplate)
charts.py           presenter: debrief charts from the results form export
prompts/            the prompts you paste into your agent
guides/             skill-writing guides used in stage 2 (with their licenses)
MANUAL.md           the same exercise by hand
HOMEWORK.md         more exercises
```
