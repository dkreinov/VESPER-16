# The workshop by hand (when `workshop.py doctor` shows RED)

Do the same three stages without the tool. Use PowerShell on Windows, a shell on Linux.
Work in a local folder, not on OneDrive. Replace `<name>` with your name and `<n>` with any number.

## Stage 1 — the agent with no skill

1. Make the run folder (PowerShell):
   ```powershell
   $R = "$env:LOCALAPPDATA\vesper-manual\s1-<name><n>"
   mkdir $R\tasks, $R\solutions | Out-Null
   copy -Recurse bin, examples $R
   copy player.html $R
   copy tasks\T3.md $R\tasks
   New-Item $R\.vesper-runs.log -ItemType File | Out-Null
   cd $R; git init -q; git add -A; git -c user.name=v -c user.email=v@local commit -qm start; cd -
   ```
   Linux: the same with `R=~/vesper-manual/s1-<name><n>`, `mkdir -p`, `cp -r`, `touch`.
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
4. Look in `$R\skill-out\vesper16`. If you see a `.vsa` file or long blocks of assembly, the agent put the
   finished game in the skill. Write this down ("yes"). Move those files out if you want a clean stage 3.

## Stage 3 — a new agent with the skill

1. Make a second run folder as in stage 1, step 1, but with `$R3 = "$env:LOCALAPPDATAesper-manual\s3-<name><n>"`
   and `$R3` instead of `$R` in all commands of that step.
2. Copy the skill into it:
   ```powershell
   mkdir $R3\.agents\skills, $R3\.claude\skills | Out-Null
   copy -Recurse $R\skill-out\vesper16 $R3\.agents\skills\vesper16
   copy -Recurse $R\skill-out\vesper16 $R3\.claude\skills\vesper16
   ```
3. Open `s3-…` as a new project, in a new thread. Paste `prompts/stage3.md` (replace `{run_id}`, `{task}`).
4. Measure as in stage 1.

## Grade

Only after your agent is done:
```powershell
python unlock.py 4 <password>
python unlocked\part-4\grader\grade.py T3 $R\solutions\T3.vsa --bin bin\vesper.exe
```
Linux: `bin/vesper` instead of `bin\vesper.exe`. Delete the `unlocked` folder before you open the kit
folder in an agent again.

## Results and cleanup

- Type your numbers into the results form (the presenter shows the link).
- When you finish, delete `%LOCALAPPDATA%\vesper-manual` (Linux: `~/vesper-manual`) and the `unlocked` folder.
