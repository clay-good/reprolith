"""Package entry point so ``python -m reprolith`` runs the CLI.

Mirrors the ``reprolith`` console script (``reprolith.cli:main``), so the terminal surface is
reachable without the installed script on ``PATH`` — the two dispatch to the same code.
"""

from __future__ import annotations

from .cli import main

if __name__ == "__main__":
    main()
