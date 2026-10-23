# How to test a skill (take this to your own work)

A skill turns an expensive discovery into a file that the next agent can reuse. Often a cheaper model can then do
the repeat work. In our lab (task T6, 3 runs each): the large model without a skill passed 3/3 for $0.44 per task;
the small model WITH the skill passed 3/3 for $0.026; the small model without it passed 0/3.

But a skill can also look good when it is not. Use these 5 steps before you trust one.

## 1. Write the skill after a hard success
When an agent finally solves something hard in your code, hardware or tools, ask it in the same thread:
"Write a skill from what you learned: verified facts, working recipes, traps. Not the answer to this task."

## 2. Test in a fresh thread, with memory off
Start a NEW thread. Turn agent memory off (Codex: `/memories`; Claude: no project memory files).
In the old thread, or with memory on, the agent remembers the work, and the skill gets the credit.

## 3. Run the same task WITHOUT the skill
Same model, same effort, same task, same limits (time, attempts). Only the skill differs.
Without this control you cannot say that the skill helped.

## 4. Test on a DIFFERENT task too
A pass on the same task proves little. It can pass for two reasons that are not knowledge:
1. memory of the earlier session;
2. the skill holds the answer itself.
A different task that needs the same knowledge shows whether the skill transfers.
To check what is inside the skill, ask an independent judge: a fresh thread that reads the skill and the old
solution and says "knowledge" or "answer" (in this kit: `python workshop.py judge`). Do not ask the thread that
wrote the skill: it judges its own work.

## 5. Measure, and keep the numbers honest
- Compare pass/fail first, then time and cost. A cheap failure is not a saving.
- Count what the skill cost to write.
- One run per arm is an example, not a result. Repeat (3 runs each is a good start) before you decide.
- Costs from token logs are estimates under list prices, not your bill.

## Then use it
Route the repeat work to the cheaper model with the skill. Keep the skill in your repo, next to the code it is about,
and update it when a fact changes.
