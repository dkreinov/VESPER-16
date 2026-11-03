# VESPER-16 workshop: the full manual

This manual starts from zero. It covers Windows first. A short Mac line follows where the steps differ.
Each sentence holds one fact. Do the numbered steps in order.

## 1. Words you need

- **Agent**: the AI coding tool you use (Codex, Cursor, Claude Code or Copilot).
- **Run folder**: a clean folder that the kit makes for one run. The agent works only there.
- **Run id**: the short name of a run, for example `s1-ab12`. It is in the first message of the chat.
- **Memory**: a feature that lets the agent remember old chats. Memory must be OFF for a clean run.

## 2. Get the tools (once)

1. Install Git. Windows: https://git-scm.com/download/win. Mac: https://git-scm.com/download/mac.
2. Install Python 3.9 or newer. Windows: https://www.python.org/downloads/ (tick "Add python.exe to PATH"). Mac: the same site.
3. Open a terminal. Windows: PowerShell. Mac: Terminal.
4. Check both tools:
   ```
   git --version
   python --version
   ```
   Mac: if `python` is not found, use `python3` in every command of this manual.
5. Choose a local folder. Do not use OneDrive.
6. Get the kit:
   ```
   git clone https://github.com/dkreinov/VESPER-16
   cd VESPER-16
   ```
   Do not use "Download ZIP" on GitHub. A ZIP has no `.git` folder, so `git pull` does not work.
7. Before class, update the kit:
   ```
   git pull
   ```
8. The grader needs numpy. Run `pip install numpy`.

Note: the emulator is `bin\vesper.exe` on Windows and `bin/vesper` on Linux. A Mac has no native emulator. Ask the instructor.

## 3. Install and sign in to your agent

Install your agent from its vendor site. Sign in. Use a paid plan, so you can pick the model.

| Agent | What to open | Sign in |
|---|---|---|
| Codex | the Codex app (or the Codex CLI) | sign in in the app or with `codex` |
| Cursor | the Cursor app | sign in in the app |
| Claude Code | `claude` in a terminal | sign in at the first start |
| Copilot | VS Code with the Copilot Chat extension | sign in to GitHub |

Copilot has partial support. Semi mode opens VS Code with the chat ready, and you send the prompt yourself. `--auto`, the Copilot CLI and the Copilot app are not supported. It is less tested than the other agents.

## 4. Check the computer

1. Run:
   ```
   python workshop.py doctor --agent codex
   ```
   Replace `codex` with `claude`, `cursor` or `copilot`.
2. Read the result. GREEN means ready. YELLOW means read the line and continue. RED means stop.
3. If it shows RED, read the first RED line. Then follow `MANUAL.md` or ask the instructor.
4. `doctor` also tells you if it found the app of your agent. If it did not, the kit uses manual mode.

## 5. The three modes

You choose the mode. The kit never switches by itself.

| Mode | Command part | What happens |
|---|---|---|
| auto | `--auto` (or `--mode auto`), stage 3 only | The kit runs the agent for you. You do nothing. |
| semi | `--mode semi` | The kit makes ONE run folder per page, opens your app on it, and shows the prompt. |
| manual | `--mode manual` | The kit makes the folder and prints the path and the prompt. You open the app yourself. |

- With no flag, the kit uses semi if it finds your app. Otherwise it uses manual.
- If the app does not open, run the same command again with `--mode manual`.
- Example: `python workshop.py new s1 --mode manual`.

## 6. Memory off, for each agent

Memory must be OFF in every workshop chat.

| Agent | What you do |
|---|---|
| Codex | In the chat, type `/memories`. Turn memory off BEFORE you send the prompt. `done` checks it later. |
| Claude Code | In semi mode the kit turns it off, and sends the message when the window opens. By hand, you do nothing. |
| Cursor | Nothing to switch. A new folder and a new chat start clean. Cursor keeps chat transcripts on disk, and an agent can read them. Use a new chat for each run. |
| Copilot | In VS Code, make a profile named `vesper-clean`. In that profile turn OFF the setting `chat.copilot.memory.enabled`. |

## 7. Stage 1: the agent writes the game (large model)

1. Run:
   ```
   python workshop.py new s1
   ```
   Add `--mode manual` if you want to open the app yourself.
2. The page shows the run folder, the prompt and the model to use.
3. Semi mode: the app opens on the run folder. Manual mode: open the printed folder in your agent as a new project.
4. Pick the large model. Never leave it on Auto.
   - Codex: gpt-6.1-sol. Codex keeps your last model, so check it.
   - Claude Code: your default model (Sonnet or Opus, not Haiku).
   - Cursor: a large model from the menu.
   - Copilot: a large model from the model picker.
