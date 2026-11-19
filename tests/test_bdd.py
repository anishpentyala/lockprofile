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
