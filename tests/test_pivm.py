"""Host-side contract tests. No real VMs, keys, network or credentials used."""
import contextlib
import json
import importlib.machinery
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
loader = importlib.machinery.SourceFileLoader("pivm", str(ROOT / "bin/pivm"))
spec = importlib.util.spec_from_loader(loader.name, loader)
pivm = importlib.util.module_from_spec(spec)
loader.exec_module(pivm)


class LauncherTests(unittest.TestCase):
    def test_sync_cli_explicit_directory_and_dry_run(self):
        args = pivm.parser().parse_args(
            ["sync", "test", "--directory", "/project", "--dry-run"])
        self.assertEqual(args.action, "sync")
        self.assertEqual(args.name, "test")
        self.assertEqual(args.directory, "/project")
        self.assertTrue(args.dry_run)

    def test_open_backend_is_selectable_and_defaults_to_core(self):
        self.assertEqual(pivm.parser().parse_args(["open", "."]).backend, "core")
        self.assertEqual(pivm.parser().parse_args(
            ["open", ".", "--backend", "core"]).backend, "core")

    def test_core_registration_uses_streaming_msb_transport(self):
        with patch.object(pivm, "run") as run:
            pivm.register_core_machine("/usr/bin/msb", "dev-test")
        argv = run.call_args.args
        self.assertEqual(argv[:4], ("hc", "machine", "add", "--install"))
        self.assertEqual(argv[4], "--via")
        self.assertIn("exec --stream --user dev dev-test -- sh -lc", argv[5])
        self.assertEqual(argv[-2:], ("--name", "pivm-dev-test"))

    def invoke(self, argv, env=None):
        calls = []
        with patch.object(pivm, "run", side_effect=lambda *a, **kw: calls.append((a, kw))), \
             patch.object(pivm, "executable", return_value="/opt/msb"), \
             patch.dict(os.environ, env or {}, clear=True), \
             patch("sys.argv", ["pivm", *argv]), contextlib.redirect_stdout(io.StringIO()):
            pivm.main()
        return calls

    def test_create_private_no_mount_no_raw_secrets(self):
        calls = self.invoke(["create", "test", "--openai", "--github"],
                            {"OPENAI_API_KEY": "not-a-real-key", "GH_TOKEN": "not-a-real-token"})
        argv = calls[0][0]
        self.assertIn("OPENAI_API_KEY:headers=[authorization]@api.openai.com", argv)
        self.assertIn("GH_TOKEN:headers=[authorization]@github.com,api.github.com", argv)
        self.assertNotIn("not-a-real-key", str(calls))
        self.assertNotIn("not-a-real-token", str(calls))
        self.assertNotIn("--mount-dir", argv)
        self.assertNotIn("--replace", argv)
        self.assertIn("restricted", argv)

    def test_no_secrets_without_opt_in(self):
        calls = self.invoke(["create", "test"], {"OPENAI_API_KEY": "not-a-real-key"})
        self.assertNotIn("--secret", calls[0][0])

    def test_missing_secret_fails_before_vm_creation(self):
        with self.assertRaises(ValueError):
            self.invoke(["create", "test", "--openai"])

    def test_invalid_origin_fails_before_create(self):
        with self.assertRaises(ValueError):
            self.invoke(["create", "test", "--import", ".", "--origin", "https://token@github.com/a/b"])

    def test_reject_url_credentials_and_non_github(self):
        for url in ["git@github.com:a/b", "https://token@github.com/a/b",
                    "https://evil.example/a/b", "https://github.com/a/b?token=secret",
                    "http://github.com/a/b", "https://github.com:443/a/b"]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                pivm.github_url(url)
        self.assertEqual(pivm.github_url("https://github.com/a/b.git"), "https://github.com/a/b.git")

    def test_reject_name_injection(self):
        for name in ["--replace", "x;touch-pwned", "../other", "Has Spaces"]:
            with self.assertRaises(Exception):
                pivm.name_arg(name)

    def test_ssh_transport_is_host_side_and_no_forward_agent(self):
        with patch.dict(os.environ, {"MSB_HOME": "/tmp/msb home"}):
            stanza = pivm.ssh_stanza("/opt/msb", "test", Path("/tmp/key"))
        self.assertIn("serve test --stdio --no-inactivity-timeout", stanza)
        self.assertIn("'MSB_HOME=/tmp/msb home'", stanza)
        self.assertIn("User dev", stanza)
        self.assertIn("ForwardAgent no", stanza)
        self.assertNotIn("StrictHostKeyChecking no", stanza)

    def test_start_is_idempotent(self):
        calls = self.invoke(["start", "test"])
        self.assertEqual(calls[0][0], ("/opt/msb", "ping", "test"))
        self.assertEqual(len(calls), 1)
        with patch.object(pivm, "run", side_effect=[
            subprocess.CalledProcessError(1, ["msb", "ping"]), None
        ]) as run:
            pivm.ensure_running("/opt/msb", "test")
        self.assertEqual(run.call_args.args, ("/opt/msb", "start", "test"))

    def test_reject_unsupported_ssh_paths(self):
        for value in ['/tmp/a"b', "/tmp/a\nb", "/tmp/a\\b"]:
            with self.assertRaises(ValueError):
                pivm.ssh_stanza("/opt/msb", "test", Path(value))

    def test_atomic_config_write_preserves_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "real-config"
            target.write_text("old")
            link = Path(tmp) / "config"
            link.symlink_to(target)
            pivm.atomic_write(link, "new")
            self.assertTrue(link.is_symlink())
            self.assertEqual(target.read_text(), "new")
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)

    def test_setup_ssh_idempotent_dedicated_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / ".ssh").mkdir()
            original = "Host *\n    ServerAliveInterval 30\n"
            (home / ".ssh/config").write_text(original)
            calls = []
            with patch.object(Path, "home", return_value=home), \
                 patch.object(pivm, "run", side_effect=lambda *a, **k: calls.append(a)), \
                 patch.object(pivm, "inspect_vm", return_value={}), \
                 patch.object(pivm, "trust_local_host_key"), \
                 contextlib.redirect_stdout(io.StringIO()):
                pivm.setup_ssh("/opt/msb", "test")
                pivm.setup_ssh("/opt/msb", "test")
                pivm.setup_ssh("/opt/msb", "second")
            config = (home / ".ssh/config").read_text()
            self.assertEqual(config.count("Include "), 1)
            self.assertIn('ssh/*.conf"', config)
            self.assertTrue((home / ".local/state/pivm/ssh/test.conf").is_file())
            self.assertTrue((home / ".local/state/pivm/ssh/second.conf").is_file())
            self.assertTrue(config.endswith(original))
            self.assertEqual((home / ".local/state/pivm/ssh/ssh-config.before-pivm").read_text(), original)
            self.assertTrue(any("authorize" in c for c in calls))

    def test_ssh_include_migrates_owned_entries_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            state = home / ".local/state/pivm/ssh"
            state.mkdir(parents=True)
            (home / ".ssh").mkdir()
            unrelated = ('Include "/other/ssh/keep.conf"\n'
                         'Host compute\n    HostName example.org\n')
            original = (f'Include "{state}/old-vm.conf"\n\n'
                        f'Include "{state}/another-vm.conf"\n\n'
                        + unrelated)
            main = home / ".ssh/config"
            main.write_text(original)
            with patch.object(Path, "home", return_value=home):
                pivm.ensure_ssh_include(state)
                first = main.read_text()
                pivm.ensure_ssh_include(state)
            self.assertEqual(main.read_text(), first)
            self.assertEqual(first, f'Include "{state}/*.conf"\n\n' + unrelated)
            self.assertEqual((state / "ssh-config.before-pivm").read_text(), original)

    def test_default_creates_mounted_vm_and_registers_sidebar(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "project"
            project.mkdir()
            calls = []
            missing = subprocess.CalledProcessError(1, "inspect", stderr="sandbox not found: test")
            with patch.object(Path, "home", return_value=root), \
                 patch.object(Path, "cwd", return_value=project), \
                 patch.object(pivm, "inspect_vm", side_effect=missing), \
                 patch.object(pivm, "setup_ssh") as ssh, \
                 patch.object(pivm, "ensure_project_workspace") as workspace, \
                 patch.object(pivm, "register_core_machine") as register, \
                 patch.object(pivm, "project_mounts", return_value=[project]), \
                 patch.object(pivm, "run", side_effect=lambda *a, **kw: calls.append((a, kw))), \
                 patch.object(pivm, "executable", return_value="/opt/msb"), \
                 patch.dict(os.environ, {"OPENAI_API_KEY": "dummy-never-in-argv"}, clear=True), \
                 patch("sys.argv", ["pivm", str(project)]), \
                 contextlib.redirect_stdout(io.StringIO()):
                pivm.main()
            create = next(a for a, _ in calls if a[1] == "create")
            self.assertIn(f"{project}:{project}:rw,uid=1000,gid=1000", create)
            self.assertNotIn("dummy-never-in-argv", str(calls))
            self.assertIn("--secret", create)
            self.assertNotIn("--replace", create)
            ssh.assert_not_called()
            workspace.assert_not_called()
            register.assert_called_once_with("/opt/msb", pivm.project_name(project))
            self.assertFalse(any(a[:2] == ("herdr", "--remote") for a, _ in calls))
            self.assertFalse(any("bundle" in a for a, _ in calls))

    def test_attach_opens_dedicated_ui(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            args = pivm.parser().parse_args(
                ["open", str(root), "--attach", "--backend", "legacy"])
            with patch.object(Path, "home", return_value=root), \
                 patch.object(pivm, "inspect_vm", return_value={
                    "config": {"labels": {"pivm.project": str(root),
                                          "pivm.backend": "legacy"}}}), \
                 patch.object(pivm, "ensure_running"), \
                 patch.object(pivm, "setup_ssh"), \
                 patch.object(pivm, "ensure_project_workspace"), \
                 patch.object(pivm, "register_project_machine"), \
                 patch.object(pivm, "run") as run, \
                 contextlib.redirect_stdout(io.StringIO()):
                pivm.open_project("/opt/msb", args)
            self.assertEqual(run.call_count, 1)
            self.assertEqual(run.call_args.args, ("herdr", "--remote",
                             f"pivm-{pivm.project_name(root)}", "--session", "agents"))

    def test_project_workspace_created_when_restored_session_is_in_home(self):
        response = subprocess.CompletedProcess([], 0, stdout=json.dumps({"result": {
            "panes": [{"cwd": "/home/dev", "workspace_id": "w5"}]}}))
        with patch.object(pivm, "guest", return_value=response) as guest:
            pivm.ensure_project_workspace("/opt/msb", "test", Path("/project"))
        self.assertEqual(guest.call_args.args, (
            "/opt/msb", "test", "herdr", "--session", "agents", "workspace",
            "create", "--cwd", Path("/project"), "--label", "project", "--focus"))

    def test_registration_keeps_original_profile_after_server_bootstrap(self):
        profiles = [{"id": "aaaa", "target": "pivm-test", "session": "agents",
                     "enabled": True}]
        with patch.object(pivm, "run", side_effect=[
                subprocess.CompletedProcess([], 0, stdout=json.dumps(profiles)),
                subprocess.CompletedProcess([], 0, stdout="Saved SSH machine bbbb.\n"),
                subprocess.CompletedProcess([], 0)]) as run:
            pivm.register_project_machine("test", Path("/project"))
        self.assertEqual(run.call_args.args, ("herdr", "machine", "remove", "bbbb"))

    def test_first_registration_is_preserved(self):
        with patch.object(pivm, "run", side_effect=[
                subprocess.CompletedProcess([], 0, stdout="[]"),
                subprocess.CompletedProcess([], 0, stdout="Saved SSH machine bbbb.\n")
                ]) as run, contextlib.redirect_stdout(io.StringIO()):
            pivm.register_project_machine("test", Path("/project"))
        self.assertEqual(run.call_count, 2)

    def test_existing_project_workspace_is_focused_not_duplicated(self):
        response = subprocess.CompletedProcess([], 0, stdout=json.dumps({"result": {
            "panes": [{"cwd": "/project", "workspace_id": "w8"}]}}))
        with patch.object(pivm, "guest", return_value=response) as guest:
            pivm.ensure_project_workspace("/opt/msb", "test", Path("/project"))
        self.assertEqual(guest.call_count, 2)
        self.assertEqual(guest.call_args.args, (
            "/opt/msb", "test", "herdr", "--session", "agents", "workspace", "focus", "w8"))

    def test_existing_project_reused_without_creation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            args = pivm.parser().parse_args(
                ["open", str(root), "--prepare-only", "--backend", "legacy"])
            with patch.object(Path, "home", return_value=root), \
                 patch.object(pivm, "inspect_vm", return_value={
                    "config": {"labels": {"pivm.project": str(root),
                                          "pivm.backend": "legacy"}}}), \
                 patch.object(pivm, "ensure_running") as start, \
                 patch.object(pivm, "setup_ssh") as ssh, \
                 patch.object(pivm, "run") as run, \
                 contextlib.redirect_stdout(io.StringIO()):
                pivm.open_project("/opt/msb", args)
            start.assert_called_once()
            ssh.assert_called_once()
            run.assert_not_called()

    def test_setup_missing_vm_does_not_modify_ssh(self):
        with patch.object(pivm, "inspect_vm", side_effect=subprocess.CalledProcessError(1, "inspect")), \
             patch.object(pivm, "ssh_paths") as paths:
            with self.assertRaisesRegex(ValueError, "does not exist"):
                pivm.setup_ssh("/opt/msb", "missing")
            paths.assert_not_called()

    def test_bundle_excludes_dirty_untracked_and_host_git_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            def git(*args):
                return subprocess.run(["git", "-C", str(repo), *args], check=True,
                                      capture_output=True)
            git("init")
            git("config", "user.name", "Test")
            git("config", "user.email", "test@example.invalid")
            (repo / "tracked").write_text("committed")
            git("add", "tracked")
            git("commit", "-m", "Initial")
            (repo / "tracked").write_text("dirty")
            (repo / ".env").write_text("not-real-secret")
            git("config", "credential.helper", "host-only-helper")
            captured = {}
            real_run = pivm.run
            def fake_run(*args, **kwargs):
                if args[0] == "git":
                    return real_run(*args, **kwargs)
                if args[1] == "copy":
                    target = Path(tmp) / "guest-clone"
                    subprocess.run(["git", "clone", str(args[2]), str(target)],
                                   check=True, capture_output=True)
                    captured["target"] = target
            with patch.object(pivm, "run", side_effect=fake_run), \
                 contextlib.redirect_stdout(io.StringIO()):
                pivm.import_repo("/opt/msb", "test", repo)
            target = captured["target"]
            self.assertEqual((target / "tracked").read_text(), "committed")
            self.assertFalse((target / ".env").exists())
            self.assertNotIn("host-only-helper", (target / ".git/config").read_text())


if __name__ == "__main__":
    unittest.main()
