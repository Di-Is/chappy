"""Entry point for spectral-database CLI.

This module allows running the package as `python -m spectral_database`
or via the installed `spectral-database` console script.
"""

from __future__ import annotations

import sys

from spectral_database.cli import main

if __name__ == "__main__":
    sys.exit(main())
