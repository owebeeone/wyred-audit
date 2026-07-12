"""Locate the wyred-contract checkout and load its schema-validator library.

wyred-audit MAY import wyred-contract (its CLAUDE.md: depends on
wyred-contract + wyred-harness; NEVER imports wyred, the engine). The
contract ships ``tools/validate.py`` — a dependency-free, purpose-built
draft-2020-12 *subset* validator (Step 1.2 of
dev-docs/WyredPlanContractSchemas.md) that drives the ten
``schemas/<kind>.schema.json`` files. That validator is SHARED CONTRACT
INFRASTRUCTURE, not the producer under audit (``wyred``), so the harness
precedent applies: import it as a **library** rather than spawn it once
per file (107 goldens would be 107 subprocess spawns). The ``tools``
CLI stays subprocess-usable for the future Rust-rewrite path noted in
wyred-audit's CLAUDE.md; the in-process import is only wyred-audit's
preference.

Search order (mirrors ``harnesslib.locate_harness``):

    1. an explicit ``--contract-src`` argument,
    2. the ``WYRED_CONTRACT_SRC`` environment variable,
    3. the sibling checkout ``<wyred-wz>/wyred-contract`` relative to this
       package's own location.

A candidate qualifies when it holds BOTH ``tools/validate.py`` and a
``schemas/`` directory. Unlike the harness (a HARD dependency: missing =>
setup error/exit 2), the schema stage is OPTIONAL, so ``locate_contract``
returns ``None`` when nothing is found — the caller warns and skips, the
same degradation as the corpus-less rebuild skip (a consumer that holds
only artifacts still audits everything else).
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType
from typing import Optional

from wyred_audit.harnesslib import AuditSetupError

_VALIDATOR_MODULE_NAME = "wyred_contract_validate"


def _qualifies(cand: Path) -> bool:
    """A directory is a usable contract checkout iff it carries the subset
    validator and the schema set the validator drives."""
    return ((cand / "tools" / "validate.py").is_file()
            and (cand / "schemas").is_dir())


def locate_contract(explicit: Optional[str] = None) -> Optional[Path]:
    """The wyred-contract checkout root, or ``None`` if none is found.

    ``None`` is NOT an error here: the schema stage degrades to a
    warn-and-skip so consumer-form audits (artifacts only, no contract
    checkout) keep working — the plan's required degradation pattern.
    """
    candidates = []
    if explicit:
        candidates.append(Path(explicit))
    env = os.environ.get("WYRED_CONTRACT_SRC")
    if env:
        candidates.append(Path(env))
    # sibling checkout: .../wyred-wz/wyred-audit/src/wyred_audit/contractlib.py
    candidates.append(
        Path(__file__).resolve().parents[3] / "wyred-contract")
    for cand in candidates:
        cand = cand.expanduser().resolve()
        if _qualifies(cand):
            return cand
    return None


def load_validator(contract_root: Path) -> ModuleType:
    """Import the contract's ``tools/validate.py`` as a module (not a
    subprocess). It is pure-stdlib (argparse/glob/json/os/re/sys), so
    importing it adds NO dependency to wyred-audit's pure-stdlib fence.

    Raises ``AuditSetupError`` (=> exit 2) if the file is absent or cannot
    be loaded; ``locate_contract`` already checks presence, so this is the
    defensive path (e.g. a truncated checkout)."""
    vp = Path(contract_root) / "tools" / "validate.py"
    if not vp.is_file():
        raise AuditSetupError(
            "wyred-contract validator not found: %s" % vp)
    spec = importlib.util.spec_from_file_location(
        _VALIDATOR_MODULE_NAME, str(vp))
    if spec is None or spec.loader is None:
        raise AuditSetupError("cannot load validator spec from %s" % vp)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[_VALIDATOR_MODULE_NAME] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception as exc:  # noqa: BLE001 - surface any import fault as setup
        raise AuditSetupError(
            "failed to import wyred-contract validator %s: %r" % (vp, exc))
    return mod
