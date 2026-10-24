# The workshop by hand (when `workshop.py doctor` shows RED)

Do the same three stages without the tool. Use PowerShell on Windows, a shell on Linux.
Work in a local folder, not on OneDrive. Choose any 4 hex digits (0-9a-f) for <s1code>.

## Stage 1 — the agent with no skill

1. Make the run folder (PowerShell):
   ```powershell
   $R = "$env:LOCALAPPDATA\vesper-manual\s1-<s1code>"
   mkdir $R\tasks, $R\solutions, $R\bin | Out-Null
   copy bin\vesper.exe $R\bin      # only the Windows binary: then bin/vesper works in every shell
   copy -Recurse examples $R
   copy player.html $R
   copy tasks\T3.md $R\tasks
   New-Item $R\.vesper-runs.log -ItemType File | Out-Null
   cd $R; git init -q; git add -A; git -c user.name=v -c user.email=v@local commit -qm start; cd -
   ```
   Linux: the same with `R=~/vesper-manual/s1-<s1code>`, `mkdir -p`, `cp -r`, `touch`, and only `bin/vesper`.
2. Write down the start time.
3. Open the run folder as a new project in your agent. Start a new thread.
4. Paste the text of `prompts/stage1.md`. Replace `{run_id}` with `s1-<s1code>` and `{task}` with `T3`.
5. When the agent is done, write down the end time.
6. Read the tokens:
   - Codex: type `/status`.
   - Claude Code: type `/cost`.
   - Cursor: open the usage page in the dashboard.
7. Count the emulator runs:
   ```powershell
   (Select-String " run " $R\.vesper-runs.log).Count
   ```
   Linux: `grep -c " run " $R/.vesper-runs.log`.

## Stage 2 — the same agent writes a skill

1. Write down the start time.
2. In the same thread, paste `prompts/stage2-plain.md` (or `stage2-builtin.md` / `stage2-superpowers.md`).
   Replace `{run_id}`. Replace `{guide}` with the full path of the `guides` folder of this kit.
3. When the agent is done, write down the end time and the tokens (as in stage 1).
4. Look in `$R\skill-out\vesper16`. If you see a `.vsa` file or long blocks of assembly, estimate how much
   of your stage-1 game is in the skill and write it down (for example 30%). Keep the files: this is only recorded.

## Stage 3 — two new agents with the skill, at the same time

With the tool, `python workshop.py new s3 --task all` is the default way. It makes four runs: T3 with the skill, T3 WITHOUT the skill (the control: no skill folders, and a prompt without the skill sentences; run id tag `n3`), T6 with the skill, and T6 WITHOUT the skill (control, same name in the task file; tag `n6`). Separate commands (`--task both`, `--task T6`, `--task T3`) also work. By hand: make two run folders: T6 (your name) and T3 again. Use the same <s1code> as in your stage-1 run_id (`s1-<s1code>`), and choose new 4 hex digits for <code>.

1. Make the first run folder as in stage 1, step 1, but with `$R3 = "$env:LOCALAPPDATA\vesper-manual\s3-<s1code>-t6-<code>"`
   and `$R3` instead of `$R` in all commands of that step. Do **not** copy `tasks\T3.md`. Instead write your T6 task:
   ```powershell
   python t6font.py <your name> --task-md $R3\tasks\T6.md
   ```
   (git add and commit after this command.)
2. Make the second run folder the same way with `$R4 = "$env:LOCALAPPDATA\vesper-manual\s3-<s1code>-t3-<code>"`, and copy
   `tasks\T3.md` as in stage 1.
3. Copy the skill into both folders:
   ```powershell
   foreach ($d in $R3, $R4) {
     mkdir $d\.agents\skills, $d\.claude\skills | Out-Null
     copy -Recurse $R\skill-out\vesper16 $d\.agents\skills\vesper16
     copy -Recurse $R\skill-out\vesper16 $d\.claude\skills\vesper16
   }
   ```
4. Codex: if Memories are on, type /memories first in each new workshop thread and turn memory off for that chat.
   Open each folder as a new project, each in a new thread, with the small model (Claude Code: Haiku; Codex:
   gpt-6-luna; Cursor: its cheapest). Paste `prompts/stage3.md` into each (replace `{run_id}` and `{task}`: T6 and T3).
5. Measure each run as in stage 1. Time box: 10 minutes. Budget: 6 emulator runs.
6. Read the results with care. Each condition has one attempt, so reliability is unknown. Check PASS or FAIL before time or cost. The gain line (T3 and T6) shows observed score gains only; it neither identifies nor rules out answer reuse. The pay-back line shows only what the skill cost to write; break-even is not established. Costs are estimates under the kit's price assumptions. The comparison is matched only when both runs have the same model and the same effort.

### Stage 3 with `--auto` (optional)

`python workshop.py new s3 --task all --auto` starts the four stage-3 agents for you (headless Codex, Claude Code or Cursor
CLI), stops each one at 10 minutes, and measures them. Run `python workshop.py doctor` first: it says whether `--auto` is
ready for your agent. For Cursor: install with `irm 'https://cursor.com/install?win32=true' | iex` (PowerShell), log in with
`agent login` in a NEW PowerShell window, and use a paid plan (a free plan runs only Auto, so the model would not match).
The tool asks `Start the 4 agents? [y/N]` first (`--yes` starts without the question). A run that fails at once
(no login, free plan) prints `RUN FAILED`: do that run by hand with `python workshop.py new s3 --task all`. If you do
not use `--auto`, follow the steps below by hand. See the README for details.

## Grade

Only after your agent is done:
```powershell
python unlock.py 4 <password>
python unlocked\part-4\grader\grade.py T3 $R\solutions\T3.vsa --bin "$PWD\bin\vesper.exe"
python unlocked\part-4\grader\grade.py T6 $R3\solutions\T6.vsa --name <your name> --bin "$PWD\bin\vesper.exe"
python unlocked\part-4\grader\grade.py T3 $R4\solutions\T3.vsa --bin "$PWD\bin\vesper.exe"
```
Linux: `--bin "$PWD/bin/vesper"` instead of `--bin "$PWD\bin\vesper.exe"`. Delete the `unlocked` folder before you open the kit
folder in an agent again.

## Results and cleanup

- With the tool, the last step is `python workshop.py submit`: it grades first if needed, then opens ONE form window (alias filled in) and copies every result that is not yet submitted to the clipboard; paste it into all_results and click Submit.
- By hand, fill the results form: https://forms.cloud.microsoft/r/xdtPcwF24a
  The form has TWO fields. Field 1 `alias`: your alias. Field 2 `all_results` (long answer): the lines below, one line per run.
  The first line is exactly `vesper-results v1`. Then write one line per run (stage 1, 2, 3), with no spaces around `;` and `=`:
  ```
  vesper-results v1
  run_id=...;stage=...;revision=1;task=...;agent=...;model=...;method=...;skill_has_solution=...;elapsed_min=...;emulator_runs=...;tok_uncached=...;tok_cache_read=...;tok_out=...;cost_usd=...;score=...;grading=graded;measurement=manual
  ```
  Example values: run_id `s1-<s1code>` or `s3-<s1code>-t6-<code>`, stage 1/2/3, task T3 or T6,
  skill_has_solution (the part of your stage-1 game in the skill, for example 27%; write 0% if none), grading = graded, measurement = manual.
  You can leave a key empty (`cost_usd=`). Rows with another run-id format are not shown in the class charts.
- When you finish, delete `%LOCALAPPDATA%\vesper-manual` (Linux: `~/vesper-manual`) and the `unlocked` folder.
