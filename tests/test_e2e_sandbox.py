"""Checks of the e2e script's sandbox and environment helpers. No agent, no tokens."""
import os, shutil, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import e2e_agent as e  # noqa: E402


class AgentEnv(unittest.TestCase):
    def test_allowlist_drops_password_and_credentials(self):
        env = {"PATH": "/bin", "HOME": "/h", "LC_ALL": "C", "VESPER_PART4_PW": "pw", "AWS_SECRET_ACCESS_KEY": "x",
               "GITHUB_TOKEN": "t", "ANTHROPIC_API_KEY": "k", "CLAUDE_CODE_OAUTH_TOKEN": "o", "VESPER_WS_HOME": "/w"}
        sb = e.agent_env(env, True)
        self.assertEqual(sorted(sb), ["CLAUDE_CODE_OAUTH_TOKEN", "HOME", "LC_ALL", "PATH", "VESPER_WS_HOME"])
        self.assertNotIn("ANTHROPIC_API_KEY", sb)
        plain = e.agent_env(env, False)
        for bad in ("VESPER_PART4_PW", "AWS_SECRET_ACCESS_KEY", "GITHUB_TOKEN"):
            self.assertNotIn(bad, plain)
        self.assertIn("ANTHROPIC_API_KEY", plain)


class BwrapArgs(unittest.TestCase):
    def test_masks_come_before_binds_and_only_run_folder_is_rw(self):
        env = {"HOME": "/tmp/o/agent-home", "PATH": os.environ.get("PATH", "")}
        a = e.bwrap_args(["true"], "/tmp/o/home/runs/r1", env, real_home="/home/u")
        self.assertEqual(a[:4], ["bwrap", "--ro-bind", "/", "/"])
        masks = [a[i + 1] for i, x in enumerate(a) if x == "--tmpfs"]
        self.assertIn("/tmp", masks)
        self.assertIn("/home", masks)
        binds = [a[i + 1] for i, x in enumerate(a) if x == "--bind"]
        self.assertEqual(sorted(binds), ["/tmp/o/agent-home", "/tmp/o/home/runs/r1"])
        self.assertLess(max(i for i, x in enumerate(a) if x == "--tmpfs"), min(i for i, x in enumerate(a) if x == "--bind"))
        self.assertNotIn("/tmp/o", binds)

    def test_sandbox_needs_out_under_tmp(self):
        if sys.platform.startswith("linux") and shutil.which("bwrap"):
            with self.assertRaises(SystemExit):
                e.require_sandbox("/var/e2e")
        else:
            with self.assertRaises(SystemExit):
                e.require_sandbox("/tmp/o")


@unittest.skipUnless(sys.platform.startswith("linux") and shutil.which("bwrap"), "needs Linux with bwrap")
class RealSandbox(unittest.TestCase):
    def test_registry_and_log_are_invisible(self):
        out = tempfile.mkdtemp(dir="/tmp")
        os.makedirs(out + "/home/runs/r1")
        os.makedirs(out + "/agent-home")
        open(out + "/home/registry.json", "w").write('{"runs": {}}')
        open(out + "/e2e.log", "w").close()
        env = {"HOME": out + "/agent-home", "PATH": os.environ["PATH"]}
        e.sandbox_selfcheck(out, out + "/home/runs/r1", env)   # raises SystemExit on a leak


if __name__ == "__main__":
    unittest.main()
