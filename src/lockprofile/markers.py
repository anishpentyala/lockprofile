"""Compile a deliberately bounded marker grammar, with no private parser API.

Only literal membership of extras/dependency_groups is symbolic. Scalar
atoms are evaluated by packaging for the explicit, complete target environment.
"""

import re

from packaging.markers import Marker
from packaging.utils import canonicalize_name

ENV_KEYS = frozenset(
    {
        "implementation_name",
        "implementation_version",
        "os_name",
        "platform_machine",
        "platform_release",
        "platform_system",
        "platform_version",
        "python_full_version",
        "platform_python_implementation",
        "python_version",
        "sys_platform",
    }
)
TOKEN = re.compile(
    r"""\s*(?:(?P<quoted>'[^'\n\r]*'|"[^"\n\r]*")|(?P<op>===|==|!=|<=|>=|~=|<|>)|(?P<word>[a-zA-Z_][a-zA-Z_0-9]*)|(?P<paren>[()]))"""
)


def tokenize(text):
    if not isinstance(text, str) or len(text) > 4096:
        raise ValueError("marker must be a string of at most 4096 characters")
    tokens = []
    position = 0
    while position < len(text.rstrip()):
        match = TOKEN.match(text, position)
        if not match:
            raise ValueError("unsupported marker spelling")
        tokens.append((match.lastgroup, match.group(match.lastgroup)))
        position = match.end()
    if not tokens or len(tokens) > 512:
        raise ValueError("marker must contain 1 through 512 tokens")
    return tokens


class Compiler:
    def __init__(self, bdd, environment, known, constants=()):
        self.bdd, self.environment, self.known = bdd, environment, known
        self.constants = set(constants)
        self.positions = {name: i for i, name in enumerate(bdd.variables)}

    def compile(self, text):
        if text is None:
            return 1
        # Parse with the public reference first; our accepted subset is narrower.
        tokens = tokenize(text)
        depth = 0
        for _, value in tokens:
            depth += (value == "(") - (value == ")")
            if depth > 48:
                raise ValueError("marker nesting exceeds 48")
        Marker(text)
        position = 0

        def expression(depth=0):
            nonlocal position
            if depth > 48:
                raise ValueError("marker nesting exceeds 48")
            result = conjunction(depth)
            while position < len(tokens) and tokens[position][1] == "or":
                position += 1
                result = self.bdd.apply("or", result, conjunction(depth))
            return result

        def conjunction(depth):
            nonlocal position
            result = atom(depth)
            while position < len(tokens) and tokens[position][1] == "and":
                position += 1
                result = self.bdd.apply("and", result, atom(depth))
            return result

        def take():
            nonlocal position
            if position == len(tokens):
                raise ValueError("incomplete marker")
            token = tokens[position]
            position += 1
            return token

        def atom(depth):
            nonlocal position
            if position < len(tokens) and tokens[position][1] == "(":
                position += 1
                result = expression(depth + 1)
                if take()[1] != ")":
                    raise ValueError("unclosed marker group")
                return result
            left = take()
            op = take()[1]
            if op == "not":
                if take()[1] != "in":
                    raise ValueError("expected not in")
                op = "not in"
            right = take()
            variables = [t[1] for t in (left, right) if t[0] == "word"]
            if any(v in {"extras", "dependency_groups"} for v in variables):
                if not (
                    left[0] == "quoted"
                    and right[0] == "word"
                    and right[1] in {"extras", "dependency_groups"}
                    and op in {"in", "not in"}
                ):
                    raise ValueError(
                        "set markers require a quoted name in/not in extras or dependency_groups"
                    )
                value = canonicalize_name(left[1][1:-1])
                key = (right[1], value)
                if key not in self.known:
                    raise ValueError(
                        "marker references an undeclared extra/group: " + value
                    )
                node = (
                    1
                    if key in self.constants
                    else self.bdd.variable(self.positions[key])
                    if key in self.positions
                    else 0
                )
                return self.bdd.neg(node) if op == "not in" else node
            if len(variables) != 1 or variables[0] not in ENV_KEYS:
                raise ValueError(
                    "scalar atoms need one explicit environment variable; extra is unsupported"
                )
            if left[0] not in {"quoted", "word"} or right[0] not in {"quoted", "word"}:
                raise ValueError("invalid scalar atom")
            # No inherited host values: environment is validated complete upstream.
            marker = Marker(left[1] + " " + op + " " + right[1])
            return int(
                marker.evaluate(environment=self.environment, context="lock_file")
            )

        result = expression()
        if position != len(tokens):
            raise ValueError("trailing marker tokens")
        return result
