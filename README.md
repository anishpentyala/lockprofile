# lockprofile

A lockfile diff can show identical package versions while a marker edit changes
which optional installations select them. Testing only the default profile or
"all extras" misses changes behind `a in extras and b not in extras`.

`lockprofile` compares **declared package-entry selection** between two PEP 751
locks at one caller-supplied, complete target environment. It checks every subset
of their common public extras/groups contract symbolically, counts exactly how
many profiles change, and gives a minimum-enabled-feature witness. The ordinary
default invocation is checked separately using each lock's own `default-groups`.
No packages are installed or resolved. Input code, build hooks, URLs and paths
inside the locks are never executed, fetched or opened.

## Run from source

Python 3.11 or later. Install this checkout with `python -m pip install .`.
The runtime deliberately pins `packaging==26.3`, the tested reference validator
and scalar marker evaluator. A dependency bump requires rerunning the marker,
selection, count and witness differential oracles, mutation controls and
installed-wheel tests on supported Python versions before changing the pin.
This is not a registry release.

```sh
lockprofile examples/before.toml examples/after.toml \
  --environment examples/linux311.json
```

The synthetic example changes only the version selected when `color` is enabled
and `progress` is disabled. A public `dev` group doubles the affected count:
**two of eight** explicit profiles change. The empty and all-enabled profiles
are unchanged. The report includes the witness `extras=["color"], groups=[]`.
The source URLs in these examples are non-resolving placeholders.

Supply all 11 `packaging.markers` environment fields in the JSON, with strings
as values. `python_version` must agree with `python_full_version` major.minor.
Nothing is filled from the host. These fields are assertions, not a verified
interpreter or proof that a platform tuple exists. Pass one file per target you need; there is no universal quantification over
Python versions/platforms.

### Explicit target matrix

Repeat `--environment` to check up to 16 complete target assertions in one
invocation. A single environment keeps the existing report shape and exit codes.
Multiple environments return an `EXPLICIT_TARGET_MATRIX` envelope. Each ordered
`targets` item contains its zero-based `index` and the complete independent
`report`, including that target's environment receipt, profile counts and witness.
Duplicate targets are retained, not deduplicated.

```sh
lockprofile examples/before.toml examples/after.toml \
  --environment examples/linux311.json \
  --environment examples/windows311.json
```

Exit 0 and `EQUIVALENT_IN_ALL_TARGETS` mean every **supplied target** has no change
in the narrow selection profile. Exit 1 and `CHANGED_OR_INVALID_TARGET` mean at
least one target reports a difference, invalid profile or no common permitted
profile. Inspect each nested report for the reason. Counts are not added across
targets; overlapping or duplicate environment assertions are not a count of
unique installations. Nothing about an omitted target is established.

The before/after files are read once. The output is held until every target has
been checked. A missing, malformed, unsupported or over-budget later target
returns exit 2 with no success report, even if earlier targets passed. Input byte
limits apply per file and `--max-nodes` applies separately to each comparison,
not to the entire matrix. A matrix can therefore use more memory and time than a
single comparison. This is not a parallel executor or a hostile-input sandbox.

## What is compared

- An explicit profile chooses any subset of declared `extras` and any subset of
  public `dependency-groups`, including the empty sets. Synthetic default groups
  are **not** implicitly added to explicit profiles.
- The default invocation has no extras and each side's own `default-groups`.
  A default-only change or ambiguity is not hidden by the explicit-profile result.
- At the fixed environment, scalar marker atoms are constants. Literal
  membership/nonmembership of extras/groups is symbolic. Parentheses, `and` and
  `or` have their usual marker precedence. Set names use PEP 685/735 normalization in
  declarations, marker literals and
  synthetic defaults. Reports and witnesses use normalized names. Different
  spellings of the same normalized name are one feature, not independent
  choices, matching the reference evaluator's set membership. Extras and groups
  remain separate namespaces.
- Identically named active rows are ambiguous even if their contents are identical.
  Ambiguous profiles and profiles with an active package's incompatible
  `requires-python` are reported separately, not counted as comparable successes.
  Top-level `requires-python` and `environments` gate lock applicability.
- A selected entry's identity is the **exact stored version spelling and source
  candidate declarations** (`vcs`, `directory`, `archive`, `sdist`, `wheels`).
  Mapping key order and artifact upload timestamps do not matter. Wheel-list
  order does matter. Two equivalent URL/version/path spellings can still differ.
  Package row order and equivalent marker rewrites do not by themselves differ.
- Dependency-list, index, attestation, creator and tool metadata are not part of
  this identity. A change to those fields alone is outside this comparison.
- Per-package affected counts can overlap. `changed_profiles.profiles` is their
  union, **not** their sum. Counts are arbitrary-precision integers, including
  values above JavaScript's exact-number range. Parse them accordingly.

The reduced ordered BDD shares Boolean subproblems instead of enumerating all
profiles. Counts include variables skipped by a reduced node. Witnesses minimize
the number of enabled features, then break ties by lexical `(set, name)` order.
All unlisted features in a witness are disabled.

