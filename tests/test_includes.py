"""Run the include hook against disposable source and image directories."""

from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "config/hooks/live/005-includes.hook.chroot"


class IncludesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="secbian-includes-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = self.root / "config"
        self.image = self.root / "image"
        self.base = self.config / "includes.chroot"
        self.overlay = self.config / "includes.chroot_after_packages"
        self.base.mkdir(parents=True)
        self.overlay.mkdir()
        self.image.mkdir()
        script = HOOK.read_text()
        required = script.split("for _FILE in \\\n", 1)[1].split("\ndo\n", 1)[0]
        self.required = [line.strip().rstrip("\\").strip().lstrip("/")
                         for line in required.splitlines() if line.strip()]
        for relative in self.required:
            self.write(self.base / relative, "base\n")
        self.apt_key = self.image / "etc/apt/trusted.gpg.d/mullvad.key.chroot.asc"
        self.write(self.apt_key, "test chroot key\n")
        # Rewrite only the hook's source/copy destination and absolute image
        # paths. All file operations then stay inside the temporary fixture.
        script = script.replace("/live-build/config", str(self.config))
        script = script.replace('cp -a "${_SRC}/." /',
                                'cp -a "${_SRC}/." "' + str(self.image) + '/"')
        script = script.replace("/etc/", str(self.image) + "/etc/")
        script = script.replace("/usr/", str(self.image) + "/usr/")
        self.hook = self.root / "hook.sh"
        self.hook.write_text(script)

    @staticmethod
    def write(path, contents):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents)

    def run_hook(self):
        return subprocess.run(["sh", str(self.hook)], capture_output=True, text=True)

    def test_empty_after_packages_does_not_hide_base(self):
        result = self.run_hook()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.image / self.required[0]).read_text(), "base\n")
        # Neither the unused include key nor a final-image key is required.
        self.assertFalse((self.image / "usr/share/keyrings/mullvad-keyring.asc").exists())
        self.assertFalse((self.image / "etc/apt/trusted.gpg.d/mullvad.key.binary.asc").exists())

    def test_after_packages_overrides_base_without_hiding_other_files(self):
        self.write(self.overlay / self.required[0], "override\n")
        result = self.run_hook()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.image / self.required[0]).read_text(), "override\n")
        self.assertEqual((self.image / self.required[1]).read_text(), "base\n")

    def test_base_works_without_after_packages_directory(self):
        self.overlay.rmdir()
        result = self.run_hook()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_reports_all_missing_includes(self):
        for relative in self.required[:2]:
            (self.base / relative).unlink()
        result = self.run_hook()
        self.assertNotEqual(result.returncode, 0)
        for relative in self.required[:2]:
            self.assertIn(str(self.image / relative), result.stderr)
        self.assertIn("committed/transferred", result.stderr)

    def test_resumed_image_with_only_binary_key_succeeds(self):
        self.apt_key.unlink()
        binary_key = self.image / "etc/apt/trusted.gpg.d/mullvad.key.binary.asc"
        self.write(binary_key, "test final-image key\n")
        result = self.run_hook()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.apt_key.exists())
        self.assertEqual(binary_key.read_text(), "test final-image key\n")

    def test_include_copy_does_not_require_or_create_archive_stage_keys(self):
        self.apt_key.unlink()
        result = self.run_hook()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.apt_key.exists())


if __name__ == "__main__":
    unittest.main()
