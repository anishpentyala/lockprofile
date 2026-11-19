import copy
import itertools
import random
import unittest

from packaging.markers import Marker, default_environment
from packaging.pylock import Pylock

from lockprofile.core import compare


def package(version="1.0", marker=None, name="demo"):
    p = {
        "name": name,
        "version": version,
        "wheels": [
            {
                "name": f"{name}-{version}-py3-none-any.whl",
                "url": f"https://example.invalid/{name}-{version}-py3-none-any.whl",
                "hashes": {"sha256": "a" * 64},
            }
        ],
    }
    if marker is not None:
        p["marker"] = marker
    return p


def lock(packages=(), extras=("a", "b"), groups=("dev",)):
    return {
        "lock-version": "1.0",
        "created-by": "synthetic-test",
        "extras": list(extras),
        "dependency-groups": list(groups),
        "packages": list(packages),
    }


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.env = default_environment()

    def test_hidden_non_monotone_change(self):
        # Empty and all-enabled profiles are equal; only a without b changes.
        a = lock([package(marker="'a' in extras and 'b' not in extras")])
        b = lock([package("2.0", "'a' in extras and 'b' not in extras")])
        report = compare(a, b, self.env)
        self.assertEqual(report["changed_profiles"]["profiles"], 2)
        self.assertEqual(
            report["changed_profiles"]["witness"],
            {"extras": ["a"], "dependency_groups": []},
        )
        self.assertFalse(report["default_invocation"]["changed"])

    def test_equivalent_rewrite_and_row_permutation(self):
        a = lock(
            [package(marker="'a' in extras or 'b' in extras"), package(name="other")]
        )
        b = lock(
            [
                package(name="other"),
                package(
                    marker="('b' in extras and 'a' not in extras) or 'a' in extras"
                ),
            ]
        )
        self.assertEqual(compare(a, b, self.env)["status"], "EQUIVALENT_IN_PROFILE")

    def test_identical_overlapping_rows_still_invalid(self):
        a = lock([package(), package()])
        report = compare(a, a, self.env)
        self.assertEqual(report["before_ambiguity"]["profiles"], 8)
        self.assertEqual(report["comparable_profiles"], 0)
        self.assertEqual(report["changed_profiles"]["profiles"], 0)
        self.assertEqual(report["status"], "CHANGED_OR_INVALID_PROFILE")

    def test_disjoint_versions(self):
        a = lock([package(marker="'a' in extras"), package("2.0", "'a' not in extras")])
        report = compare(a, copy.deepcopy(a), self.env)
        self.assertEqual(report["before_ambiguity"]["profiles"], 0)
        self.assertEqual(report["status"], "EQUIVALENT_IN_PROFILE")

    def test_source_hash_and_candidate_order_are_part_of_identity(self):
        a = lock([package()])
        b = copy.deepcopy(a)
        b["packages"][0]["wheels"][0]["hashes"]["sha256"] = "b" * 64
        self.assertEqual(compare(a, b, self.env)["changed_profiles"]["profiles"], 8)
        b = copy.deepcopy(a)
        a["packages"][0]["wheels"][0]["upload-time"] = __import__("datetime").datetime(
            2026, 1, 1, tzinfo=__import__("datetime").timezone.utc
        )
        self.assertEqual(compare(a, b, self.env)["status"], "EQUIVALENT_IN_PROFILE")

    def test_default_groups_not_forced_on_explicit_subsets(self):
        a = lock([package(marker="'dev' in dependency_groups")])
        a["default-groups"] = ["dev"]
        b = copy.deepcopy(a)
        b["default-groups"] = []
        report = compare(a, b, self.env)
        self.assertEqual(report["changed_profiles"]["profiles"], 0)
        self.assertTrue(report["default_invocation"]["changed"])
        self.assertIn("demo", report["default_invocation"]["before"]["selected"])
        self.assertNotIn("demo", report["default_invocation"]["after"]["selected"])

    def test_default_only_ambiguity_not_hidden(self):
        a = lock(
            [
                package(marker="'base' in dependency_groups"),
                package(marker="'base' in dependency_groups"),
            ]
        )
        a["default-groups"] = ["base"]
        report = compare(a, a, self.env)
        self.assertEqual(report["before_ambiguity"]["profiles"], 0)
        self.assertTrue(report["default_invocation"]["before"]["ambiguous"])
        self.assertEqual(report["status"], "CHANGED_OR_INVALID_PROFILE")

    def test_package_requires_python_is_error_not_skip(self):
        a = lock([package(marker="'a' in extras")])
        a["packages"][0]["requires-python"] = "<2"
        report = compare(a, a, self.env)
        self.assertEqual(report["before_python_incompatible"]["profiles"], 4)
        self.assertEqual(report["comparable_profiles"], 4)

    def test_environment_gate_and_empty_common_domain(self):
        a, b = lock(), lock()
        a["requires-python"] = "<2"
        self.assertEqual(
            compare(a, b, self.env)["applicability_changed"]["profiles"], 8
        )
        self.assertEqual(
            compare(a, a, self.env)["status"], "NO_COMMON_PERMITTED_PROFILE"
        )

    def test_unknown_declarations_and_singular_extra_refused(self):
        for marker in (
            "'c' in extras",
            "extra == 'a'",
            "extras == 'a'",
            "'missing' not in dependency_groups",
        ):
            with self.subTest(marker=marker), self.assertRaises(ValueError):
                compare(lock([package(marker=marker)]), lock(), self.env)
        with self.assertRaises(ValueError):
            compare(lock(), lock(extras=("a",)), self.env)

    def test_complete_environment_and_version_consistency(self):
        env = dict(self.env)
        del env["platform_release"]
        with self.assertRaises(ValueError):
            compare(lock(), lock(), env)
        env = dict(self.env, python_version="1.0")
        with self.assertRaises(ValueError):
            compare(lock(), lock(), env)

    def test_boolean_differential_against_reference_marker_and_pylock_select(self):
        rng = random.Random(571)
        atoms = [
            "'a' in extras",
            "'b' not in extras",
            "'dev' in dependency_groups",
            "python_version >= '3.0'",
            "sys_platform == 'unreal-os'",
        ]
        masks = [
            {
                "extras": {e for e, b in zip(("a", "b"), bits[:2]) if b},
                "dependency_groups": {"dev"} if bits[2] else set(),
            }
            for bits in itertools.product((False, True), repeat=3)
        ]
        for _ in range(120):
            m1 = f"({rng.choice(atoms)} {rng.choice(('and', 'or'))} {rng.choice(atoms)}) {rng.choice(('and', 'or'))} {rng.choice(atoms)}"
            m2 = f"{rng.choice(atoms)} {rng.choice(('and', 'or'))} ({rng.choice(atoms)} {rng.choice(('and', 'or'))} {rng.choice(atoms)})"
            a, b = lock([package(marker=m1)]), lock([package("2.0", m2)])
            report = compare(a, b, self.env)
            expected = []
            for mask in masks:
                ma = Marker(m1).evaluate(dict(self.env, **mask), context="lock_file")
                mb = Marker(m2).evaluate(dict(self.env, **mask), context="lock_file")
                expected.append(bool(ma or mb))
                for doc, selected in ((a, ma), (b, mb)):
                    self.assertEqual(
                        bool(
                            list(
                                Pylock.from_dict(doc).select(
                                    environment=self.env, **mask
                                )
                            )
                        ),
                        selected,
                    )
            self.assertEqual(report["changed_profiles"]["profiles"], sum(expected))
            witness = report["changed_profiles"]["witness"]
            if witness is not None:
                self.assertTrue(
                    Marker(m1).evaluate(
                        dict(self.env, **{k: set(v) for k, v in witness.items()}),
                        context="lock_file",
                    )
                    or Marker(m2).evaluate(
                        dict(self.env, **{k: set(v) for k, v in witness.items()}),
                        context="lock_file",
                    )
                )

    def test_large_symbolic_domain(self):
        names = [f"flag-{i:03}" for i in range(80)]
        a = lock(
            [package(marker="'flag-073' in extras and 'flag-002' not in extras")],
            extras=names,
            groups=(),
        )
        b = lock(
            [package("2.0", "'flag-073' in extras and 'flag-002' not in extras")],
            extras=names,
            groups=(),
        )
        report = compare(a, b, self.env)
        self.assertEqual(report["explicit_profiles"], 1 << 80)
        self.assertEqual(report["changed_profiles"]["profiles"], 1 << 78)
        self.assertLess(report["bdd_nodes"], 20)
        self.assertEqual(report["changed_profiles"]["witness"]["extras"], ["flag-073"])

    def test_multirow_profiles_differential_reference_selector(self):
        from packaging.pylock import PylockSelectError

        rng = random.Random(821)
        atoms = [
            "'a' in extras",
            "'a' not in extras",
            "'b' in extras",
            "'b' not in extras",
            "'dev' in dependency_groups",
            "python_version < '2'",
        ]
        profiles = [
            {
                "extras": {e for e, bit in zip(("a", "b"), bits[:2]) if bit},
                "dependency_groups": {"dev"} if bits[2] else set(),
            }
            for bits in itertools.product((False, True), repeat=3)
        ]

        def selected(doc, profile):
            try:
                entries = list(
                    Pylock.from_dict(doc).select(environment=self.env, **profile)
                )
                return {
                    str(p.name): (
                        str(p.version),
                        art.url,
                        tuple(sorted(art.hashes.items())),
                    )
                    for p, art in entries
                }
            except PylockSelectError:
                return None

        for _ in range(100):
            docs = [
                lock(
                    [
                        package(
                            rng.choice(("1.0", "2.0")),
                            rng.choice(atoms),
                            rng.choice(("demo", "other")),
                        )
                        for _ in range(rng.randrange(5))
                    ]
                )
                for _ in range(2)
            ]
            report = compare(*docs, self.env)
            differences = []
            errors = [0, 0]
            valid = 0
            for profile in profiles:
                a, b = [selected(doc, profile) for doc in docs]
                errors[0] += a is None
                errors[1] += b is None
                if a is not None and b is not None:
                    valid += 1
                    if a != b:
                        differences.append(profile)
            self.assertEqual(report["comparable_profiles"], valid)
            self.assertEqual(report["before_ambiguity"]["profiles"], errors[0])
            self.assertEqual(report["after_ambiguity"]["profiles"], errors[1])
            self.assertEqual(report["changed_profiles"]["profiles"], len(differences))
            expected = min(
                differences,
                key=lambda p: (
                    sum(map(len, p.values())),
                    tuple(sorted((k, x) for k, v in p.items() for x in v)),
                ),
                default=None,
            )
            self.assertEqual(
                report["changed_profiles"]["witness"],
                None
                if expected is None
                else {k: sorted(v) for k, v in expected.items()},
            )

    def test_prerelease_python_matches_reference_errors(self):
        from packaging.pylock import PylockSelectError

        env = dict(self.env, python_version="3.16", python_full_version="3.16.0a1")
        for requirement in (">=3.11", ">=3.16.0a1", "<3.16"):
            a = lock([package()])
            a["packages"][0]["requires-python"] = requirement
            try:
                list(Pylock.from_dict(a).select(environment=env))
                error = False
            except PylockSelectError:
                error = True
            self.assertEqual(
                bool(compare(a, a, env)["before_python_incompatible"]["profiles"]),
                error,
            )
