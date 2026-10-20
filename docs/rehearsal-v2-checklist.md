# VESPER-16 workshop v2: rehearsal checklist (organiser, by hand)

Who: the organiser only. This file is not for learners.
Where: Windows PowerShell in `C:\Users\dkreinov\claude\workshop\vesper-16`, unless a step says otherwise.
Passwords: this file has no password. Use "the part-4 password (in the private repo notes)". Type it at a prompt. Never put it in a command line, a file or a log.
Log: write one row for each step that fails or surprises you in `agents-skills-workshop/experiments/04-blackbox-console/PRESENTER.md`, section `## v2 rehearsal log`. Columns: date, where, agent, step, result, note.

Expected results after grading (controller ruling F3): stage 1 graded, stage 2 grading none, stage 3 (T6 and T3) graded.

## A. Preparation (Windows)

1. Run `git status; git log --oneline -12`. You see a clean tree on `workshop-tool` and the commits of Tasks 1-10.
2. Run `python -m unittest discover -s tests`. You see `OK (skipped=2)`.
3. Run `$env:VESPER_PART4_PW = Read-Host "part-4 password"`. Type the part-4 password (in the private repo notes).
4. Run `python -m unittest discover -s tests -p test_part4.py -v`. You see 2 tests OK.
5. Run `Remove-Item Env:VESPER_PART4_PW`. The variable is gone.
6. Part-4 build check (required, private repo, organiser only). Run `$env:PART4_PW = Read-Host "part-4 password"`. Type the part-4 password.
7. Run `python C:\Users\dkreinov\claude\workshop\agents-skills-workshop\experiments\04-blackbox-console\harness\build_part4.py --kit C:\Users\dkreinov\claude\workshop\vesper-16 --check-only --show-diff`. You see that the font files match and the staged grader self-test gives `MIRA = 100`, a wrong name below 90, and T3 = 100. Read the diff.
8. Run `Remove-Item Env:PART4_PW`. The variable is gone.
9. Use a separate workshop home. Run `$env:VESPER_WS_HOME = "$env:LOCALAPPDATA\vesper-v2-test"`.
10. If that folder exists from an earlier try, make a backup first. The folder is not under git. Run:
    `if (Test-Path $env:VESPER_WS_HOME) { Copy-Item -Recurse $env:VESPER_WS_HOME "$env:VESPER_WS_HOME.bak-$(Get-Date -Format yyyyMMddHHmm)"; python workshop.py cleanup --yes --no-copy }`
    You see `Cleanup done.` or nothing (no folder).
11. Set `$env:VESPER_WS_HOME` again in each new PowerShell window you use for this rehearsal.

## B. Microsoft Forms, one manual step (before the first form check)

1. Open the results form in Microsoft Forms. Open question 5 (the task).
2. If question 5 is a Choice question, add the option `T6`. Type exactly `T6`, with no other text.
3. If question 5 is a Text question, do nothing.
4. Check this later at step C21 with `python workshop.py form <T6 run_id> 3`. Question 5 must show `T6`.

## C. Full flow with the Codex app (Windows)

