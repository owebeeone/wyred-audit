"""wyred-audit — consumer-side trust verification over a wyred artifact tree.

The audit NEVER imports the engine (wyred): every verdict is computed from
artifacts re-read from disk, verified with the wyred-harness library plus
the audit's own independent checkers, and — where an engine run is required
(rebuild honesty, the from-disk cross-path differential) — the engine is
composed as a SUBPROCESS over the shared artifact directory, per the
composition rule in wyred-wz/dev-docs/RunnerSplit.md.
"""

__all__ = ["__version__"]
__version__ = "0.1.0"
