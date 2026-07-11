"""Directory crosscheck — the engine's from-disk differential, subprocess.

``python3 -m wyred.crosscheck --dir <tree> --all`` re-runs the cross-path
differential (netlist <-> BOM <-> pin-map <-> records <-> l1) and the
engine-side connector-lock gate over every artifact set, entirely from
disk. The audit composes it as a SUBPROCESS (never an import — the
composition rule in wyred-wz/dev-docs/RunnerSplit.md): each failure line
the engine prints (``<artifact> <CODE>: <msg>``) is echoed as a
CROSSCHECK_FAILED finding carrying the engine's code.

Codes: CROSSCHECK_FAILED, CROSSCHECK_UNREADABLE.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Dict, List

from wyred_audit.harnesslib import engine_env, locate_engine_pythonpath


def check_crosscheck(tree: Path, engine_src: str) -> List[Dict[str, str]]:
    """Structured failures {"artifact", "code", "msg"}; empty == clean."""
    fails: List[Dict[str, str]] = []
    env = engine_env(locate_engine_pythonpath(engine_src))
    proc = subprocess.run(
        [sys.executable, "-m", "wyred.crosscheck",
         "--dir", str(tree), "--all"],
        env=env, capture_output=True, text=True)
    if proc.returncode == 0:
        return fails
    if proc.returncode == 1:
        for line in proc.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            artifact = line.split(" ", 1)[0]
            fails.append({"artifact": artifact, "code": "CROSSCHECK_FAILED",
                          "msg": line})
        if not fails:
            fails.append({"artifact": "", "code": "CROSSCHECK_FAILED",
                          "msg": "wyred.crosscheck exited 1 with no "
                                 "failure lines: %s" % proc.stderr.strip()})
        return fails
    fails.append({
        "artifact": "", "code": "CROSSCHECK_UNREADABLE",
        "msg": "wyred.crosscheck exited %d: %s"
               % (proc.returncode, (proc.stderr or proc.stdout).strip())})
    return fails
