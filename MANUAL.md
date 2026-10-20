# The workshop by hand (when `workshop.py doctor` shows RED)

Do the same three stages without the tool. Use PowerShell on Windows, a shell on Linux.
Work in a local folder, not on OneDrive. Replace `<name>` with your name and `<n>` with any number.

## Stage 1 — the agent with no skill

1. Make the run folder (PowerShell):
   ```powershell
   $R = "$env:LOCALAPPDATA\vesper-manual\s1-<name><n>"
   mkdir $R\tasks, $R\solutions, $R\bin | Out-Null
   copy bin\vesper.exe $R\bin      # only the Windows binary: then bin/vesper works in every shell
   copy -Recurse examples $R
   copy player.html $R
   copy tasks\T3.md $R\tasks
   New-Item $R\.vesper-runs.log -ItemType File | Out-Null
   cd $R; git init -q; git add -A; git -c user.name=v -c user.email=v@local commit -qm start; cd -
   ```
   Linux: the same with `R=~/vesper-manual/s1-<name><n>`, `mkdir -p`, `cp -r`, `touch`, and only `bin/vesper`.
2. Write down the start time.
3. Open the run folder as a new project in your agent. Start a new thread.
4. Paste the text of `prompts/stage1.md`. Replace `{run_id}` with `s1-<name><n>` and `{task}` with `T3`.
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

Make two run folders: T6 (your name) and T3 again.

1. Make the first run folder as in stage 1, step 1, but with `$R3 = "$env:LOCALAPPDATA\vesper-manual\s3-<name><n>-t6"`
   and `$R3` instead of `$R` in all commands of that step. Do **not** copy `tasks\T3.md`. Instead write your T6 task:
   ```powershell
   python t6font.py <your name> --task-md $R3\tasks\T6.md
   ```
   (git add and commit after this command.)
2. Make the second run folder the same way with `$R4 = "$env:LOCALAPPDATA\vesper-manual\s3-<name><n>-t3"`, and copy
   `tasks\T3.md` as in stage 1.
3. Copy the skill into both folders:
   ```powershell
   foreach ($d in $R3, $R4) {
     mkdir $d\.agents\skills, $d\.claude\skills | Out-Null
     copy -Recurse $R\skill-out\vesper16 $d\.agents\skills\vesper16
     copy -Recurse $R\skill-out\vesper16 $d\.claude\skills\vesper16
   }
   ```
4. Open each folder as a new project, each in a new thread, with the small model (Claude Code: Haiku; Codex:
   gpt-6-luna; Cursor: its cheapest). Paste `prompts/stage3.md` into each (replace `{run_id}` and `{task}`: T6 and T3).
5. Measure each run as in stage 1. Time box: 10 minutes. Budget: 6 emulator runs.

## Grade

Only after your agent is done:
```powershell
python unlock.py 4 <password>
python unlocked\part-4\grader\grade.py T3 $R\solutions\T3.vsa --bin bin\vesper.exe
python unlocked\part-4\grader\grade.py T6 $R3\solutions\T6.vsa --name <your name> --bin bin\vesper.exe
```
Linux: `bin/vesper` instead of `bin\vesper.exe`. Delete the `unlocked` folder before you open the kit
folder in an agent again.

## Results and cleanup

- Type your numbers into the results form: https://forms.cloud.microsoft/r/xdtPcwF24a
  (alias, run_id such as `s1-<name><n>`, stage 1/2/3, revision 1, task T3 or T6, agent, model, method,
  skill_has_solution (the part of your stage-1 game in the skill, for example 27%; write 0% if none), elapsed_min, emulator_runs, the token numbers, cost_usd if you know it, score,
  grading = graded, measurement = manual).
- When you finish, delete `%LOCALAPPDATA%\vesper-manual` (Linux: `~/vesper-manual`) and the `unlocked` folder.
