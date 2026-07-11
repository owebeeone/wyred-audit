#!/usr/bin/env python3
"""Regenerate tests/fixtures/ from the wyred-contract goldens.

``python3 tests/make_fixtures.py``  (from the wyred-audit repo root; set
WYRED_CONTRACT_GOLDENS to point elsewhere)

pristine/                 untouched copies of five golden artifact sets:
                          watchy_v1_reva (baseline + connlock),
                          watchy_v1_revb (fork: baseline + connlock +
                          lifecycle), intent_05a_pinned (baseline only),
                          watchy_v1_draft + watchy_v1_draft_btn3 (the
                          ECO pair: incumbent + pinmapdiff record).
tampered/<case>/          a full copy of pristine/ with EXACTLY ONE
                          mutation applied; see fixtures/README.md for
                          the mutation table and the code each one must
                          make ``python3 -m wyred_audit`` fire.

The mutations are applied programmatically here so they are reproducible
and reviewable; the generated trees are committed as fixtures.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures"
GOLDENS = Path(os.environ.get(
    "WYRED_CONTRACT_GOLDENS",
    HERE.parents[1] / "wyred-contract" / "goldens" / "ga019"))

SETS = ("watchy_v1_reva", "watchy_v1_revb", "intent_05a_pinned",
        "watchy_v1_draft", "watchy_v1_draft_btn3")


def _copy_pristine(dst: Path) -> None:
    dst.mkdir(parents=True)
    for name in SETS:
        for src in sorted(GOLDENS.glob("%s.*.json" % name)):
            shutil.copy2(src, dst / src.name)


def _edit_json(path: Path, mutate) -> None:
    doc = json.loads(path.read_text())
    mutate(doc)
    # engine artifacts are json_str-style dumps; match the retained bytes'
    # shape (indent=2, sorted keys, trailing newline) so ONLY the mutated
    # field differs semantically, not the formatting.
    path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")


def mut_locked_row_edit(tree: Path) -> None:
    """Edit a LOCKED allocation decision in place — no break_lock, no
    series fork. The retained-baseline gate must fire LOCK_VIOLATION."""
    def mutate(l1):
        for e in l1["allocation"]["entries"]:
            if e.get("locked_by"):
                e["unit"] = int(e["unit"]) + 1
                return
        raise AssertionError("no locked entry to tamper")
    _edit_json(tree / "watchy_v1_reva.l1.json", mutate)


def mut_series_hand_edit(tree: Path) -> None:
    """Hand-edit the series string with NO forked_from record — the fake
    'legalization' of a locked edit. Must fire SERIES_UNJUSTIFIED."""
    def mutate(l1):
        assert l1.get("forked_from") is None
        l1["series"] = l1["series"] + "Z"
    _edit_json(tree / "watchy_v1_reva.l1.json", mutate)


def mut_lifecycle_ok_flip(tree: Path) -> None:
    """Flip the engine-written lifecycle verdict field — the engine
    self-certification F3 warned about. The audit's harness re-derivation
    must disagree: LIFECYCLE_DISAGREE."""
    def mutate(life):
        assert life["ok"] is True
        life["ok"] = False
    _edit_json(tree / "watchy_v1_revb.lifecycle.json", mutate)


def mut_connlock_ok_flip(tree: Path) -> None:
    """Flip the engine-written connector-lock verdict field. The audit's
    independent re-derivation must disagree: CONNLOCK_DISAGREE."""
    def mutate(conn):
        assert conn["ok"] is True
        conn["ok"] = False
    _edit_json(tree / "watchy_v1_reva.connlock.json", mutate)


def mut_bom_value_swap(tree: Path) -> None:
    """Swap the value payloads of two BOM line items (sets and counts stay
    legal — the part-to-buy payload changes). The engine's from-disk
    cross-path differential must fire XPATH_BOM_FIELDS, reported by the
    audit as CROSSCHECK_FAILED."""
    def mutate(bom):
        items = [i for i in bom["line_items"] if i.get("refdes")]
        distinct = {}
        for i in items:
            distinct.setdefault(i.get("value"), i)
        vals = list(distinct)
        assert len(vals) >= 2, "need two distinct BOM values to swap"
        a, b = distinct[vals[0]], distinct[vals[1]]
        a["value"], b["value"] = b["value"], a["value"]
    _edit_json(tree / "watchy_v1_reva.bom.json", mutate)


def mut_pinmapdiff_blanked(tree: Path) -> None:
    """Blank the ECO diff's change lists — the engine-lobotomy shape the
    R1 residual warned about (a differ/incumbency check that reports
    nothing stays green everywhere). The audit's independent re-derivation
    from the two pinmap+alloc artifact pairs must disagree:
    PINMAPDIFF_DISAGREE."""
    def mutate(pdiff):
        assert pdiff["allocation"]["changed"] and pdiff["terminals"]
        assert pdiff["minimal_disturbance_violations"] == []
        pdiff["allocation"]["changed"] = []
        pdiff["terminals"] = []
    _edit_json(tree / "watchy_v1_draft_btn3.pinmapdiff.json", mutate)


def mut_sticky_alloc_moved(tree: Path) -> None:
    """Move a SOLVER-chosen sticky allocation to a free unit in the alloc
    artifact while the engine-written pinmapdiff keeps claiming minimal
    disturbance (violations []). The audit's _check_incumbency port must
    re-derive the violation from disk: PINMAPDIFF_DISAGREE +
    MINIMAL_DISTURBANCE_NOT_OK."""
    def mutate(alloc):
        entries = alloc["allocation"]["entries"]
        taken = {(e["pool"], e["unit"]) for e in entries}
        for e in entries:
            if e.get("chosen_by") == "solver":
                unit = int(e["unit"]) + 1
                while (e["pool"], unit) in taken:
                    unit += 1
                e["unit"] = unit
                return
        raise AssertionError("no solver-chosen entry to move")
    _edit_json(tree / "watchy_v1_draft_btn3.alloc.json", mutate)


def mut_bom_totals_edit(tree: Path) -> None:
    """Shift the BOM's authored/generated split by one — a payload field
    NO semantic gate reads (the cross-path differential never consumes
    authored_total/generated_total), so only the byte-level FROM-PRIMARIES
    rebuild can catch it: REBUILD_FROM_PRIMARIES, and nothing else."""
    def mutate(bom):
        assert (bom["authored_total"] + bom["generated_total"]
                == bom["component_total"])
        bom["authored_total"] += 1
        bom["generated_total"] -= 1
    _edit_json(tree / "watchy_v1_reva.bom.json", mutate)


MUTATIONS = {
    "locked_row_edit": mut_locked_row_edit,
    "series_hand_edit": mut_series_hand_edit,
    "lifecycle_ok_flip": mut_lifecycle_ok_flip,
    "connlock_ok_flip": mut_connlock_ok_flip,
    "bom_value_swap": mut_bom_value_swap,
    "pinmapdiff_blanked": mut_pinmapdiff_blanked,
    "sticky_alloc_moved": mut_sticky_alloc_moved,
    "bom_totals_edit": mut_bom_totals_edit,
}


def main() -> int:
    if not GOLDENS.is_dir():
        print("goldens not found: %s (set WYRED_CONTRACT_GOLDENS)"
              % GOLDENS, file=sys.stderr)
        return 2
    pristine = FIXTURES / "pristine"
    tampered = FIXTURES / "tampered"
    for d in (pristine, tampered):
        if d.exists():
            shutil.rmtree(d)
    _copy_pristine(pristine)
    print("pristine/: %d file(s) from %s"
          % (len(list(pristine.iterdir())), GOLDENS))
    for case, mutate in sorted(MUTATIONS.items()):
        dst = tampered / case
        shutil.copytree(pristine, dst)
        mutate(dst)
        print("tampered/%s/: one mutation applied" % case)
    return 0


if __name__ == "__main__":
    sys.exit(main())
