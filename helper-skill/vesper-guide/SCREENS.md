# THE SCREENS LIST

Each entry is one message that the kit can show. `Screen:` holds the text on the screen. `Means:` says what it means. `Do:` gives the steps. `Why:` gives the reason.
Match the learner's pasted text to ONE entry. Answer from the entry. Give one step at a time. The learner types every command.
Never add detail about the VESPER-16 console, the game code or the scoring. If no entry matches, say so, ask for the command and the last 15 lines, and tell the learner to send them to the instructor.

## doctor

### Doctor GREEN
Screen: "GREEN: all good."
Means: Every check passed.
Do: 1. Go on with `python workshop.py new s1`.

### Doctor YELLOW
Screen: "YELLOW: it works - read the warnings."
Means: The kit works, but one WARN line needs a look.
Do: 1. Read each WARN line. 2. Find the line in this list and do its steps. 3. Go on.

### Doctor RED
Screen: "RED: follow MANUAL.md or work with a neighbour."
Means: A FAIL line stops the workshop.
Do: 1. Read the first FAIL line only. 2. Find that line in this list. 3. Fix it and run `python workshop.py doctor --agent <name>` again.
Why: One fault often causes the other FAIL lines.

### Doctor report file
Screen: "The setup has a fault. A report for help is in:"
Means: The kit wrote the file doctor-report.txt in the kit folder.
Do: 1. Open a new chat in the kit folder. 2. Paste the prompt that the screen prints. 3. Or send the file to the instructor.

### Python too old
Screen: "Python 3.9 or newer is needed"
Means: The Python on this computer is too old.
Do: 1. Install Python 3.9 or newer from python.org. 2. Tick "Add to PATH". 3. Open a NEW terminal. 4. Run `python workshop.py doctor --agent <name>`. Mac: use `python3`.

### Git missing
Screen: "git is missing"
Means: Git is not installed, or the terminal cannot find it.
Do: 1. Install Git from git-scm.com. 2. Open a NEW terminal. 3. Run `git --version`. 4. Run `python workshop.py doctor --agent <name>`.

### Program in bin does not run
Screen: "the emulator does not run"
Means: The VESPER-16 program in the `bin` folder does not start.
Do: 1. Check that the kit came from `git clone`, not from a ZIP. 2. Check the antivirus. It may block the file. 3. Run `git pull`. 4. Send the line to the instructor if it stays.

### Workshop home on OneDrive
Screen: "the workshop home is on OneDrive"; "is on OneDrive. Set VESPER_WS_HOME"
Means: The kit would store run folders in OneDrive. OneDrive breaks them.
Do: 1. PowerShell: `$env:VESPER_WS_HOME = "C:\vesper-runs"`. Bash: `export VESPER_WS_HOME=$HOME/vesper-runs`. 2. Run the same command again.
Why: OneDrive locks and syncs files while the agent works.

### Kit on OneDrive
Screen: "the kit is on OneDrive; it works"
Means: The kit folder is in OneDrive. It works but it is slow.
Do: 1. Go on. 2. Next time use `git clone` in a local folder.

### Global VESPER skill
Screen: "a VESPER skill is in a global folder (stage 3 would not be clean)"; "A VESPER skill is in a global folder, so stage 3 would not be clean"
Means: A skill named vesper sits in a user skill folder. Every agent would load it.
Do: 1. Move the folder named on the screen out of the skill folder. 2. Or run `python workshop.py harvest --move-aside` after stage 2. 3. Run `python workshop.py doctor --agent <name>` again.
Why: Stage 3 must use only the skill in its run folder.

### Superpowers WARN
Screen: "superpowers is active for"
Means: A plugin called superpowers is on. The agent may stop to ask for approval.
Do: 1. Go on. 2. When the agent asks, reply: go on. 3. Or turn the plugin off in the agent settings. The learner decides.

### Codex Memories WARN
Screen: "Codex Memories hold VESPER notes from earlier sessions"
Means: Codex kept notes from earlier VESPER sessions.
Do: 1. In every new workshop thread, type `/memories`. 2. Turn memory off for that chat. 3. Then send the prompt.
Why: A clean attempt must not use old notes.

### App not found
Screen: "app not found: semi mode falls back to manual"
Means: The kit did not find the agent app. It will use manual mode.
Do: 1. Go on. 2. The page prints a folder. Open it yourself in the agent.

### Copilot partial support
Screen: "GitHub Copilot: PARTIAL SUPPORT (experimental)"; "Name it vesper-clean."
Means: Copilot works in a limited way. This is normal for Copilot.
Do: 1. In VS Code create the profile `vesper-clean`. 2. In that profile turn OFF `chat.copilot.memory.enabled`. 3. Use a NEW chat for each run.

