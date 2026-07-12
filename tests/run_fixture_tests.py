#!/usr/bin/env python3
"""Fixture acceptance for wyred-audit (F6): pristine passes, tamper fires.

``python3 tests/run_fixture_tests.py``  (from the wyred-audit repo root)

Runs ``python3 -m wyred_audit`` — as a subprocess, the way a consumer
would — over tests/fixtures/pristine (must exit 0) and over every
tests/fixtures/tampered/<case> (must exit 1 AND print the case's expected
named code). WHOLE-CORPUS rebuild honesty is exercised separately (it
needs the full corpus; the fixture trees are deliberately partial), so
the fixture runs pass --engine-src only: baselines + lifecycle + connlock
+ pinmapdiff/incumbency + the corpus-less FROM-PRIMARIES rebuild +
crosscheck.

Env overrides: WYRED_ENGINE_SRC, WYRED_HARNESS_SRC, WYRED_CONTRACT_SRC
(default: the sibling checkouts under this repo's parent). The runs pass
--contract-src explicitly so the schema stage is deterministically
exercised (the two schema_* tamper cases depend on it).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
FIXTURES = HERE / "fixtures"
ENGINE = os.environ.get("WYRED_ENGINE_SRC", str(REPO.parent / "wyred"))
CONTRACT = os.environ.get("WYRED_CONTRACT_SRC",
                          str(REPO.parent / "wyred-contract"))

# tampered case -> the named code(s) that MUST appear in the findings
EXPECT = {
    "locked_row_edit": ("LOCK_VIOLATION",),
    "series_hand_edit": ("SERIES_UNJUSTIFIED",),
    "lifecycle_ok_flip": ("LIFECYCLE_DISAGREE",),
    "connlock_ok_flip": ("CONNLOCK_DISAGREE",),
    "bom_value_swap": ("CROSSCHECK_FAILED", "XPATH_BOM_FIELDS",
                       "REBUILD_FROM_PRIMARIES"),
    "pinmapdiff_blanked": ("PINMAPDIFF_DISAGREE",),
    "sticky_alloc_moved": ("PINMAPDIFF_DISAGREE",
                           "MINIMAL_DISTURBANCE_NOT_OK"),
    "bom_totals_edit": ("REBUILD_FROM_PRIMARIES",),
    # shape defects the semantic gates do not classify — caught by the
    # optional contract schema stage (Step 2.1). The byte-level
    # from-primaries rebuild also fires, but SCHEMA_INVALID is the code
    # that proves the schema stage ran and named the shape violation.
    "schema_bom_missing_qty": ("SCHEMA_INVALID",),
    "schema_pinmap_net_number": ("SCHEMA_INVALID",),
}

# tampered case -> code(s) that must NOT appear (the case exists to prove
# a check catches what another gate misses)
FORBID = {
    # authored_total/generated_total are read by no semantic gate: only
    # the byte-level from-primaries rebuild may fire.
    "bom_totals_edit": ("CROSSCHECK_FAILED",),
}


def run_audit(tree: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO / "src") + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [sys.executable, "-m", "wyred_audit", "--tree", str(tree),
         "--engine-src", ENGINE, "--contract-src", CONTRACT],
        env=env, capture_output=True, text=True)


def main() -> int:
    failures = 0

    proc = run_audit(FIXTURES / "pristine")
    if proc.returncode != 0:
        failures += 1
        print("FAIL pristine: audit exited %d\n%s%s"
              % (proc.returncode, proc.stdout, proc.stderr))
    else:
        print("PASS pristine: audit exits 0")

    for case, want_codes in sorted(EXPECT.items()):
        proc = run_audit(FIXTURES / "tampered" / case)
        missing = [c for c in want_codes if c not in proc.stdout]
        forbidden = [c for c in FORBID.get(case, ())
                     if c in proc.stdout]
        if proc.returncode != 1 or missing or forbidden:
            failures += 1
            print("FAIL tampered/%s: exit=%d (want 1), missing codes %s, "
                  "forbidden codes fired %s\n%s%s"
                  % (case, proc.returncode, missing or "[]",
                     forbidden or "[]", proc.stdout, proc.stderr))
        else:
            fired = sorted({ln.split()[2].rstrip(":")
                            for ln in proc.stdout.splitlines()
                            if ln.startswith("FAIL ")})
            print("PASS tampered/%-18s exit 1; fired: %s"
                  % (case + ":", ", ".join(fired)))

    print("\nFIXTURE TESTS: %s (%d failure(s))"
          % ("PASS" if failures == 0 else "FAIL", failures))
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