1. Fault path. Run `Rename-Item bin\vesper.exe vesper.exe.off`.
2. Run `python workshop.py new s1`. You see `FAIL  the emulator does not run`, `RED`, a path to `doctor-report.txt` in the kit folder, a PROMPT block with `Read doctor-report.txt and help me fix the setup. Do not change files outside this folder.`, and an exit message.
3. Open `doctor-report.txt`. It lists the fault, OS, Python, agent CLI versions (codex, claude, cursor-agent, cursor), the paths, and the kit folder files.
4. Open the kit folder as a project in the Codex app. Open a new thread. Paste the help prompt.
5. You see that the agent finds `bin\vesper.exe` missing. It does not change files outside the kit folder. Do not let it change anything. Write down what it suggested.
6. Run `Rename-Item bin\vesper.exe.off vesper.exe; git status`. You see a clean tree (`doctor-report.txt` is ignored).
7. Run `python workshop.py new s1`. Doctor runs again and shows `GREEN` or `YELLOW`. On this computer you also see `WARN  superpowers is active for codex (config.toml enables superpowers@openai-curated) ... answer 'go on'.` `doctor-report.txt` is gone. You see the STAGE 1 banner, the method draw, and a prompt that ends with `Work on your own until the task is done. Do not stop to ask for approval or a design review.`
8. In the Codex app, open the printed folder as a new project. Open a new thread with the default model. Paste the prompt.
9. You see the agent work to the end without a request for approval. If it stops, answer `go on` and log it.
10. Run `python workshop.py done`. You see the stage-1 row (`measurement log`), a frame picture, the 18 numbered answers, and the form in the browser with values filled in. Submit with alias `rehearsal`.
11. Run `python workshop.py skill`. Paste the output into the SAME thread.
12. Run `python workshop.py harvest`. You see a NEXT box with two lines: `python workshop.py new s3 --task T6` and `python workshop.py new s3 --task T3`. Submit the stage-2 form. The stage-2 row shows grading `none` (ruling F3).
13. Run `python workshop.py new s3 --task T6`. At the name question type `Mira`. You see `Name on the T6 screen: MIRA`, the "Stage 3 rules" card with `-> Codex: gpt-6-luna`, `10 minutes`, `6 emulator runs`, a NEXT box `python workshop.py done s3-<code>-t6-<code>`, and the hint `python workshop.py new s3 --task T3`.
14. Run `Get-Content <T6 folder>\tasks\T6.md -TotalCount 20`. You see `**MIRA**` and five rows that start `#.#.###.##...#.`.
15. Run `python workshop.py new s3 --task T3`. You see a second folder and a NEXT box `python workshop.py done s3-<code>-t3-<code>`. The two run ids share the stage-1 code.
16. In the Codex app, make two new projects (one for each folder). In each, open one new thread and choose `gpt-6-luna`. Paste the matching prompt in each. The two runs go at the same time, each in its own agent thread. Write down the start time. The time box is 10 minutes. Nothing stops the agents.
17. While they run, run `python workshop.py show`. You see two `Active: stage 3 of ...` lines (T6 and T3).
18. Run `python workshop.py new s3 --task T3`. You see a refusal that names the active T3 run.
19. When the first agent is done, run `python workshop.py done <run_id>`. Use the run id of the finished run, from the NEXT box. (Without a run id, `done` shows `2 stage-3 runs are active:` and asks for a number. Type the number of the finished run.)
20. You see its row, its form (question 5 = `T6` or `T3`), and a NEXT box for the other run.
21. If the finished run is T6, run `python workshop.py form <T6 run_id> 3`. Question 5 must show `T6`. If it does not, fix the Forms option (section B) and log it.
22. When the second agent is done, run `python workshop.py done <other run_id>`. You see two "YOUR RESULT" tables. The T6 table says `Note: different task: compare with the measured baseline.` and `T6 baseline: small model, no skill: 0/12 pass in 5 min ...` with an empty change column.
23. Run `python workshop.py unlock 4 (Read-Host "part-4 password")`. Type the part-4 password (in the private repo notes). The history keeps only the `Read-Host` text.
24. Run `python workshop.py grade`. You see scores for stage 1, T6 and T3, and a form for each row. Stage 2 shows grading `none`; stages 1 and 3 show `graded`.
25. Check that T6 used the name. Run these three commands:
    `$g = "$env:VESPER_WS_HOME\.grader\grader\grade.py"; $s = "$env:VESPER_WS_HOME\.snapshots\<T6 run_id>-3.vsa"`
    `python $g T6 $s --name MIRA --bin bin\vesper.exe | python -c "import json,sys; print(json.load(sys.stdin)['score'])"`
    `python $g T6 $s --name VESPER --bin bin\vesper.exe | python -c "import json,sys; print(json.load(sys.stdin)['score'])"`
26. The first number equals the T6 score in `python workshop.py show`. The second number is lower when the agent drew the name.

## D. Charts trial

Trial 1: the test fixture (no Forms needed).

1. Run:
    `mkdir charts-out; python -c "import sys; sys.path.insert(0,'tests'); import test_charts as t; t.write_xlsx('charts-out/fixture.xlsx',[t.HEAD]+t.ROWS)"`
    The file `charts-out\fixture.xlsx` exists. (`charts-out/` is ignored by git.)
