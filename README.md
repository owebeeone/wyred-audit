# wyred-audit — the one-command consumer-side audit tool

Rebuild honesty (whole-corpus and from-primaries) + external-baseline/
lifecycle/connlock/ECO-pinmapdiff verification + engine crosscheck over a
wyred artifact directory. The consumer-trust half of elecscad ga019's
`runner.py`, per `wyred-wz/dev-docs/RunnerSplit.md`.

The audit **never imports the engine** (`wyred`): every verdict is computed
from artifacts re-read from disk, using the wyred-harness library plus the
audit's own independent checkers. Where an engine run is required it is
composed as a **subprocess** over the shared artifact directory
(`python3 -m wyred.emit`, `python3 -m wyred.crosscheck`) — composition at
the process level, never by import.

## Usage

```sh
# consumer form: artifacts only (rebuilds + crosscheck skipped, warned)
python3 -m wyred_audit --tree <artifact-dir>

# artifacts + engine, no corpus: adds the from-primaries rebuild + crosscheck
python3 -m wyred_audit --tree <artifact-dir> --engine-src <wyred-checkout>

# full audit: corpus rebuild honesty + baseline verification +
# from-primaries rebuild + engine crosscheck
python3 -m wyred_audit --tree <artifact-dir> \
    --corpus-dir <corpus> --engine-src <wyred-checkout>

# verify against a separately retained baseline copy (the trust anchor)
python3 -m wyred_audit --tree <artifact-dir> --baseline-dir <dir>
```

Exit 0 iff every check passed; 1 on any finding; 2 on a setup error. The
harness is located via `--harness-src`, `$WYRED_HARNESS_SRC`, or the
sibling `wyred-harness/` checkout.

## What is implemented

1. **Rebuild honesty** (`--corpus-dir` + `--engine-src`): the corpus is
   re-emitted by the engine — as a subprocess — into a temp dir, and every
   `*.json` artifact is byte-compared against the tree, both ways
   (`REBUILD_DIFF` / `REBUILD_MISSING` / `REBUILD_FOREIGN` /
   `REBUILD_EMIT_FAILED`). Skipped with a warning when `--corpus-dir` is
   absent — a consumer may hold artifacts only.
2. **External-baseline verification — the F3 counter-check.** The engine
   retains a `<name>.baseline.json` at every locked emit, written by its
   own dict port of the harness lock helpers (`wyred/src/wyred/emit.py`).
   The audit re-derives that snapshot independently —
   `harness.allocation.snapshot_locks` over `schema_l1.from_json(l1)` plus
   the alloc artifact's connector rows — and byte-compares
   (`BASELINE_DRIFT` on any disagreement between the two implementations
   or any tree edit). Every baselined artifact is then gated with
   `harness.allocation.check_lock_violations`: a locked-row edit without a
   fork fires `LOCK_VIOLATION`; a hand-edited series fires
   `SERIES_UNJUSTIFIED`. Locked documents with no retained baseline are
   `BASELINE_MISSING`; orphaned baselines are `BASELINE_ORPHANED`.
3. **Lifecycle re-verification** (runner.py:716-771, from disk): every
   `<name>.lifecycle.json` fork record's legal-fork codes and both tamper
   counter-probes (forked_from stripped → `SERIES_UNJUSTIFIED`; locked
   parent decision edited in place → `LOCK_VIOLATION`) are re-derived via
   the harness and compared field by field (`LIFECYCLE_DISAGREE`,
   `LIFECYCLE_NOT_OK`, `LIFECYCLE_PARENT_BASELINE_MISSING`).
