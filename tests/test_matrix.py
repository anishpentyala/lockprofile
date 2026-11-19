"""Explicit target matrices retain each independently checked result."""

import contextlib
import hashlib
import io
import json
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch

from packaging.markers import default_environment

from lockprofile.cli import main
from lockprofile.core import compare


class MatrixTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.old, self.new, self.env = (
            root / x for x in ("old.toml", "new.toml", "env.json")
        )
        self.old.write_text('lock-version="1.0"\ncreated-by="test"\npackages=[]\n')
        self.new.write_bytes(self.old.read_bytes())
        self.env.write_text(json.dumps(default_environment()))
        self.args = [str(self.old), str(self.new), "--environment", str(self.env)]

    def invoke(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(self.args)
        return code, out.getvalue(), err.getvalue()

    def add_target(self, env=None):
        path = self.env.with_name(f"env-{len(self.args)}.json")
        if env is None:
            path.write_bytes(self.env.read_bytes())
        else:
            path.write_text(json.dumps(env))
        self.args += ["--environment", str(path)]
        return path

    def platform_change(self):
        template = """lock-version="1.0"
created-by="matrix-test"
[[packages]]
name="demo"
version="VERSION"
marker="sys_platform == 'win32'"
[packages.directory]
path="."
"""
        self.old.write_text(template.replace("VERSION", "1"))
        self.new.write_text(template.replace("VERSION", "2"))
        env = json.loads(self.env.read_text())
        env["sys_platform"] = "linux"
        self.env.write_text(json.dumps(env))
        env["sys_platform"] = "win32"
        return self.add_target(env)

    def test_single_target_shape_is_unchanged(self):
        code, out, err = self.invoke()
        expected = compare(
            tomllib.loads(self.old.read_text()),
            tomllib.loads(self.new.read_text()),
            json.loads(self.env.read_bytes()),
        )
        expected["receipts"] = {
            key: {
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "bytes": path.stat().st_size,
            }
            for key, path in (
                ("before", self.old),
                ("after", self.new),
                ("environment", self.env),
            )
        }
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        self.assertEqual(json.loads(out), expected)

    def test_later_changed_target_cannot_be_hidden(self):
        windows = self.platform_change()
        code, out, err = self.invoke()
        report = json.loads(out)
        self.assertEqual((code, err), (1, ""))
        self.assertEqual(report["mode"], "EXPLICIT_TARGET_MATRIX")
        self.assertEqual(report["status"], "CHANGED_OR_INVALID_TARGET")
        self.assertEqual(report["target_count"], 2)
        self.assertEqual([x["index"] for x in report["targets"]], [0, 1])
        self.assertEqual(
            [x["report"]["status"] for x in report["targets"]],
            ["EQUIVALENT_IN_PROFILE", "CHANGED_OR_INVALID_PROFILE"],
        )
        for i, path in enumerate((self.env, windows)):
            self.assertEqual(
                report["targets"][i]["report"]["receipts"]["environment"]["sha256"],
                hashlib.sha256(path.read_bytes()).hexdigest(),
            )
        self.args = self.args[:2] + self.args[4:] + self.args[2:4]
        code, out, err = self.invoke()
        self.assertEqual(code, 1)
        self.assertEqual(
            json.loads(out)["targets"][0]["report"]["status"],
            "CHANGED_OR_INVALID_PROFILE",
        )

    def test_all_equivalent_preserves_duplicates_and_order(self):
        self.add_target()
        code, out, err = self.invoke()
        report = json.loads(out)
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(report["status"], "EQUIVALENT_IN_ALL_TARGETS")
        self.assertEqual(report["target_count"], 2)
        self.assertEqual(report["targets"][0]["report"], report["targets"][1]["report"])

    def test_late_invalid_target_has_no_partial_output(self):
        self.add_target()
        bad = self.add_target()
        for content in (
            "{}",
            '{"sys_platform":"linux","sys_platform":"win32"}',
            "[]",
            "not json",
        ):
            with self.subTest(content=content):
                bad.write_text(content)
                code, out, err = self.invoke()
                self.assertEqual(code, 2)
                self.assertFalse(out)
                self.assertTrue(err)
        bad.unlink()
        code, out, err = self.invoke()
        self.assertEqual(code, 2)
        self.assertFalse(out)
        self.assertTrue(err)

    def test_target_cap_is_checked_before_input_reads(self):
        for _ in range(16):
            self.add_target()
        with patch(
            "lockprofile.cli.read_regular", side_effect=AssertionError("input opened")
        ):
            code, out, err = self.invoke()
        self.assertEqual(code, 2)
        self.assertFalse(out)
        self.assertIn("16 explicit", err)

    def test_sixteen_targets_are_accepted(self):
        for _ in range(15):
            self.add_target()
        code, out, err = self.invoke()
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(json.loads(out)["target_count"], 16)

    def test_nonapplicable_target_stays_visible_and_is_not_success(self):
        self.old.write_text(
            'lock-version="1.0"\ncreated-by="test"\nrequires-python=">=99"\npackages=[]\n'
        )
        self.new.write_bytes(self.old.read_bytes())
        self.add_target()
        code, out, err = self.invoke()
        report = json.loads(out)
        self.assertEqual((code, err), (1, ""))
        self.assertEqual(report["status"], "CHANGED_OR_INVALID_TARGET")
        self.assertTrue(
            all(
                x["report"]["status"] == "NO_COMMON_PERMITTED_PROFILE"
                for x in report["targets"]
            )
        )

    def test_matrix_matches_independent_single_invocations(self):
        self.platform_change()
        env = json.loads(self.env.read_text())
        env.update(python_version="3.12", python_full_version="3.12.0")
        self.add_target(env)
        matrix_args = list(self.args)
        code, out, err = self.invoke()
        matrix = json.loads(out)
        self.assertEqual((code, err), (1, ""))
        for index in range(3):
            self.args = matrix_args[:2] + matrix_args[2 + index * 2 : 4 + index * 2]
            single_code, single_out, single_err = self.invoke()
            single = json.loads(single_out)
            self.assertEqual(
                single_code, int(single["status"] != "EQUIVALENT_IN_PROFILE")
            )
            self.assertFalse(single_err)
            self.assertEqual(matrix["targets"][index]["report"], single)

    def test_seventeen_actual_targets_are_refused(self):
        for _ in range(16):
            self.add_target()
        code, out, err = self.invoke()
        self.assertEqual(code, 2)
        self.assertFalse(out)
        self.assertIn("16 explicit", err)

    def test_late_budget_failure_is_atomic_and_budget_is_per_target(self):
        from lockprofile.cli import compare as actual_compare

        self.add_target()
        seen = []

        def limited(*args, **kwargs):
            seen.append(kwargs["max_nodes"])
            if len(seen) == 2:
                raise ValueError("BDD node budget exceeded")
            return actual_compare(*args, **kwargs)

        self.args += ["--max-nodes", "79"]
        with patch("lockprofile.cli.compare", side_effect=limited):
            code, out, err = self.invoke()
        self.assertEqual(code, 2)
        self.assertEqual(seen, [79, 79])
        self.assertFalse(out)
        self.assertIn("budget", err)

    def test_locks_are_snapshotted_once(self):
        from lockprofile.cli import read_regular as actual_read

        self.add_target()
        with patch("lockprofile.cli.read_regular", wraps=actual_read) as reader:
            code, out, err = self.invoke()
        self.assertEqual((code, err), (0, ""))
        paths = [str(call.args[0]) for call in reader.call_args_list]
        self.assertEqual(paths.count(str(self.old)), 1)
        self.assertEqual(paths.count(str(self.new)), 1)
        self.assertEqual(len(paths), 4)
        self.assertEqual(json.loads(out)["target_count"], 2)

    def test_matrix_output_failure_is_not_a_success(self):
        self.add_target()
        with patch("sys.stdout.write", side_effect=BrokenPipeError("closed")):
            self.assertEqual(main(self.args), 2)
