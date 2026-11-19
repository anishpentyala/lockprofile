"""Re-run focused tests against deliberate implementation defects."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MUTANTS = {
    "drop-skipped-variable-count": (
        "bdd.py",
        "return self._count(node) << self.nodes[node][0]",
        "return self._count(node)",
        "test_large_symbolic_domain",
    ),
    "forget-nonmembership": (
        "markers.py",
        'return self.bdd.neg(node) if op == "not in" else node',
        "return node",
        "test_hidden_non_monotone_change",
    ),
    "ignore-ambiguity": (
        "core.py",
        "for other, _, _ in rows[name]:",
        "for other, _, _ in []:",
        "test_identical_overlapping_rows_still_invalid",
    ),
    "equate-different-identities": (
        "core.py",
        "if aid == bid:",
        "if True:",
        "test_source_hash_and_candidate_order_are_part_of_identity",
    ),
}


def run():
    outcomes = {}
    for name, (filename, old, new, test) in MUTANTS.items():
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for folder in ("src", "tests"):
                shutil.copytree(
                    ROOT / folder,
                    root / folder,
                    ignore=shutil.ignore_patterns("__pycache__"),
                )
            path = root / "src/lockprofile" / filename
            text = path.read_text()
            if text.count(old) != 1:
                raise RuntimeError("mutation target count changed: " + name)
            path.write_text(text.replace(old, new))
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "unittest",
                    "discover",
                    "-s",
                    str(root / "tests"),
                    "-p",
                    "test_core.py",
                    "-k",
                    test,
                    "-v",
                ],
                cwd=root,
                env=dict(os.environ, PYTHONPATH=str(root / "src")),
                capture_output=True,
                text=True,
                check=False,
            )
            log = result.stdout + result.stderr
            (ROOT / "evidence" / (name + ".log")).write_text(log)
            if not result.returncode or "FAIL:" not in log or "ERROR:" in log:
                raise RuntimeError(
                    "mutant did not fail by the intended assertion: " + name
                )
            outcomes[name] = {
                "exit_code": result.returncode,
                "assertion_failures": log.count("FAIL:"),
            }
    (ROOT / "evidence/mutations.json").write_text(json.dumps(outcomes, indent=2) + "\n")
    print(json.dumps(outcomes, sort_keys=True))


if __name__ == "__main__":
    run()
