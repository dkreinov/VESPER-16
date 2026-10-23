# How to test a skill (take this to your own work)

A skill turns an expensive discovery into a file that the next agent can reuse. Often a cheaper model can then do
the repeat work. In our lab (task T6, 3 runs each): the large model without a skill passed 3/3 for $0.44 per task;
the small model WITH the skill passed 3/3 for $0.026; the small model without it passed 0/3.

But a skill can also look good when it is not. These are the steps you did in the workshop.

> **Before you write a skill**
> - **Search first:** maybe a skill, script or tool already does it. A skill that many people use is a good start:
>   take it and adapt it. Read it before you use it (it runs with your permissions), and test it again after you change it.
> - **A fixed procedure with no judgement → a script.** The skill can call it.
> - **A few short facts that every session needs → a memory note** (AGENTS.md / CLAUDE.md). Keep it short: it costs
>   context in every session.

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

## Then use it
Route the repeat work to the cheaper model with the skill. Keep the skill (and its benchmark, if you made one) in
your repo, next to the code it is about, and update it when a fact changes.
