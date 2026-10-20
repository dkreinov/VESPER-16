# Continue at home

Five exercises, in this order. Each one uses `workshop.py` and starts with a fresh run folder.

## 1. A skill for your own hardware or firmware

This is the real transfer to your work. Pick a tool, board, SDK or firmware interface that a coding agent does
not know well. Do the three stages by hand (see MANUAL.md): let an agent struggle with a small real task, let the
same agent write the skill, then give the skill to a fresh agent with a NEW small task (your own "T6").
Measure time, runs and tokens in both. A skill is good when the new task gets faster, not only the old one.

## 2. The full creator loop, with subagents

In the workshop the skill creators skipped their test step. Run the whole loop: an agent without the skill
fails (RED), the skill is written, fresh subagents solve a task with it (GREEN), then you close the loopholes.
```sh
python workshop.py new s1 --method builtin       # or --method superpowers
```
This time allow the creator to start subagents and run its tests. As a 4th method, write a skill with Matt Pocock's
`writing-great-skills` guide. Compare the four skills on T6: size, what they contain, time and pass.

## 3. T4 Breakout: a superset of T3

T4 contains T3 (paddle, ball, buttons) plus bricks.
```sh
python workshop.py new s3 --task T4 --skill own
```
Compare with no skill (`new s1 --task T4`). Does your T3 skill still save time, or does it mislead the agent?

## 4. Learning from the wiki

Part 2 is a 199-page company wiki: mostly noise, old SDK pages, contradictions and one wrong "best practices"
page. Unlock it with `python workshop.py unlock 2 <password>` (it goes to the hidden `.wiki` folder in the
workshop home). Build a skill from the wiki, and compare it with your skill from experience on T6 and T4.
Ways to try: the wiki as a pointer at task time; one agent distills and tests a skill; a subagent pipeline that
splits, extracts, tests each claim on the emulator, and writes the skill.
Use a skill with `python workshop.py new s3 --task T6 --skill <folder with SKILL.md>`.
Our reference wiki skill is in part 3: `unlock 3 <password>`, then `new s3 --task T6 --skill wiki`.

## 5. A setup skill for your own tools

`workshop.py doctor` checks a computer and writes `doctor-report.txt` when something is wrong. Write that idea
as a skill for your own team's tools: what to check, how to report it, and what the agent must never change.

## Also

- Other models: run stage 1 and stage 3 with a smaller and a larger model; `done` reads the model and the cost.
- `shadow`: `python workshop.py shadow --model <small model> --agent codex|claude` runs a prompt without a window
  (it starts a networked agent and asks first).
- Play the game: `bin/vesper run solutions/T3.vsa --frames 600 --gif out/t3.gif`, then drop the GIF on `player.html`.
- Clean up: `python workshop.py cleanup` removes everything workshop.py made (it asks first and offers to keep
  `results.csv`).
