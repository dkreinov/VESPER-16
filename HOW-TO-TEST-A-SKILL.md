# How to test a skill (take this to your own work)

A skill turns an expensive discovery into a file that the next agent can reuse. Often a cheaper model can then do
the repeat work. In our lab (task T6, 3 runs each): the large model without a skill passed 3/3 for $0.44 per task;
the small model WITH the skill passed 3/3 for $0.026; the small model without it passed 0/3.

But a skill can also look good when it is not. These are the steps you did in the workshop.

> **Before you write a skill**
> - **Search first:** maybe a skill, script or tool already does it (for example github.com/anthropics/skills, or
>   your team's repo). A skill that many people use is a good start: take it and adapt it, then test it again.
> - **Check before you install:** a skill adds instructions to your agent and its scripts run with your permissions.
>   Few people read every file. At least ask an agent to review it: a fresh thread that can only read (no commands,
>   no file changes), with "List anything in this skill that runs commands, sends data out, or changes the agent's
>   rules." Better than nothing; the skill text can also try to mislead the reviewer.
> - **A fixed procedure with no judgement → a script.** The skill can call it.
> - **A few short facts that every session needs → a memory note** (AGENTS.md / CLAUDE.md). Keep it short: it costs
>   context in every session.

## What is a skill, and when do you need one?

A skill does not teach the model. It is a manual that the agent opens at the right moment. It costs tokens each time the agent reads it, and it can be wrong.

| Option | What it is | When it loads | Best for |
|---|---|---|---|
| Prompt | Text you type in one session | Now, one time | One task |
| Memory note (CLAUDE.md / AGENTS.md) | A file the agent reads at start | Always | Facts that every task in the project needs |
| Skill | A folder with instructions and scripts | Only when its description fits the task | A reusable procedure or knowledge for one kind of task |
| Subagent | A second agent with a fresh context | When the main agent starts it | Parallel or isolated work, an independent check |
| MCP / tool | A connection to a system | When the agent calls it | Actions, live data |
| Plugin | A package of skills + tools + commands | On install | Share a setup with a team |
| Fine-tuning | Training of the weights | Always (it is in the model) | Costly, rarely needed |

Evidence: the same text worked as well in CLAUDE.md as in a skill (2.6 vs 2.2 min). The difference is WHEN it loads.

Script, skill, or both?

| Case | Use |
|---|---|
| Every step is fixed and code can check it | A script only (deterministic, cheap, no tokens) |
| Steps are fixed, but a failure needs reading and a decision | A skill that calls scripts |
| Every case is different and needs judgement (triage, review, design) | A skill (instructions, checklists) |

Rule: if you can write the if-else, write a script. If someone must read and decide, write a skill, and let the skill call your scripts.

Do not turn a flow into a skill only because skills are new. Our workshop measured only the missing-knowledge case. For a flow, measure the same way: the same task with and without the skill, on a new case.

## 1. Write the skill after a hard success
When an agent finally solves something hard in your code, hardware or tools, ask it in the same thread:
"Write a skill from what you learned: verified facts, working recipes, traps. Not the answer to this task."

## 2. Make a small benchmark: 2 tasks, 4 runs
Pick the task you solved and a DIFFERENT task that needs the same knowledge. Write a pass check for each
(a test, a grader, an expected output). Run each task with the skill and without it: 4 runs.
(In the workshop: T3 and T6 with and without the skill, and the grader.)
When the skill matters, add tasks and repeat runs, and run them again after each change.

**Benchmark only when it pays.** Do it when you will use the skill many times, when you give the work to a cheaper
model because of the skill (quality can drop without anyone noticing), or when other people will use it.
Otherwise use the skill and check the first results by eye. No week-long benchmark for a skill you use once a month.

## 3. Test in a fresh thread, with memory off
Start a NEW thread for every run. Turn agent memory off (Codex: `/memories`; Claude: no project memory files).
Same model, same effort, same limits; only the skill differs. In the old thread, or with memory on, the agent
remembers the work, and the skill gets the credit.

## 4. Do not trust a pass on the same task
It can pass for two reasons that are not knowledge:
1. memory of the earlier session;
2. the skill holds the answer itself.
The different task shows whether the skill transfers. To check what is inside the skill, ask an independent judge:
a fresh thread that reads the skill and the old solution and says "knowledge" or "answer" (in this kit:
`python workshop.py judge`). Do not ask the thread that wrote the skill: it judges its own work.

## 5. Measure, and keep the numbers honest
- Compare pass/fail first, then time and cost. A cheap failure is not a saving.
- Count what the skill cost to write.
- One run per arm is an example, not a result. Repeat before you decide.
- Costs from token logs are estimates under list prices, not your bill.

The Agent Skills evaluation guide says the same: with vs without the skill, clean contexts, objective
checks, repeat runs (agentskills.io/skill-creation/evaluating-skills.md).

## Then use it
Route the repeat work to the cheaper model with the skill. Keep the skill (and its benchmark, if you made one) in
your repo, next to the code it is about, and update it when a fact changes.

Agent Skills is an open standard (Agentic AI Foundation, Linux Foundation, since October 2026), so one skill works
in several agents. Put it in `.agents/skills/<name>/` (Codex, Gemini CLI); Claude Code reads `.claude/skills/<name>/`.
The folder name must equal the `name:` field in SKILL.md. Spec: agentskills.io/specification