### Auto mode not ready
Screen: "NOT ready - "; "--auto not ready: "
Means: `--auto` cannot start your agent now. The reason follows on the line.
Do: 1. Read the reason. 2. Use the normal flow without `--auto`: `python workshop.py new s3 --task all`.

### Agent program not found
Screen: "claude was not found"; "codex was not found"; "cursor-agent was not found"; "codex on PATH is too old"
Means: The command line program of the agent is missing or too old. Only `--auto` needs it.
Do: 1. Install or update the agent program. Claude Code: `npm install -g @anthropic-ai/claude-code`. 2. Or skip `--auto` and use the app.

### Agent install help
Screen: "Install Claude Code:  npm install -g @anthropic-ai/claude-code"; "Install the Codex app"; "Then open a NEW PowerShell window"
Means: These lines tell how to install the agent program.
Do: 1. Follow the line for your agent. 2. Open a NEW terminal. 3. Run `python workshop.py doctor --agent <name>`.

### Cursor not logged in
Screen: "Cursor is not logged in"; "Log in:  agent login"
Means: The Cursor program has no login.
Do: 1. Run `agent login`. 2. Finish the login in the browser. 3. Run `python workshop.py doctor --agent cursor`.

### Free plan
Screen: "free plan: only Auto"; "Named models need a paid plan."
Means: The account cannot pick a named model.
Do: 1. Use the manual flow, or change the plan in the agent app. The learner fixes the account.
Why: The workshop needs a fixed model, never Auto.

### Auto check failed
Screen: "FAIL: the agent wrote a file OUTSIDE its folder"; "FAIL: the agent did not run bin/vesper"; "FAIL: the agent could not write out/ok.txt"
Means: The test run of `--auto` did not pass.
Do: 1. Do not use `--auto`. 2. Use the normal flow: `python workshop.py new s3 --task all`.

### Auto limit not verified
Screen: "Not verified on this computer: run  doctor --check-auto"
Means: The kit did not test the limits of `--auto` here.
Do: 1. Run `python workshop.py doctor --agent <name> --check-auto`. 2. Or use the normal flow.

### Cursor rules WARN
Screen: "Cursor loads User Rules and alwaysApply rules"; "alwaysApply rules in"
Means: Cursor rules can change what the agent does in every run.
Do: 1. Turn the rules off in Cursor Settings > Rules for the workshop. The learner decides.

### Auto start refused
Screen: "is not ready for"; "Or run the manual flow without --auto."
Means: The command stopped. `--auto` does not work for your agent now.
Do: 1. Run the same command without `--auto`.

## new s1 and new s3

### Doctor runs first
Screen: "Checking this computer first (doctor)."
Means: This is the first command. The kit runs `doctor` once.
Do: 1. Read the result. 2. If it is RED, fix the first FAIL line.

### Fix the FAIL lines
Screen: "Fix the FAIL lines first"
Means: `new` stopped because `doctor` found a FAIL.
Do: 1. Scroll up to the first FAIL line. 2. Find it in this list. 3. Fix it. 4. Run the same `new` command again.

### Task for stage 3 only
Screen: "is for stage 3 only:  python workshop.py new s3 --task all"
Means: You used `--task all` or `--task both` with stage 1.
Do: 1. Stage 1: `python workshop.py new s1`. 2. Stage 3: `python workshop.py new s3 --task all`.

### Auto for stage 3 only
Screen: "--auto is for stage 3 only"
Means: `--auto` does not exist for stage 1.
Do: 1. Run `python workshop.py new s1`.

### T6 in stage 1
Screen: "T6 is a stage-3 task."
Means: Stage 1 uses T3 only.
Do: 1. Run `python workshop.py new s1`.

### Stage is still active
Screen: "is still active. Next:"
Means: An earlier stage is not finished. The line after Next: is the command.
Do: 1. Run the command on the line. Stage 1: `python workshop.py done`. 2. Or, to begin again: `python workshop.py new s1 --restart`.
Why: The kit keeps one clean run at a time.

### Start again from scratch (the offer)
Screen: "Start again from scratch:  python workshop.py new"
Means: The kit blocked your command because a run is still active. This line offers a way out: `--restart` ends the active run and makes a new one. Nothing has been restarted yet.
Do: 1. Stage 1: type `python workshop.py new s1 --restart`. 2. Stage 3: type `python workshop.py new s3 --task all --restart`. 3. Or finish the active run first with `python workshop.py done`.
Why: The old folder stays until `python workshop.py cleanup`.

### Started again from scratch (the confirmation)
Screen: "Started again from scratch. The old run folder stays on disk until you run cleanup."
Means: The restart already ran. The old run is closed and a new run page follows.
Do: 1. Read the new page that the kit prints below this line. 2. Follow it from the top: new chat, model, memory off, send the prompt.
Why: Never reuse the old chat.

