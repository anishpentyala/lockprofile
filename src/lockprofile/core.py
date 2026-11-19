"""Exact package-entry selection comparison over a finite feature universe."""

import json
from collections import defaultdict

from packaging.pylock import Pylock
from packaging.specifiers import SpecifierSet
from packaging.version import Version

from .bdd import BDD
from .markers import ENV_KEYS, Compiler

SOURCES = ("vcs", "directory", "archive", "sdist", "wheels")


def validate_environment(environment):
    if not isinstance(environment, dict) or set(environment) != ENV_KEYS:
        raise ValueError(
            "target must contain exactly all 11 packaging marker environment keys"
        )
    if any(not isinstance(v, str) for v in environment.values()):
        raise ValueError("environment values must be strings")
    version = Version(environment["python_full_version"])
    if len(version.release) < 2 or environment["python_version"] != ".".join(
        map(str, version.release[:2])
    ):
        raise ValueError("python_version must match python_full_version major.minor")
    return dict(environment)


def load_lock(data):
    if not isinstance(data, dict):
        raise TypeError("lock must be a table")
    if data.get("lock-version") != "1.0":
        raise ValueError("only lock-version 1.0 is supported")
    if len(data.get("packages", [])) > 2000:
        raise ValueError("at most 2000 package rows are supported")
    Pylock.from_dict(data)  # Public structural validator; no install or network.
    if "environments" in data:
        if not data["environments"]:
            raise ValueError("empty environments list is unsupported")
        from .markers import tokenize

        for marker in data["environments"]:
            if any(
                kind == "word" and word in {"extras", "dependency_groups", "extra"}
                for kind, word in tokenize(marker)
            ):
                raise ValueError("top-level environments must not depend on features")
    # Retain the caller's source spelling in identities, not inferred file content.
    return data


def known_features(lock):
    return {
        (key, name)
        for key, field in (
            ("extras", "extras"),
            ("dependency_groups", "dependency-groups"),
        )
        for name in lock.get(field, [])
    } | {("dependency_groups", name) for name in lock.get("default-groups", [])}


def public_features(lock):
    return {
        (key, name)
        for key, field in (
            ("extras", "extras"),
            ("dependency_groups", "dependency-groups"),
        )
        for name in lock.get(field, [])
    }


def signature(package):
    """Exact declared candidate identity, not an artifact/byte equivalence claim."""
    identity = {key: package[key] for key in ("version",) + SOURCES if key in package}
    # Upload times do not participate in installation candidate identity.
    for key in ("sdist", "archive"):
        if key in identity:
            identity[key] = {
                k: v for k, v in identity[key].items() if k != "upload-time"
            }
    if "wheels" in identity:
        identity["wheels"] = [
            {k: v for k, v in wheel.items() if k != "upload-time"}
            for wheel in identity["wheels"]
        ]
    return json.dumps(identity, sort_keys=True, separators=(",", ":"))


def region(bdd, node):
    witness = bdd.witness(node)
    return {
        "profiles": bdd.count(node),
        "witness": None
        if witness is None
        else {
            "extras": [value for key, value in witness if key == "extras"],
            "dependency_groups": [
                value for key, value in witness if key == "dependency_groups"
            ],
        },
    }


def compile_lock(lock, compiler):
    bdd = compiler.bdd
    environment = compiler.environment
    python = environment["python_full_version"]
    permitted = int(SpecifierSet(lock.get("requires-python", "")).contains(python))
    if "environments" in lock:
        permitted = bdd.apply(
            "and",
            permitted,
            bdd.any(compiler.compile(marker) for marker in lock["environments"]),
        )
    rows = defaultdict(list)
    ambiguity = 0
    python_error = 0
    for index, package in enumerate(lock.get("packages", [])):
        node = compiler.compile(package.get("marker"))
        name = package["name"]
        for other, _, _ in rows[name]:
            ambiguity = bdd.apply("or", ambiguity, bdd.apply("and", other, node))
        if not SpecifierSet(package.get("requires-python", "")).contains(python):
            python_error = bdd.apply("or", python_error, node)
        rows[name].append((node, signature(package), index))
    return {
        "permitted": permitted,
        "rows": rows,
        "ambiguity": bdd.apply("and", permitted, ambiguity),
        "python_error": bdd.apply("and", permitted, python_error),
    }


