# CLI reference

`wyred-audit` is invoked as a module over a directory. It takes no
configuration file and writes nothing into the tree it reads.

```
python3 -m wyred_audit --tree ARTIFACT_DIR [options]
```

The console-script entry point `wyred-audit` (declared in `pyproject.toml`) is
equivalent to `python3 -m wyred_audit` once the package is installed.

## Synopsis

<!-- cwd: wyred-audit -->
<!-- pythonpath: wyred-audit/src -->
```console
$ python3 -m wyred_audit --help
usage: wyred_audit [-h] --tree ARTIFACT_DIR [--corpus-dir DIR]
                   [--engine-src PATH] [--baseline-dir DIR]
                   [--harness-src PATH] [--contract-src PATH] [--verbose]
# expect: usage: wyred_audit
# expect: --tree ARTIFACT_DIR
# expect: --corpus-dir
```

## Flags

Every flag below is defined in `wyred-audit/src/wyred_audit/cli.py`.

| flag | argument | what it does |
|---|---|---|
| `--tree` | `ARTIFACT_DIR` | **required.** The artifact directory to audit — a `wyred.emit --out` dir, or a consumer's retained copy. |
| `--corpus-dir` | `DIR` | The source corpus package dir. Enables whole-corpus rebuild honesty `[2/5]`. Requires `--engine-src`. |
| `--engine-src` | `PATH` | A `wyred` engine checkout (repo root or `src/`). Enables from-primaries rebuild `[4/5]` and the engine crosscheck `[5/5]`, both run as **subprocesses**. |
| `--baseline-dir` | `DIR` | Read retained `*.baseline.json` files from a separate directory instead of the tree (defends against a coordinated artifact-plus-in-tree-baseline rewrite). Default: the tree. |
| `--harness-src` | `PATH` | A `wyred-harness` checkout. Default: `$WYRED_HARNESS_SRC` or the sibling checkout. |
| `--contract-src` | `PATH` | A `wyred-contract` checkout (schemas + validator). Enables the schema stage `[1/5]`. Default: `$WYRED_CONTRACT_SRC` or the sibling; warn-and-skip when none is found. |
| `--verbose` | — | Echo the subprocess emit output during rebuild honesty. |

`--corpus-dir` without `--engine-src` is a setup error (exit `2`): the
whole-corpus rebuild has nothing to re-emit with.

## Dependency discovery

The audit depends on two sibling members and locates each with the same
three-tier search (explicit flag → environment variable → sibling checkout):

- **`wyred-harness` — hard dependency.** The harness supplies the allocation
  oracle the tree-only stages re-derive against. If it cannot be found the
  audit exits `2`. Search order: `--harness-src`, then `$WYRED_HARNESS_SRC`,
  then the sibling `wyred-harness/harness/` checkout.
- **`wyred-contract` — optional dependency.** Supplies the schemas and the
  fail-closed subset validator for stage `[1/5]`. If none is found the stage
  warns and skips (a consumer holding only artifacts still audits everything
  else). Search order: `--contract-src`, then `$WYRED_CONTRACT_SRC`, then the
  sibling `wyred-contract/` checkout.

Only `$WYRED_HARNESS_SRC` and `$WYRED_CONTRACT_SRC` are read by the CLI. There
is no engine environment variable — the engine is supplied only via
`--engine-src`, and only ever as a subprocess target.

## Tree-only vs. full: the forms matrix

Which stages run is a pure function of which inputs you supply. `RUN` means the
stage executes; `skip` means it prints a `WARN … SKIPPED` line and moves on.

| stage | `--tree` only | `+ --engine-src` | `+ --corpus-dir --engine-src` (full) |
|---|---|---|---|
| `[1/5]` schema validation | RUN¹ | RUN¹ | RUN¹ |
| `[2/5]` rebuild honesty (corpus) | skip | skip | RUN |
| `[3/5]` external-baseline / lifecycle / connlock / ECO | RUN | RUN | RUN |
| `[4/5]` from-primaries rebuild | skip | RUN | RUN |
| `[5/5]` engine crosscheck | skip | RUN | RUN |

¹ `[1/5]` runs whenever a contract checkout is discovered — including in the
tree-only form, because the sibling `wyred-contract/` is found by default. Pass
`--contract-src`/`$WYRED_CONTRACT_SRC` to pin a specific checkout, or run
somewhere no contract is reachable to see the warn-and-skip.

### The engine form (`--engine-src`, no corpus)

Adds the from-primaries rebuild `[4/5]` and engine crosscheck `[5/5]` without
needing the source corpus — the "artifacts plus an engine checkout" consumer
story. On the honest `pristine/` tree it still exits `0`:

<!-- cwd: wyred-audit -->
<!-- pythonpath: wyred-audit/src -->
```console
$ python3 -m wyred_audit --tree tests/fixtures/pristine --engine-src ../wyred
...
[4/5] from-primaries rebuild (python3 -m wyred.rebuild --all)
PASS from-primaries: every secondary path (bom/pinmap/records) rebuilds byte-identically from the on-disk primaries alone
...
AUDIT: PASS (0 finding(s))
# expect: [4/5] from-primaries rebuild
# expect: PASS from-primaries:
# expect: AUDIT: PASS
```

### The full form (`--corpus-dir --engine-src`)

Adds whole-corpus rebuild honesty `[2/5]`: the corpus is re-emitted by the
engine into a temp dir and every `*.json` is byte-compared against the tree,
both ways. This needs a tree that **is** a full corpus emit, so the example
below emits one first (into a throwaway dir), then audits it. This is the
mechanism `wyred-examples/run_gate.py` composes as its audit stage.

<!-- cwd: wyred-examples -->
<!-- pythonpath: wyred-audit/src -->
```console
$ OUT=$(mktemp -d)
$ PYTHONPATH=../wyred/src python3 -m wyred.emit --corpus-dir corpus --out "$OUT" >/dev/null
$ python3 -m wyred_audit --tree "$OUT" --corpus-dir corpus --engine-src ../wyred
$ rm -rf "$OUT"
# expect: [2/5] rebuild honesty
# expect: PASS rebuild: every *.json artifact is byte-identical
# expect: AUDIT: PASS
```

The canonical full invocation, as wired into the gate, reads (paths relative to
`wyred-examples/`, where `out/` is the engine's emit from an earlier stage):

```bash
python3 -m wyred_audit --tree out --corpus-dir corpus --engine-src ../wyred
```

## Composition, never import

The two engine stages shell out — `python3 -m wyred.emit`,
`python3 -m wyred.rebuild`, `python3 -m wyred.crosscheck` — with the engine put
on the subprocess `PYTHONPATH` from `--engine-src`. The audit process itself
imports only `wyred-harness` and (for `[1/5]`) the `wyred-contract` validator,
never `wyred`. This is the composition rule from
`wyred-wz/dev-docs/RunnerSplit.md`; keeping the interface subprocess-friendly is
also what keeps a future single-binary rewrite on the table.
