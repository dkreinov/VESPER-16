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

## Check your skill with an independent judge

After `harvest`, `workshop.py` shows how many lines your skill shares with your T3 solution. A line match is free,
but it cannot tell a useful helper from the answer written in other words. A judge can.

Use a fresh thread as the judge, not the thread that wrote the skill. The writer would judge its own work, and it
remembers its T3 solution.

```sh
python workshop.py judge
```

It builds a read-only folder (your skill, your T3 solution, the task, the kit examples) and copies a prompt to the
clipboard. Open a NEW thread (any model; memory off) in that folder, paste the prompt, and read the answer
(about 2 minutes; nothing is graded or sent). The verdict is KNOWLEDGE, ANSWER or MIXED.

- KNOWLEDGE: the skill should help on tasks other than T3. Go on.
- ANSWER or MIXED: go back to the thread that wrote the skill. Ask it to rewrite the skill as knowledge (how the
  console works, what fails, how to test), without the game logic of T3. Then test the new skill on T6.

## Share your skill (open standard)

Agent Skills is an open standard (Agentic AI Foundation, since October 2026). Before you share your skill:
1. Check the format: install the reference validator (agentskills.io) and run `skills-ref validate ./skill-out/vesper16`.
2. Put it in `.agents/skills/vesper16/` in a project (Codex, Gemini CLI) or `.claude/skills/vesper16/` (Claude Code),
   and try it in a second agent. Use only the standard frontmatter fields (`name`, `description`), so it works everywhere.
3. Ask a fresh read-only thread to review it as an outsider would: "List anything that runs commands, sends data
   out, or changes the agent's rules."

## Also

- Other models: run stage 1 and stage 3 with a smaller and a larger model; `done` reads the model and the cost.
- `shadow`: `python workshop.py shadow --model <small model> --agent codex|claude` runs a prompt without a window
  (it starts a networked agent and asks first).
- Play the game: `bin/vesper run solutions/T3.vsa --frames 600 --gif out/t3.gif`, then drop the GIF on `player.html`.
- Clean up: `python workshop.py cleanup` removes everything workshop.py made (it asks first and offers to keep
  `results.csv`).
