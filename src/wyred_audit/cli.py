#!/usr/bin/env python3
"""wyred-audit — the one-command consumer-side audit over an artifact tree.

``python3 -m wyred_audit --tree <artifact-dir>``
                              audit the tree FROM DISK with the
                              wyred-harness library plus the audit's own
                              independent checkers: (2a) the F3
                              counter-check — every engine-retained
                              ``<name>.baseline.json`` must be
                              byte-identical to the harness-library
                              re-derivation (``snapshot_locks`` over the
                              l1 + the alloc artifact's connector rows);
                              (2b) the retained-baseline lock gate —
                              ``check_lock_violations`` over every
                              baselined artifact (a locked-row edit
                              without a fork -> LOCK_VIOLATION, a
                              hand-edited series -> SERIES_UNJUSTIFIED);
                              (2c) every ``<name>.lifecycle.json`` fork
                              record re-derived (legal-fork codes + both
                              tamper counter-probes) and compared field by
                              field; (2d) every ``<name>.connlock.json``
                              re-derived with the audit's independent
                              connector-lock gate and compared field by
                              field; (2e) every ``<name>.pinmapdiff.json``
                              ECO record re-derived with the audit's
                              independent ports of the engine's pin-map
                              differ + minimal-disturbance check — the R1
                              counter-check on the engine-self-certified
                              ``minimal_disturbance_violations`` verdict —
                              and compared field by field.
``... --corpus-dir <dir> --engine-src <path>``
                              additionally (1) REBUILD HONESTY: re-emit
                              the corpus with the engine — as a
                              subprocess, never an import — into a temp
                              dir and byte-compare every ``*.json``
                              artifact against the tree, both ways.
                              Skipped with a warning when --corpus-dir is
                              absent (a consumer may hold artifacts only).
``... --engine-src <path>``   additionally (3) FROM-PRIMARIES rebuild
                              honesty, ``python3 -m wyred.rebuild --all``
                              as a subprocess: every secondary path
                              (bom/pinmap/records) must rebuild
                              byte-identically from the on-disk primaries
                              alone (l2 + alloc + l1) — no corpus needed;
                              and (4) the engine's own from-disk
                              cross-path differential + connector-lock
                              gate, ``python3 -m wyred.crosscheck --all``
                              as a subprocess.
``... --baseline-dir <dir>``  read the retained external baselines from a
                              separately-kept directory instead of the
                              tree itself (the baseline is the trust
                              anchor: a consumer who retains baselines
                              out-of-tree also defeats a coordinated
                              rewrite of artifact + in-tree baseline).

Exit 0 iff every check passed; 1 on any finding; 2 on a setup error.
The audit process NEVER imports the engine (wyred) and never writes into
the audited tree.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from wyred_audit import baselines as _baselines
from wyred_audit import connlock as _connlock
from wyred_audit import incumbency as _incumbency
from wyred_audit.crosscheckrun import check_crosscheck
from wyred_audit.harnesslib import AuditSetupError, load_harness
from wyred_audit.rebuild import check_rebuild, check_rebuild_from_primaries


def _report(fails) -> int:
    for f in fails:
        who = f["artifact"] or "(tree)"
        print("FAIL %-28s %s: %s" % (who, f["code"], f["msg"]))
    return len(fails)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="wyred_audit", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tree", required=True, metavar="ARTIFACT_DIR",
                    help="the artifact directory to audit (a wyred.emit "
                         "--out dir, or a consumer's retained copy)")
    ap.add_argument("--corpus-dir", metavar="DIR",
                    help="corpus package dir; enables rebuild honesty "
                         "(requires --engine-src)")
    ap.add_argument("--engine-src", metavar="PATH",
                    help="wyred engine checkout (repo root or src dir); "
                         "enables rebuild honesty and the engine "
                         "crosscheck — both run as SUBPROCESSES, never "
                         "imports")
    ap.add_argument("--baseline-dir", metavar="DIR",
                    help="directory holding the retained external "
                         "*.baseline.json files (default: the tree)")
    ap.add_argument("--harness-src", metavar="PATH",
                    help="wyred-harness checkout (repo root or harness "
                         "dir); default: $WYRED_HARNESS_SRC or the "
                         "sibling checkout")
    ap.add_argument("--verbose", action="store_true",
                    help="echo subprocess emit output")
    args = ap.parse_args(argv)

    tree = Path(args.tree)
    if not tree.is_dir():
        print("not a directory: %s" % tree, file=sys.stderr)
        return 2
    if args.corpus_dir and not args.engine_src:
        print("--corpus-dir requires --engine-src (the rebuild re-emits "
              "the corpus with the engine, as a subprocess)",
              file=sys.stderr)
        return 2
    baseline_dir = Path(args.baseline_dir) if args.baseline_dir else tree
    if not baseline_dir.is_dir():
        print("not a directory: %s" % baseline_dir, file=sys.stderr)
        return 2

    try:
        allocation, schema_l1 = load_harness(args.harness_src)
    except AuditSetupError as exc:
        print("setup: %s" % exc, file=sys.stderr)
        return 2

    failures = 0
    n_l1 = len(list(tree.glob("*.l1.json")))
    n_base = len(list(baseline_dir.glob("*.baseline.json")))
    print("== wyred-audit: %s (%d artifact set(s), %d retained "
          "baseline(s)) ==" % (tree, n_l1, n_base))

    # ---- (1) rebuild honesty: subprocess re-emit, byte-compare ----------
    print("\n[1/4] rebuild honesty (re-emit the corpus, byte-compare)")
    if args.corpus_dir:
        try:
            fails = check_rebuild(tree, Path(args.corpus_dir),
                                  args.engine_src, verbose=args.verbose)
        except AuditSetupError as exc:
            print("setup: %s" % exc, file=sys.stderr)
            return 2
        failures += _report(fails)
        if not fails:
            print("PASS rebuild: every *.json artifact is byte-identical "
                  "to a fresh subprocess emit of %s" % args.corpus_dir)
    else:
        print("WARN rebuild SKIPPED: no --corpus-dir (consumer may hold "
              "artifacts only) — the tree was NOT verified against a "
              "fresh engine emit")

    # ---- (2) external baselines / lifecycle / connlock / pinmapdiff -----
    print("\n[2/4] external-baseline verification (harness re-derivation "
          "+ tamper gates)")
    fails = _baselines.check_baselines(allocation, schema_l1, tree,
                                       baseline_dir)
    failures += _report(fails)
    if not fails:
        print("PASS baselines: %d retained baseline(s) byte-identical to "
              "the harness re-derivation; lock gates clean" % n_base)
    fails = _baselines.check_lifecycles(allocation, schema_l1, tree,
                                        baseline_dir)
    failures += _report(fails)
    if not fails:
        n = len(list(tree.glob("*.lifecycle.json")))
        print("PASS lifecycle: %d fork record(s) agree with the harness "
              "re-derivation (legal fork + both tamper probes)" % n)
    fails = _connlock.check_connlocks(tree, baseline_dir)
    failures += _report(fails)
    if not fails:
        n = len(list(tree.glob("*.connlock.json")))
        print("PASS connlock: %d connector-lock record(s) agree with the "
              "audit re-derivation (gate + both tamper probes)" % n)
    fails = _incumbency.check_incumbencies(tree)
    failures += _report(fails)
    if not fails:
        n = len(list(tree.glob("*.pinmapdiff.json")))
        print("PASS pinmapdiff: %d ECO record(s) agree with the audit "
              "re-derivation (pin-map diff + minimal disturbance)" % n)

    # ---- (3) from-primaries rebuild honesty, subprocess -----------------
    print("\n[3/4] from-primaries rebuild (python3 -m wyred.rebuild "
          "--all)")
    if args.engine_src:
        try:
            fails = check_rebuild_from_primaries(tree, args.engine_src)
        except AuditSetupError as exc:
            print("setup: %s" % exc, file=sys.stderr)
            return 2
        failures += _report(fails)
        if not fails:
            print("PASS from-primaries: every secondary path "
                  "(bom/pinmap/records) rebuilds byte-identically from "
                  "the on-disk primaries alone")
    else:
        print("WARN from-primaries SKIPPED: no --engine-src — the "
              "secondary paths were NOT re-derived from the on-disk "
              "primaries")

    # ---- (4) the engine's own from-disk differential, subprocess --------
    print("\n[4/4] engine crosscheck (python3 -m wyred.crosscheck --all)")
    if args.engine_src:
        try:
            fails = check_crosscheck(tree, args.engine_src)
        except AuditSetupError as exc:
            print("setup: %s" % exc, file=sys.stderr)
            return 2
        failures += _report(fails)
        if not fails:
            print("PASS crosscheck: the engine's from-disk differential "
                  "fired no codes")
    else:
        print("WARN crosscheck SKIPPED: no --engine-src — the cross-path "
              "differential was NOT re-run")

    print("\nAUDIT: %s (%d finding(s))"
          % ("PASS" if failures == 0 else "FAIL", failures))
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