### Repeat attempt question
Screen: "Stage 3 is done. Start a repeat attempt"; "needs a person to say yes. Add --yes to start it."
Means: Stage 3 of this skill is finished. The kit asks before it makes new runs.
Do: 1. Press Enter to say no. 2. Or type y for new runs. 3. See old results with `python workshop.py show`.

### Stage 3 already set up
Screen: "Stage 3 is already set up. Showing its pages again."
Means: Stage 3 runs exist. The kit shows their pages again. It makes no new run.
Do: 1. Use the same folders and chats. 2. Do not send a prompt twice.

### T6 name question
Screen: "Your name for the T6 nameplate (up to 8 letters A-Z; Enter = VESPER)"; "Your alias has no A-Z letters"
Means: The T6 task needs a short name in capital letters A to Z.
Do: 1. Type up to 8 letters, or press Enter. 2. Or give it in the command: `python workshop.py new s3 --task all --name <name>`.

### Run could not be created
Screen: "The T3 run could not be created"; "A run could not be created"; "Runs already created stay valid"
Means: A run folder failed. The reason follows on the line.
Do: 1. Read the reason. A full disk or an antivirus is common. 2. Run the same command again. Finished runs stay valid.

### Stage 3 paused with Ctrl+C
Screen: "Stopped. Run the same command again to see the pages."
Means: You pressed Ctrl+C. The runs stay.
Do: 1. Run the same `new s3` command again.

### Stage 1 paused with Ctrl+C
Screen: "stays active. Its prompt:"
Means: You pressed Ctrl+C. The stage 1 run stays active. The prompt is printed again.
Do: 1. Copy the prompt. 2. Finish with `python workshop.py done`.

### Page confirmation
Screen: "Done with these steps? [y/n] (n = show them again)"
Means: The kit waits for you to open the folder, start a new thread and pick the model.
Do: 1. Do the numbered steps above. 2. Type y.

### Press Enter for the next run
Screen: "Press Enter for the next run: "
Means: You sent the prompt of this run. The kit shows the next run.
Do: 1. Send the prompt. 2. Press Enter. Do not wait for the agent.
Why: The four agents work at the same time.

### Codex memory step on a page
Screen: "Type /memories first and turn off memory for this chat."; "turn memory off for this chat."
Means: Codex memory must be off before the prompt.
Do: 1. Type `/memories` in the new thread. 2. Turn memory OFF. 3. Then paste the prompt.

### Codex memories card
Screen: "Codex Memories are ON on this computer. Stage 3 must be a fresh agent"
Means: The kit sees Codex memory on. Each stage 3 thread needs the switch.
Do: 1. In EACH new thread type `/memories`. 2. Turn memory off. 3. Paste the prompt.

### Mode line SEMI
Screen: "Mode: SEMI. The kit opens"
Means: The kit opens the agent app for you.
Do: 1. Look at the app. 2. If it did not open, run the same command with `--mode manual`.

### Mode line MANUAL
Screen: "Mode: MANUAL. You open"; "The kit did not find the"
Means: You open the app yourself. The folder is on the page.
Do: 1. Open the printed folder as a NEW project. 2. Start a NEW thread. 3. Want the kit to open it? Add `--mode semi`.

### Mode box SEMI
Screen: "MODE: SEMI."; "Did not open or wrong folder?"
Means: The box at the end of a page says if the app opened.
Do: 1. Look at the app. Is it on the run folder? 2. If not: run the same command with `--mode manual`. Open the printed folder yourself.

### App did not open
Screen: "The app did not open on its own."; "did NOT open. Open it by hand (see above)."
Means: The kit could not start the app.
Do: 1. Read the lines above for the reason. 2. Open the printed folder in the app as a new project. 3. Or run the same command with `--mode manual`.

### App launcher problems
Screen: "launcher does not exist"; "The kit cannot open a terminal window on this system."; "The kit could not open the app ("; "The Codex app link needs Windows."; "Unknown agent:"
Means: The kit could not start the app. This is not your fault.
Do: 1. Run the same command with `--mode manual`. 2. Open the folder by hand.

### First, before you send
Screen: "FIRST, BEFORE YOU SEND THE PROMPT"
Means: Codex or Copilot needs a memory step first.
Do: 1. Do the memory step on the next line. 2. Only then send the prompt.
Why: An agent that remembers old chats is not a clean attempt.

### Codex box empty
Screen: "The box is empty on purpose."; "When memory is OFF in the new thread, press Enter to see the prompt."
Means: The kit waits until memory is off.
Do: 1. Type `/memories` in the thread. 2. Turn memory off. 3. Press Enter in the terminal. 4. Paste the message and send it.

