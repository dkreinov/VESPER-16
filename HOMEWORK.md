# Continue at home

Each exercise uses `workshop.py`. Each one starts with a fresh run folder.

## 1. A new game: does your skill transfer? (T4, Breakout)

T3 in the workshop is **same-task reuse**: the skill was written on T3 and used on T3.
T4 is a different game, and it contains T3 (paddle, ball, buttons) plus bricks.
```sh
python workshop.py new s3 --task T4 --skill own
```
Compare with no skill (`new s1 --task T4`) and with the wiki skill (below). Is your T3 skill faster on T4, or
slower because it is incomplete or misleading?

## 2. Learning from a wiki (the most important extra exercise)

Part 2 is a 199-page company wiki: mostly noise, old SDK pages, contradictions and one wrong
"best practices" page. Unlock it with `python workshop.py unlock 2 <password>` (it goes to the hidden
`.wiki` folder in the workshop home).

Try three ways and measure each one on T3 and T4:
1. **Wiki as a pointer:** give the agent the wiki folder at task time, no skill.
2. **One agent distills a skill:** read the wiki, test each claim on the emulator, write the skill.
3. **A subagent pipeline:** one agent splits the wiki, helper agents extract claims, other agents test
   each claim on the emulator, one agent writes the skill. Which model for which role?

Use the skill with `python workshop.py new s3 --skill <folder with SKILL.md>`.
Our reference wiki skill is in part 3: `unlock 3 <password>`, then `new s3 --skill wiki`.

## 3. Other models and their cost

Run stage 1 and stage 3 with a smaller and a larger model. `done` reads the model from the log and
calculates the API-equivalent cost. Does a small model with a skill beat a large model without one?

## 4. Skill-writing methods

`python workshop.py new s1 --method builtin | superpowers | plain` fixes the method for stage 2.
Compare the skills: size, what they contain, and how stage 3 goes with each.

## 5. A small model without a window (`shadow`)

`python workshop.py shadow --model <small model> --agent codex|claude` runs the same prompt with
`codex exec` or `claude -p`. It starts a networked agent and uses your quota; it asks first.

## 6. Play the game

`player.html` shows the frames of a run (`bin/vesper run solutions/T3.vsa --frames 600 --gif out/t3.gif`,
then drop the GIF on the page). A keyboard player is planned.

## 7. Clean up

`python workshop.py cleanup` removes everything workshop.py made. It asks first, and it offers to keep
`results.csv`.