5. Turn memory off and send the prompt. The steps depend on the agent:
   - Codex app: the short message is in the box. Type `/memories`, turn memory off, then send.
   - Codex CLI: a terminal opens. Type `/memories` and turn memory off. Then paste the message (it is on the clipboard) and send it.
   - Claude Code: the kit turns memory off and sends the message when the window opens. You do nothing.
   - Cursor: nothing to turn off. Paste the message (it is on the clipboard) in a new chat and send it.
   - Copilot: use the `vesper-clean` profile with `chat.copilot.memory.enabled` OFF. The kit opens that profile. The message is in the chat box. Send it.
6. The full prompt is on the page. It is the same text as `PROMPT.txt` in the run folder.
   The short message tells the agent to read `PROMPT.txt`.
8. When the agent is done, run:
   ```
   python workshop.py done
   ```
9. Cursor and Codex app: `done` reads the chat for the model, the time and (Codex) the memory state.
   `memory: OFF (verified)` is good. A memory warning means the run is not clean.
   "Chat not found" is a hint, not an error.

## 8. Stage 2: the same agent writes a skill

1. Run:
   ```
   python workshop.py skill
   ```
2. The prompt goes to the clipboard in semi mode. No new window opens.
3. Go back to the SAME chat of stage 1. Paste the prompt. Send it.
   Cursor and Copilot: type `/create-skill` first, then paste the prompt.
4. When the agent is done, run:
   ```
   python workshop.py harvest
   ```
5. `harvest` takes the skill out and checks it. If it reports a global skill, run `python workshop.py harvest --move-aside` or `--remove-global`.

## 9. Stage 3: four runs at the same time (small model)

1. Run:
   ```
   python workshop.py new s3 --task all
   ```
2. The kit shows four pages, one after the other, in this order:

   | Page | Run | Folder name starts with |
   |---|---|---|
   | 1 | T3 with your skill | `T3_WITH_SKILL_` |
   | 2 | T3 without the skill (control) | `T3_NO_SKILL_` |
   | 3 | T6 with your skill | `T6_WITH_SKILL_` |
   | 4 | T6 without the skill (control) | `T6_NO_SKILL_` |

3. For each page, do this:
   1. Read the run name and the prompt.
   2. Open the folder in a NEW window and a NEW chat (semi mode does this for you).
   3. Pick the small model. Never use Auto.
      - Claude Code: Haiku 5.5 (`/model claude-haiku-5-5`).
      - Codex: gpt-6-luna, effort high.
      - Cursor: GPT-5.6 Luna High.
      - Copilot: Claude Haiku 5.5 or GPT-6 Luna.
   4. Turn memory off and send the prompt, as in section 7 step 5. Claude Code does both by itself.
   5. Press Enter in the terminal. The next page appears at once.
4. Do not wait for a run to end. After page 4, the kit prints the stop time of each run (start plus 10 minutes).
5. Stop every agent at its stop time.
6. Press Enter once in the terminal. The kit then runs `done` for all four runs.
   If you ran by hand, run `python workshop.py done <run_id>` for each run.
7. The agent has a budget of 6 emulator runs and 10 minutes.

## 10. Grade, show, submit, clean up

1. Unlock the grader only after all agents are done:
   ```
   python workshop.py unlock 4 <password from the slide>
   ```
2. Score the runs:
   ```
   python workshop.py grade
   ```
3. See your table:
   ```
   python workshop.py show
   ```
   Add `--compare` to see the with and without tables while agents work.
4. Send all results in one form window:
   ```
   python workshop.py submit
   ```
   Click the `all_results` field. Press Ctrl+V (Cmd+V on a Mac). Click Submit.
5. Delete the `unlocked` folder before you open the kit folder in an agent again.
6. At the end, remove everything the kit made:
   ```
   python workshop.py cleanup
   ```
   Close the agent windows first.

## 11. If you are stuck

| Problem | Do this |
|---|---|
| The app did not open | Run the command again with `--mode manual`. Open the printed folder by hand. |
| `doctor` shows RED | Read the first RED line. Follow `MANUAL.md`. |
| `done` says chat not found | Check that the first message holds the run id. Then run `python workshop.py done <run_id>` again. |
| Memory warning at `done` | The run is not clean. Start the stage again with memory off. |
| Global skill blocked | Run `python workshop.py harvest --move-aside`. |
| The model shows Auto | Pick a named model. An Auto row never counts as a matched pair. |
| The agent did not finish | Run `python workshop.py done <run_id> --partial`. |
| Nothing works | Do the exercise by hand: follow `MANUAL.md`. Or load the `vesper-helper` skill from `helper-skill/vesper-helper` into your agent. |

Fallback commands:
```
python workshop.py new s1 --mode manual
python workshop.py new s3 --task all --mode manual
python workshop.py doctor --agent <name>
```

Note: the `--mode` flag is new. Run `python workshop.py new -h` to confirm that your copy has it. Run `git pull` if it does not.