### Message on the clipboard
Screen: "The message is on the clipboard. Paste it in the chat."; "The message is on the clipboard. Paste it in the thread (Ctrl+V) and send it."
Means: The short message with the run id is ready. It tells the agent to read PROMPT.txt.
Do: 1. Paste with Ctrl+V (Cmd+V on a Mac). 2. Send it.

### Clipboard failed
Screen: "The clipboard did not work. Type this message in the chat:"; "The clipboard did not work. Copy the text between the PROMPT lines by hand."
Means: The kit could not copy text.
Do: 1. Copy the text between the PROMPT lines yourself. 2. Or type the short message that the screen prints.

### Copilot message waits
Screen: "The message is in the chat box. Do not send it before you turn memory off."
Means: VS Code opened with the message ready.
Do: 1. Check the profile `vesper-clean`. 2. Check `chat.copilot.memory.enabled` is OFF. 3. Send the message.

### Claude Code opens
Screen: "Memory is off. The kit set it. The message is sent as the first prompt."
Means: A new terminal runs Claude Code. The kit already sent the message.
Do: 1. Look at the new window. 2. Do not type anything.

### Memory line
Screen: "Memory: Cursor has no memory switch. Nothing to turn off."; "Memory: Claude Code keeps memory per project. Nothing to turn off by hand."; "Memory: off. The kit turned it off for this window."
Means: This agent needs no memory step.
Do: 1. Cursor: use a NEW chat for each run. 2. Claude Code: do nothing.

### Send the prompt in the app
Screen: "Send the prompt in the app. Then press Enter here."
Means: The kit waits for you to send the prompt.
Do: 1. Send the prompt in the app. 2. Press Enter in the terminal. The next page opens at once.

### Check the model
Screen: "Check the model:"; "Check the model. Never use Auto."
Means: The model in the app must match the line.
Do: 1. Pick the named model. 2. Never pick Auto.
Why: Auto changes models between requests.

### Cursor model line
Screen: "Not Auto. Do not use Plan mode."
Means: Cursor needs a named model and no Plan mode.
Do: 1. Pick GPT-5.6 Luna High. 2. Leave Plan mode off.

### Start order
Screen: "Start in this order:"
Means: The kit gives the order to start the four runs.
Do: 1. Start the runs in that order. 2. Do not wait between runs.

### Benchmark line
Screen: "Together, these 4 runs are a small benchmark of your skill"
Means: The four runs show your skill with and without the skill.
Do: 1. Go on with the four pages.

### Method line
Screen: "Stage-2 method for you:"; "(the room is split 3 ways at random)"
Means: The kit picked how your agent writes the skill.
Do: 1. Go on. Do not change the method.

## skill

### Stage 1 first
Screen: "Do stage 1 first:  python workshop.py new s1"
Means: There is no finished stage 1.
Do: 1. Run `python workshop.py new s1`. 2. Finish it with `python workshop.py done`.

### Stage 2 already done
Screen: "is already done. Next:  python workshop.py new s3 --task all"
Means: The skill of this run is saved.
Do: 1. Run `python workshop.py new s3 --task all`.

### Stage 2 has no auto
Screen: "Stage 2 has no auto mode."
Means: `--auto` is for stage 3 only.
Do: 1. Run `python workshop.py skill`.

### Stage 2 prompt again
Screen: "Stage 2 is already running (the clock started at the first"
Means: You ran `skill` twice. The kit shows the same prompt again.
Do: 1. Paste it in the SAME chat as stage 1. 2. Then run `python workshop.py harvest`.

### Same chat for stage 2
Screen: "Go back to the SAME thread as stage 1"
Means: The agent must still hold what it learned in stage 1.
Do: 1. Open the stage 1 chat. 2. Paste the prompt there.

### Prompt on the clipboard
Screen: "The prompt is on the clipboard. Paste it (Ctrl+V) in the SAME chat as stage 1."
Means: The kit copied the stage 2 prompt.
Do: 1. Go to the stage 1 chat. 2. Paste and send. 3. Wait. 4. Run `python workshop.py harvest`.

## harvest

### No skill file
Screen: "No skill at"; "Ask the agent to write it there, then run harvest again."
Means: The agent has not written `skill-out\vesper16\SKILL.md` in the run folder.
Do: 1. Run `python workshop.py skill`. 2. Paste the prompt in the SAME chat as stage 1. 3. Wait until the agent says the skill is written. 4. Check that `skill-out\vesper16\SKILL.md` exists in the run folder. 5. Run `python workshop.py harvest` again.
Why: The kit reads the skill from this exact path.

### Skill in a global folder
Screen: "It may be in a global folder:"; "A skill was written here instead:"
Means: The agent wrote the skill in a wrong place.
Do: 1. Ask the agent to write it into the run folder path on the screen. 2. Run `python workshop.py harvest` again.

