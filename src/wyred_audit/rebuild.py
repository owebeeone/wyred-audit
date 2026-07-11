"""Rebuild honesty — engine SUBPROCESS re-derivations, byte-compared.

Two distinct disk-honesty properties, both composed as subprocesses
(never imports — the composition rule in wyred-wz/dev-docs/RunnerSplit.md):

``check_rebuild`` — the consumer-trust generalization of ga019 runner.py's
whole-corpus check: the WHOLE corpus is re-emitted by the engine into a
temp directory — ``python3 -m wyred.emit`` as a subprocess — and EVERY
``*.json`` artifact is compared byte-for-byte against the audited tree,
both ways. Needs ``--corpus-dir`` + ``--engine-src``; proves emit
determinism against the SOURCE corpus:

    REBUILD_EMIT_FAILED  the engine re-emit exited nonzero
    REBUILD_DIFF         a tree artifact differs from the fresh emit
    REBUILD_MISSING      the fresh emit produced an artifact the tree lacks
    REBUILD_FOREIGN      the tree holds a *.json artifact the fresh emit
                         did not produce

``check_rebuild_from_primaries`` — the direct port of ga019
runner.py:554-574's FROM-PRIMARIES disk-honesty check (the R2 residual):
``python3 -m wyred.rebuild --dir <tree> --all`` re-derives every artifact
set's SECONDARY paths (bom/pinmap/records) from its on-disk PRIMARY
artifacts alone (l2 + alloc + l1) and byte-compares. Needs only
``--engine-src`` and the tree — NO corpus — so a consumer holding
artifacts alone can prove the secondaries are pure functions of the
on-disk primaries:

    REBUILD_FROM_PRIMARIES  a secondary path does not rebuild
                            byte-identically from the primaries (or the
                            engine rebuild CLI failed outright)

Non-JSON files in the tree are outside the emit contract and ignored.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List

from wyred_audit.harnesslib import engine_env, locate_engine_pythonpath


def check_rebuild(tree: Path, corpus_dir: Path, engine_src: str,
                  verbose: bool = False) -> List[Dict[str, str]]:
    """Structured failures {"artifact", "code", "msg"}; empty == honest."""
    fails: List[Dict[str, str]] = []
    env = engine_env(locate_engine_pythonpath(engine_src))
    with tempfile.TemporaryDirectory(prefix="wyred-audit-reemit-") as tmp:
        proc = subprocess.run(
            [sys.executable, "-m", "wyred.emit",
             "--corpus-dir", str(corpus_dir), "--out", tmp],
            env=env, capture_output=True, text=True)
        if verbose and proc.stdout:
            print(proc.stdout, end="")
        if proc.returncode != 0:
            fails.append({
                "artifact": "", "code": "REBUILD_EMIT_FAILED",
                "msg": "engine re-emit exited %d: %s"
                       % (proc.returncode,
                          (proc.stderr or proc.stdout).strip()[-2000:])})
            return fails
        fresh = {p.name: p for p in Path(tmp).glob("*.json")}
        held = {p.name: p for p in tree.glob("*.json")}
        for name in sorted(set(fresh) | set(held)):
            if name not in held:
                fails.append({
                    "artifact": name, "code": "REBUILD_MISSING",
                    "msg": "a fresh engine emit produces %s but the tree "
                           "does not hold it" % name})
            elif name not in fresh:
                fails.append({
                    "artifact": name, "code": "REBUILD_FOREIGN",
                    "msg": "the tree holds %s but a fresh engine emit does "
                           "not produce it" % name})
            elif fresh[name].read_bytes() != held[name].read_bytes():
                fails.append({
                    "artifact": name, "code": "REBUILD_DIFF",
                    "msg": "%s is not byte-identical to a fresh engine "
                           "emit of the corpus" % name})
    return fails


def check_rebuild_from_primaries(tree: Path, engine_src: str
                                 ) -> List[Dict[str, str]]:
    """Structured failures {"artifact", "code", "msg"}; empty == every
    secondary path rebuilds byte-identically from the on-disk primaries.

    ``python3 -m wyred.rebuild --dir <tree> --all`` prints one line per
    mismatch (``FAIL <artifact> <path> does not rebuild ...``) and exits
    0 iff clean; each line is echoed as a REBUILD_FROM_PRIMARIES finding,
    and any other nonzero exit (missing/unreadable set, no sets at all)
    folds into one finding carrying the CLI's own message."""
    fails: List[Dict[str, str]] = []
    env = engine_env(locate_engine_pythonpath(engine_src))
    proc = subprocess.run(
        [sys.executable, "-m", "wyred.rebuild",
         "--dir", str(tree), "--all"],
        env=env, capture_output=True, text=True)
    if proc.returncode == 0:
        return fails
    if proc.returncode == 1:
        for line in proc.stdout.splitlines():
            line = line.strip()
            if not line.startswith("FAIL "):
                continue
            parts = line.split()
            artifact = parts[1] if len(parts) > 1 else ""
            fails.append({
                "artifact": artifact, "code": "REBUILD_FROM_PRIMARIES",
                "msg": " ".join(parts[1:])})
        if not fails:
            fails.append({
                "artifact": "", "code": "REBUILD_FROM_PRIMARIES",
                "msg": "wyred.rebuild exited 1 with no FAIL lines: %s"
                       % proc.stderr.strip()})
        return fails
    fails.append({
        "artifact": "", "code": "REBUILD_FROM_PRIMARIES",
        "msg": "wyred.rebuild exited %d: %s"
               % (proc.returncode, (proc.stderr or proc.stdout).strip())})
    return fails
