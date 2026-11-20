"""The public pylock validator's errors are invalid input, not profile changes."""

import contextlib
import copy
import io
import itertools
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from packaging.markers import default_environment
from packaging.pylock import Pylock, PylockValidationError
from test_core import lock, package

from lockprofile.cli import main
from lockprofile.core import load_lock


class ValidationBoundaryTests(unittest.TestCase):
    def test_structural_errors_become_value_errors_with_cause(self):
        cases = [
            {"lock-version": "1.0", "packages": []},
            {"lock-version": "1.0", "created-by": 42, "packages": []},
            dict(lock(), extras=["Not_Normalized"]),
            lock([dict(package(), marker="not a valid marker")]),
            lock([dict(package(), version="not a version")]),
            lock([dict(package(), wheels=[])]),
        ]
        for doc in cases:
            with self.subTest(doc=doc):
                with self.assertRaises(PylockValidationError):
                    Pylock.from_dict(doc)
                with self.assertRaises(ValueError) as caught:
                    load_lock(doc)
                self.assertIsInstance(caught.exception.__cause__, PylockValidationError)
                self.assertTrue(str(caught.exception).startswith("invalid pylock: "))

    def test_bounded_field_substitutions_cannot_leak_validator_errors(self):
        values = [True, 1, 1.5, [], {}, "", "bad", ["a"], [1], [{}]]
        base = lock([package()])
        top = [
            "created-by",
            "requires-python",
            "environments",
            "extras",
            "dependency-groups",
            "default-groups",
            "packages",
        ]
        nested = [
            "name",
            "version",
            "marker",
            "requires-python",
            "wheels",
            "archive",
            "vcs",
            "directory",
            "sdist",
            "dependencies",
            "index",
        ]
        checked = 0
        for level, fields in [("top", top), ("package", nested)]:
            for key, value in itertools.product(fields, values):
                doc = copy.deepcopy(base)
                (doc if level == "top" else doc["packages"][0])[key] = value
                try:
                    Pylock.from_dict(doc)
                except PylockValidationError:
                    with (
                        self.subTest(level=level, field=key, value=value),
                        self.assertRaises((ValueError, TypeError)),
                    ):
                        load_lock(doc)
                    checked += 1
        self.assertGreater(checked, 140)

    def test_cli_both_sides_single_and_matrix(self):
        invalids = [
            'lock-version="1.0"\npackages=[]\n',
            'lock-version="1.0"\ncreated-by=42\npackages=[]\n',
            'lock-version="1.0"\ncreated-by="test"\nextras=["Not_Normalized"]\npackages=[]\n',
            'lock-version="1.0"\ncreated-by="test"\n[[packages]]\nname="demo"\nversion="invalid"\n[packages.directory]\npath="."\n',
            'lock-version="1.0"\ncreated-by="test"\n[[packages]]\nname="demo"\nversion="1"\n',
        ]
        valid = 'lock-version="1.0"\ncreated-by="test"\npackages=[]\n'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            before, after, env = [
                root / name for name in ["before.toml", "after.toml", "env.json"]
            ]
            env.write_text(json.dumps(default_environment()))
            for text, side, matrix in itertools.product(
                invalids, ["before", "after"], [False, True]
            ):
                with self.subTest(text=text, side=side, matrix=matrix):
                    before.write_text(text if side == "before" else valid)
                    after.write_text(text if side == "after" else valid)
                    args = [str(before), str(after), "--environment", str(env)]
                    if matrix:
                        args += ["--environment", str(env)]
                    out, err = io.StringIO(), io.StringIO()
                    with (
                        contextlib.redirect_stdout(out),
                        contextlib.redirect_stderr(err),
                    ):
                        status = main(args)
                    self.assertEqual(status, 2)
                    self.assertEqual(out.getvalue(), "")
                    self.assertTrue(
                        err.getvalue().startswith("lockprofile: invalid pylock: ")
                    )
                    self.assertNotIn("Traceback", err.getvalue())
                    run = subprocess.run(
                        [sys.executable, "-m", "lockprofile", *args],
                        check=False,
                        capture_output=True,
                        text=True,
                    )
                    self.assertEqual(run.returncode, 2)
                    self.assertEqual(run.stdout, "")
                    self.assertEqual(run.stderr, err.getvalue())

    def test_executable_invalid_schema_has_exit_two_not_traceback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            before, after, env = [root / x for x in ["a.toml", "b.toml", "env.json"]]
            env.write_text(json.dumps(default_environment()))
            good = 'lock-version="1.0"\ncreated-by="test"\npackages=[]\n'
            bad = 'lock-version="1.0"\ncreated-by=42\npackages=[]\n'
            for side, matrix in itertools.product(["before", "after"], [False, True]):
                with self.subTest(side=side, matrix=matrix):
                    before.write_text(bad if side == "before" else good)
                    after.write_text(bad if side == "after" else good)
                    args = [str(before), str(after), "--environment", str(env)]
                    if matrix:
                        args += ["--environment", str(env)]
                    run = subprocess.run(
                        [sys.executable, "-m", "lockprofile", *args],
                        check=False,
                        capture_output=True,
                        text=True,
                    )
                    self.assertEqual(run.returncode, 2)
                    self.assertEqual(run.stdout, "")
                    self.assertNotIn("Traceback", run.stderr)
                    self.assertIn("created-by", run.stderr)

    def test_diagnostic_write_failure_still_returns_two(self):
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            before, after, env = [root / x for x in ["a.toml", "b.toml", "env.json"]]
            before.write_text('lock-version="1.0"\ncreated-by=42\npackages=[]\n')
            after.write_bytes(before.read_bytes())
            env.write_text(json.dumps(default_environment()))
            args = [str(before), str(after), "--environment", str(env)]
            with patch("sys.stderr.write", side_effect=OSError("closed")):
                self.assertEqual(main(args), 2)
            if os.path.exists("/dev/full"):
                with open("/dev/full", "wb") as full:
                    run = subprocess.run(
                        [sys.executable, "-m", "lockprofile", *args],
                        check=False,
                        stdout=subprocess.PIPE,
                        stderr=full,
                    )
                self.assertEqual(run.returncode, 2)
                self.assertEqual(run.stdout, b"")
