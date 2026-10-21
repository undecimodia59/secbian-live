"""Isolated checks: no host services, USB changes, hostname changes or network."""

import hashlib
import os
from pathlib import Path
import re
import subprocess
import tempfile
import types
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
INCLUDES = ROOT / "config/includes.chroot"
HOOKS = ROOT / "config/hooks/live"


def load_script(relative):
    path = INCLUDES / relative
    module = types.ModuleType(path.name)
    exec(compile(path.read_text(), str(path), "exec"), module.__dict__)
    return module


class HostnameTests(unittest.TestCase):
    def setUp(self):
        self.script = load_script("usr/local/sbin/secbian-random-hostname")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "etc").mkdir()

    def configure(self, hosts):
        (self.root / "etc/hosts").write_text(hosts)
        setter = Mock()
        name = self.script.configure(self.root, setter)
        self.assertRegex(name, r"^sec-[0-9a-f]{8}$")
        setter.assert_called_once_with(name.encode("ascii"))
        self.assertEqual((self.root / "etc/hostname").read_text(), name + "\n")
        return name, (self.root / "etc/hosts").read_text()

    def test_replaces_old_name_and_preserves_localhost(self):
        name, hosts = self.configure("127.0.0.1 localhost\n127.0.1.1 secbian\n::1 localhost\n")
        self.assertEqual(hosts, f"127.0.0.1 localhost\n127.0.1.1\t{name}\n::1 localhost\n")

    def test_appends_missing_mapping_with_missing_final_newline(self):
        name, hosts = self.configure("127.0.0.1 localhost")
        self.assertEqual(hosts, f"127.0.0.1 localhost\n127.0.1.1\t{name}\n")

    def test_does_not_replace_similar_ip(self):
        name, hosts = self.configure("127.0.1.10 other\n")
        self.assertEqual(hosts, f"127.0.1.10 other\n127.0.1.1\t{name}\n")

    def test_handles_empty_hosts(self):
        name, hosts = self.configure("")
        self.assertEqual(hosts, f"127.0.1.1\t{name}\n")

    def test_syscall_failure_is_not_hidden(self):
        (self.root / "etc/hosts").write_text("127.0.0.1 localhost\n")
        with self.assertRaises(PermissionError):
            self.script.configure(self.root, Mock(side_effect=PermissionError))

    def test_read_failure_prevents_hostname_syscall(self):
        setter = Mock()
        with self.assertRaises(FileNotFoundError):
            self.script.configure(self.root, setter)
        setter.assert_not_called()