2. Run `python charts.py charts-out\fixture.xlsx --from 2026-10-27 --to 2026-10-27 --out charts-out\trial`. You see `Wrote charts-out/trial\charts.html (7 rows, 2 learners; dates 2026-10-27 to 2026-10-27)`.
3. Run `start charts-out\trial\charts.html`. The page opens. You see 5 charts, each with a data table.

Trial 2: the real export.

4. In Microsoft Forms open **Responses**, then **Open results in Excel** (or the "..." menu, then **Download a copy**). Save the .xlsx file.
5. Run `python charts.py "$HOME\Downloads\<export file>.xlsx" --from <today yyyy-mm-dd> --to <today yyyy-mm-dd> --out charts-out\rehearsal --png`. You see `Wrote charts-out\rehearsal\charts.html (... rows, 1 learners ...)`. With matplotlib you also see PNG files.
6. Run `start charts-out\rehearsal\charts.html`. You see 5 charts with your rows only.
7. If the number of rows is 0, run again with `--date-format "%d/%m/%Y %H:%M:%S"` and log it.
8. If a column is missing, run again with `--map "<question title>=<field>"` and log it.
9. Run `Remove-Item -Recurse charts-out`. The folder is gone.

## E. End of the Codex flow

1. Run `python workshop.py cleanup --yes`. You see `Saved vesper-results.csv` in the current folder, then `Cleanup done.`
2. Move `vesper-results.csv` out of the kit folder.

## F. Claude Code on Windows (same flow, only the differences)

1. Run `$env:VESPER_WS_HOME = "$env:LOCALAPPDATA\vesper-v2-test-claude"`.
2. Run `python workshop.py doctor --agent claude --alias rehearsal`. You see `WARN  superpowers is active for claude (settings.json enables superpowers@superpowers-dev) ...`.
3. Run `python workshop.py new s1`. Start `claude` in the run folder (terminal), or open the VS Code extension on it. Paste the prompt.
4. When the agent is done, run `python workshop.py done`. You see `measurement` = `log, output lower bound`.
5. Run `python workshop.py skill`. If the method is `builtin`, first run `/plugin install skill-creator@claude-plugins-official` as printed. Paste the prompt in the SAME session.
6. Run `python workshop.py harvest`. You see the NEXT box with the two stage-3 commands.
7. Run `python workshop.py new s3 --task T6 --name Mira`. Run `python workshop.py new s3 --task T3`.
8. Open one new Claude Code session for each folder. In each, type `/model haiku` first. The two runs go at the same time. Paste the matching prompts. You see the card arrow on `Claude Code: Haiku`.
9. Run `python workshop.py done <T6 run_id>`. Run `python workshop.py done <T3 run_id>`.
10. Run `python workshop.py unlock 4 (Read-Host "part-4 password")`, then `python workshop.py grade`. You see model `claude-haiku-*` in both stage-3 rows. Stage 2 shows grading `none`.
11. Run `python workshop.py cleanup --yes`.

## G. Cursor: detection, and a run if tokens allow

1. Run `$env:VESPER_WS_HOME = "$env:LOCALAPPDATA\vesper-v2-test-cursor"`.
2. Run `python workshop.py doctor --agent cursor --alias rehearsal`. You see no superpowers warning (this computer has no superpowers under `~/.cursor/plugins`).
3. Positive check. Run `mkdir $HOME\.cursor\plugins\local\superpowers`. Run the doctor command from step 2 again. You see a WARN line that names that folder.
4. Run `Remove-Item $HOME\.cursor\plugins\local\superpowers`. This is the empty folder you made in step 3.
5. Optional run: `python workshop.py new s1`, work in Cursor with its cheapest model, then `python workshop.py done`. You see a question for input tokens, output tokens and model (Cursor has no logs). Type the numbers from the Cursor usage screen. You see `measurement manual`.
6. For a Cursor stage 3, use the cheapest Cursor model, and repeat the two-run steps of section C.
7. Run `python workshop.py cleanup --yes`.

## H. Scripted sandboxed run on epgg112 (Linux)

The controller starts this run. Do not start it by hand while the controller runs it. The script spends real tokens.

