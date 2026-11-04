"""Check rebuild orchestration without running live-build or modifying the host."""

import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class BuildEntrypointTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="secbian-build-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        self.tools = self.root / "tools"
        self.tools.mkdir()
        self.script = self.repo / "scripts/build-live.sh"
        self.write(self.script, (ROOT / "scripts/build-live.sh").read_text())
        for name in ["common", "bootstrap", "chroot", "binary", "source"]:
            self.write(self.repo / "config" / name, "# fixture\n")
        for name in ["chroot", "binary"]:
            self.write(self.repo / f"config/archives/mullvad.key.{name}", "fixture key\n")
        self.binary = self.repo / "config/includes.chroot/usr/local/bin/httpied"
        self.write(self.binary, "fixture binary\n")
        checksum = hashlib.sha256(self.binary.read_bytes()).hexdigest()
        self.write(self.repo / "config/includes.chroot/usr/share/doc/httpied/SHA256SUMS",
                   checksum + "  /usr/local/bin/httpied\n")
        self.calls = self.root / "calls"
        self.env = dict(os.environ, PATH=str(self.tools), SECBIAN_TEST_CALLS=str(self.calls))
        self.command("id", 'printf "%s\\n" "${SECBIAN_TEST_UID:-0}"')
        self.command("veritysetup", "exit 0")
        self.command("lb", 'printf "%s:%s\\n" "$1" "$PWD" >> "$SECBIAN_TEST_CALLS"\n'
                           '[ "$1" != "${SECBIAN_TEST_FAIL_STEP:-}" ]')
        for name in ["dirname", "sed", "sha256sum"]:
            (self.tools / name).symlink_to(shutil.which(name))

    @staticmethod
    def write(path, contents):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents)

    def command(self, name, body):
        path = self.tools / name
        path.write_text("#!/bin/sh\n" + body + "\n")
        path.chmod(0o755)

    def run_script(self):
        # Deliberately start outside the fixture repository.
        return subprocess.run(["/bin/sh", str(self.script)], cwd=self.root, env=self.env,
                              text=True, capture_output=True)

    def steps(self):
        return self.calls.read_text().splitlines() if self.calls.exists() else []

    def test_cleans_all_stages_before_config_and_build_without_purging_cache(self):
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.steps(), [f"{step}:{self.repo}" for step in ["clean", "config", "build"]])

    def test_clean_failure_prevents_config_and_build(self):
        self.env["SECBIAN_TEST_FAIL_STEP"] = "clean"
        self.assertNotEqual(self.run_script().returncode, 0)
        self.assertEqual(self.steps(), [f"clean:{self.repo}"])

    def test_config_failure_prevents_build(self):
        self.env["SECBIAN_TEST_FAIL_STEP"] = "config"
        self.assertNotEqual(self.run_script().returncode, 0)
        self.assertEqual(self.steps(), [f"clean:{self.repo}", f"config:{self.repo}"])

    def test_nonroot_refused_before_clean(self):
        self.env["SECBIAN_TEST_UID"] = "1000"
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("sudo", result.stderr)
        self.assertEqual(self.steps(), [])

    def test_missing_prerequisite_refused_before_clean(self):
        (self.tools / "veritysetup").unlink()
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("veritysetup", result.stderr)
        self.assertEqual(self.steps(), [])

    def test_missing_source_key_refused_before_clean(self):
        (self.repo / "config/archives/mullvad.key.binary").unlink()
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("mullvad.key.binary", result.stderr)
        self.assertEqual(self.steps(), [])

    def test_modified_binary_refused_before_clean(self):
        self.binary.write_bytes(b"modified")
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.steps(), [])


class SetupPreflightTests(unittest.TestCase):
    def check(self, missing):
        with tempfile.TemporaryDirectory(prefix="secbian-package-test-") as directory:
            root = Path(directory)
            hook = (ROOT / "config/hooks/live/010-setup.hook.chroot").read_text()
            hook = hook.split("# Configure the image's firewall offline.", 1)[0]
            hook += '\nprintf "preflight passed\\n"\n'
            path = root / "hook.sh"
            path.write_text(hook)
            for command in ["ufw", "i3", "lightdm", "shred", "dpkg-query"]:
                if command in missing:
                    continue
                program = root / command
                program.write_text("#!/bin/sh\nexit 0\n")
                program.chmod(0o755)
            return subprocess.run(["/bin/sh", str(path)], env=dict(os.environ, PATH=str(root)),
                                  text=True, capture_output=True)

    def test_actual_reported_missing_packages_are_named_together(self):
        result = self.check({"ufw", "i3", "lightdm"})
        self.assertNotEqual(result.returncode, 0)
        for name in ["ufw", "i3", "lightdm"]:
            self.assertIn(f"required command missing from PATH: {name}", result.stderr)
        self.assertIn("package: i3-wm", result.stderr)
        self.assertIn("build-live.sh", result.stderr)

    def test_existing_commands_pass(self):
        result = self.check(set())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("preflight passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