class UsbTests(unittest.TestCase):
    DEVICE = ('7', '7: block id 1234:5678 name "Keyboard" with-interface 03:01:01')

    def setUp(self):
        self.ui = load_script("usr/local/bin/secbian-usb")
        self.ui.run = Mock(return_value=subprocess.CompletedProcess([], 0, "", ""))
        self.ui.dialog = Mock()

    def test_parser_only_accepts_blocked_numeric_ids(self):
        self.ui.run.return_value.stdout = self.DEVICE[1] + '\n8: allow id 1234:5678\n-1: block fake\n'
        self.assertEqual(self.ui.blocked_devices(), [self.DEVICE])

    def test_backend_failure_is_visible(self):
        self.ui.run.return_value.returncode = 1
        self.assertEqual(self.ui.main(), 1)
        self.ui.dialog.assert_called_once()
        self.assertIn("unavailable", self.ui.dialog.call_args.args[0])

    def test_cancel_never_authorizes(self):
        self.ui.blocked_devices = Mock(return_value=[self.DEVICE])
        self.ui.choose = Mock(return_value=None)
        self.assertEqual(self.ui.main(), 0)
        self.ui.run.assert_not_called()

    def test_cancel_confirmation_closes_menu(self):
        self.ui.blocked_devices = Mock(return_value=[self.DEVICE])
        self.ui.choose = Mock(side_effect=[0, None])
        self.assertEqual(self.ui.main(), 0)
        self.ui.run.assert_not_called()

    def test_keep_blocked_never_authorizes(self):
        self.ui.blocked_devices = Mock(side_effect=[[self.DEVICE], [self.DEVICE]])
        self.ui.choose = Mock(side_effect=[0, 0, None])
        self.assertEqual(self.ui.main(), 0)
        self.ui.run.assert_not_called()

    def test_confirmation_authorizes_only_selected_id_without_permanent_flag(self):
        self.ui.blocked_devices = Mock(side_effect=[[self.DEVICE], [self.DEVICE], []])
        self.ui.choose = Mock(side_effect=[0, 1])
        self.assertEqual(self.ui.main(), 0)
        self.assertEqual(self.ui.run.call_args_list[0].args,
                         ("sudo", "-n", "usbguard", "allow-device", "7"))
        self.assertEqual(self.ui.run.call_count, 2)  # approval and notification

    def test_stale_device_is_not_authorized(self):
        self.ui.blocked_devices = Mock(side_effect=[[self.DEVICE], [], []])
        self.ui.choose = Mock(side_effect=[0, 1])
        self.assertEqual(self.ui.main(), 0)
        self.ui.run.assert_not_called()
        self.assertIn("changed", self.ui.dialog.call_args_list[0].args[0])

    def test_descriptor_controls_are_removed(self):
        self.assertEqual(self.ui.visible('Keyboard\n\x1b\u202eFAKE'), "Keyboard FAKE")

    def test_review_shows_name_identity_and_interfaces(self):
        label, details = self.ui.describe(*self.DEVICE)
        self.assertEqual(label, "Keyboard  [1234:5678]  #7")
        self.assertIn("Interfaces: 03:01:01", details)

    def test_name_cannot_spoof_interface_attribute(self):
        label, details = self.ui.describe('7',
            '7: block id 1234:5678 name "Disk with-interface 08:06:50" with-interface 03:01:01')
        self.assertIn("Interfaces: 03:01:01", details)
        self.assertNotIn("Interfaces: 08:06:50", details)

    def test_rofi_uses_indices_and_escapes_markup(self):
        completed = subprocess.CompletedProcess([], 0, "0\n", "")
        with patch.object(self.ui.subprocess, "run", return_value=completed) as runner:
            self.assertEqual(self.ui.choose(["Device"], "USB", '<b>forged</b>'), 0)
        args = runner.call_args.args[0]
        self.assertIn("-no-markup-rows", args)
        self.assertEqual(args[args.index("-mesg") + 1], "&lt;b&gt;forged&lt;/b&gt;")
        self.assertEqual(args[args.index("-format") + 1], "i")

    def test_invalid_selection_is_rejected(self):
        for value in ["-1", "2", "7: block fake", ""]:
            with self.subTest(value=value), patch.object(
                self.ui.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, value, "")
            ):
                self.assertIsNone(self.ui.choose(["Device"], "USB"))


class BootTests(unittest.TestCase):
    def test_failsafe_retains_all_normal_arguments(self):
        output = subprocess.check_output([
            "sh", "-c", '. "$1"; printf "%s\\n%s\\n" "$LB_BOOTAPPEND_LIVE" "$LB_BOOTAPPEND_LIVE_FAILSAFE"',
            "sh", str(ROOT / "config/binary")
        ], text=True)
        normal, failsafe = output.splitlines()
        self.assertTrue(set(normal.split()) <= set(failsafe.split()))
        self.assertIn("dm-verity-oncorruption=panic", normal.split())

    @unittest.skipUnless(Path("/usr/sbin/veritysetup").exists(), "veritysetup not installed")
    def test_binary_hook_rejects_corruption_and_missing_metadata(self):
        hook = HOOKS / "070-verify-rootfs.hook.binary"
        env = dict(os.environ, PATH="/usr/sbin:" + os.environ.get("PATH", ""))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "live").mkdir()
            image = root / "live/filesystem.squashfs"
            image.write_bytes(os.urandom(64 * 4096))
            tree = Path(str(image) + ".verity")
            result = subprocess.run(["/usr/sbin/veritysetup", "format", str(image), str(tree)],
                                    text=True, capture_output=True, check=True)
            digest = re.search(r"Root hash:\s+([0-9a-f]+)", result.stdout).group(1)
            hashfile = Path(str(image) + ".roothash")
            hashfile.write_text(digest)

            def check():
                return subprocess.run(["sh", str(hook)], cwd=root, env=env, capture_output=True).returncode

            self.assertEqual(check(), 0)
            with image.open("r+b") as file:
                first = file.read(1)
                file.seek(0)
                file.write(bytes([first[0] ^ 1]))
            self.assertNotEqual(check(), 0)
            hashfile.write_text("")
            self.assertNotEqual(check(), 0)
            hashfile.write_text(digest)
            tree.unlink()
            self.assertNotEqual(check(), 0)


