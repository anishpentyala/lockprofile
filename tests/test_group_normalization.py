"""Declared group names and marker literals share the reference set semantics."""

import copy
import itertools
import unittest

from packaging.markers import Marker, default_environment
from packaging.pylock import Pylock
from test_core import lock, package

from lockprofile.core import compare


class GroupNormalizationTests(unittest.TestCase):
    def setUp(self):
        self.env = default_environment()

    def test_mixed_spelling_membership_matches_reference(self):
        spellings = ["dev-test", "Dev_Test", "DEV.TEST", "dev___test"]
        for declared, literal, op in itertools.product(
            spellings, spellings, ["in", "not in"]
        ):
            marker = f"'{literal}' {op} dependency_groups"
            before = lock([package(marker=marker)], extras=(), groups=(declared,))
            after = copy.deepcopy(before)
            after["packages"][0] = package(
                "2.0", marker=before["packages"][0]["marker"]
            )
            with self.subTest(declared=declared, literal=literal, op=op):
                Pylock.from_dict(before)
                report = compare(before, after, self.env)
                selected = [
                    enabled
                    for enabled in [set(), {declared}]
                    if Marker(marker).evaluate(
                        dict(self.env, dependency_groups=enabled), context="lock_file"
                    )
                ]
                self.assertEqual(report["changed_profiles"]["profiles"], len(selected))
                self.assertEqual(
                    report["changed_profiles"]["witness"]["dependency_groups"],
                    ["dev-test"] if op == "in" else [],
                )

    def test_contract_compares_normalized_names(self):
        before = lock(
            [package(marker="'Dev_Test' in dependency_groups")],
            extras=(),
            groups=("Dev_Test",),
        )
        after = copy.deepcopy(before)
        after["dependency-groups"] = ["dev.test"]
        self.assertEqual(
            compare(before, after, self.env)["status"], "EQUIVALENT_IN_PROFILE"
        )
        after["dependency-groups"] = ["other"]
        with self.assertRaisesRegex(ValueError, "declarations differ"):
            compare(before, after, self.env)

    def test_synthetic_defaults_are_normalized_and_not_public(self):
        before = lock(
            [package(marker="'Dev_Test' in dependency_groups")], extras=(), groups=()
        )
        before["default-groups"] = ["DEV.TEST"]
        after = copy.deepcopy(before)
        after["default-groups"] = ["dev___test"]
        report = compare(before, after, self.env)
        self.assertEqual(report["status"], "EQUIVALENT_IN_PROFILE")
        self.assertEqual(report["changed_profiles"]["profiles"], 0)
        self.assertEqual(len(report["default_invocation"]["before"]["selected"]), 1)
        after["default-groups"] = []
        # Keep the name declared on both sides so the absent-default comparison
        # tests disabling a known feature, rather than undeclared-name refusal.
        before["dependency-groups"] = ["dev-test"]
        after["dependency-groups"] = ["DEV_TEST"]
        report = compare(before, after, self.env)
        self.assertTrue(report["default_invocation"]["changed"])
        self.assertEqual(report["changed_profiles"]["profiles"], 0)

    def test_normalized_public_group_enables_non_normalized_default(self):
        before = lock(
            [package(marker="'dev-test' in dependency_groups")],
            extras=(),
            groups=("dev-test",),
        )
        before["default-groups"] = ["Dev_Test"]
        after = copy.deepcopy(before)
        after["packages"][0] = package("2.0", marker=before["packages"][0]["marker"])
        report = compare(before, after, self.env)
        self.assertTrue(report["default_invocation"]["changed"])
        self.assertIn("demo", report["default_invocation"]["before"]["selected"])
        self.assertEqual(report["changed_profiles"]["profiles"], 1)

    def test_default_only_change_is_not_false_equivalence(self):
        before = lock(
            [package(marker="'dev-test' in dependency_groups")],
            extras=(),
            groups=("dev-test",),
        )
        before["default-groups"] = ["Dev_Test"]
        after = copy.deepcopy(before)
        after["default-groups"] = []
        report = compare(before, after, self.env)
        self.assertEqual(report["status"], "CHANGED_OR_INVALID_PROFILE")
        self.assertTrue(report["default_invocation"]["changed"])
        self.assertEqual(report["changed_profiles"]["profiles"], 0)

    def test_aliases_are_one_axis_and_namespaces_stay_separate(self):
        before = lock(
            [package(marker="'Dev_Test' in dependency_groups")],
            extras=("dev-test",),
            groups=("Dev_Test", "dev.test", "DEV-TEST"),
        )
        after = copy.deepcopy(before)
        after["packages"][0] = package("2.0", marker=before["packages"][0]["marker"])
        report = compare(before, after, self.env)
        self.assertEqual(report["explicit_profiles"], 4)
        self.assertEqual(
            report["features"],
            {"extras": ["dev-test"], "dependency_groups": ["dev-test"]},
        )
        self.assertEqual(report["changed_profiles"]["profiles"], 2)
        self.assertEqual(
            report["changed_profiles"]["witness"],
            {"extras": [], "dependency_groups": ["dev-test"]},
        )


if __name__ == "__main__":
    unittest.main()
