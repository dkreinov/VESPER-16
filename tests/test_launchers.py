"""launchers.py: find the agent app and open it on the run folder. Dry run only: no real app starts."""
import json, os, sys, tempfile, unittest
from unittest import mock
from urllib.parse import urlparse, parse_qs

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
import launchers as L  # noqa: E402

AGENTS = ("codex", "cursor", "claude", "copilot")


class Base(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="vlau_")
        self.log = os.path.join(self.d, "dry.jsonl")
        self.folder = os.path.join(self.d, "run folder & more")
        os.makedirs(self.folder)
        self.fake = os.path.join(self.d, "fakeapp.cmd")
        open(self.fake, "w").close()
        env = {"VESPER_LAUNCHER_DRYRUN": self.log}
        for a in AGENTS:
            env["VESPER_LAUNCHER_" + a.upper()] = self.fake
        p = mock.patch.dict(os.environ, env)
        p.start()
        self.addCleanup(p.stop)

    def entries(self):
        if not os.path.exists(self.log):
            return []
        with open(self.log, encoding="utf-8") as f:
            return [json.loads(x) for x in f if x.strip()]


class OneLine(unittest.TestCase):
    def test_text(self):
        self.assertEqual(L.one_line("s1-ab12"),
                         "Workshop run: s1-ab12. Read PROMPT.txt in this folder and do what it says.")


class Link(unittest.TestCase):
    def test_encoding(self):
        folder = "C:\\My Runs\\a&b\u00e9\u05d0"
        link = L.codex_link(folder, "Workshop run: x & y")
        self.assertTrue(link.startswith("codex://new?path="))
        self.assertEqual(link.count("&"), 1)
        q = parse_qs(urlparse(link).query)
        self.assertEqual(q["path"], [folder])
        self.assertEqual(q["prompt"], ["Workshop run: x & y"])
        self.assertNotIn(" ", link)


class Config(Base):
    def read(self):
        with open(os.path.join(self.folder, ".codex", "config.toml"), encoding="utf-8") as f:
            return f.read()

    def test_both(self):
        files = L.write_run_config("codex", self.folder, "gpt-x", "high")
        self.assertEqual(len(files), 1)
        t = self.read()
        self.assertIn('model = "gpt-x"', t)
        self.assertIn('model_reasoning_effort = "high"', t)

    def test_model_only(self):
        L.write_run_config("codex", self.folder, "gpt-x", None)
        t = self.read()
        self.assertIn('model = "gpt-x"', t)
        self.assertNotIn("reasoning", t)

    def test_none_given(self):
        self.assertEqual(L.write_run_config("codex", self.folder, None, None), [])
        self.assertFalse(os.path.exists(os.path.join(self.folder, ".codex")))

    def test_other_agents_write_nothing(self):
        for a in ("cursor", "claude", "copilot"):
            self.assertEqual(L.write_run_config(a, self.folder, "m", "high"), [])
        self.assertEqual(os.listdir(self.folder), [])


class Find(unittest.TestCase):
    def test_none_override(self):
        for a in AGENTS:
            with mock.patch.dict(os.environ, {"VESPER_LAUNCHER_" + a.upper(): "none"}):
                self.assertIsNone(L.find_app(a))

    def test_path_override(self):
        with mock.patch.dict(os.environ, {"VESPER_LAUNCHER_CURSOR": "X:\\c\\cursor.cmd"}):
            f = L.find_app("cursor")
        self.assertEqual((f.kind, f.path), ("cursor", "X:\\c\\cursor.cmd"))
        with mock.patch.dict(os.environ, {"VESPER_LAUNCHER_COPILOT": "X:\\code.cmd"}):
            self.assertEqual(L.find_app("copilot").kind, "vscode")
        with mock.patch.dict(os.environ, {"VESPER_LAUNCHER_CLAUDE": "X:\\claude.exe"}):
            self.assertEqual(L.find_app("claude").kind, "claude-cli")
        with mock.patch.dict(os.environ, {"VESPER_LAUNCHER_CODEX": "X:\\codex.cmd"}):
            self.assertEqual(L.find_app("codex").kind, "codex-cli")
        d = tempfile.mkdtemp()
        with mock.patch.dict(os.environ, {"VESPER_LAUNCHER_CODEX": d}):
            self.assertEqual(L.find_app("codex").kind, "codex-app")

    def test_unknown_agent(self):
        self.assertIsNone(L.find_app("nope"))

    def test_codex_cli_note_when_cli_is_preferred(self):
        env = {"VESPER_LAUNCHER_CODEX": ""}
        with mock.patch.dict(os.environ, env), mock.patch.object(L, "_which", return_value="codex.cmd"), mock.patch.object(L, "_codex_app_dir", return_value="appdir"):
            cli = L.find_app("codex", prefer="cli")
            app = L.find_app("codex")
        self.assertEqual((cli.kind, cli.note), ("codex-cli", "Codex CLI found."))
        self.assertNotIn("not found", cli.note)
        self.assertEqual(app.kind, "codex-app")

    def test_codex_cli_note_when_the_app_is_missing(self):
        with mock.patch.dict(os.environ, {"VESPER_LAUNCHER_CODEX": ""}), mock.patch.object(L, "_which", return_value="codex.cmd"), mock.patch.object(L, "_codex_app_dir", return_value=None):
            f = L.find_app("codex")
        self.assertEqual(f.kind, "codex-cli")
        self.assertIn("the app was not found", f.note)