class JwtTests(unittest.TestCase):
    def test_existing_checkout_must_be_clean_including_ignored_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checkout = root / "jwt"
            checkout.mkdir()
            bindir = root / "bin"
            bindir.mkdir()
            env = dict(os.environ, GIT_AUTHOR_NAME="Test", GIT_AUTHOR_EMAIL="test@example.invalid",
                       GIT_COMMITTER_NAME="Test", GIT_COMMITTER_EMAIL="test@example.invalid")

            def git(*args):
                return subprocess.check_output(["git", "-C", str(checkout), *args], env=env,
                                               text=True, stderr=subprocess.DEVNULL).strip()

            git("init", "-q")
            program = checkout / "jwt_tool.py"
            program.write_text("#!/usr/bin/python3\n")
            program.chmod(0o644)
            (checkout / ".gitignore").write_text("ignored\n")
            git("add", ".")
            git("commit", "-qm", "fixture")
            commit = git("rev-parse", "HEAD")
            script = (HOOKS / "030-jwt-tool.hook.chroot").read_text()
            script = re.sub(r'JWT_TOOL_COMMIT="[0-9a-f]+"', f'JWT_TOOL_COMMIT="{commit}"', script)
            script = script.replace("/opt/jwt_tool", str(checkout)).replace("/usr/local/bin", str(bindir))
            # Dependency imports are unrelated to checkout integrity in this test.
            script = re.sub(r'python3 -c ".*?" 2>/dev/null', "true", script)
            hook = root / "hook"
            hook.write_text(script)

            def check():
                return subprocess.run(["sh", str(hook)], env=env, capture_output=True).returncode

            self.assertEqual(check(), 0)
            # The hook's chmod must not make a clean incremental build fail.
            self.assertEqual(check(), 0)
            program.write_text("tampered\n")
            self.assertNotEqual(check(), 0)
            git("checkout", "--", "jwt_tool.py")
            (checkout / "ignored").write_text("untracked code\n")
            self.assertNotEqual(check(), 0)


class NucleiTests(unittest.TestCase):
    def test_hook_replaces_existing_binary_and_refuses_bad_download(self):
        import zipfile
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bindir = root / "bin"
            bindir.mkdir()
            destination = root / "installed"
            destination.mkdir()
            archive = root / "nuclei.zip"
            with zipfile.ZipFile(archive, "w") as zipfile_:
                zipfile_.writestr("nuclei", "#!/bin/sh\necho 'Nuclei Engine Version: v3.11.1'\n")
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            downloader = bindir / "wget"
            downloader.write_text('#!/bin/sh\ncp "$CACHED_ARCHIVE" "$3"\n')
            downloader.chmod(0o755)
            binary = destination / "nuclei"
            binary.write_text("#!/bin/sh\nexit 99\n")
            binary.chmod(0o755)
            script = (HOOKS / "040-nuclei.hook.chroot").read_text()
            script = re.sub(r'NUCLEI_SHA256="[0-9a-f]+"', f'NUCLEI_SHA256="{digest}"', script)
            script = script.replace("/usr/local/bin", str(destination))
            hook = root / "hook"
            hook.write_text(script)
            env = dict(os.environ, PATH=str(bindir) + ":" + os.environ.get("PATH", ""),
                       CACHED_ARCHIVE=str(archive))
            result = subprocess.run(["sh", str(hook)], env=env, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Nuclei Engine Version", binary.read_text())
            good = binary.read_bytes()
            archive.write_bytes(b"corrupted download")
            result = subprocess.run(["sh", str(hook)], env=env, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(binary.read_bytes(), good)


if __name__ == "__main__":
    unittest.main()
