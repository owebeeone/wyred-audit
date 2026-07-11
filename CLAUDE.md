# wyred-audit — boundary rules

- Depends on wyred-contract + wyred-harness. Never imports wyred (the engine): an audit that consults the engine that produced the artifacts is not an audit.
- Consumer-facing: zero-configuration CLI over a directory. Future Rust-rewrite candidate (single static binary) — keep the interface subprocess-friendly.
- Test fixtures: goldens + tamper-mutated goldens.
