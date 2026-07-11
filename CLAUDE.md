# wyred-audit — boundary rules

- Depends on wyred-contract + wyred-harness. **Never imports wyred (the
  engine)**: an audit that consults the engine that produced the artifacts
  is not an audit. Engine runs the audit needs (rebuild re-emit,
  `wyred.crosscheck`) are composed as SUBPROCESSES over the shared
  artifact directory — the composition rule in
  wyred-wz/dev-docs/RunnerSplit.md.
- The harness is consumed as ga019 did: the flat `wyred-harness/harness/`
  dir goes on sys.path (`harnesslib.py`; `--harness-src` /
  `$WYRED_HARNESS_SRC` / sibling checkout).
- `src/wyred_audit/connlock.py::audit_connector_locks` is a deliberate
  independent port of the engine's `paths.check_connector_locks` (the one
  gate the harness does not carry, F5). Keep it in lockstep with
  `wyred/src/wyred/paths.py` — drift turns audits red, by design.
- Consumer-facing: zero-configuration CLI over a directory
  (`python3 -m wyred_audit --tree <dir>`). Future Rust-rewrite candidate
  (single static binary) — keep the interface subprocess-friendly, pure
  stdlib, no new dependencies.
- Test fixtures: goldens + tamper-mutated goldens under `tests/fixtures/`
  (regenerate with `tests/make_fixtures.py`; acceptance:
  `tests/run_fixture_tests.py` — pristine exits 0, every tamper case
  fires its named code). Never hand-edit fixture files.
- README.md lists what IS implemented and what is explicitly deferred;
  keep both lists honest when changing scope.
