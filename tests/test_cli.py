import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from packaging.markers import default_environment

from lockprofile.cli import main


class CLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.old, self.new, self.env = (
            root / x for x in ("old.toml", "new.toml", "env.json")
        )
        self.old.write_text(
            'lock-version = "1.0"\ncreated-by = "test"\npackages = []\n'
        )
        self.new.write_bytes(self.old.read_bytes())
        self.env.write_text(json.dumps(default_environment()))
        self.args = [str(self.old), str(self.new), "--environment", str(self.env)]

    def invoke(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(self.args)
        return code, out.getvalue(), err.getvalue()

    def test_no_change_receipts(self):
        code, out, err = self.invoke()
        self.assertEqual(code, 0)
        self.assertFalse(err)
        self.assertEqual(json.loads(out)["explicit_profiles"], 1)
        self.assertEqual(
            json.loads(out)["receipts"]["before"]["bytes"], self.old.stat().st_size
        )

    def test_parse_error_has_no_report(self):
        for invalid in (
            "bad toml =",
            'lock-version = "2.0"\ncreated-by="test"\npackages=[]',
        ):
            self.new.write_text(invalid)
            code, out, err = self.invoke()
            self.assertEqual(code, 2)
            self.assertFalse(out)
            self.assertTrue(err)

    def test_bad_environment_no_report(self):
        for invalid in ("{}", '{"x":1,"x":2}', "[]"):
            self.env.write_text(invalid)
            code, out, err = self.invoke()
            self.assertEqual(code, 2)
            self.assertFalse(out)
            self.assertTrue(err)

    def test_fifo_refused_without_waiting(self):
        self.old.unlink()
        os.mkfifo(self.old)
        code, out, err = self.invoke()
        self.assertEqual(code, 2)
        self.assertFalse(out)
        self.assertTrue(err)

    def test_output_failure_returns_two(self):
        with patch("sys.stdout.write", side_effect=BrokenPipeError("closed")):
            self.assertEqual(main(self.args), 2)

    def test_input_size_limit(self):
        self.old.write_bytes(b" " * (4 * 1024 * 1024 + 1))
        code, out, err = self.invoke()
        self.assertEqual(code, 2)
        self.assertFalse(out)
        self.assertIn("4 MiB", err)

    def test_budget_failure_is_not_partial_success(self):
        self.old.write_text("""lock-version="1.0"
created-by="test"
extras=["a"]
[[packages]]
name="demo"
version="1"
marker="'a' in extras"
[packages.directory]
path="."
""")
        self.new.write_bytes(self.old.read_bytes())
        self.args += ["--max-nodes", "2"]
        code, out, err = self.invoke()
        self.assertEqual(code, 2)
        self.assertFalse(out)
        self.assertIn("budget", err)

    def test_executable_output_failure_and_diagnostic_failure(self):
        import subprocess
        import sys

        for target in ("stdout", "stderr"):
            args = list(self.args)
            if target == "stderr":
                args[0] = str(self.old.parent / "missing")
            with open("/dev/full", "wb") as full:
                result = subprocess.run(
                    [sys.executable, "-m", "lockprofile", *args],
                    stdout=full if target == "stdout" else subprocess.PIPE,
                    stderr=full if target == "stderr" else subprocess.PIPE,
                    check=False,
                )
            self.assertEqual(result.returncode, 2)
