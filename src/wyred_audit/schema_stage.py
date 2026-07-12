"""Optional schema-validation stage (Step 2.1 of
dev-docs/WyredPlanContractSchemas.md).

Validate every recognized ``*.json`` artifact in a tree against the
wyred-contract draft-2020-12 schemas, mapping each schema failure to the
audit finding code ``SCHEMA_INVALID``.

Composition (justified against wyred-audit's fences — see CLAUDE.md and
contractlib.py): the audit MAY depend on wyred-contract, and the
contract's subset validator is shared contract infrastructure — NOT the
engine (``wyred``) under audit — so it is IMPORTED as a library
(``contractlib.load_validator``) rather than spawned as a subprocess, the
same precedent by which the harness is sys.path-imported. The schemas and
the fail-closed subset validator both live in wyred-contract; this stage
only drives them over the on-disk tree and reports one ``SCHEMA_INVALID``
finding per failing file (carrying the first failure's JSON-pointer +
keyword, and a count of any further failures in the same file).

Degradation: when no contract checkout (or no ``schemas/``) is found the
stage warns and SKIPS — a consumer holding only artifacts still audits
everything else, the same pattern as the corpus-less rebuild skip. A
malformed schema set (the validator's fail-closed keyword scan trips) is
a genuine setup error and surfaces as ``AuditSetupError`` (=> exit 2).
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from wyred_audit.contractlib import load_validator, locate_contract
from wyred_audit.harnesslib import AuditSetupError


class SchemaStageResult:
    """Outcome of the schema stage, for cli.py to render.

    ``skipped`` -> the stage did not run (``reason`` says why); ``fails``
    is the standard list of ``{artifact, code, msg}`` finding dicts (empty
    == every recognized artifact validated); ``n_valid``/``n_total`` count
    the recognized artifacts; ``contract`` is the checkout that was used
    (None when skipped)."""

    __slots__ = ("skipped", "reason", "contract", "n_total", "n_valid",
                 "fails")

    def __init__(self) -> None:
        self.skipped: bool = False
        self.reason: str = ""
        self.contract: Optional[Path] = None
        self.n_total: int = 0
        self.n_valid: int = 0
        self.fails: List[Dict[str, str]] = []


def _kind_of(path: Path) -> Optional[str]:
    """``<name>.<kind>.json`` -> ``<kind>``; None if the filename is not
    of that three-part shape (so non-artifact JSON is silently ignored)."""
    parts = path.name.split(".")
    if len(parts) < 3 or parts[-1] != "json":
        return None
    return parts[-2]


def check_schemas(tree: Path,
                  contract_src: Optional[str] = None) -> SchemaStageResult:
    """Validate every recognized ``*.json`` in ``tree`` against its kind
    schema. Never raises for a *validation* failure (those become
    ``SCHEMA_INVALID`` findings); raises ``AuditSetupError`` only for a
    genuine setup fault (unloadable validator, malformed schema set)."""
    res = SchemaStageResult()
    contract = locate_contract(contract_src)
    if contract is None:
        res.skipped = True
        res.reason = ("no wyred-contract checkout found (pass --contract-src "
                      "or set WYRED_CONTRACT_SRC) — artifact shapes were NOT "
                      "schema-validated")
        return res
    res.contract = contract

    validator = load_validator(contract)
    schemas_dir = contract / "schemas"
    try:
        ss = validator.SchemaSet(str(schemas_dir))
    except validator.SetupError as exc:
        # A broken schema set (e.g. the fail-closed keyword scan tripped)
        # is a real setup error, not a per-artifact finding.
        raise AuditSetupError(
            "wyred-contract schemas under %s are unusable: %s"
            % (schemas_dir, exc))

    for path in sorted(tree.glob("*.json")):
        kind = _kind_of(path)
        if kind is None or kind not in ss.by_kind:
            continue  # not a contract artifact kind -> nothing to validate
        res.n_total += 1
        name = ".".join(path.name.split(".")[:-2])
        try:
            schema_ok, _canon, failures = validator.validate_file(
                str(path), ss, False)
        except validator.SetupError as exc:
            # Recognized kind but the validator refused it structurally —
            # treat as a setup fault (should not happen after the by_kind
            # pre-filter), not a silent pass.
            raise AuditSetupError(
                "validator setup error on %s: %s" % (path.name, exc))
        if schema_ok:
            res.n_valid += 1
            continue
        first = failures[0]
        extra = (" (+%d more)" % (len(failures) - 1)
                 if len(failures) > 1 else "")
        res.fails.append({
            "artifact": name,
            "code": "SCHEMA_INVALID",
            "msg": "%s fails %s.schema.json at %s [%s]: %s%s"
                   % (path.name, kind, first.pointer or "/", first.keyword,
                      first.message, extra),
        })
    return res