class Open(Base):
    def test_codex_app(self):
        os.environ["VESPER_LAUNCHER_CODEX"] = self.d  # a folder means the app
        r = L.open_project("codex", self.folder, "s1-ab12", model="gpt-x", effort="high")
        self.assertTrue(r.ok)
        self.assertEqual(r.how, "codex-link")
        self.assertTrue(r.manual)
        e = self.entries()
        self.assertEqual(len(e), 1)
        self.assertEqual(e[0]["agent"], "codex")
        link = [a for a in e[0]["argv"] if a.startswith("codex://")][0]
        q = parse_qs(urlparse(link).query)
        self.assertEqual(q["path"], [self.folder])
        self.assertEqual(q["prompt"], [L.one_line("s1-ab12")])
        self.assertTrue(os.path.exists(os.path.join(self.folder, ".codex", "config.toml")))

    def test_codex_cli(self):
        r = L.open_project("codex", self.folder, "s1-ab12", model="gpt-x")
        self.assertTrue(r.ok)
        self.assertEqual(r.how, "codex-terminal")
        argv = self.entries()[0]["argv"]
        self.assertEqual(argv[0], self.fake)
        self.assertEqual(argv[argv.index("-C") + 1], self.folder)
        self.assertEqual(argv[argv.index("-m") + 1], "gpt-x")
        self.assertEqual(argv[-1], L.one_line("s1-ab12"))

    def test_cursor(self):
        clip = mock.Mock(return_value=True)
        r = L.open_project("cursor", self.folder, "s1-ab12", clip=clip)
        self.assertTrue(r.ok)
        self.assertEqual(r.how, "cursor-folder")
        self.assertEqual(self.entries()[0]["argv"], [self.fake, "-n", self.folder])
        clip.assert_called_once_with(L.one_line("s1-ab12"))

    def test_cursor_clip_failure_is_not_fatal(self):
        r = L.open_project("cursor", self.folder, "s1-ab12", clip=mock.Mock(return_value=False))
        self.assertTrue(r.ok)
        self.assertTrue(any("PROMPT.txt" in x for x in r.lines))

    def test_claude(self):
        r = L.open_project("claude", self.folder, "s1-ab12", model="opus")
        self.assertTrue(r.ok)
        self.assertEqual(r.how, "claude-terminal")
        e = self.entries()[0]
        self.assertEqual(e["env"].get("CLAUDE_CODE_DISABLE_AUTO_MEMORY"), "1")
        self.assertEqual(e["argv"][e["argv"].index("--model") + 1], "opus")
        self.assertEqual(e["argv"][-1], L.one_line("s1-ab12"))

    def test_copilot(self):
        r = L.open_project("copilot", self.folder, "s1-ab12")
        self.assertTrue(r.ok)
        self.assertEqual(r.how, "vscode-chat")
        e = self.entries()
        self.assertEqual(e[0]["argv"], [self.fake, "-n", self.folder])
        self.assertEqual(e[1]["argv"], [self.fake, "chat", "-r", "-m", "agent", L.one_line("s1-ab12")])

    def test_missing_app(self):
        for a in AGENTS:
            os.environ["VESPER_LAUNCHER_" + a.upper()] = "none"
            r = L.open_project(a, self.folder, "s1-ab12")
            self.assertFalse(r.ok)
            self.assertEqual(r.how, "")
            self.assertTrue(r.manual)
            self.assertTrue(any(self.folder in x for x in r.manual))
            self.assertTrue(r.lines)
        self.assertEqual(self.entries(), [])

    def test_launcher_path_does_not_exist_no_exception(self):
        del os.environ["VESPER_LAUNCHER_DRYRUN"]
        for a in ("cursor", "copilot", "claude", "codex"):
            os.environ["VESPER_LAUNCHER_" + a.upper()] = os.path.join(self.d, "nothing-here.exe")
            with mock.patch.object(L, "_terminal_available", return_value=False), \
                    mock.patch("subprocess.Popen", side_effect=OSError("boom")), \
                    mock.patch("subprocess.run", side_effect=OSError("boom")):
                r = L.open_project(a, self.folder, "s1-ab12", clip=lambda t: True)
            self.assertFalse(r.ok)
            self.assertTrue(r.manual)

    def test_unknown_agent(self):
        r = L.open_project("nope", self.folder, "s1-ab12")
        self.assertFalse(r.ok)
        self.assertTrue(r.manual)


class Script(Base):
    def test_terminal_script_is_in_temp_not_run_folder(self):
        p = L._write_script(self.folder, {"A": "1"}, [self.fake, "x", "100%"])
        self.addCleanup(os.remove, p)
        self.assertFalse(p.startswith(self.folder))
        self.assertEqual(os.path.dirname(p), tempfile.gettempdir())
        t = open(p, encoding="utf-8", errors="replace").read()
        self.assertIn(self.folder, t)
        self.assertIn("100%%", t)
        self.assertEqual(os.listdir(self.folder), [])


if __name__ == "__main__":
    unittest.main()