### Harvest in wrong order
Screen: "harvest ends stage 2. Start stage 2 with"
Means: Stage 2 did not start.
Do: 1. Run `python workshop.py skill`. 2. Paste in the same chat. 3. Run `python workshop.py harvest`.

### Already harvested
Screen: "is already harvested."
Means: The skill is saved. Stage 2 is over.
Do: 1. Run the Next command on the screen: `python workshop.py new s3 --task all`.

### Remove global copies
Screen: "CHECK - a VESPER skill is in a global folder"; "Remove these global copies? [y/N]"
Means: A VESPER skill sits outside the run folder. It would reach stage 3.
Do: 1. Type y. The learner decides. 2. Or run `python workshop.py harvest --remove-global`.

### Stage 2 done
Screen: "STAGE 2 DONE: skill saved"
Means: The kit saved your skill.
Do: 1. Read the NEXT box. 2. Choose one way to run stage 3.

### Copied lines note
Screen: "of your T3 solution's own lines are in your skill"; "No copied block of your T3 solution was found in your skill"
Means: A check compared your skill to your stage 1 file. The kit records it for the debrief.
Do: 1. Go on. 2. Ask the instructor in the debrief.

### Judge option
Screen: "Optional (2 min): python workshop.py judge"
Means: A second chat can read your skill and comment on it.
Do: 1. Skip it, or run `python workshop.py judge`. 2. Use a NEW chat for it.

### Judge errors
Screen: "No harvested skill yet. Do stage 2"; "has no harvested skill. Do stage 2 for it"; "No T3 solution snapshot for run"
Means: The judge needs a saved skill and a saved stage 1 file.
Do: 1. Run `python workshop.py skill`. 2. Paste in the same chat. 3. Run `python workshop.py harvest`.

### Judge page
Screen: "A fresh thread judges the skill."
Means: The kit made a folder for a NEW chat. Nothing is graded or sent.
Do: 1. Open the folder in a NEW thread. 2. Paste the prompt. 3. Read the answer.

### Wiki skill locked
Screen: "The wiki skill is in locked part 3"
Means: You asked for the instructor skill. It is locked.
Do: 1. Use your own skill. 2. Or unlock part 3 with the slide password: `python workshop.py unlock 3 <password from the slide>`.

### Skill folder has no SKILL.md
Screen: "No SKILL.md in"
Means: The folder in `--skill` has no SKILL.md.
Do: 1. Check the path. 2. Or leave out `--skill`.

## done

### Stage 2 ends with harvest
Screen: "Stage 2 ends with:  python workshop.py harvest"
Means: Stage 2 uses `harvest`, not `done`.
Do: 1. Run `python workshop.py harvest`.

### Unknown run id
Screen: "No active or finished stage 1 or 3 is called"
Means: The run id is wrong.
Do: 1. Run `python workshop.py show`. 2. Copy the exact run id. 3. Run `python workshop.py done <run id>`.

### No stage active
Screen: "No stage is active. Start with:  python workshop.py new s1"
Means: There is no run to end.
Do: 1. Run `python workshop.py new s1`.

### Done runs again
Screen: "Updating the finished stage"
Means: This run was done before. The kit reads it again.
Do: 1. Go on. This is safe.

### Several runs are active
Screen: "stage-3 runs are active:"; "Which agent is done? Type its number"
Means: The kit asks which run to end.
Do: 1. Type the number of the run. 2. Or name the run: `python workshop.py done <run id>`.

### Nothing finished
Screen: "Nothing finished. Name the run that is done:"
Means: You pressed Enter without a number.
Do: 1. Run one of the listed commands, for example `python workshop.py done <run id>`.

### Several sessions
Screen: "Several agent sessions contain"; "Which one is this run (usually the newest file)?"
Means: More than one agent log holds this run id.
Do: 1. Type the number of the newest file. 2. Or press Enter for 1.
Why: The kit reads time and model from that log.

### No agent log
Screen: "No agent log contains"; "Type the numbers from the agent's usage screen"
Means: The kit cannot find the agent log. Cursor and Copilot have no log.
Do: 1. Type the tokens and model from the agent usage screen. 2. Or press Enter to skip. The run still counts.

### Cursor chat not found
Screen: "Cursor chat not found."; "when the chat is saved."
Means: This is only a hint. The kit could not read time and model from Cursor.
Do: 1. Check that the first message of the chat holds the run id. 2. Wait for the chat to save. 3. Run `python workshop.py done <run id>` again.

### Cursor chat found
Screen: "Cursor chat found: model"; "Tokens and cost: not available in the Cursor app."
Means: The kit read the model and time. Cursor shows no tokens or cost.
Do: 1. Check that the model is not auto. 2. Go on.

