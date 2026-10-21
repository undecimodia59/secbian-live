"""Exercise deletion only inside disposable temporary directories."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "config/includes.chroot/usr/local/bin/erase"


class EraseTests(unittest.TestCase):
    def setUp(self):
        self.tool = types.ModuleType("erase")
        exec(compile(SCRIPT.read_text(), str(SCRIPT), "exec"), self.tool.__dict__)
        self.temp = tempfile.TemporaryDirectory(prefix="secbian-erase-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def file(self, name="file", contents=b"sensitive data"):
        path = self.root / name
        path.write_bytes(contents)
        return path

    @unittest.skipUnless(shutil.which("shred"), "GNU shred not installed")
    def test_real_shred_file_with_spaces_and_leading_dash(self):
        path = self.file("- file with spaces")
        self.assertEqual(self.tool.main(["--", str(path)]), 0)
        self.assertFalse(path.exists())

    @unittest.skipUnless(shutil.which("shred"), "GNU shred not installed")
    def test_real_shred_recursive_tree(self):
        folder = self.root / "folder"
        (folder / "nested").mkdir(parents=True)
        (folder / ".hidden").write_bytes(b"private")
        (folder / "nested/file").write_bytes(b"private")
        self.assertEqual(self.tool.main(["-r", str(folder)]), 0)
        self.assertFalse(folder.exists())

    def test_directory_without_r_is_retained(self):
        folder = self.root / "folder"
        folder.mkdir()
        with patch.object(self.tool.subprocess, "run") as runner:
            self.assertEqual(self.tool.main([str(folder)]), 1)
        runner.assert_not_called()
        self.assertTrue(folder.is_dir())

    def test_exact_passes_then_unlink(self):
        path = self.file()

        def overwrite(command, **kwargs):
            self.assertTrue(path.exists())
            self.assertEqual(command[:4], ["shred", "--iterations=1", "--zero", "--"])
            fd = kwargs["pass_fds"][0]
            self.assertEqual(command[4], f"/proc/self/fd/{fd}")
            os.write(fd, b"\0" * len(path.read_bytes()))
            return subprocess.CompletedProcess(command, 0, "", "")

        unlink = os.unlink

        def remove(name, **kwargs):
            self.assertEqual(path.read_bytes(), b"\0" * len(b"sensitive data"))
            unlink(name, **kwargs)

        with patch.object(self.tool.subprocess, "run", side_effect=overwrite), \
                patch.object(self.tool.os, "unlink", side_effect=remove):
            self.assertEqual(self.tool.main([str(path)]), 0)
        self.assertFalse(path.exists())

    def test_overwrite_failure_retains_file_and_directory(self):
        folder = self.root / "folder"
        folder.mkdir()
        file = folder / "file"
        file.write_bytes(b"private")
        with patch.object(self.tool.subprocess, "run", return_value=
                          subprocess.CompletedProcess([], 1, "", "write failed")):
            self.assertEqual(self.tool.main(["-r", str(folder)]), 1)
        self.assertEqual(file.read_bytes(), b"private")

    def test_symlink_is_not_followed(self):
        outside = self.file("outside")
        folder = self.root / "folder"
        folder.mkdir()
        (folder / "link").symlink_to(outside)
        with patch.object(self.tool.subprocess, "run") as runner:
            self.assertEqual(self.tool.main(["-r", str(folder)]), 1)
        runner.assert_not_called()
        self.assertEqual(outside.read_bytes(), b"sensitive data")
        self.assertTrue((folder / "link").is_symlink())

    def test_hardlinks_are_retained(self):
        original = self.file()
        link = self.root / "hardlink"
        os.link(original, link)
        with patch.object(self.tool.subprocess, "run") as runner:
            self.assertEqual(self.tool.main([str(original)]), 1)
        runner.assert_not_called()
        self.assertEqual(link.read_bytes(), b"sensitive data")
        self.assertTrue(original.exists())

    def test_fifo_is_skipped_without_opening(self):
        fifo = self.root / "fifo"
        os.mkfifo(fifo)
        with patch.object(self.tool.subprocess, "run") as runner:
            self.assertEqual(self.tool.main([str(fifo)]), 1)
        runner.assert_not_called()
        self.assertTrue(fifo.exists())

    def test_mountpoint_is_skipped(self):
        folder = self.root / "mounted"
        folder.mkdir()
        with patch.object(self.tool, "mounted_paths", return_value={str(folder)}), \
                patch.object(self.tool.subprocess, "run") as runner:
            self.assertEqual(self.tool.main(["-r", str(folder)]), 1)
        runner.assert_not_called()
        self.assertTrue(folder.exists())

    def test_replaced_path_is_not_removed(self):
        file = self.file()

        def replace(command, **kwargs):
            file.rename(self.root / "original")
            file.write_bytes(b"replacement")
            return subprocess.CompletedProcess(command, 0, "", "")

        with patch.object(self.tool.subprocess, "run", side_effect=replace):
            self.assertEqual(self.tool.main([str(file)]), 1)
        self.assertEqual(file.read_bytes(), b"replacement")

    def test_root_and_current_directory_are_refused(self):
        with patch.object(self.tool.subprocess, "run") as runner:
            self.assertEqual(self.tool.main(["-r", "/"]), 1)
            self.assertEqual(self.tool.main(["-r", "."]), 1)
        runner.assert_not_called()


if __name__ == "__main__":
    unittest.main()
