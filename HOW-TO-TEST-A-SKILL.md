# How to build and test a skill (take this to your own work)

A skill turns an expensive discovery into a file that the next agent can reuse. Often a cheaper model can then do
the repeat work. In our lab (task T6, 3 runs each): the large model without a skill passed 3/3 for $0.44 per task;
the small model WITH the skill passed 3/3 for $0.026; the small model without it passed 0/3.

But a skill is not always the right tool, and a skill can look good when it is not. Use these steps.

## 1. Check first: does it already exist?
Search before you write: your team's skills, the plugin/skill marketplaces of your agent, existing tools, scripts
and MCP servers. Reuse or extend one if it fits.

## 2. Choose the right form
| The knowledge is... | Best form | Why |
|---|---|---|
| A fixed procedure with no judgement (build, convert, check) | **A script** (the skill can call it) | Same result every time, no tokens, easy to test |
| A few short facts that every session needs | **A memory note** (AGENTS.md / CLAUDE.md / project memory) | Always loaded; but it costs context in every session, so keep it short |
| Knowledge and recipes that only some tasks need | **A skill** | Loaded only when needed |
| A whole role with many steps, its own tools or a separate context | **An agent / subagent** (it can use skills) | Own context, can run in parallel, isolated |
Often the answer is a mix: a skill that explains when to run which script.

## 3. Build a small benchmark before you trust anything
Write down 3 to 5 tasks with a clear pass check (a test, a grader, an expected output):
- the original task;
- one or two variants of it;
- at least one DIFFERENT task that needs the same knowledge.
Keep the benchmark next to the skill. Run it again every time the skill or the model changes.
(In this workshop: T3 is the original, T6 the different task, and the locked grader is the pass check.)

## 4. Write the skill after a hard success
When an agent finally solves something hard in your code, hardware or tools, ask it in the same thread:
"Write a skill from what you learned: verified facts, working recipes, traps. Not the answer to this task."

## 5. Test in a fresh thread, with memory off, against a run without the skill
Start a NEW thread and turn agent memory off (Codex: `/memories`; Claude: no project memory files).
Run each benchmark task twice: with the skill and without it. Same model, same effort, same limits.
Without the run without the skill, you cannot say that the skill helped.

## 6. Do not trust a pass on the same task
It can pass for two reasons that are not knowledge:
1. memory of the earlier session;
2. the skill holds the answer itself.
The DIFFERENT task in your benchmark shows whether the skill transfers. To check what is inside the skill, ask an
independent judge: a fresh thread that reads the skill and the old solution and says "knowledge" or "answer"
(in this kit: `python workshop.py judge`). Do not ask the thread that wrote the skill: it judges its own work.

## 7. Measure, and keep the numbers honest
- Compare pass/fail first, then time and cost. A cheap failure is not a saving.
- Count what the skill cost to write.
- One run per arm is an example, not a result. Repeat (3 runs each is a good start) before you decide.
- Costs from token logs are estimates under list prices, not your bill.

## Then use it
Route the repeat work to the cheaper model with the skill. Keep the skill and its benchmark in your repo, next to the
code they are about, and update both when a fact changes.
