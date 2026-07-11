"""Connector-pinout lock gate, audited from disk (runner.py:779-840).

The ``connector_pinout`` decision class is the one the harness's
allocation oracle does not materialize, so its external-baseline gate
(``check_connector_locks``) lives in the engine's paths module — which
the audit is FORBIDDEN to import. ``audit_connector_locks`` below is the
audit's own faithful port of that gate's semantics (source of truth:
wyred/src/wyred/paths.py::check_connector_locks == elecscad
ga019/modeller/paths.py; keep in lockstep): an INDEPENDENT third
implementation, so the engine-written ``<name>.connlock.json`` record is
re-verified from outside — and, when ``--engine-src`` is given, the
engine's own implementation re-runs from disk too, as a
``python3 -m wyred.crosscheck`` subprocess (see crosscheckrun.py). If any
two of the three drift, the audit turns red.

``check_connlocks`` re-derives every field of every connlock record the
way the emit loop derived it (runner.py:779-840, faithfully): the rows /
series from the alloc artifact, ``forked_from`` from the l1, the gate run
against the artifact's OWN retained baseline, both tamper counter-probes
(a locked row's net rewritten -> CONNECTOR_LOCK_VIOLATION; a hand-edited
series without a fork record -> CONNECTOR_SERIES_UNJUSTIFIED), the
fork-vs-parent gate when the artifact is a fork, and the composed ``ok``.
Any field disagreeing with the engine-written record is
CONNLOCK_DISAGREE; a re-derived verdict of False is CONNLOCK_NOT_OK.

Codes: CONNLOCK_DISAGREE, CONNLOCK_NOT_OK, CONNLOCK_BASELINE_MISSING,
CONNECTOR_LOCK_VIOLATION / CONNECTOR_SERIES_UNJUSTIFIED (via the gate),
UNREADABLE.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def audit_connector_locks(baseline: Dict[str, Any],
                          rows: List[Dict[str, Any]],
                          series: str,
                          forked_from: Optional[Dict[str, Any]] = None
                          ) -> List[Dict[str, str]]:
    """The external-baseline gate for connector-pinout rows — the audit's
    independent port of the engine's ``paths.check_connector_locks`` (same
    semantics as the harness's ``check_lock_violations``, applied to the
    baseline's retained ``connector_pinout`` rows): a LOCKED row
    (``locked_by`` set) whose net changed / that disappeared without a
    series bump is a violation; a differing series is legal only through a
    ``forked_from`` record naming the baseline series.

    Returns structured failure dicts {"code", "msg"}; empty == clean."""
    fails: List[Dict[str, str]] = []
    base_series = baseline.get("series")
    if series != base_series:
        if (isinstance(forked_from, dict)
                and forked_from.get("series") == base_series):
            return fails            # legal fork: locked edits permitted
        fails.append({
            "code": "CONNECTOR_SERIES_UNJUSTIFIED",
            "msg": "series %r differs from the baseline series %r without a "
                   "forked_from record naming it (forked_from=%r) — a "
                   "connector-pinout edit is never legalized by hand-editing "
                   "the series string" % (series, base_series, forked_from)})
        return fails
    cur = {(r.get("connector"), r.get("pin")): r for r in rows}
    for b in baseline.get("connector_pinout", []) or []:
        if not b.get("locked_by"):
            continue                # never locked; free to drift
        key = (b.get("connector"), b.get("pin"))
        c = cur.get(key)
        if c is None:
            fails.append({
                "code": "CONNECTOR_LOCK_VIOLATION",
                "msg": "locked connector-pinout row %s.%s (locked_by %s) "
                       "disappeared without a series bump (series %r)"
                       % (key[0], key[1], b.get("locked_by"), series)})
            continue
        if c.get("net") != b.get("net"):
            fails.append({
                "code": "CONNECTOR_LOCK_VIOLATION",
                "msg": "locked connector-pinout row %s.%s changed net %r -> "
                       "%r without a series bump (series %r, locked_by %s)"
                       % (key[0], key[1], b.get("net"), c.get("net"),
                          series, b.get("locked_by"))})
    return fails


def _read_json(path: Path):
    return json.loads(path.read_text())


def _fail(fails, artifact, code, msg):
    fails.append({"artifact": artifact, "code": code, "msg": msg})


def check_connlocks(tree: Path, baseline_dir: Path) -> List[Dict[str, str]]:
    """Re-derive every <name>.connlock.json record from disk and compare it
    field-by-field against what the engine wrote."""
    fails: List[Dict[str, str]] = []
    for cp in sorted(tree.glob("*.connlock.json")):
        name = cp.name[:-len(".connlock.json")]
        try:
            conn = _read_json(cp)
            l1 = _read_json(tree / ("%s.l1.json" % name))
            alloc = _read_json(tree / ("%s.alloc.json" % name))
        except (OSError, ValueError) as exc:
            _fail(fails, name, "UNREADABLE",
                  "connlock artifact set unreadable: %r" % exc)
            continue
        rows = alloc.get("connector_pinout", [])
        series = alloc.get("series", "")
        ff = l1.get("forked_from")
        base_path = baseline_dir / ("%s.baseline.json" % name)
        if not base_path.is_file():
            _fail(fails, name, "CONNLOCK_BASELINE_MISSING",
                  "%s.connlock.json exists but no external baseline was "
                  "retained (%s.baseline.json missing) — the connector "
                  "lock state is unverifiable" % (name, name))
            continue
        own_base = _read_json(base_path)

        # --- the emit loop's derivation, re-run from disk ----------------
        unlocked = sorted({"%s.%s" % (r["connector"], r["pin"])
                           for r in rows if not r.get("locked_by")})
        clean = audit_connector_locks(own_base, rows, series, ff)
        for f in clean:             # a dirty gate is a finding in itself
            _fail(fails, name, f["code"], f["msg"])
        # tamper 1: one locked row's net rewritten, same series
        t_rows = copy.deepcopy(rows)
        for r in t_rows:
            if r.get("net") is not None:
                r["net"] = "TAMPERED_CONN_NET"
                break
        t1c = sorted({f["code"] for f in audit_connector_locks(
            own_base, t_rows, series, ff)})
        # tamper 2: hand-edited series, no fork record
        t2c = sorted({f["code"] for f in audit_connector_locks(
            own_base, t_rows, series + "Z", None)})
        # the groups the record claims fired: from disk, the lock groups
        # covering connector_pinout at version >= 1 in the emitted l1
        groups = sorted(
            g["name"] for g in l1.get("allocation", {}).get(
                "lock_groups", [])
            if "connector_pinout" in (g.get("covers") or [])
            and int(g.get("version", 0)) >= 1)
        derived: Dict[str, Any] = {
            "artifact": name,
            "groups": groups,
            "rows": len(rows),
            "unlocked_rows": unlocked,
            "gate_clean": [f["code"] for f in clean],
            "tamper_net_codes": t1c,
            "tamper_series_codes": t2c,
        }
        # a fork additionally verifies its rows against the PARENT's
        # retained baseline (the lifecycle record names the parent)
        parent_ok = True
        life_path = tree / ("%s.lifecycle.json" % name)
        if life_path.is_file() or "fork_vs_parent_codes" in conn:
            try:
                parent = _read_json(life_path)["forked_from"]
            except (OSError, ValueError, KeyError) as exc:
                _fail(fails, name, "UNREADABLE",
                      "connlock names a fork but %s.lifecycle.json is "
                      "unreadable: %r" % (name, exc))
                continue
            pb_path = baseline_dir / ("%s.baseline.json" % parent)
            if pb_path.is_file():
                pcodes = sorted({f["code"] for f in audit_connector_locks(
                    _read_json(pb_path), rows, series, ff)})
            else:
                pcodes = ["(no parent baseline)"]
            derived["fork_vs_parent_codes"] = pcodes
            parent_ok = pcodes == []
        derived["ok"] = (bool(rows) and not unlocked
                         and derived["gate_clean"] == []
                         and "CONNECTOR_LOCK_VIOLATION" in t1c
                         and "CONNECTOR_SERIES_UNJUSTIFIED" in t2c
                         and parent_ok)
        for field, want in derived.items():
            got = conn.get(field)
            if got != want:
                _fail(fails, name, "CONNLOCK_DISAGREE",
                      "%s.connlock.json field %r is %r but the audit "
                      "re-derivation from disk gives %r"
                      % (name, field, got, want))
        if not derived["ok"]:
            _fail(fails, name, "CONNLOCK_NOT_OK",
                  "re-derived connector-lock verdict is NOT ok: %r"
                  % derived)
    return fails