### Copilot tokens
Screen: "input tokens are not available in Copilot Chat"
Means: Copilot gives no input tokens. There is no cost.
Do: 1. Go on.

### Stage 1 finished
Screen: "STAGE 1 FINISHED"
Means: The kit saved stage 1. A summary follows with time, runs, cost, memory and isolation.
Do: 1. Read the warnings below the summary. 2. Run the NEXT command: `python workshop.py skill`.

### Run finished line
Screen: "(stopped at the time box)"; "(partial)"
Means: The run ended at its stop time, or you used `--partial`.
Do: 1. Go on. The kit uses what the agent made.

### Memory ON
Screen: "WARNING: memory was ON."
Means: The summary shows Memory ON. The agent could read notes of earlier sessions.
Do: 1. Do the stage again with memory off. 2. Stage 1: `python workshop.py new s1 --restart`. 3. Stage 3: `python workshop.py new s3 --task all --restart`. 4. Codex: type `/memories` before you send the prompt.
Why: A run with memory on is not a clean attempt.

### Codex memory OFF
Screen: "memory: OFF (verified)"
Means: The kit checked the Codex thread. Memory was off.
Do: 1. Go on.

### Codex memory ON
Screen: "WARNING: Codex memory was ON for this run. This run is not clean."; "Do this run again with memory off"
Means: Codex memory was on when you sent the prompt.
Do: 1. Start this stage again. 2. Type `/memories` and turn memory off BEFORE you send the prompt.

### Isolation CHECK
Screen: "CHECK: the agent may have read outside the run folder."
Means: The summary shows Isolation CHECK. The log shows a read in another folder.
Do: 1. Read the note line under it. 2. Next time open exactly the run folder as the project. 3. Ask the instructor in the debrief.

### Wrong folder
Screen: "WRONG FOLDER"; "Its files are not where the tool looks."
Means: The agent worked in a folder other than the run folder.
Do: 1. In the agent, open exactly the run folder path on the screen as the project. Not a folder above it. 2. Ask the agent to redo the step there. 3. Run `python workshop.py done` or `python workshop.py harvest` again.

### Small model in stage 1
Screen: "CHECK: stage 1 ran on a small model"
Means: Stage 1 needs the large model.
Do: 1. Run `python workshop.py new s1 --restart`. 2. Pick the large model. Never Auto.

### Overrun
Screen: "Over the 10-minute time box: flagged in the results."
Means: The agent worked more than 10 minutes.
Do: 1. Go on. 2. Next time stop the agent at its STOP time.

### Play your game
Screen: "Optional: play your game: python workshop.py play"
Means: You can watch the game of your agent.
Do: 1. Run `python workshop.py play`. 2. Press Ctrl+C to stop.

### Next: write the skill
Screen: "stage 2 (the SAME agent thread writes a skill), run:"
Means: Stage 1 is over.
Do: 1. Run `python workshop.py skill`.

### Agents still working
Screen: "agents are still working. When each is done (or at 10 min), run its line:"; "1 agent is still working."
Means: Some runs are not ended.
Do: 1. Stop each agent at its STOP time. 2. Run the line for that run.

### All agents done
Screen: "all agents are done. Now:"
Means: All runs ended. The box lists the last steps in order.
Do: 1. Run the numbered commands one by one. They are unlock, grade, show and submit.

### Score not graded yet
Screen: "Score not graded yet."; "Score: graded at the end."
Means: The grader is locked or `grade` did not run.
Do: 1. After all agents are done: `python workshop.py unlock 4 <password from the slide>`. 2. Then `python workshop.py grade`.

## the stage 3 run list

### Stop times
Screen: "Stop each agent at its stop time (start + "
Means: Each run has a STOP time. It is 10 minutes after you sent the prompt.
Do: 1. Stop each agent in the app at its time. 2. Type its number in the terminal.
Why: Each run gets the same time.

### Type the NUMBER
Screen: "Type the NUMBER (1-"
Means: The kit waits for the number of a run whose agent has stopped.
Do: 1. Stop the agent in the app. 2. Type its number. 3. Type q to leave the list.

### Bad number
Screen: "Type a number from 1 to"
Means: The input was not a run number. An Enter alone does nothing.
Do: 1. Type a number from the list. 2. Or q.

### Did you stop its agent
Screen: "Did you stop its agent?"; "Not ended. Stop the agent first, then type the number again."
Means: The run has time left. The kit asks before it ends the run.
Do: 1. Stop the agent in the app. 2. Type y. 3. Or type the number again later.
Why: A running agent can change the files after the kit saved them.

### You left the list
Screen: "You left the list."
Means: You typed q. The runs are not ended.
Do: 1. Later run the printed line for each run: `python workshop.py done <run id>`.

