"""ECO pin-map-diff verification, audited from disk (runner.py:685-711).

The ``<name>.pinmapdiff.json`` ECO view — what changed against the
incumbent artifact, and whether the incumbent-seeded re-solve was
MINIMALLY DISTURBING — is written by the engine alone
(``wyred/src/wyred/emit.py``: ``paths.diff_pinmaps`` +
``_check_incumbency``), so its ``minimal_disturbance_violations`` verdict
was engine-self-certified: a lobotomized ``_check_incumbency`` stayed
green everywhere (the R1 residual — the same one-artifact-wide shape as
the closed F3 finding). ``check_incumbencies`` below is the
counter-check: the audit's own INDEPENDENT ports of the engine's
``paths.diff_pinmaps`` and ``emit._check_incumbency`` (sources of truth:
wyred/src/wyred/paths.py::diff_pinmaps and
wyred/src/wyred/emit.py::_check_incumbency == elecscad ga019
runner.py:685-711; keep in lockstep — drift turns audits red, by design)
re-derive EVERY field of the record from the on-disk artifacts alone: the
incumbent's pinmap + alloc (the record's own ``incumbents`` field names
the incumbent artifact, exactly as the emit loop recorded it) and the
artifact's own pinmap + alloc, then compare field by field against what
the engine wrote — ``minimal_disturbance_violations`` included.

Any field disagreeing with the engine-written record is
PINMAPDIFF_DISAGREE; a NON-EMPTY re-derived violation list is
MINIMAL_DISTURBANCE_NOT_OK regardless of what the record claims.

Codes: PINMAPDIFF_DISAGREE, MINIMAL_DISTURBANCE_NOT_OK,
PINMAPDIFF_INCUMBENT_MISSING, UNREADABLE.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

# suffix of the ECO record this module audits
_SUFFIX = ".pinmapdiff.json"


def audit_diff_pinmaps(a: Dict[str, Any],
                       b: Dict[str, Any]) -> Dict[str, Any]:
    """The audit's independent port of the engine's ``paths.diff_pinmaps``:
    what changed between two pin-map emits — allocation rows keyed by
    demand, per-terminal net changes, component set changes, and the two
    stamps. Empty ``allocation``/``terminals``/component lists == the maps
    agree (stamps may still differ — that is the point of stamping)."""
    def by_demand(pm: Dict[str, Any]) -> Dict[str, List[str]]:
        m: Dict[str, List[str]] = {}
        for e in pm.get("allocations", []):
            m.setdefault(str(e.get("demand")), []).append(json.dumps(
                {k: e.get(k) for k in ("pool", "unit", "state", "chosen_by",
                                       "locked_by", "node")},
                sort_keys=True))
        return {k: sorted(v) for k, v in m.items()}

    da, db = by_demand(a), by_demand(b)
    alloc_diff = {
        "added": sorted(k for k in db if k not in da),
        "removed": sorted(k for k in da if k not in db),
        "changed": sorted(k for k in db if k in da and da[k] != db[k]),
    }

    def nodes(pm: Dict[str, Any]):
        out: Dict[Any, Any] = {}
        for c in pm.get("components", []):
            for t in c.get("terminals", []):
                out[(c["refdes"], t["name"])] = t.get("net")
        return out

    na, nb = nodes(a), nodes(b)
    term_changes = []
    for key in sorted(set(na) | set(nb)):
        va, vb = na.get(key), nb.get(key)
        if va != vb:
            term_changes.append({"refdes": key[0], "terminal": key[1],
                                 "a": va, "b": vb})

    refs_a = {c["refdes"] for c in a.get("components", [])}
    refs_b = {c["refdes"] for c in b.get("components", [])}
    return {
        "stamp_a": a.get("stamp"),
        "stamp_b": b.get("stamp"),
        "allocation": alloc_diff,
        "terminals": term_changes,
        "components_only_in_a": sorted(refs_a - refs_b),
        "components_only_in_b": sorted(refs_b - refs_a),
    }


def audit_check_incumbency(parent_entries: List[Dict[str, Any]],
                           child_entries: List[Dict[str, Any]]
                           ) -> List[str]:
    """Minimal disturbance, checked mechanically — the audit's independent
    port of the engine's ``emit._check_incumbency``: every SOLVER-chosen
    entry of the incumbent record must survive unchanged in the re-solve
    unless a change made that impossible (its unit taken by another
    demand, the demand author-pinned or gone). Returns violation strings
    (byte-for-byte the engine's, so an honest record compares equal)."""
    out: List[str] = []
    child_rows = {(e["pool"], e["unit"], e["demand"])
                  for e in child_entries}
    child_demands: Dict[Any, List[Dict[str, Any]]] = {}
    unit_owner: Dict[Any, Any] = {}
    for e in child_entries:
        child_demands.setdefault(e["demand"], []).append(e)
        unit_owner[(e["pool"], e["unit"])] = e["demand"]
    for e in parent_entries:
        if e.get("chosen_by") != "solver":
            continue
        row = (e["pool"], e["unit"], e["demand"])
        if row in child_rows:
            continue
        taken_by = unit_owner.get((e["pool"], e["unit"]))
        if taken_by is not None and taken_by != e["demand"]:
            continue    # unit taken by another demand: a forced move
        kids = child_demands.get(e["demand"], [])
        if not kids:
            continue    # demand gone: not a disturbance
        if all(k.get("chosen_by") == "author" for k in kids):
            continue    # author re-pinned it: authored change, not churn
        out.append("incumbent (pool=%r, unit=%r, demand=%r) was moved to %s "
                   "although its unit stayed free — the re-solve is not "
                   "minimal-disturbance"
                   % (e["pool"], e["unit"], e["demand"],
                      [(k["pool"], k["unit"]) for k in kids]))
    return out


def _read_json(path: Path):
    return json.loads(path.read_text())


def _fail(fails, artifact, code, msg):
    fails.append({"artifact": artifact, "code": code, "msg": msg})


def check_incumbencies(tree: Path) -> List[Dict[str, str]]:
    """Re-derive every <name>.pinmapdiff.json ECO record from disk and
    compare it field-by-field against what the engine wrote."""
    fails: List[Dict[str, str]] = []
    for pp in sorted(tree.glob("*" + _SUFFIX)):
        name = pp.name[:-len(_SUFFIX)]
        try:
            pdiff = _read_json(pp)
        except (OSError, ValueError) as exc:
            _fail(fails, name, "UNREADABLE",
                  "%s%s unreadable: %r" % (name, _SUFFIX, exc))
            continue
        inc = pdiff.get("incumbents")
        if not isinstance(inc, str) or not inc:
            _fail(fails, name, "PINMAPDIFF_INCUMBENT_MISSING",
                  "%s%s names no incumbent artifact (incumbents=%r) — the "
                  "ECO verdict is unverifiable" % (name, _SUFFIX, inc))
            continue
        needed = [tree / ("%s.pinmap.json" % inc),
                  tree / ("%s.alloc.json" % inc),
                  tree / ("%s.pinmap.json" % name),
                  tree / ("%s.alloc.json" % name)]
        missing = sorted(p.name for p in needed if not p.is_file())
        if missing:
            _fail(fails, name, "PINMAPDIFF_INCUMBENT_MISSING",
                  "%s%s names incumbent %r but the artifacts needed to "
                  "re-derive the ECO verdict are missing from the tree: %s"
                  % (name, _SUFFIX, inc, ", ".join(missing)))
            continue
        try:
            inc_pinmap, inc_alloc, own_pinmap, own_alloc = [
                _read_json(p) for p in needed]
        except (OSError, ValueError) as exc:
            _fail(fails, name, "UNREADABLE",
                  "pinmapdiff artifact set unreadable: %r" % exc)
            continue

        # --- the emit loop's derivation, re-run from disk ----------------
        derived = audit_diff_pinmaps(inc_pinmap, own_pinmap)
        derived["incumbents"] = inc
        derived["minimal_disturbance_violations"] = audit_check_incumbency(
            inc_alloc.get("allocation", {}).get("entries", []),
            own_alloc.get("allocation", {}).get("entries", []))
        for field in sorted(set(derived) | set(pdiff)):
            want, got = derived.get(field), pdiff.get(field)
            if got != want:
                _fail(fails, name, "PINMAPDIFF_DISAGREE",
                      "%s%s field %r is %r but the audit re-derivation "
                      "from disk gives %r"
                      % (name, _SUFFIX, field, got, want))
        if derived["minimal_disturbance_violations"]:
            _fail(fails, name, "MINIMAL_DISTURBANCE_NOT_OK",
                  "the incumbent-seeded re-solve disturbed sticky "
                  "allocations (re-derived from disk): %s"
                  % "; ".join(derived["minimal_disturbance_violations"]))
    return fails
