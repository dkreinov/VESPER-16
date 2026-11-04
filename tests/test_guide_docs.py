"""The learner guide (helper-skill/vesper-guide/SKILL.md) must fit the script, and must not drift into the console."""
import ast, contextlib, io, os, re, subprocess, sys, unittest

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


SCREENS = os.path.join(ROOT, "helper-skill", "vesper-guide", "SCREENS.md")


def screens_text():
    with open(SCREENS, encoding="utf-8") as f:
        return f.read().replace("\r\n", "\n")


def screens_entries():
    """[(title, {"Screen": line, "Means": line, "Do": line, ...})] from the '### ' entries of SCREENS.md."""
    out = []
    for block in re.split(r"^### ", screens_text(), flags=re.M)[1:]:
        title, _, rest = block.partition("\n")
        fields = {}
        for ln in rest.splitlines():
            m = re.match(r"^(Screen|Means|Do|Why):\s*(.*)$", ln)
            if m:
                fields[m.group(1)] = m.group(2)
        out.append((title.strip(), fields))
    return out


def screen_phrases():
    out = []
    for title, f in screens_entries():
        out += [(title, p) for p in re.findall(r'"([^"]+)"', f.get("Screen", ""))]
    return out


def source_text():
    """Text of every script that shows a message to the learner."""
    parts = [script_text()]
    with open(os.path.join(ROOT, "measure.py"), encoding="utf-8") as f:
        parts.append(f.read())
    return "\n".join(parts)


# Messages that no learner meets in the workshop: each has a one-line reason.
ALLOWLIST = {
    "cannot start": "shadow: a presenter command, not part of the learner flow",
}


def _segments(node):
    """Literal pieces of a message expression: each string constant is cut at the first % or { placeholder
    and at every new line; pieces of 12 characters or more are returned (stripped)."""
    segs = []
    for n in ast.walk(node):
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            for part in re.split(r"%[-0-9.]*[sdrf]|\{[^}]*\}|\n", n.value):
                part = part.strip()
                if len(part) >= 12:
                    segs.append(part)
    return segs


def script_messages():
    """[(line, [segments])] of every sys.exit(...) and print(c_err(...)) call in workshop.py that has a literal."""
    with open(os.path.join(ROOT, "workshop.py"), encoding="utf-8") as f:
        tree = ast.parse(f.read())
    out = []
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call) or not n.args:
            continue
        fn = n.func
        is_exit = isinstance(fn, ast.Attribute) and fn.attr == "exit" and getattr(fn.value, "id", "") == "sys"
        arg = n.args[0]
        is_err = isinstance(fn, ast.Name) and fn.id == "print" and isinstance(arg, ast.Call) \
            and isinstance(arg.func, ast.Name) and arg.func.id == "c_err" and arg.args
        if is_err:
            arg = arg.args[0]
        if not (is_exit or is_err):
            continue
        segs = _segments(arg)
        if segs:
            out.append((n.lineno, segs))
    return out


class ScreensList(unittest.TestCase):
    def test_every_key_phrase_is_in_the_script(self):
        src = source_text()
        phrases = screen_phrases()
        self.assertGreaterEqual(len(phrases), 70)
        for title, p in phrases:
            with self.subTest(entry=title, phrase=p):
                self.assertIn(p, src, "not in the scripts: " + p)

    def test_at_least_70_entries_with_screen_means_do(self):
        ents = screens_entries()
        self.assertGreaterEqual(len(ents), 70)
        titles = [t for t, _ in ents]
        self.assertEqual(len(titles), len(set(titles)), "duplicate entry titles")
        for title, f in ents:
            with self.subTest(entry=title):
                for k in ("Screen", "Means", "Do"):
                    self.assertTrue(f.get(k), "entry '%s' has no %s:" % (title, k))

    def test_required_learner_cases_are_listed(self):
        have = " ".join(p for _, p in screen_phrases())
        for needle in ("No skill at", "is still active", "Wrong password.", "WRONG FOLDER", "memory was ON",
                       "memory: OFF (verified)", "may have read outside the run folder", "Cursor chat not found",
                       "Did you stop its agent", "Type a number from 1 to", "You left the list",
                       "The app did not open on its own", "SKILL NOT FOUND", "Several agent sessions contain",
                       "Fix the FAIL lines first", "Unlocked part", "There is no locked part",
                       "RED:", "YELLOW:", "superpowers is active for", "Codex Memories hold VESPER notes",
                       "is on OneDrive", "global folder", "git is missing", "Python 3.9 or newer is needed"):
            with self.subTest(case=needle):
                self.assertIn(needle, have)
        self.assertIn("numpy", screens_text())

    def test_coverage_of_error_messages(self):
        phrases = [p for _, p in screen_phrases()]
        missing = []
        for line, segs in script_messages():
            if any(a in s or s in a for s in segs for a in phrases):
                continue
            if any(k in s for s in segs for k in ALLOWLIST):
                continue
            missing.append("workshop.py:%d  %s" % (line, " | ".join(segs)[:150]))
        self.assertEqual(missing, [], "sys.exit / print(c_err()) messages with no entry in SCREENS.md "
                                      "(add an entry or an ALLOWLIST line with a reason):\n" + "\n".join(missing))

    def test_allowlist_has_reasons_and_is_used(self):
        segs = [s for _, ss in script_messages() for s in ss]
        for k, why in ALLOWLIST.items():
            with self.subTest(key=k):
                self.assertTrue(why.strip())
                self.assertTrue(any(k in s for s in segs), "allowlist entry matches no message: " + k)

    def test_no_console_or_game_words(self):
        low = screens_text().lower()
        for w in GuideStaysOutOfTheConsole.BANNED:
            with self.subTest(word=w):
                self.assertNotIn(w, low)
        # "console" may only appear as "the VESPER-16 console"
        rest = screens_text().replace("the VESPER-16 console", "")
        self.assertNotIn("console", rest.lower())
        for w in ("invented", "fake", "simulat"):
            self.assertNotIn(w, low)

    def test_commands_in_screens_parse(self):
        cmds = commands(screens_text())
        self.assertGreaterEqual(len(cmds), 30)
        for argv in cmds:
            with self.subTest(command=" ".join(argv)):
                err = io.StringIO()
                try:
                    with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                        W.parse(argv)
                except SystemExit as e:
                    if e.code in (0, None):
                        continue
                    self.fail("does not parse (%s): %s" % (e.code, err.getvalue().strip()[-160:]))

    def test_guide_prompt_holds_the_screens(self):
        with open(os.path.join(ROOT, "docs", "GUIDE-PROMPT.txt"), encoding="utf-8") as f:
            t = f.read().replace("\r\n", "\n")
        self.assertIn("--- THE SCREENS LIST (match the learner's pasted text to an entry) ---", t)
        self.assertIn("### Wrong password", t)

    def test_skill_points_to_the_screens_list(self):
        t = skill_text()
        self.assertIn("SCREENS.md", t)
        self.assertIn("send them to the instructor", t)


if __name__ == "__main__":
    unittest.main()