### Run already ended
Screen: "is already ENDED."; "runs are ENDED."
Means: The kit saved this run.
Do: 1. Type another number. 2. When all are ENDED: `python workshop.py show`.

### Play the results
Screen: "PLAY what the agents made"
Means: All runs ended. You can watch the games.
Do: 1. Run `python workshop.py play T3` or `python workshop.py play T6`. 2. Then `python workshop.py show`.

### Done failed in the list
Screen: "done could not finish for"; "done stopped for"
Means: `done` stopped for one run. The other runs are safe.
Do: 1. Run `python workshop.py done <run id>` for that run. 2. Send the message to the instructor if it repeats.

### Table of runs
Screen: "ENDED  (done saved)"
Means: The kit saved this run.
Do: 1. Go on.

## unlock, grade, show, play, submit, cleanup

### Wrong password
Screen: "Wrong password."
Means: The password does not match.
Do: 1. Read the password on the slide again. 2. Type it exactly. 3. Run `python workshop.py unlock 4 <password from the slide>`.

### No such part
Screen: "There is no locked part"
Means: The part number is wrong.
Do: 1. Use the part on the slide, for example `python workshop.py unlock 4 <password from the slide>`.

### Unlocked part
Screen: "Unlocked part"
Means: The part is open. It is outside every run folder.
Do: 1. Go on. Never copy it into a run folder.

### Unlock while agents work
Screen: "Unlock the grader only after the agents are done."; "Unlock anyway?"
Means: A run is still active.
Do: 1. Press Enter for no. 2. Finish the runs with `python workshop.py done`. 3. Unlock again.
Why: The agents must finish before the grader opens.

### Grader locked
Screen: "The grader is locked:  python workshop.py unlock 4"; "Unlock the grader first:"
Means: `grade` or `submit` needs the unlock first.
Do: 1. Run `python workshop.py unlock 4 <password from the slide>`. 2. Run the first command again.

### Nothing to grade
Screen: "Nothing to grade."
Means: All runs have a score.
Do: 1. Run `python workshop.py show`.

### Grading failed
Screen: "grading failed:"
Means: The grader program did not run. A missing numpy is the usual reason.
Do: 1. Run `pip install numpy`. 2. Run `python workshop.py grade` again. 3. If it stays, send the line to the instructor.

### Saved line
Screen: "Saved. You submit all results at the end"
Means: The scores are saved on this computer.
Do: 1. Run `python workshop.py show`. 2. Later run `python workshop.py submit`.

### No results yet
Screen: "No results yet."
Means: No run is finished.
Do: 1. Finish a run with `python workshop.py done`.

### Show with and without
Screen: "The with/without tables: python workshop.py show --compare"
Means: The tables are hidden while agents work.
Do: 1. Run `python workshop.py show --compare`.

### Table notes
Screen: "* = stopped early; graded as partial work."; "! = over"
Means: Marks next to a result. A star means the run was stopped. A mark ! means it ran past 10 minutes.
Do: 1. Go on.

### Not a matched comparison
Screen: "Settings differ: this is not a matched comparison."; "One run was over the time box: this is not a matched comparison."
Means: The two runs used different models, or one ran too long.
Do: 1. Go on. 2. Next time use the same named model in all chats and stop at the STOP time.

### Failed attempt note
Screen: "At least one attempt failed."; "Change not shown: one attempt failed"
Means: The table does not show a change for a failed attempt.
Do: 1. Go on. 2. Ask in the debrief.

### Observed results note
Screen: "Observed results: one attempt per condition."; "Estimated cost under the kit's price assumptions."
Means: These notes describe the table. The numbers are one try each. The cost is an estimate.
Do: 1. Go on.

### Waiting for a pair
Screen: "waiting for its control run"; "waiting for the run WITH the skill"; "no control run"
Means: The other run of this pair is not finished.
Do: 1. Finish the other run with `python workshop.py done <run id>`.

### No control runs
Screen: "No control runs: run python workshop.py new s3 --task all for a fair comparison."
Means: This stage 3 had no runs without the skill.
Do: 1. Run `python workshop.py new s3 --task all`.

### Observed gains line
Screen: "Observed score gains: T3"; "Break-even not established."
Means: These lines are facts for the debrief. They make no claim.
Do: 1. Go on. 2. Ask the instructor in the debrief.

### Nothing to submit
Screen: "Nothing to submit. All results are submitted."
Means: Every result was sent.
Do: 1. Run `python workshop.py cleanup` when you are finished.

### Submit steps
Screen: "If Forms asks 'Use previous draft or New draft?', click New draft."; "Your results are on the clipboard."
Means: The form opened with your alias. The results are copied.
Do: 1. Click the all_results field. 2. Press Ctrl+V (Cmd+V on a Mac). 3. Click Submit. 4. Press Enter in the terminal.

