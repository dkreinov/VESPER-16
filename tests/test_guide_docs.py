"""The learner guide (helper-skill/vesper-guide/SKILL.md) must fit the script, and must not drift into the console."""
import contextlib, io, os, re, subprocess, sys, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import workshop as W  # noqa: E402

SKILL = os.path.join(ROOT, "helper-skill", "vesper-guide", "SKILL.md")


def skill_text():
    with open(SKILL, encoding="utf-8") as f:
        return f.read().replace("\r\n", "\n")


def script_text():
    parts = []
    for p in [os.path.join(ROOT, "workshop.py"), os.path.join(ROOT, "launchers.py"), os.path.join(ROOT, "copilot_partial.py")] \
            + [os.path.join(ROOT, "prompts", n) for n in os.listdir(os.path.join(ROOT, "prompts"))]:
        with open(p, encoding="utf-8") as f:
            parts.append(f.read())
    return "\n".join(parts)


FILL = {"<command>": "new", "<name>": "codex", "<run id>": "s1-abcd", "<password from the slide>": "x"}


def commands(text):
    """Every `python workshop.py ...` inside backticks, as an argv list (placeholders filled)."""
    out = []
    for m in re.finditer(r"`python workshop\.py ([^`]+)`", text):
        raw = m.group(1)
        for k, v in FILL.items():
            raw = raw.replace(k, v)
        raw = re.sub(r"\s*\(.*$", "", raw)           # drop "(stage 1: ...)" tails
        out.append(raw.split())
    return out


class GuideMatchesScript(unittest.TestCase):
    def test_every_command_parses(self):
        cmds = commands(skill_text())
        self.assertGreaterEqual(len(cmds), 10)
        for argv in cmds:
            with self.subTest(command=" ".join(argv)):
                err = io.StringIO()
                try:
                    with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                        W.parse(argv)
                except SystemExit as e:
                    if e.code in (0, None):       # -h exits 0: the command exists
                        continue
                    self.fail("does not parse (%s): %s" % (e.code, err.getvalue().strip()[-160:]))

    def test_screen_phrases_exist_in_the_script(self):
        src = script_text()
        for phrase in ("MODE: SEMI", "Mode: MANUAL", "FIRST, BEFORE YOU SEND THE PROMPT", "Type the NUMBER",
                       "ENDED", "Did you stop its agent", "memory: OFF (verified)", "STAGE 3 - RUN",
                       "NEXT:", "SKILL NOT FOUND", "Workshop run:", "Make reasonable assumptions and continue"):
            with self.subTest(phrase=phrase):
                self.assertTrue(phrase in src, "not in the script: " + phrase)
                self.assertTrue(phrase in skill_text(), "not in the guide: " + phrase)

    def test_model_names_match_the_script(self):
        for name in ("gpt-6-luna", "Haiku 5.5", "GPT-5.6 Luna High"):
            with self.subTest(model=name):
                self.assertIn(name, W.SMALL_SHORT["codex"] + W.SMALL_SHORT["claude"] + W.SMALL_SHORT["cursor"])
                self.assertIn(name, skill_text())

    def test_time_box_and_run_count_match(self):
        self.assertIn("(10 minutes each)", skill_text())
        self.assertEqual(W.TIME_BOX_MIN, 10)
        self.assertIn("20 runs", skill_text())
        self.assertIn("6 runs", skill_text())

    def test_prompt_file_is_in_step_with_the_skill(self):
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "make_guide_prompt.py"), "--check"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


class GuideStaysOutOfTheConsole(unittest.TestCase):
    # The guide holds no knowledge of the console, the games or the scoring. A word here is a leak.
    BANNED = ("opcode", "instruction set", "register", "framebuffer", "interrupt", "sprite", "assembler syntax",
              "memory map", "paddle", "brick", "squash", "breakout", "score is", "points for", "threshold")

    def test_no_console_or_game_words(self):
        # rule 1 names the forbidden topics on purpose; every other line must stay free of them
        lines = [l for l in skill_text().splitlines() if "Never explain how the VESPER-16 console" not in l]
        low = " ".join(lines).lower()
        for w in self.BANNED:
            with self.subTest(word=w):
                self.assertNotIn(w, low)

    def test_hard_rules_are_present(self):
        t = skill_text()
        for needle in ("Finding out how the console works is part of the exercise", "Never run `unlock`",
                       "SEPARATE chat", "Type SPOIL again to continue", "never give game code"):
            with self.subTest(rule=needle):
                self.assertIn(needle, t)

    def test_size_and_front_matter(self):
        t = skill_text()
        self.assertLess(len(t), 10000)
        self.assertTrue(t.startswith("---\nname: vesper-guide\n"))
        self.assertIn("description:", t.split("\n---\n", 1)[0])


if __name__ == "__main__":
    unittest.main()