def compare(before, after, environment, *, max_nodes=100_000):
    """Compare explicit groups/extras subsets, plus the distinct default invocation.

    A profile selects a subset of the common public declarations. Synthetic
    default groups are absent in explicit profiles. The default invocation is
    checked separately with each lock's own default-groups and no extras.
    """
    before, after = load_lock(before), load_lock(after)
    environment = validate_environment(environment)
    features = public_features(before)
    if features != public_features(after):
        raise ValueError(
            "public extra/group declarations differ; compare a common contract first"
        )
    bdd = BDD(sorted(features), max_nodes=max_nodes)
    compiled = [
        compile_lock(lock, Compiler(bdd, environment, known_features(lock)))
        for lock in (before, after)
    ]
    left, right = compiled
    common = bdd.apply("and", left["permitted"], right["permitted"])
    errors = bdd.any(
        side[key] for side in compiled for key in ("ambiguity", "python_error")
    )
    valid = bdd.apply("and", common, bdd.neg(errors))
    changed = 0
    package_changes = []
    for name in sorted(left["rows"].keys() | right["rows"].keys()):
        a, b = left["rows"].get(name, []), right["rows"].get(name, [])
        absent_a = bdd.neg(bdd.any(row[0] for row in a))
        absent_b = bdd.neg(bdd.any(row[0] for row in b))
        same = bdd.apply("and", absent_a, absent_b)
        for anode, aid, _ in a:
            for bnode, bid, _ in b:
                if aid == bid:
                    same = bdd.apply("or", same, bdd.apply("and", anode, bnode))
        difference = bdd.apply("and", valid, bdd.neg(same))
        if difference:
            changed = bdd.apply("or", changed, difference)
            details = region(bdd, difference)
            witness = details["witness"]
            enabled = {("extras", x) for x in witness["extras"]} | {
                ("dependency_groups", x) for x in witness["dependency_groups"]
            }
            package_changes.append(
                {
                    "name": name,
                    **details,
                    "before": [
                        json.loads(identity)
                        for node, identity, _ in a
                        if bdd.evaluate(node, enabled)
                    ],
                    "after": [
                        json.loads(identity)
                        for node, identity, _ in b
                        if bdd.evaluate(node, enabled)
                    ],
                }
            )
    applicability = bdd.apply("xor", left["permitted"], right["permitted"])
    default = []
    for lock in (before, after):
        constants = {("dependency_groups", x) for x in lock.get("default-groups", [])}
        dbdd = BDD([], max_nodes=max_nodes)
        side = compile_lock(
            lock, Compiler(dbdd, environment, known_features(lock), constants)
        )
        default.append(
            {
                "permitted": bool(side["permitted"]),
                "ambiguous": bool(side["ambiguity"]),
                "python_incompatible": bool(side["python_error"]),
                "selected": {
                    name: [
                        json.loads(identity)
                        for identity in sorted(
                            identity for node, identity, _ in rows if node
                        )
                    ]
                    for name, rows in sorted(side["rows"].items())
                    if any(row[0] for row in rows)
                },
            }
        )
    default_changed = default[0] != default[1]
    default_error = any(
        side["permitted"] and (side["ambiguous"] or side["python_incompatible"])
        for side in default
    )
    problems = bool(
        errors or applicability or changed or default_changed or default_error
    )
    status = "CHANGED_OR_INVALID_PROFILE" if problems else "EQUIVALENT_IN_PROFILE"
    if not common and not problems:
        status = "NO_COMMON_PERMITTED_PROFILE"
    return {
        "schema_version": 1,
        "status": status,
        "scope": "declared version/source-candidate selection; not installation or artifact bytes",
        "environment": environment,
        "features": {
            "extras": sorted(before.get("extras", [])),
            "dependency_groups": sorted(before.get("dependency-groups", [])),
        },
        "explicit_profiles": 1 << len(features),
        "common_permitted_profiles": bdd.count(common),
        "comparable_profiles": bdd.count(valid),
        "changed_profiles": region(bdd, changed),
        "applicability_changed": region(bdd, applicability),
        "before_ambiguity": region(bdd, left["ambiguity"]),
        "after_ambiguity": region(bdd, right["ambiguity"]),
        "before_python_incompatible": region(bdd, left["python_error"]),
        "after_python_incompatible": region(bdd, right["python_error"]),
        "package_changes": package_changes,
        "default_invocation": {
            "changed": default_changed,
            "before": default[0],
            "after": default[1],
        },
        "bdd_nodes": len(bdd.nodes),
    }
