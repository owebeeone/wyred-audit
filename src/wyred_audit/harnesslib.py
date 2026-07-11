"""Locate and load the wyred-harness library (flat modules, ga019 style).

wyred-audit MAY import the harness (its CLAUDE.md: depends on
wyred-contract + wyred-harness; NEVER imports wyred, the engine). The
harness is a flat directory of modules (``import allocation``,
``import schema_l1`` — exactly how ga019's runner consumed it), so it is
put on sys.path rather than imported as a package.

Search order:

    1. an explicit ``--harness-src`` argument,
    2. the ``WYRED_HARNESS_SRC`` environment variable,
    3. the sibling checkout ``<wyred-wz>/wyred-harness/harness`` relative
       to this package's own location.

Either the harness dir itself (containing ``allocation.py``) or its repo
root (containing ``harness/allocation.py``) is accepted.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import ModuleType
from typing import Optional, Tuple


class AuditSetupError(RuntimeError):
    """The audit could not be set up (missing harness/engine/inputs)."""


def locate_harness(explicit: Optional[str] = None) -> Path:
    """The harness module directory, or raise AuditSetupError."""
    candidates = []
    if explicit:
        candidates.append(Path(explicit))
    env = os.environ.get("WYRED_HARNESS_SRC")
    if env:
        candidates.append(Path(env))
    # sibling checkout: .../wyred-wz/wyred-audit/src/wyred_audit/harnesslib.py
    candidates.append(
        Path(__file__).resolve().parents[3] / "wyred-harness" / "harness")
    for cand in candidates:
        cand = cand.expanduser().resolve()
        if (cand / "allocation.py").is_file():
            return cand
        if (cand / "harness" / "allocation.py").is_file():
            return cand / "harness"
    raise AuditSetupError(
        "wyred-harness not found (tried: %s) — pass --harness-src or set "
        "WYRED_HARNESS_SRC" % ", ".join(str(c) for c in candidates))


def load_harness(explicit: Optional[str] = None
                 ) -> Tuple[ModuleType, ModuleType]:
    """(allocation, schema_l1) harness modules, path-loaded flat."""
    hdir = locate_harness(explicit)
    if str(hdir) not in sys.path:
        sys.path.insert(0, str(hdir))
    import allocation      # noqa: PLC0415 - flat harness module by design
    import schema_l1       # noqa: PLC0415
    got = Path(allocation.__file__).resolve().parent
    if got != hdir:
        raise AuditSetupError(
            "module 'allocation' resolved to %s, not the requested harness "
            "%s — sys.path is polluted" % (got, hdir))
    return allocation, schema_l1


def locate_engine_pythonpath(engine_src: str) -> Path:
    """The directory to put on a SUBPROCESS's PYTHONPATH so that
    ``python3 -m wyred.emit`` / ``python3 -m wyred.crosscheck`` import the
    engine at ``engine_src``. Accepts the wyred repo root (containing
    ``src/wyred/``) or its src dir (containing ``wyred/``). The audit
    process itself never imports the engine."""
    p = Path(engine_src).expanduser().resolve()
    for cand in (p / "src", p):
        if (cand / "wyred" / "__init__.py").is_file():
            return cand
    raise AuditSetupError(
        "no wyred engine package under %s (expected src/wyred/ or wyred/)"
        % p)


def engine_env(engine_pythonpath: Path) -> dict:
    """A subprocess environment with the engine importable and bytecode
    writing off (the audit must not leave droppings in trees it reads)."""
    env = dict(os.environ)
    prior = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (str(engine_pythonpath) if not prior
                         else "%s%s%s" % (engine_pythonpath, os.pathsep,
                                          prior))
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env