4. **Connector-lock re-verification** (runner.py:779-840, from disk):
   every `<name>.connlock.json` is re-derived with the audit's own
   independent port of the connector-lock gate (`wyred_audit/connlock.py`;
   the engine's `paths.check_connector_locks` cannot be imported here) and
   compared field by field (`CONNLOCK_DISAGREE`, `CONNLOCK_NOT_OK`,
   `CONNLOCK_BASELINE_MISSING`).
5. **ECO / minimal-disturbance re-verification — the R1 counter-check**
   (runner.py:685-711, from disk): every `<name>.pinmapdiff.json` is
   re-derived with the audit's own independent ports of the engine's
   `paths.diff_pinmaps` and `emit._check_incumbency`
   (`wyred_audit/incumbency.py`; keep in lockstep — drift turns audits
   red, by design) from the incumbent's pinmap+alloc (the record's own
   `incumbents` field names it) and the artifact's pinmap+alloc, and
   compared field by field — `minimal_disturbance_violations` included,
   so a lobotomized engine-side incumbency check no longer stays green
   (`PINMAPDIFF_DISAGREE`, `MINIMAL_DISTURBANCE_NOT_OK`,
   `PINMAPDIFF_INCUMBENT_MISSING`).
6. **From-primaries rebuild honesty — the R2 stage** (`--engine-src`,
   corpus-less): `python3 -m wyred.rebuild --dir <tree> --all` as a
   subprocess — every artifact set's secondary paths (bom/pinmap/records)
   must rebuild byte-identically from its on-disk primaries alone
   (l2 + alloc + l1); mismatches and CLI failures are
   `REBUILD_FROM_PRIMARIES`. Unlike check 1 this needs NO corpus — the
   consumer story: artifacts + an engine checkout suffice.
7. **Engine crosscheck** (`--engine-src`): `python3 -m wyred.crosscheck
   --dir <tree> --all` as a subprocess — the engine's own from-disk
   cross-path differential + connector-lock gate; failures are echoed as
   `CROSSCHECK_FAILED` findings carrying the engine's codes.
8. **Fixtures** (`tests/fixtures/`): pristine golden sets + eight
   tamper-mutated variants, each firing its named code (and, where the
   point is isolation, NOT firing a forbidden one); acceptance runner
   `tests/run_fixture_tests.py`, regenerator `tests/make_fixtures.py`.

## Explicitly deferred (not implemented here)

- **The harness gate driver** (L1 oracle gating, v3 stack, XPATH probe
  battery, determinism double-emit): that is wyred-harness's half of the
  runner split, not the audit's — BUILT at `wyred-harness/harness/gate.py`;
  see RunnerSplit.md.
- **Coordinated re-baselining detection**: an attacker who rewrites the
  artifacts AND the in-tree baseline consistently is only caught when the
  consumer retains baselines out-of-tree (`--baseline-dir`) or supplies
  the corpus for rebuild honesty; the retention discipline itself is the
  consumer's.
- **Connlock-missing detection**: a fork child whose connector groups stay
  locked but that did not re-freeze writes no connlock record; freeze
  membership is not recoverable from disk, so its absence is not flagged.
- **Tree-only lineage forgery (pinmapdiff)**: the tree-only audit trusts the
  pinmapdiff record's own `incumbents` field, so a self-consistent post-emit
  forgery (record rewritten to name itself as incumbent, with vacuously empty
  diffs) passes tree-only; the full-form audit (`--corpus-dir`) catches it via
  rebuild honesty (`REBUILD_DIFF`). Same trust shape as coordinated
  re-baselining above: lineage anchoring is the consumer's retention job.
- **Connlock `groups` derivation asymmetry (R4, fails closed)**: the audit
  re-derives a connlock record's `groups` as the l1's lock groups covering
  `connector_pinout` at version >= 1, while the engine recorded the groups
  it FROZE at that emit (freeze ∩ covers) — freeze membership is not on
  disk. An inherited locked connector group that was not re-frozen at an
  emit would make the audit's set larger and fire a spurious
  `CONNLOCK_DISAGREE`: a false alarm, never a missed tamper. No corpus
  artifact exercises that shape today; accepted and recorded.
- **Board-agreement probes** (watchy/mppt): GATE-WIRED in wyred-examples.