### Submit link only
Screen: "(the browser did not open)"; "Copy ALL the lines between the two marks below"
Means: The browser did not open, or the copy failed.
Do: 1. Open the printed link. 2. Copy all lines between the marks. 3. Paste them in all_results. 4. Click Submit. 5. Press Enter.

### Submit skip
Screen: "Press Enter when submitted (s = skip, mark nothing)"; "Run submit again when you are ready."
Means: The kit waits until you click Submit.
Do: 1. Click Submit in the form. 2. Press Enter. 3. Or type s and run `python workshop.py submit` later.

### Submit result
Screen: "results submitted"; "(run submit again for the rest)"
Means: The kit counted your sent results.
Do: 1. If some are left: `python workshop.py submit`.

### Play pair
Screen: "key 1 = with skill, 2 = without"
Means: A page shows the two games.
Do: 1. Run `python workshop.py play T3` or `python workshop.py play T6`.

### Play problems
Screen: "runs with and without the skill yet."; "No stage-1 run yet. Start with"; "has no saved program (solutions/"
Means: There is no game file to play.
Do: 1. Finish the run with `python workshop.py done`. 2. Run `python workshop.py show`.

### Form again
Screen: "No finished stage"
Means: `form` found no finished stage.
Do: 1. Run `python workshop.py show`. 2. Use a run id from the list.

### Cleanup question
Screen: "Delete all of these? [y/N]"; "Copy results.csv to"
Means: `cleanup` deletes everything the kit made. It lists the items first.
Do: 1. Close all agent windows. 2. Type Y to copy your results file. 3. Type y to delete. Type n to keep.
Why: This frees disk space.

### Cleanup notes
Screen: "Nothing deleted."; "skipped (outside the workshop home, or a link)"; "Cleanup done."
Means: The result of `cleanup`.
Do: 1. Go on.

### Cleanup leftovers
Screen: "VESPER skills in global folders (not made by workshop.py"; "Left in"
Means: Files that the kit did not make stay in place.
Do: 1. Look at them. 2. Type y to remove skill folders, or keep them. The learner decides.

## modes, auto and restart

### Auto question
Screen: "Not started: no terminal to answer. Add --yes to start them."; "What they may do:"
Means: `--auto` shows what the agents may do and asks first.
Do: 1. Read the lines. 2. Type y to start, or n.

### Auto run failed
Screen: "RUN FAILED"; "Do the failed runs by hand:"
Means: The tool could not run one agent.
Do: 1. Read the reason on the line. 2. Run `python workshop.py new s3 --task all`. It shows the page of each failed run.

### Auto usage limit
Screen: "A usage limit stopped the agent."
Means: The plan of the account reached its limit.
Do: 1. Wait for the limit to reset. 2. Or do the stage by hand.

### Auto stopped
Screen: "Stopped with Ctrl+C. All agents are killed."; "Each stopped run is saved as partial work."
Means: You stopped `--auto`. Each run keeps its work.
Do: 1. Run `python workshop.py show`.

### Auto agent ended
Screen: "The agent ended with exit code"; "the finish failed"; "could not start:"
Means: The agent program ended with an error or did not start.
Do: 1. Read the reason. 2. Run `python workshop.py done <run id>`. 3. Or use the normal flow.

### Auto resume
Screen: "an agent still works on it in another window."; "an --auto agent works on it in another window."; "you run it by hand. When it is done:"
Means: Another terminal runs this agent.
Do: 1. Do not start it twice. 2. Wait for it, then run `python workshop.py done <run id>`.

### Auto old work
Screen: "has work from an earlier agent. Start a new agent there?"
Means: The run folder holds work from an agent that stopped.
Do: 1. Type n to keep the work. 2. Run `python workshop.py done <run id> --partial`.

### Auto nothing to start
Screen: "No run can be started by --auto now."
Means: All runs are done or run by hand.
Do: 1. Run `python workshop.py show`.

## warnings and extra lines

### Copilot stage 2 step
Screen: "Copilot Chat: in the SAME chat, type /create-skill"
Means: Copilot needs the skill command first.
Do: 1. Type /create-skill. 2. Paste the prompt in the SAME chat.

### Auto confirmation line
Screen: "The tool stops each agent at"
Means: With `--auto` the tool stops each agent at 10 minutes.
Do: 1. Go on.

### Skill not found
Screen: "SKILL NOT FOUND"
Means: The agent said SKILL NOT FOUND. It could not load the skill in a WITH-skill run.
Do: 1. Check that the project is exactly the run folder. 2. If not: `python workshop.py new s3 --task all --restart`. 3. If yes, send the last 15 lines to the instructor.
Why: The skill copies live inside the run folder.
