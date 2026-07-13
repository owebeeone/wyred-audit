# Finding codes

Every problem the audit reports is a **finding**: one line of the form

```text
FAIL <artifact>  <CODE>: <message>
```

where `<artifact>` is the artifact-set name (or `(tree)` for a
directory-wide finding), `<CODE>` is one of the codes below, and `<message>`
explains the specific disagreement. Any finding makes the run exit `1` and
print `AUDIT: FAIL (n finding(s))`; a clean run exits `0` with `AUDIT: PASS`.

Codes are grouped by the stage that raises them (see the
[CLI forms matrix](cli.md#tree-only-vs-full-the-forms-matrix) for which stages
run in which form). Every code is greppable in
`wyred-audit/src/wyred_audit/`. The audit **describes** disagreements; the
authoritative semantics of what a valid artifact, a lock, a fork, or a
cross-path relationship *is* live in `wyred-contract` (`EMIT_CONTRACT.md`,
`schemas/`) and `wyred-harness` — this page links to those, it does not restate
them.

## `[1/5]` schema validation

Raised in `schema_stage.py`. Runs when a contract checkout is discovered.

| code | fires when |
|---|---|
| `SCHEMA_INVALID` | a recognized `<name>.<kind>.json` fails `<kind>.schema.json`. The message carries the first failure's JSON-pointer and keyword, plus a count of any further failures in the same file. |

Shape truth is `wyred-contract/schemas/<kind>.schema.json`; the audit only
drives the contract's own fail-closed validator over the tree.

## `[2/5]` rebuild honesty (whole corpus)

Raised in `rebuild.py`. Runs only in the full form (`--corpus-dir` +
`--engine-src`): the corpus is re-emitted into a temp dir and byte-compared
against the tree, both ways.

| code | fires when |
|---|---|
| `REBUILD_EMIT_FAILED` | the engine re-emit subprocess exited non-zero — the corpus could not be re-emitted at all. |
| `REBUILD_DIFF` | a tree artifact is not byte-identical to the fresh emit of the corpus. |
| `REBUILD_MISSING` | the fresh emit produces an artifact the tree does not hold. |
| `REBUILD_FOREIGN` | the tree holds a `*.json` artifact the fresh emit does not produce. |

## `[3/5]` external-baseline / lifecycle / connlock / ECO

The tree-only heart of the audit, raised across `baselines.py`, `connlock.py`,
and `incumbency.py`. Each record kind is re-derived independently from disk and
compared field by field against what the engine wrote.

### Retained baselines + the lock gate (`baselines.py`)

| code | fires when |
|---|---|
| `BASELINE_DRIFT` | the retained `<name>.baseline.json` is not byte-identical to the harness-library re-derivation (`snapshot_locks` of the l1 plus the alloc's connector rows) — the engine's baseline writer and the harness disagree, or the tree was edited. |
| `BASELINE_MISSING` | a document carries locked groups (version ≥ 1) but no baseline was retained — the lock state is unverifiable. |
| `BASELINE_ORPHANED` | a retained baseline has no matching `<name>.l1.json` in the tree. |
| `LOCK_VIOLATION` | a locked decision changed without a fork. **Harness code**, surfaced from `allocation.check_lock_violations`. |
| `SERIES_UNJUSTIFIED` | the series string was hand-edited with no `forked_from` record to justify it. **Harness code**, surfaced from the same gate. |

`LOCK_VIOLATION` / `SERIES_UNJUSTIFIED` are defined by `wyred-harness`
(`allocation.py`); the audit reports whatever that gate returns.

### Lifecycle / fork records (`baselines.py`)

| code | fires when |
|---|---|
| `LIFECYCLE_DISAGREE` | a field of `<name>.lifecycle.json` differs from the harness re-derivation from disk (legal-fork codes, both tamper probes, stamps, or `ok`). |
| `LIFECYCLE_NOT_OK` | the re-derived fork verdict is not ok, regardless of what the record's `ok` field claims. |
| `LIFECYCLE_PARENT_BASELINE_MISSING` | the fork parent named by the record retained no external baseline, so the fork cannot be verified. |

### Connector-lock records (`connlock.py`)

The connector-pinout gate is the audit's own independent port of the engine's
`paths.check_connector_locks` (the one gate the harness does not carry).

| code | fires when |
|---|---|
| `CONNLOCK_DISAGREE` | a field of `<name>.connlock.json` differs from the audit's independent re-derivation from disk. |
| `CONNLOCK_NOT_OK` | the re-derived connector-lock verdict is not ok. |
| `CONNLOCK_BASELINE_MISSING` | a connlock record exists but no baseline was retained — the connector-lock state is unverifiable. |
| `CONNECTOR_LOCK_VIOLATION` | a locked connector-pinout row's net changed, or the row disappeared, without a series bump. |
| `CONNECTOR_SERIES_UNJUSTIFIED` | the connector series differs from the baseline series with no `forked_from` record naming it. |

### ECO / minimal-disturbance records (`incumbency.py`)

Independent ports of the engine's `paths.diff_pinmaps` and
`emit._check_incumbency` — the counter-check that keeps a self-certified
`minimal_disturbance_violations` verdict honest.

| code | fires when |
|---|---|
| `PINMAPDIFF_DISAGREE` | a field of `<name>.pinmapdiff.json` differs from the audit's independent re-derivation (allocation diff, terminal changes, component sets, or the violation list). |
| `MINIMAL_DISTURBANCE_NOT_OK` | the re-derived incumbency check finds a non-empty violation list (a solver-chosen allocation moved though its unit stayed free), regardless of what the record claims. |
| `PINMAPDIFF_INCUMBENT_MISSING` | the record names no incumbent artifact, or the pinmap/alloc pairs needed to re-derive the ECO verdict are missing from the tree. |

### Shared

| code | fires when |
|---|---|
| `UNREADABLE` | an artifact in a set could not be read or parsed as JSON. Raised by any of the `[3/5]` checkers when the set it needs is corrupt. |

## `[4/5]` from-primaries rebuild

Raised in `rebuild.py`. Runs with `--engine-src` (no corpus needed):
`python3 -m wyred.rebuild --dir <tree> --all` as a subprocess.

| code | fires when |
|---|---|
| `REBUILD_FROM_PRIMARIES` | a secondary path (bom / pinmap / records) does not rebuild byte-identically from the on-disk primaries alone (l2 + alloc + l1), or the rebuild CLI failed outright. |

This is the byte-level check that catches payload tampers no semantic gate
reads — see the [worked contrast](#tree-only-vs-full-a-worked-contrast).

## `[5/5]` engine crosscheck

Raised in `crosscheckrun.py`. Runs with `--engine-src`:
`python3 -m wyred.crosscheck --dir <tree> --all` as a subprocess.

| code | fires when |
|---|---|
| `CROSSCHECK_FAILED` | the engine's from-disk cross-path differential fired. The message carries the engine's **own** code (for example `XPATH_BOM_FIELDS`), so the audit's finding names both `CROSSCHECK_FAILED` and the underlying engine code. |
| `CROSSCHECK_UNREADABLE` | the `wyred.crosscheck` subprocess exited with an unexpected status (not 0 and not the clean-failure exit 1). |

The engine differential's own vocabulary (`XPATH_*` and friends) is defined by
`wyred` and re-run here as a subprocess; the audit does not redefine it.

## Worked examples

The `wyred-audit/tests/fixtures/tampered/` tree holds golden artifact sets each
mutated in exactly one place to fire one named code. They make honest, runnable
demonstrations. (Tree-only unless noted; the harness and contract are found as
siblings.)

A forged connlock verdict — the record claims `ok: false`, the audit's
independent re-derivation says otherwise:

<!-- cwd: wyred-audit -->
<!-- pythonpath: wyred-audit/src -->
```console
$ python3 -m wyred_audit --tree tests/fixtures/tampered/connlock_ok_flip 2>&1 | grep -m1 CONNLOCK_DISAGREE || true
# expect: CONNLOCK_DISAGREE
```

A locked allocation row edited in place — the retained baseline no longer
matches (`BASELINE_DRIFT`) and the harness lock gate fires (`LOCK_VIOLATION`):

<!-- cwd: wyred-audit -->
<!-- pythonpath: wyred-audit/src -->
```console
$ python3 -m wyred_audit --tree tests/fixtures/tampered/locked_row_edit 2>&1 | grep -m1 LOCK_VIOLATION || true
# expect: LOCK_VIOLATION
```

A sticky allocation moved to a free unit while the ECO record still claims no
disturbance — the minimal-disturbance counter-check catches it:

<!-- cwd: wyred-audit -->
<!-- pythonpath: wyred-audit/src -->
```console
$ python3 -m wyred_audit --tree tests/fixtures/tampered/sticky_alloc_moved 2>&1 | grep -m1 MINIMAL_DISTURBANCE_NOT_OK || true
# expect: MINIMAL_DISTURBANCE_NOT_OK
```

A shape defect — a required `qty` key deleted from a BOM line item — caught by
the optional schema stage:

<!-- cwd: wyred-audit -->
<!-- pythonpath: wyred-audit/src -->
```console
$ python3 -m wyred_audit --tree tests/fixtures/tampered/schema_bom_missing_qty 2>&1 | grep -m1 SCHEMA_INVALID || true
# expect: SCHEMA_INVALID
```

## Tree-only vs. full: a worked contrast

Not every tamper is visible to every form. The `bom_value_swap` fixture swaps
two BOM line-item payloads while keeping sets and counts legal — so the
tree-only semantic gates see nothing wrong, and the audit **passes**:

<!-- cwd: wyred-audit -->
<!-- pythonpath: wyred-audit/src -->
```console
$ python3 -m wyred_audit --tree tests/fixtures/tampered/bom_value_swap | tail -1
AUDIT: PASS (0 finding(s))
# expect: AUDIT: PASS
```

Add `--engine-src` and the same tree fails: the from-primaries rebuild
(`REBUILD_FROM_PRIMARIES`) finds the bytes no longer rebuild from the
primaries, and the engine crosscheck (`CROSSCHECK_FAILED`, carrying
`XPATH_BOM_FIELDS`) finds the BOM disagreeing with the netlist:

<!-- cwd: wyred-audit -->
<!-- pythonpath: wyred-audit/src -->
```console
$ python3 -m wyred_audit --tree tests/fixtures/tampered/bom_value_swap --engine-src ../wyred 2>&1 | grep -m1 CROSSCHECK_FAILED || true
# expect: CROSSCHECK_FAILED
```

This is the whole point of the [consumer forms](index.md#consumer-forms): the
more of the trust chain a consumer retains (an engine checkout, the source
corpus, out-of-tree baselines), the more classes of tamper the audit can catch.
A tree-only audit is honest about being tree-only — it loudly skips the stages
it cannot run.

The full tamper-case catalog — every fixture, its one mutation, and the exact
code(s) it must fire — is maintained alongside the fixtures in
`wyred-audit/tests/fixtures/README.md`.
