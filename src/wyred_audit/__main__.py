"""``python3 -m wyred_audit`` — the consumer-side audit CLI."""

import sys

from wyred_audit.cli import main

if __name__ == "__main__":
    sys.exit(main())
