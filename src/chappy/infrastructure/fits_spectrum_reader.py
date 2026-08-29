"""FITS-backed spectrum reader adapter."""

from __future__ import annotations

from typing import TYPE_CHECKING

from chappy.infrastructure.fits_reader import FitsReader

if TYPE_CHECKING:
    from chappy.core.spectrum import Spectrum


class FitsSpectrumReader:
    """Spectrum reader implemented with ``FitsReader``."""

    def read_spectrum(self, path: str) -> Spectrum:
        """Read a FITS spectrum.

        Args:
            path: FITS file path.

        Returns:
            Spectrum read from the FITS file.
        """
        return FitsReader.read_spectrum(path)

    def validate_spectrum(self, path: str) -> tuple[bool, list[str]]:
        """Validate whether a FITS file can be read as a spectrum.

        Args:
            path: FITS file path.

        Returns:
            Pair of validity flag and validation issue messages.
        """
        return FitsReader.validate_fits_spectrum(path)

    def get_spectrum_info(self, path: str) -> dict[str, object]:
        """Return FITS metadata for display and preflight inspection.

        Args:
            path: FITS file path.

        Returns:
            FITS metadata keyed by stable display field names.
        """
        fits_info = FitsReader.get_fits_info(path)
        return {str(key): value for key, value in fits_info.items()}
