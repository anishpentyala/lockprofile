# Qualification

This source candidate is private until independent review. The tested source tree
is carried by the review packet's git archive and bundle. No registry publication,
outside project bug, outside use, or personal review by Anish is claimed.

## Scope

Only declared version/source-candidate selection at one complete supplied marker
environment, over every public feature subset plus the distinct default invocation.
This is not an installation plan, dependency resolver, artifact selector, full
validator or artifact-byte comparison. README refusals and resource limits apply.
Source identity uses exact version and source field spellings, excluding upload
metadata. Informational dependency/index/tool/attestation fields are not compared.
No result extends beyond the explicit environment and common feature contract.

## Reproducible checks

- `PYTHONPATH=src python -m pytest -q` passes on Python 3.11.18 and 3.15.2.
- 256 Boolean functions on three variables, all 196,608 pairwise Boolean operation
  results, exact model counts and minimum-enabled-feature witnesses are checked.
- 120 seeded marker comparisons and 100 multirow lock comparisons enumerate all
  eight assignments with public packaging 26.3 `Marker.evaluate`/`Pylock.select`
  as independent semantic oracles. Reference selection uses universal wheels and
  is not a general wheel compatibility test.
- The 80-feature test represents 2^80 profiles and finds exactly 2^78 changed
  profiles with fewer than 20 BDD nodes. No wall-clock performance promise.
- Four deliberate implementation defects are each rejected by an assertion
  failure, not setup/import failures. Reproduce with
  `PYTHONPATH=src python evidence/mutation_checks.py`. The committed mutation
  logs were generated with Python 3.15.2; traceback formatting and temporary
  paths may differ when reproduced on another Python version.
- CLI tests cover complete input, malformed TOML/JSON, duplicate JSON keys,
  missing environment fields, node/input limits, nonblocking FIFO refusal,
  and actual executable stdout/stderr failures on `/dev/full`.

## Actual exporter control

`uv-control/pyproject.toml` is our small project. The saved version is recorded in
`uv-control/version.txt`. We ran:

```
uv lock --no-build
uv export --format pylock.toml --all-extras --all-groups --no-emit-project --output-file pylock.toml
```

The genuine output is a **single-use** union of four entries, with no retained
extras/groups markers. Its self-comparison reports one unchanged explicit profile.
`reference-selection.json` is the independently selected four-entry inventory
using `packaging.pylock.Pylock.select` at the example environment. Referenced
artifact hashes/URLs are exporter declarations, not independently downloaded or
verified bytes. No dependency source was built or installed by this control.
This is a parsing and candidate-identity smoke test, not a real-world demonstration
of a nonmonotone feature regression. That harder regression is deliberately
synthetic in `examples/` and in the oracle tests. No uv defect is alleged.

## Comparators inspected

- https://packaging.python.org/en/latest/specifications/pylock-toml/
- https://packaging.pypa.io/en/stable/pylock.html
- https://packaging.pypa.io/en/stable/markers.html
- https://docs.rs/crate/lockdiff/latest/source/src/python/pylock.rs
- https://nab.readthedocs.io/en/stable/how-to/reason-about-markers.html
- https://github.com/fernforge/pylock-lint
- https://github.com/jazzband/pip-tools/pull/2380
- https://github.com/pypa/pipenv/pull/6734

The gap is a bounded exact two-lock feature-profile comparison, not novel Boolean
algebra, marker overlap detection, an installer, or replacement for these tools.
Reports embed raw source declarations and environment data. Review audience before
sharing. Tests are synthetic unless explicitly labeled as actual exporter output.
