"""NIST table parsing utilities.

This module provides tools for extracting data from NIST Atomic Spectra Database
tables with column name normalization and robust value extraction.
"""

from __future__ import annotations

import contextlib
import math
import re
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from astropy.table import Table


class NistColumn(Enum):
    """NIST table column name variations (normalized candidates)."""

    # Wavelength columns (all vacuum wavelengths)
    RITZ = (
        "Ritz Wavelength Vacuum (Å)",
        "Ritz Wavelength Vacuum (A)",
        "ritz_wl_vac (A)",
        "Ritz",
        "Ritz Wavelength",
        "Ritz Wavelength (Å)",
        "Ritz Wavelength (A)",
    )
    OBSERVED = (
        "Observed Wavelength Vacuum (Å)",
        "Observed Wavelength Vacuum (A)",
        "obs_wl_vac (A)",
        "Observed",
        "Observed Wavelength",
        "Observed Wavelength (Å)",
        "Observed Wavelength (A)",
    )

    # Wavelength uncertainties
    RITZ_UNC = ("Unc. Ritz", "Ritz Unc.", "Ritz Uncertainty", "unc_ritz", "Unc._1", "Unc1")
    OBSERVED_UNC = ("Unc. Obs.", "Obs. Unc.", "Observed Uncertainty", "unc_obs", "Unc.", "Unc")

    # Physical quantities
    F_VALUE = ("f", "f_value", "fik", "f_ik", "oscillatorstrength", "oscillator_strength")
    AKI = ("Aki", "Aki(s-1)", "Aki (s^-1)", "A (s^-1)")
    EI = ("Ei", "Ei (cm-1)", "Ei(cm-1)", "Lower level energy", "E_lower")
    EK = ("Ek", "Ek (cm-1)", "Ek(cm-1)", "Upper level energy", "E_upper")
    EI_EK = ("Ei Ek", "Ei           Ek", "EiEk", "Ei,Ek")

    # Metadata
    ION = ("Ion", "Spectrum", "Species")
    ACCURACY = ("Acc.", "Acc", "Accuracy", "Accuracy code")
    TYPE = ("Type",)

    # Level information
    LOWER_LEVEL = ("Lower level", "Lower", "Lower level Term", "Lower Term")
    UPPER_LEVEL = ("Upper level", "Upper", "Upper level Term", "Upper Term")

    # References
    TP_REF = ("TP", "TP Ref.", "TP Ref", "TP reference")
    LINE_REF = ("Line", "Line Ref.", "Line Ref", "Line reference")

    # Degeneracies
    GI_GK = ("gi   gk", "gi gk", "gi_gk", "gi/gk", "gi", "g_i g_k")


def _normalize_column_name(name: str) -> str:
    """Normalize column name for comparison.

    Args:
        name: Column name from NIST table

    Returns:
        Normalized column name (lowercase, no special chars)
    """
    text = name.lower().replace("å", "a")
    text = text.replace("(å)", "(a)")
    return re.sub(r"[^a-z0-9]", "", text)


