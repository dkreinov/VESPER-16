"""doctor v2: report + help prompt on a fault, auto-run in new s1 until it passes, superpowers warning."""
import contextlib, io, json, os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fakes import fresh_ws, run  # noqa: E402


def capture(fn, *a):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        r = fn(*a)
    return r, out.getvalue()


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


class DoctorReportTest(unittest.TestCase):
    def setUp(self):
        self.w, self.tmp = fresh_ws()
        self.real_bin = self.w.vesper_bin
        self.report = os.environ["VESPER_DOCTOR_REPORT"]

    def break_emulator(self):
        self.w.vesper_bin = lambda: os.path.join(self.tmp, "no-emulator")

    def test_fault_writes_report_and_prints_help_prompt(self):
        self.break_emulator()
        rc, out = capture(run, self.w, "doctor", "--agent", "codex", "--alias", "")
        self.assertEqual(rc, 2)
        with open(self.report, encoding="utf-8") as f:
            text = f.read()
        for s in ("Faults:", "the emulator does not run", "OS:", "Python:", "kit folder: " + self.w.KIT,
                  "Agent CLI versions:", "  codex: ", "workshop home: "):
            self.assertIn(s, text)
        self.assertIn(self.w.HELP_PROMPT, out)
        self.assertEqual(self.w.HELP_PROMPT, "Read doctor-report.txt and help me fix the setup. "
                                             "Do not change files outside this folder.")

    def test_new_s1_reruns_doctor_until_it_passes(self):
        self.break_emulator()
        with self.assertRaises(SystemExit):
            run(self.w, "new", "s1")
        self.assertEqual(self.w.Registry.load().data["doctor"]["level"], 2)
        self.assertTrue(os.path.exists(self.report))
        self.w.vesper_bin = self.real_bin
        run(self.w, "new", "s1")
        reg = self.w.Registry.load()
        self.assertEqual(reg.data["doctor"]["level"], 0)
        self.assertEqual(reg.data["active"]["stage"], "1")
        self.assertFalse(os.path.exists(self.report))       # a green doctor removes the old report

    def test_cli_version_not_found(self):
        self.assertEqual(self.w.cli_version("no-such-agent-cli-xyz"), "not found")


class SuperpowersTest(unittest.TestCase):
    def setUp(self):
        self.w, self.tmp = fresh_ws()
        self.claude = os.environ["CLAUDE_CONFIG_DIR"]
        self.codex = os.environ["CODEX_HOME"]
        self.home = os.environ["VESPER_WS_USERHOME"]

    def test_nothing_installed(self):
        for agent in ("codex", "claude", "cursor", "other"):
            self.assertEqual(self.w.superpowers_evidence(agent), [])

    def test_claude_enabled_plugin(self):
        write(os.path.join(self.claude, "settings.json"),
              json.dumps({"enabledPlugins": {"superpowers@superpowers-dev": True, "x@y": True}}))
        ev = self.w.superpowers_evidence("claude")
        self.assertEqual(len(ev), 1)
        self.assertIn("superpowers@superpowers-dev", ev[0])
        self.assertEqual(self.w.superpowers_evidence("codex"), [])

    def test_claude_installed_but_disabled_is_quiet(self):
        write(os.path.join(self.claude, "settings.json"),
              json.dumps({"enabledPlugins": {"superpowers@superpowers-dev": False}}))
        write(os.path.join(self.claude, "plugins", "installed_plugins.json"),
              json.dumps({"plugins": {"superpowers@superpowers-dev": [{"scope": "user"}]}}))
        self.assertEqual(self.w.superpowers_evidence("claude"), [])

    def test_claude_installed_plugin(self):
        write(os.path.join(self.claude, "plugins", "installed_plugins.json"),
              json.dumps({"plugins": {"superpowers@superpowers-dev": [{"scope": "user"}]}}))
        self.assertEqual(len(self.w.superpowers_evidence("claude")), 1)

    def test_codex_config_enabled_and_disabled(self):
        cfg = os.path.join(self.codex, "config.toml")
        write(cfg, '[plugins."gmail@openai-curated"]\nenabled = true\n\n'
                   '[plugins."superpowers@openai-curated"]\nenabled = true\n')
        self.assertEqual(len(self.w.superpowers_evidence("codex")), 1)
        write(cfg, '[plugins."superpowers@openai-curated"]\nenabled = false\n[other]\nenabled = true\n')
        self.assertEqual(self.w.superpowers_evidence("codex"), [])

    def test_codex_skill_folder(self):
        write(os.path.join(self.home, ".agents", "skills", "using-superpowers", "SKILL.md"), "x")
        self.assertEqual(len(self.w.superpowers_evidence("codex")), 1)

    def test_cursor_plugin_folder(self):
        os.makedirs(os.path.join(self.home, ".cursor", "plugins", "cache", "mkt", "superpowers"))
        self.assertEqual(len(self.w.superpowers_evidence("cursor")), 1)

    def test_doctor_warns_and_stays_yellow(self):
        write(os.path.join(self.claude, "settings.json"),
              json.dumps({"enabledPlugins": {"superpowers@superpowers-dev": True}}))
        rc, out = capture(run, self.w, "doctor", "--agent", "claude", "--alias", "")
        self.assertEqual(rc, 0)
        self.assertIn("answer 'go on'", out)
        self.assertEqual(self.w.Registry.load().data["doctor"]["level"], 1)


if __name__ == "__main__":
    unittest.main()