1. Copy the committed kit. In Git Bash on Windows run:
    `git -C C:/Users/dkreinov/claude/workshop/vesper-16 archive --format=tar workshop-tool | ssh dkreinov@epgg112.me-corp.lan 'rm -rf ~/v2kit && mkdir ~/v2kit && tar -x -C ~/v2kit && chmod +x ~/v2kit/bin/vesper'`
2. Run `ssh dkreinov@epgg112.me-corp.lan 'cd ~/v2kit && which bwrap && ls ~/.claude-eval-token && python3 -m unittest discover -s tests 2>&1 | tail -2'`. You see a bwrap path, the token file, and `OK (skipped=...)`.
3. Test the sandbox with no agent and no tokens. On epgg112 run `cd ~/v2kit && python3 tests/e2e_agent.py --sandbox --sandbox-check --out /tmp/e2e-v2-check`. You see `sandbox ok:`.
4. Start the run. The `--out` folder must be under `/tmp` (the script refuses any other place). On epgg112, in an interactive ssh session, run:
    `cd ~/v2kit && read -s -p "part-4 password: " VESPER_PART4_PW && export VESPER_PART4_PW && echo`
    Type the part-4 password (in the private repo notes). `read -s` keeps it out of the history and the log.
5. Run this command (the exact scripted-run command):
    `nohup python3 tests/e2e_agent.py --agent claude --model sonnet --s3-model haiku --v2 --name MIRA --sandbox --timeout 30 --out /tmp/e2e-v2-claude > /tmp/e2e-v2-claude.out 2>&1 &`
    The script reads `VESPER_PART4_PW` once and removes it from the environment of every child process. The Claude token comes from `~/.claude-eval-token`.
6. Run `unset VESPER_PART4_PW`. The variable is gone from the shell.
7. Wait with ONE blocking command (Windows, in the background; it wakes you once):
    `ssh dkreinov@epgg112.me-corp.lan 'while [ ! -e /tmp/e2e-v2-claude/DONE ]; do sleep 60; done; python3 -c "import json; s=json.load(open(\"/dev/stdin\")); print(s[\"ok\"], s.get(\"error\",\"\")); [print(r[\"run_id\"], r[\"stage\"], r[\"task\"], r[\"score\"], r[\"grading\"], r[\"elapsed_min\"]) for r in s.get(\"rows\", [])]" < /tmp/e2e-v2-claude/status.json'`
    You see `True`, then 4 rows: stage 1 T3, stage 2, stage 3 T6, stage 3 T3. Stages 1 and 3 show grading `graded`. Stage 2 shows grading `none` (ruling F3).
8. Check the log. On epgg112 run `grep -c "unlock 4 <password>" /tmp/e2e-v2-claude/e2e.log`. You see `1`.
9. Check that the password is not in the files. Type it again with `read -s -p "part-4 password: " CHK` and run `grep -c -F "$CHK" /tmp/e2e-v2-claude/e2e.log /tmp/e2e-v2-claude/status.json`. You see `0` for both files. Then run `unset CHK`.
10. Run `grep -n "\[agent stage3-" /tmp/e2e-v2-claude/e2e.log`. You see two lines. The start times overlap.
11. Check the sandbox. Run:
    `S1=$(ls -d /tmp/e2e-v2-claude/home/s1-*)`
    `for f in $(grep -l "Workshop run: s3-" /tmp/e2e-v2-claude/agent-home/.claude/projects/*/*.jsonl); do echo "$f $(grep -c "$S1" "$f")"; done`
    You see two or more files, each with `0` (the stage-3 agents did not see the stage-1 game).
12. Optional Codex variant. Repeat steps 4-11 with `--agent codex --model gpt-6.1-sol --s3-model gpt-6-luna --out /tmp/e2e-v2-codex`. The session logs are in `/tmp/e2e-v2-codex/agent-home/.codex/sessions`.

## I. Record the results

1. Write the results (pass or fail, minutes, scores) in `## v2 rehearsal log` in PRESENTER.md.
2. Run:
    `cd C:/Users/dkreinov/claude/workshop/agents-skills-workshop`
    `git add experiments/04-blackbox-console/PRESENTER.md`
    `git commit -m "PRESENTER: v2 rehearsal log (Windows Codex/Claude/Cursor, epgg112 sandboxed e2e)"`