class TableValueExtractor:
    """Unified value extraction from NIST tables with fallback handling."""

    def __init__(self, table: Table) -> None:
        """Initialize extractor with NIST table.

        Args:
            table: Astropy Table from NIST query
        """
        self.table = table
        # Build normalized column name mapping
        self._col_map = {_normalize_column_name(col): col for col in table.colnames}

    def find_column(self, column: NistColumn) -> str | None:
        """Find first matching column from enum candidates.

        Args:
            column: NistColumn enum with candidate column names

        Returns:
            Actual column name in table, or None if not found
        """
        for candidate in column.value:
            norm = _normalize_column_name(candidate)
            if norm in self._col_map:
                return self._col_map[norm]
        return None

    def extract_float(self, row_idx: int, column: NistColumn) -> float | None:
        """Extract float value from row with regex and direct conversion fallback.

        Args:
            row_idx: Row index in table
            column: NistColumn to extract from

        Returns:
            Extracted float value, or None if not found or invalid
        """
        col_name = self.find_column(column)
        if not col_name:
            return None

        cell = self.table[col_name][row_idx]

        # Try regex extraction from string representation
        with contextlib.suppress(Exception):
            s = str(cell)
            m = re.search(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", s)
            if m:
                val = float(m.group(0))
                if math.isfinite(val):
                    return val

        # Fallback: direct float conversion
        with contextlib.suppress(Exception):
            val = float(cell)
            if math.isfinite(val):
                return val

        return None

    def extract_ei_ek(self, row_idx: int) -> tuple[float | None, float | None]:
        """Extract both Ei and Ek from 'Ei Ek' column.

        Args:
            row_idx: Row index in table

        Returns:
            Tuple of (Ei, Ek) values, either may be None if not found
        """
        col_name = self.find_column(NistColumn.EI_EK)
        if not col_name:
            return None, None

        cell = self.table[col_name][row_idx]
        s = str(cell)

        numbers = re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", s)

        ei = None
        ek = None

        if len(numbers) >= 1:
            with contextlib.suppress(Exception):
                val = float(numbers[0])
                if math.isfinite(val):
                    ei = val

        if len(numbers) >= 2:
            with contextlib.suppress(Exception):
                val = float(numbers[1])
                if math.isfinite(val):
                    ek = val

        return ei, ek

    def extract_string(self, row_idx: int, column: NistColumn, normalize: bool = True) -> str:
        """Extract string value from row.

        Args:
            row_idx: Row index in table
            column: NistColumn to extract from
            normalize: If True, convert "--", "-", "—" to empty string

        Returns:
            Extracted string value (may be empty)
        """
        col_name = self.find_column(column)
        if not col_name:
            return ""

        value = str(self.table[col_name][row_idx]).strip()
        if normalize and value in {"--", "-", "—"}:
            return ""
        return value

    def extract_wavelengths_with_uncertainties(
        self, row_idx: int
    ) -> tuple[float | None, str | None, float | None, float | None, float | None, float | None]:
        """Extract Ritz and Observed wavelengths with uncertainties.

        Returns best wavelength (smallest uncertainty) as primary value.

        Args:
            row_idx: Row index in table

        Returns:
            Tuple of (best_wavelength, source, ritz_wl, ritz_unc, obs_wl, obs_unc)
            where source is "ritz" or "observed"
        """
        ritz_wl = self.extract_float(row_idx, NistColumn.RITZ)
        ritz_unc = self.extract_float(row_idx, NistColumn.RITZ_UNC)
        obs_wl = self.extract_float(row_idx, NistColumn.OBSERVED)
        obs_unc = self.extract_float(row_idx, NistColumn.OBSERVED_UNC)

        # Choose wavelength with smallest uncertainty
        # If no uncertainty, prefer Ritz over Observed
        # If neither has wavelength, return None
        if ritz_wl is None and obs_wl is None:
            return None, None, None, None, None, None

        # Default: prefer Ritz if both exist with no uncertainties
        if ritz_wl is not None and obs_wl is None:
            return ritz_wl, "ritz", ritz_wl, ritz_unc, None, None

        if obs_wl is not None and ritz_wl is None:
            return obs_wl, "observed", None, None, obs_wl, obs_unc

        # Both exist - choose by uncertainty
        if ritz_unc is not None and obs_unc is not None:
            if ritz_unc <= obs_unc:
                return ritz_wl, "ritz", ritz_wl, ritz_unc, obs_wl, obs_unc
            return obs_wl, "observed", ritz_wl, ritz_unc, obs_wl, obs_unc
        if ritz_unc is not None:
            # Only ritz has uncertainty - prefer it
            return ritz_wl, "ritz", ritz_wl, ritz_unc, obs_wl, obs_unc
        if obs_unc is not None:
            # Only obs has uncertainty - prefer it
            return obs_wl, "observed", ritz_wl, ritz_unc, obs_wl, obs_unc
        # No uncertainties - prefer Ritz
        return ritz_wl, "ritz", ritz_wl, ritz_unc, obs_wl, obs_unc

    def extract_ref_codes(self, row_idx: int) -> tuple[str, str]:
        """Extract TP and Line reference codes from table row.

        Args:
            row_idx: Row index in table

        Returns:
            Tuple of (tp_code, line_code) reference strings (may be empty)
        """
        tp = self.extract_string(row_idx, NistColumn.TP_REF)
        line = self.extract_string(row_idx, NistColumn.LINE_REF)
        return tp, line
