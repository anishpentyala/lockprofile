import itertools
import unittest

from lockprofile.bdd import BDD, LimitError


class BDDTests(unittest.TestCase):
    def test_exhaustive_boolean_functions_and_operations(self):
        bdd = BDD(range(3))
        assignments = [
            frozenset(i for i, bit in enumerate(bits) if bit)
            for bits in itertools.product((False, True), repeat=3)
        ]
        functions = []
        for mask in range(256):
            clauses = []
            for i, assignment in enumerate(assignments):
                if mask & (1 << i):
                    clauses.append(
                        bdd.all(
                            bdd.variable(j)
                            if j in assignment
                            else bdd.neg(bdd.variable(j))
                            for j in range(3)
                        )
                    )
            node = bdd.any(clauses)
            functions.append(node)
            actual = [a for i, a in enumerate(assignments) if mask & (1 << i)]
            self.assertEqual(bdd.count(node), len(actual))
            best = min(actual, key=lambda a: (len(a), tuple(sorted(a))), default=None)
            self.assertEqual(bdd.witness(node), None if best is None else sorted(best))
            for i, assignment in enumerate(assignments):
                self.assertEqual(bdd.evaluate(node, assignment), bool(mask & (1 << i)))
        self.assertEqual(len(set(functions)), 256)
        for a in range(256):
            for b in range(256):
                for op, expected in (("and", a & b), ("or", a | b), ("xor", a ^ b)):
                    self.assertEqual(
                        bdd.apply(op, functions[a], functions[b]), functions[expected]
                    )

    def test_skipped_levels_and_large_exact_counts(self):
        bdd = BDD(range(100))
        self.assertEqual(bdd.count(bdd.variable(73)), 1 << 99)
        self.assertEqual(bdd.count(1), 1 << 100)
        self.assertEqual(bdd.witness(bdd.variable(73)), [73])
        self.assertEqual(bdd.witness(bdd.neg(bdd.variable(73))), [])

    def test_budget(self):
        with self.assertRaises(LimitError):
            BDD(range(129))
        with self.assertRaises(LimitError):
            BDD(["x"], max_nodes=2).variable(0)


class IdentityReductionTests(unittest.TestCase):
    def test_identities_skip_recursive_apply_cache(self):
        bdd = BDD(range(128))
        node = bdd.all(bdd.variable(i) for i in range(128))
        cases = [
            ("and", node, node, node),
            ("or", node, node, node),
            ("xor", node, node, 0),
            ("and", node, 0, 0),
            ("and", node, 1, node),
            ("or", node, 0, node),
            ("or", node, 1, 1),
            ("xor", node, 0, node),
        ]
        for op, a, b, expected in cases:
            for left, right in [(a, b), (b, a)]:
                bdd._apply.cache_clear()
                before = len(bdd.nodes)
                self.assertEqual(bdd.apply(op, left, right), expected)
                self.assertEqual(bdd._apply.cache_info().misses, 0, (op, left, right))
                self.assertEqual(bdd._apply.cache_info().hits, 0)
                self.assertEqual(len(bdd.nodes), before)

    def test_true_xor_and_invalid_operation_are_not_identity_shortcuts(self):
        bdd = BDD(range(6))
        node = bdd.all(bdd.variable(i) for i in [0, 3, 5])
        complement = bdd.apply("xor", node, 1)
        self.assertEqual(bdd.count(complement), 56)
        self.assertEqual(bdd.witness(complement), [])
        self.assertEqual(bdd.apply("xor", 1, complement), node)
        for left, right in [(node, node), (0, node), (1, node)]:
            with self.assertRaises(ValueError):
                bdd.apply("invalid", left, right)

    def test_repeated_formula_at_exact_budget_does_not_allocate(self):
        bdd = BDD(range(8))
        node = bdd.any(bdd.variable(i) for i in [1, 3, 7])
        bdd.max_nodes = len(bdd.nodes)
        for _ in range(100):
            self.assertEqual(bdd.all([node, node, 1]), node)
            self.assertEqual(bdd.any([node, node, 0]), node)
        self.assertEqual(bdd.count(node), 224)
        self.assertEqual(bdd.witness(node), [1])