## What this does not prove

`EQUIVALENT_IN_PROFILE` means no difference in this deliberately narrow selection
profile, not equivalent installations, reproducibility, dependency satisfaction,
security, or unchanged bytes. No wheel tags are evaluated, no best artifact is
chosen, no hash is verified, and no local/VCS/archive content is read. The same
relative path or URL may name different bytes across lock locations or time.
Changed unused wheel candidates can produce a difference even when a particular
installer would choose the same wheel. Invalid/unsupported artifacts can remain
undetected. Use an installer and artifact checks for those separate questions.

Every declared public feature combination is considered; project-specific
mutual-exclusion rules outside the standard lock fields are not inferred. There
is no inferred dependency graph traversal or repair recommendation.

## Refusals, limits and exit codes

Both locks must use `lock-version="1.0"`, pass `packaging.pylock.Pylock.from_dict`,
and declare identical public extras/groups. Added/removed public feature names
are a contract change requiring separate review, not silently equated with absent
packages. Marker membership may reference only declared public names or synthetic
default groups. Singular `extra`, reversed set tests, set equality, variable-to-
variable/literal-to-literal comparisons and other unsupported spellings are refused.
Only a quoted name `in`/`not in` `extras`/`dependency_groups` is supported for sets.
An undocumented datetime-valued key in a source table, other than a stripped
`upload-time`, can survive the reference validator and then be refused during
JSON candidate-identity serialization (exit 2). It is not silently ignored.
Top-level environment markers must be scalar; an empty `environments` list is
refused. These refusals are not findings that an otherwise valid lock is invalid.

CLI inputs must be regular UTF-8 files, at most 4 MiB each. JSON duplicate keys
are refused. At most 2,000 rows per lock, 128 public feature variables, 4,096
characters/512 tokens/48 nesting levels per marker, and 100,000 BDD nodes per
comparison (adjust with `--max-nodes`). Caps are admission limits, not a hostile-
input sandbox, wall-clock guarantee, or strict memory limit. Some Boolean
functions still grow exponentially and fail the node budget.

One complete JSON document is emitted only after the comparison succeeds.
Exit **0** means `EQUIVALENT_IN_PROFILE` for one target, or
`EQUIVALENT_IN_ALL_TARGETS` for a matrix; **1** means a change, invalid profile,
or `NO_COMMON_PERMITTED_PROFILE`; **2** means unsupported/invalid input, limit,
I/O or output failure. An output failure can leave a partial prefix at its
recipient. Never treat exit 2 as an audit or a negative finding. Two locks that
both reject the target have no common permitted profile, not a vacuous success.

Reports contain the full supplied environment, package names, raw source
candidate declarations (possibly private URLs/paths), feature names, input hashes
and byte counts. Check the audience before sharing; hashes are not anonymization.

## Existing work and evidence

- [PEP 751 specification](https://packaging.python.org/en/latest/specifications/pylock-toml/)
  defines profile selection, default groups and the ambiguity error.
- [packaging.pylock](https://packaging.pypa.io/en/stable/pylock.html) validates
  structure and selects artifacts for **one** profile. This tool uses its public
  validator, plus [Marker](https://packaging.pypa.io/en/stable/markers.html) for
  scalar evaluation; it does not replace its installer-facing selection API.
- [lockdiff's pylock handler](https://docs.rs/crate/lockdiff/latest/source/src/python/pylock.rs)
  parses package inventories. This tool instead asks which feature selections
  are affected by a marker or source-candidate change.
- [nab-markersets](https://nab.readthedocs.io/en/stable/how-to/reason-about-markers.html)
  already provides general marker-set algebra, overlap checks and witnesses.
  This tool is not a claim to invent those operations. It compares two concrete
  lock selections with exact counts over a bounded finite feature domain.
- [pylock-lint](https://github.com/fernforge/pylock-lint) checks artifact-source,
  hash-presence and portability policy. It addresses a different question.
- [pip-tools' proposed pip-lock work](https://github.com/jazzband/pip-tools/pull/2380)
  includes overlap validation and witnesses, not this two-lock profile diff.

The tests exhaust all 256 Boolean functions on three variables, all 196,608
pairwise `and`/`or`/`xor` results, reduced-level counts and minimum witnesses.
Seeded marker and multirow tests compare against public `Marker.evaluate` and
`Pylock.select` on every small-domain assignment. An 80-feature control counts
2^78 changed profiles with fewer than 20 nodes. These are synthetic controls,
not claims of a bug in a real project or evidence of adoption.

```sh
python -m pip install pytest ruff build
PYTHONPATH=src python -m pytest -q
ruff check src tests evidence
ruff format --check src tests evidence
PYTHONPATH=src python evidence/mutation_checks.py
```

See `evidence/QUALIFICATION.md` for the exact tested revision and limits.
MIT licensed.
