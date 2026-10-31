"""All sync tests are local fixtures/mocks; no real VM/network/auth access."""
import base64
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "pivm_sync", Path(__file__).resolve().parents[1] / "bin/pivm_sync.py")
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.agent = self.home / ".pi/agent"
        self.agent.mkdir(parents=True)
        self.env = patch.dict(os.environ, {"PI_CODING_AGENT_DIR": str(self.agent)})
        self.env.start()
        self.addCleanup(self.env.stop)

    def put(self, name, data):
        path = self.agent / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data)
        return path

    def settings(self, data):
        self.put("settings.json", json.dumps(data))

    def build(self):
        with patch.object(sync.subprocess, "run", return_value=subprocess.CompletedProcess(
                [], 1, "", "")):
            return sync.build_payload(self.home)

    def payload(self, files=None, settings=None):
        return {"files": {k: base64.b64encode(v.encode()).decode()
                          for k, v in (files or {}).items()},
                "settings": settings or {}, "identity": {"user.name": "VM Author"}}

    def apply(self, payload):
        with patch.object(Path, "home", return_value=self.home), \
                patch("subprocess.run") as run, contextlib.redirect_stdout(io.StringIO()):
            sync.guest_apply(payload)
        return run

    def test_preferences_only_no_auth_sessions_or_arbitrary_extension_config(self):
        self.settings({"defaultModel": "model", "theme": "dark", "sessionDir": "/host",
                       "shellCommandPrefix": "secret", "httpProxy": "credential",
                       "arbitraryExtension": {"token": "secret"}})
        self.put("auth.json", "not even JSON")
        self.put("sessions/test.json", "never read")
        original = Path.read_bytes
        def guard(path):
            self.assertNotIn("auth.json", str(path))
            self.assertNotIn("sessions", path.parts)
            return original(path)
        with patch.object(Path, "read_bytes", guard):
            payload = self.build()
        self.assertEqual(payload["settings"]["defaultModel"], "model")
        self.assertNotIn("sessionDir", payload["settings"])
        self.assertNotIn("arbitraryExtension", payload["settings"])
        self.assertNotIn("secret", json.dumps(payload))

    def test_resources_symlinks_secrets_and_node_modules_skipped(self):
        self.put("skills/tool/SKILL.md", "skill")
        self.put("skills/tool/.env", "secret")
        self.put("skills/tool/node_modules/a.js", "dependency")
        target = self.put("private.txt", "hidden")
        (self.agent / "skills/tool/link").symlink_to(target)
        payload = self.build()
        self.assertEqual(set(payload["files"]), {"skills/tool/SKILL.md"})

    def test_absolute_reference_relocated_and_exclusion_preserved(self):
        external = self.home / "outside.md"
        external.write_text("prompt")
        self.settings({"prompts": [str(external)],
                       "extensions": ["-extensions/disabled.ts", "-builtin:mcp"]})
        payload = self.build()
        ref = payload["settings"]["prompts"][0]
        self.assertTrue(ref.startswith("./prompts/pivm-"))
        self.assertIn(ref[2:], payload["files"])
        self.assertEqual(payload["settings"]["extensions"],
                         ["-./extensions/disabled.ts", "-builtin:mcp"])

    def test_npm_pins_installed_version_and_git_keeps_filters(self):
        self.put("npm/node_modules/@test/plugin/package.json", '{"version":"2.3.4"}')
        self.settings({"packages": [
            {"source": "npm:@test/plugin@latest", "skills": [], "extensions": ["x.ts"]},
            "npm:missing", "./local", "git:github.com/a/b",
            "https://user:password@host/repo"]})
        payload = self.build()
        self.assertEqual(payload["settings"]["packages"], [
            {"source": "npm:@test/plugin@2.3.4", "skills": [], "extensions": ["x.ts"]},
            "git:github.com/a/b"])
        self.assertFalse(any("node_modules" in p for p in payload["files"]))

    def test_dry_run_no_guest_calls_and_prints_plan(self):
        self.put("prompts/a.md", "hello")
        out = io.StringIO()
        with patch.object(sync.subprocess, "run", return_value=subprocess.CompletedProcess(
                [], 1, "", "")) as run, contextlib.redirect_stdout(out):
            sync.sync("/bin/msb", "vm", self.home, dry_run=True)
        self.assertTrue(all(c.args[0][0] == "git" for c in run.call_args_list))
        self.assertIn("prompts/a.md", out.getvalue())

    def test_transport_uses_json_stdin_and_argument_arrays(self):
        payload = self.payload()
        with patch.object(sync, "build_payload", return_value=payload), \
                patch.object(sync.subprocess, "run") as run:
            sync.sync("/bin/msb", "vm; echo bad", self.home)
        args, kwargs = run.call_args
        self.assertEqual(args[0][:5], ["/bin/msb", "exec", "vm; echo bad", "--", "python3"])
        self.assertEqual(json.loads(kwargs["input"]), payload)
        self.assertNotIn("shell", kwargs)

    def test_guest_merge_backup_and_safe_pruning(self):
        self.settings({"theme": "light", "guestOnly": 1})
        self.put("auth.json", "guest credential sentinel")
        self.put("sessions/keep", "session sentinel")
        self.apply(self.payload({"prompts/a.md": "one", "prompts/b.md": "one"},
                                {"theme": "dark"}))
        self.put("prompts/b.md", "guest edit")
        self.apply(self.payload({"prompts/new.md": "two"}, {"quietStartup": True}))
        self.assertFalse((self.agent / "prompts/a.md").exists())
        self.assertEqual((self.agent / "prompts/b.md").read_text(), "guest edit")
        result = json.loads((self.agent / "settings.json").read_text())
        self.assertEqual(result, {"guestOnly": 1, "quietStartup": True})
        self.assertEqual((self.agent / "auth.json").read_text(), "guest credential sentinel")
        self.assertEqual((self.agent / "sessions/keep").read_text(), "session sentinel")
        self.assertTrue(list((self.agent / ".pivm-sync-backups").glob("*/settings.json")))

    def test_guest_symlink_and_manifest_traversal_rejected(self):
        outside = self.home / "outside"
        outside.mkdir()
        (self.agent / "prompts").symlink_to(outside)
        with self.assertRaises(ValueError):
            self.apply(self.payload({"prompts/a.md": "bad"}))
        self.assertEqual(list(outside.iterdir()), [])
        (self.agent / "prompts").unlink()
        self.put(".pivm-sync.json", json.dumps({"files": {"../auth.json": "hash"}}))
        with self.assertRaises(ValueError):
            self.apply(self.payload())

    def test_guest_package_install_identity_scoped_global_preserves_helpers(self):
        run = self.apply(self.payload(settings={"packages": [
            {"source": "npm:test@1.2.3", "skills": []}]}))
        calls = [call.args[0] for call in run.call_args_list]
        self.assertIn(["pi", "install", "npm:test@1.2.3"], calls)
        self.assertIn(["git", "config", "--global", "user.name", "VM Author"], calls)
        self.assertIn(["git", "config", "--global", "commit.gpgsign", "false"], calls)
        self.assertIn(["git", "config", "--global", "user.useConfigOnly", "true"], calls)
        self.assertNotIn("credential", str(calls))

    def test_modified_destination_backed_up_before_overwrite(self):
        self.put("prompts/a.md", "guest original")
        self.apply(self.payload({"prompts/a.md": "host version"}))
        backups = list((self.agent / ".pivm-sync-backups").glob("*/prompts/a.md"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), "guest original")

    def test_executable_resource_bit_preserved_without_world_permissions(self):
        script = self.put("skills/tool/run.sh", "#!/bin/sh\ntrue\n")
        script.chmod(0o755)
        payload = self.build()
        self.assertEqual(payload["executable_files"], ["skills/tool/run.sh"])
        self.apply(payload)
        self.assertEqual(script.stat().st_mode & 0o777, 0o700)

    def test_failed_install_restores_merged_settings_without_manifest_commit(self):
        self.settings({"guestOnly": True})
        payload = self.payload(settings={"theme": "dark", "packages": ["npm:test@1.2.3"]})
        with patch.object(Path, "home", return_value=self.home), \
                patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, ["pi"])):
            with self.assertRaises(subprocess.CalledProcessError):
                sync.guest_apply(payload)
        self.assertEqual(json.loads((self.agent / "settings.json").read_text()),
                         {"guestOnly": True, **payload["settings"]})
        self.assertFalse((self.agent / ".pivm-sync.json").exists())


if __name__ == "__main__":
    unittest.main()
