"""Bounded reduced ordered binary decision diagrams with exact counts."""

from functools import lru_cache


class LimitError(ValueError):
    pass


class BDD:
    def __init__(self, variables, max_nodes=100_000):
        self.variables = tuple(variables)
        if len(set(variables)) != len(variables) or len(variables) > 128:
            raise LimitError("expected at most 128 distinct feature variables")
        if type(max_nodes) is not int or max_nodes < 2:
            raise LimitError("node budget must be an integer >= 2")
        self.max_nodes = max_nodes
        self.nodes = [(len(variables), 0, 0), (len(variables), 1, 1)]
        self.unique = {}
        self._apply = lru_cache(maxsize=200_000)(self._apply_uncached)
        self._count = lru_cache(maxsize=None)(self._count_uncached)
        self._best = lru_cache(maxsize=None)(self._best_uncached)

    def node(self, variable, low, high):
        if low == high:
            return low
        key = (variable, low, high)
        if key not in self.unique:
            if len(self.nodes) >= self.max_nodes:
                raise LimitError("BDD node budget exceeded; no partial comparison")
            self.unique[key] = len(self.nodes)
            self.nodes.append(key)
        return self.unique[key]

    def variable(self, index):
        return self.node(index, 0, 1)

    def _apply_uncached(self, op, a, b):
        if a < 2 and b < 2:
            return int({"and": a and b, "or": a or b, "xor": a != b}[op])
        variable = min(self.nodes[a][0], self.nodes[b][0])
        a0, a1 = self.nodes[a][1:] if self.nodes[a][0] == variable else (a, a)
        b0, b1 = self.nodes[b][1:] if self.nodes[b][0] == variable else (b, b)
        return self.node(variable, self.apply(op, a0, b0), self.apply(op, a1, b1))

    def apply(self, op, a, b):
        if op not in {"and", "or", "xor"}:
            raise ValueError("unsupported Boolean operation")
        return self._apply(op, min(a, b), max(a, b))

    def neg(self, a):
        return self.apply("xor", a, 1)

    def all(self, nodes):
        result = 1
        for node in nodes:
            result = self.apply("and", result, node)
        return result

    def any(self, nodes):
        result = 0
        for node in nodes:
            result = self.apply("or", result, node)
        return result

    def _count_uncached(self, node):
        if node < 2:
            return node
        variable, low, high = self.nodes[node]
        return sum(
            self._count(child) << (self.nodes[child][0] - variable - 1)
            for child in (low, high)
        )

    def count(self, node):
        return self._count(node) << self.nodes[node][0]

    def _best_uncached(self, node):
        if node == 0:
            return None
        if node == 1:
            return ()
        variable, low, high = self.nodes[node]
        a = self._best(low)
        b = self._best(high)
        if b is not None:
            b = (variable,) + b
        return min(
            (x for x in (a, b) if x is not None),
            key=lambda x: (len(x), x),
            default=None,
        )

    def witness(self, node):
        """Minimum number of enabled features, then lexical variable order."""
        best = self._best(node)
        return None if best is None else [self.variables[i] for i in best]

    def evaluate(self, node, enabled):
        while node >= 2:
            variable, low, high = self.nodes[node]
            node = high if self.variables[variable] in enabled else low
        return bool(node)
