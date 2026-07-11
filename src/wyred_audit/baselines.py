"""External-baseline verification + lifecycle tamper audit (from disk).

The consumer-trust half of ga019 runner.py, ported faithfully:

* Baseline agreement — the F3 counter-check. The engine RETAINS an
  external lock baseline at every locked emit (``<name>.baseline.json``,
  written by wyred's own ~110-line dict port of the harness lock helpers,
  wyred/src/wyred/emit.py). The audit re-derives that snapshot
  INDEPENDENTLY — ``harness.allocation.snapshot_locks`` over
  ``schema_l1.from_json(<name>.l1.json)`` plus the alloc artifact's
  connector-pinout rows — and byte-compares against the retained file.
  Any drift between the engine's duplicated implementation and the
  harness's turns the audit red (BASELINE_DRIFT).

* Lock-state gate — runner.py's retained-baseline verification: the
  artifact's CURRENT l1 document is checked against its retained baseline
  with ``harness.allocation.check_lock_violations``; a locked-row edit
  without a fork fires LOCK_VIOLATION, a hand-edited series fires
  SERIES_UNJUSTIFIED (the exact section-2.5 codes).

* Lifecycle re-verification — runner.py:716-771 re-run from disk: the
  legal-fork codes and BOTH tamper counter-probes (forked_from stripped ->
  SERIES_UNJUSTIFIED; a locked decision edited in the parent in place ->
  LOCK_VIOLATION) are re-derived with the harness library and compared
  field-by-field against the engine-written ``<name>.lifecycle.json``
  (codes, stamps, ``ok``). Disagreement is LIFECYCLE_DISAGREE; a
  re-derived verdict of False is LIFECYCLE_NOT_OK regardless of what the
  record claims.

Codes: BASELINE_DRIFT, BASELINE_MISSING, BASELINE_ORPHANED,
LOCK_VIOLATION, SERIES_UNJUSTIFIED, LIFECYCLE_DISAGREE, LIFECYCLE_NOT_OK,
LIFECYCLE_PARENT_BASELINE_MISSING, UNREADABLE.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def _fail(fails, artifact, code, msg):
    fails.append({"artifact": artifact, "code": code, "msg": msg})


def _read_json(path: Path):
    return json.loads(path.read_text())


def rederive_baseline(allocation, schema_l1, l1: Dict[str, Any],
                      alloc: Optional[Dict[str, Any]]) -> str:
    """The retained-baseline bytes the ENGINE must have written for this
    artifact, re-derived from the harness library alone: snapshot_locks of
    the l1 document + the alloc artifact's connector-pinout rows (the M4
    extra key), dumped exactly as the emit loop dumps it."""
    snap = allocation.snapshot_locks(schema_l1.from_json(l1))
    snap["connector_pinout"] = [
        dict(r) for r in (alloc or {}).get("connector_pinout", [])]
    return json.dumps(snap, indent=2, sort_keys=True) + "\n"


def _locked(l1: Dict[str, Any]) -> bool:
    """Did this emit fire any lock group (version >= 1)? — the engine's
    condition for retaining an external baseline."""
    return any(int(g.get("version", 0)) >= 1
               for g in l1.get("allocation", {}).get("lock_groups", []))


def check_baselines(allocation, schema_l1, tree: Path, baseline_dir: Path
                    ) -> List[Dict[str, str]]:
    """Baseline agreement (F3) + the lock-state gate, every artifact."""
    fails: List[Dict[str, str]] = []
    l1_names = sorted(p.name[:-len(".l1.json")]
                      for p in tree.glob("*.l1.json"))
    for name in l1_names:
        try:
            l1 = _read_json(tree / ("%s.l1.json" % name))
        except (OSError, ValueError) as exc:
            _fail(fails, name, "UNREADABLE",
                  "%s.l1.json unreadable: %r" % (name, exc))
            continue
        base_path = baseline_dir / ("%s.baseline.json" % name)
        if not base_path.is_file():
            if _locked(l1):
                _fail(fails, name, "BASELINE_MISSING",
                      "the document carries LOCKED groups (version >= 1) "
                      "but no external baseline was retained "
                      "(%s.baseline.json missing) — the lock state is "
                      "unverifiable" % name)
            continue
        alloc_path = tree / ("%s.alloc.json" % name)
        try:
            alloc = _read_json(alloc_path) if alloc_path.is_file() else None
            retained = base_path.read_text()
            baseline = json.loads(retained)
        except (OSError, ValueError) as exc:
            _fail(fails, name, "UNREADABLE",
                  "baseline/alloc artifact unreadable: %r" % exc)
            continue
        if alloc is None:
            _fail(fails, name, "UNREADABLE",
                  "%s.baseline.json is retained but %s.alloc.json is "
                  "missing — the baseline's connector rows cannot be "
                  "re-derived" % (name, name))
        else:
            # --- F3 counter-check: harness re-derivation, byte-for-byte --
            want = rederive_baseline(allocation, schema_l1, l1, alloc)
            if want != retained:
                _fail(fails, name, "BASELINE_DRIFT",
                      "the engine-retained %s.baseline.json is NOT "
                      "byte-identical to the harness-library re-derivation "
                      "(snapshot_locks(l1) + alloc connector rows) — the "
                      "engine's baseline writer and the harness disagree, "
                      "or the tree was edited" % name)
        # --- the retained-baseline lock gate (runner.py's verification) --
        doc = schema_l1.from_json(l1)
        for v in allocation.check_lock_violations(baseline, doc):
            _fail(fails, name, v.code, v.msg)
    # a retained baseline whose artifact vanished is itself a finding
    held = {p.name[:-len(".baseline.json")]
            for p in baseline_dir.glob("*.baseline.json")}
    for name in sorted(held.difference(l1_names)):
        _fail(fails, name, "BASELINE_ORPHANED",
              "%s.baseline.json is retained but the tree has no "
              "%s.l1.json" % (name, name))
    return fails


def check_lifecycles(allocation, schema_l1, tree: Path, baseline_dir: Path
                     ) -> List[Dict[str, str]]:
    """Re-run runner.py:716-771 from disk for every <name>.lifecycle.json
    and compare against the engine-written record, field by field."""
    fails: List[Dict[str, str]] = []
    for lp in sorted(tree.glob("*.lifecycle.json")):
        name = lp.name[:-len(".lifecycle.json")]
        try:
            life = _read_json(lp)
            l1 = _read_json(tree / ("%s.l1.json" % name))
            child_alloc = _read_json(tree / ("%s.alloc.json" % name))
            parent = life["forked_from"]
            parent_l1 = _read_json(tree / ("%s.l1.json" % parent))
            parent_alloc = _read_json(tree / ("%s.alloc.json" % parent))
        except (OSError, ValueError, KeyError) as exc:
            _fail(fails, name, "UNREADABLE",
                  "lifecycle artifact set unreadable: %r" % exc)
            continue
        pb_path = baseline_dir / ("%s.baseline.json" % parent)
        if not pb_path.is_file():
            _fail(fails, name, "LIFECYCLE_PARENT_BASELINE_MISSING",
                  "fork parent %r retained no external lock baseline "
                  "(%s.baseline.json missing)" % (parent, parent))
            continue
        pb = _read_json(pb_path)

        # --- the runner's fork verification, re-derived via the harness --
        legal = sorted(v.code for v in
                       allocation.check_lock_violations(
                           pb, schema_l1.from_json(l1)))
        # tamper 1: same edit, forked_from record stripped
        t1 = copy.deepcopy(l1)
        t1.pop("forked_from", None)
        t1_codes = sorted(v.code for v in
                          allocation.check_lock_violations(
                              pb, schema_l1.from_json(t1)))
        # tamper 2: edit a LOCKED decision in the parent doc in place
        # (series untouched, no fork)
        t2 = copy.deepcopy(parent_l1)
        t2_codes = ["(no locked entry to tamper)"]
        for e in t2.get("allocation", {}).get("entries", []):
            if e.get("locked_by"):
                e["unit"] = int(e["unit"]) + 1
                t2_codes = sorted(v.code for v in
                                  allocation.check_lock_violations(
                                      pb, schema_l1.from_json(t2)))
                break
        ok = (legal == []
              and "SERIES_UNJUSTIFIED" in t1_codes
              and "LOCK_VIOLATION" in t2_codes)

        derived = {
            "artifact": name,
            "forked_from": parent,
            "new_series": l1.get("series"),
            "parent_stamp": parent_alloc.get("stamp"),
            "child_stamp": child_alloc.get("stamp"),
            "legal_fork_codes": legal,
            "tamper_series_hand_edit_codes": t1_codes,
            "tamper_locked_edit_codes": t2_codes,
            "ok": ok,
        }
        for field, want in derived.items():
            got = life.get(field)
            if got != want:
                _fail(fails, name, "LIFECYCLE_DISAGREE",
                      "%s.lifecycle.json field %r is %r but the harness "
                      "re-derivation from disk gives %r"
                      % (name, field, got, want))
        if not ok:
            _fail(fails, name, "LIFECYCLE_NOT_OK",
                  "re-derived fork verdict is NOT ok: legal=%s "
                  "tamper_series=%s tamper_locked=%s"
                  % (legal, t1_codes, t2_codes))
    return fails
