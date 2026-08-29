"""NIST spectral line database generator for astronomical spectroscopy.

This package fetches spectral line data from NIST Atomic Spectra Database
and generates CSV files with multiplet grouping for absorption line analysis.
"""

from __future__ import annotations

from spectral_database.cli import main
from spectral_database.data_models import FilterOptions, LineRecord

__version__ = "0.1.0"

__all__ = ["FilterOptions", "LineRecord", "__version__", "main"]
