import itertools
import unittest

from packaging.markers import Marker, default_environment

from lockprofile.bdd import BDD
from lockprofile.markers import Compiler


class MarkerTests(unittest.TestCase):
    def test_normalization_precedence_and_scalar_direction(self):
        bdd = BDD([("extras", "a-b"), ("dependency_groups", "dev")])
        compiler = Compiler(bdd, default_environment(), set(bdd.variables))
        for text in (
            "'A_B' in extras",
            "'dev' not in dependency_groups and 'a-b' in extras or python_version < '2'",
            "'a-b' in extras and ('dev' not in dependency_groups or '3.0' > python_version)",
            "python_version in '2.7,3.10,3.11' or 'dev' in dependency_groups",
            "'lin' in sys_platform or 'dev' not in dependency_groups",
        ):
            node = compiler.compile(text)
            for bits in itertools.product((False, True), repeat=2):
                enabled = {key for key, value in zip(bdd.variables, bits) if value}
                env = dict(
                    default_environment(),
                    extras={"a-b"} if bits[0] else set(),
                    dependency_groups={"dev"} if bits[1] else set(),
                )
                self.assertEqual(
                    bdd.evaluate(node, enabled),
                    Marker(text).evaluate(env, context="lock_file"),
                )

    def test_limits_and_unsupported_set_operators(self):
        compiler = Compiler(BDD([]), default_environment(), set())
        for text in (
            "'x' == extras",
            "extras in 'x'",
            "('x' in extras)",
            "(" * 49 + "python_version > '2'" + ")" * 49,
            "python_version == '" + "1" * 5000 + "'",
            "'a' == 'b'",
            "python_version == os_name",
        ):
            with self.subTest(text=text[:60]), self.assertRaises(ValueError):
                compiler.compile(text)
