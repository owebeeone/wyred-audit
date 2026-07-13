# wyred-audit — the consumer-side audit

`wyred-audit` is the one-command, consumer-trust audit over a wyred artifact
directory. Point it at a tree of emitted `*.json` artifacts and it re-derives
every trust-bearing verdict **from disk** — using the `wyred-harness` library
plus the audit's own independent checkers — and tells you whether the tree is
honest.

The one invariant that makes it an audit: **it never imports the engine
(`wyred`).** An audit that consults the tool that produced the artifacts is not
an audit. Where an engine run is genuinely needed (re-emitting the corpus,
running the engine's own cross-path differential) it is composed as a
**subprocess** over the shared directory, never by import. The full rationale
and the exact list of what is and isn't covered live in the member's own
`wyred-audit/README.md` and in `wyred-wz/dev-docs/RunnerSplit.md`; this page
explains and links, it does not restate them.

These reference pages:

- **[CLI reference](cli.md)** — every flag, the discovery rules, and the
  tree-only vs. full **forms** matrix.
- **[Finding codes](finding-codes.md)** — every code the audit can emit, what
  it means, and what makes it fire (with runnable worked examples).

## What it checks

The audit runs five stages and prints a `[n/5]` banner for each. Stages that
need an input you didn't supply are **loudly skipped**, never silently passed:

| stage | proves | enabled by |
|---|---|---|
| `[1/5]` schema validation | every recognized artifact matches its `wyred-contract` draft-2020-12 schema | a contract checkout (`--contract-src`, `$WYRED_CONTRACT_SRC`, or the sibling) — else warn-and-skip |
| `[2/5]` rebuild honesty | every artifact is byte-identical to a fresh engine re-emit of the source corpus | `--corpus-dir` + `--engine-src` — else warn-and-skip |
| `[3/5]` external-baseline verification | retained baselines, lock gates, lifecycle/connlock/ECO records agree with an independent re-derivation | always (the harness is a hard dependency) |
| `[4/5]` from-primaries rebuild | every secondary path (bom/pinmap/records) rebuilds byte-identically from the on-disk primaries alone | `--engine-src` — else warn-and-skip |
| `[5/5]` engine crosscheck | the engine's own from-disk cross-path differential fires no codes | `--engine-src` — else warn-and-skip |

Stage `[3/5]` is the heart of the tree-only audit: it needs nothing but the
artifacts and the harness library. The exact record kinds it re-derives —
`baseline`, `lifecycle`, `connlock`, `pinmapdiff` — and the semantics of each
are defined by `wyred-contract` (`EMIT_CONTRACT.md` + `schemas/`); see
[Finding codes](finding-codes.md) for the per-record codes.

## Consumer forms

A consumer holds different things depending on how much of the trust chain they
retain. The audit degrades gracefully across four escalating forms — each adds
stages without removing any:

| form | invocation | adds over the previous form |
|---|---|---|
| tree-only | `--tree DIR` | schema `[1/5]` (if a contract is found) + baseline/lifecycle/connlock/ECO `[3/5]` |
| + engine | `--tree DIR --engine-src WYRED` | from-primaries `[4/5]` + engine crosscheck `[5/5]` |
| + corpus (full) | `--tree DIR --corpus-dir CORPUS --engine-src WYRED` | whole-corpus rebuild honesty `[2/5]` |
| + retained baseline | any of the above `--baseline-dir DIR` | reads baselines from a separately-kept directory (the trust anchor against a coordinated in-tree rewrite) |

**Tree-only is a real audit, but it trusts what it cannot re-derive without the
engine.** A consumer who holds only artifacts still verifies every locked
decision, fork, connector lock and ECO record against an independent
re-derivation — but it cannot catch a tamper that only shows up when a
secondary path is rebuilt byte-for-byte from primaries, or against a fresh emit
of the source corpus. Those are exactly the `[2/5]`/`[4/5]`/`[5/5]` stages the
engine forms add. [Finding codes](finding-codes.md#tree-only-vs-full-a-worked-contrast)
shows a tamper that tree-only misses and the full form catches.

The canonical **full** invocation, wired into the end-to-end gate, is stage 3
of `wyred-examples/run_gate.py` — that is the composition to copy for CI.

## Exit codes

| code | meaning |
|---|---|
| `0` | every stage that ran passed — `AUDIT: PASS` |
| `1` | at least one finding — `AUDIT: FAIL (n finding(s))` |
| `2` | a setup error (bad `--tree`, missing harness, unusable schema set) — nothing was audited |

Exit `2` is distinct from exit `1` on purpose: a setup error means the audit
could not run, not that the tree is dishonest. Treat `2` as "fix the
invocation", `1` as "investigate the findings".

## Hello, audit

The audit ships golden fixtures under `wyred-audit/tests/fixtures/`. The
`pristine/` tree is an honest, partial artifact set; a tree-only audit of it
passes. (These blocks run from the `wyred-audit` repo with the package on
`PYTHONPATH`; the harness and contract are found as sibling checkouts.)

<!-- cwd: wyred-audit -->
<!-- pythonpath: wyred-audit/src -->
```console
$ python3 -m wyred_audit --tree tests/fixtures/pristine
== wyred-audit: tests/fixtures/pristine (5 artifact set(s), 3 retained baseline(s)) ==
...
AUDIT: PASS (0 finding(s))
# expect: [1/5] schema validation
# expect: PASS baselines:
# expect: AUDIT: PASS
```
