"""FITS file reader for astronomical spectra."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
from astropy.io import fits  # type: ignore[import-untyped]
from astropy.wcs import WCS  # type: ignore[import-untyped]
from numpy.typing import NDArray

from chappy.core.spectrum import Spectrum

if TYPE_CHECKING:
    from collections.abc import Mapping

logger = logging.getLogger(__name__)
FloatArray = NDArray[np.float64]
type TableData = Any

# Constants for astronomical wavelength validation
DIMENSION_2D = 2  # 2D array dimension check
MIN_ASTRONOMICAL_WAVELENGTH = 0.1  # Minimum wavelength in Angstroms (UV)
MAX_ASTRONOMICAL_WAVELENGTH = 250000  # Maximum wavelength in Angstroms (far-IR)
MAX_WAVELENGTH_SPACING = 100  # Maximum reasonable wavelength spacing
MIN_SPECTRUM_PIXELS = 10  # Minimum number of pixels for a valid spectrum


class FitsReader:
    """Reader for FITS format spectral data.

    Supports various FITS formats commonly used in astronomy:
    - 1D spectra (wavelength, flux arrays)
    - Multi-extension FITS
    - Binary tables
    - WCS coordinate systems
    """

    @staticmethod
    def read_spectrum(filename: str) -> Spectrum:
        """Read a spectrum from a FITS file.

        Args:
            filename: Path to FITS file

        Returns:
            Spectrum object

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If FITS format is not supported
            Exception: For other FITS reading errors
        """
        filepath = Path(filename)
        if not filepath.exists():
            msg = f"FITS file not found: {filename}"
            raise FileNotFoundError(msg)

        logger.info("Reading FITS file: %s", filename)

        try:
            with fits.open(filename) as hdul:
                spectrum = FitsReader._try_read_strategies(hdul, filename)
                logger.info("Successfully read spectrum with %d pixels", spectrum.n_pixels)
                return spectrum
        except (OSError, ValueError, TypeError, IndexError, KeyError):
            logger.exception("Failed to read FITS file %s", filename)
            raise

    @staticmethod
    def _try_read_strategies(hdul: fits.HDUList, filename: str) -> Spectrum:
        """Try different strategies to read spectrum from FITS.

        Args:
            hdul: Opened FITS HDU list
            filename: Original filename for error messages

        Returns:
            Spectrum object

        Raises:
            ValueError: If no strategy succeeds
        """
        strategies = [
            FitsReader._read_primary_image,
            FitsReader._read_binary_table,
            FitsReader._read_multi_extension,
        ]

        errors = []

        for strategy in strategies:
            try:
                spectrum = strategy(hdul, filename)
                if spectrum is not None:
                    return spectrum
            except (ValueError, TypeError, IndexError, KeyError, OSError) as e:
                errors.append(f"{strategy.__name__}: {e}")

        # If all strategies failed
        error_msg = f"Could not read FITS file {filename}. Tried strategies:\n"
        error_msg += "\n".join(errors)
        raise ValueError(error_msg)

    @staticmethod
    def _read_primary_image(hdul: fits.HDUList, _filename: str) -> Spectrum | None:
        """Read spectrum from primary HDU as image.

        Args:
            hdul: FITS HDU list
            filename: Filename for reference

        Returns:
            Spectrum if successful, None otherwise
        """
        primary = hdul[0]

        if primary.data is None:
            return None

        header = primary.header
        data = primary.data

        # Handle different data shapes
        if data.ndim == 1:
            flux = data.astype(np.float64)
        elif data.ndim == DIMENSION_2D:
            if data.shape[0] == 1:
                flux = data[0].astype(np.float64)
            elif data.shape[1] == 1:
                flux = data[:, 0].astype(np.float64)
            else:
                msg = (
                    "Ambiguous 2D primary image spectrum: "
                    f"shape={data.shape}. Provide a 1D image, a single-row/single-column "
                    "image, or a table/multi-extension FITS with explicit wavelength/flux data."
                )
                raise ValueError(msg)
        else:
            msg = f"Unsupported data dimensionality: {data.ndim}"
            raise ValueError(msg)

        # Construct wavelength array
        wavelength = FitsReader._construct_wavelength(header, len(flux))

        # Extract header information
        header_dict = dict(header)

        return Spectrum(
            wavelength=np.asarray(wavelength, dtype=np.float64),
            flux=np.asarray(flux, dtype=np.float64),
            header=header_dict,
            crval1=FitsReader._required_header_float(header, "CRVAL1"),
            cdelt1=FitsReader._required_cdelt1(header),
            crpix1=int(FitsReader._required_header_float(header, "CRPIX1")),
            dc_flag=bool(header.get("DC-FLAG", 0)),
        )

    @staticmethod
    def _read_binary_table(hdul: fits.HDUList, _filename: str) -> Spectrum | None:
        """Read spectrum from binary table extension.

        Args:
            hdul: FITS HDU list
            filename: Filename for reference

        Returns:
            Spectrum if successful, None otherwise
        """
        for hdu in hdul:
            if isinstance(hdu, fits.BinTableHDU):
                spectrum = FitsReader._extract_spectrum_from_table(hdu)
                if spectrum:
                    return spectrum
        return None

    @staticmethod
    def _extract_spectrum_from_table(hdu: fits.BinTableHDU) -> Spectrum | None:
        """Extract spectrum data from binary table HDU.

        Args:
            hdu: Binary table HDU

        Returns:
            Spectrum if successful, None otherwise
        """
        table = hdu.data
        header = dict(hdu.header)

        wavelength, flux, error = FitsReader._find_table_columns(table)

        wavelength, flux = FitsReader._require_table_arrays(wavelength, flux)
        return Spectrum(
            wavelength=np.asarray(wavelength, dtype=np.float64),
            flux=np.asarray(flux, dtype=np.float64),
            error=np.asarray(error, dtype=np.float64) if error is not None else None,
            header=dict(header),
        )

    @staticmethod
    def _find_table_columns(
        table: TableData,
    ) -> tuple[FloatArray | None, FloatArray | None, FloatArray | None]:
        """Find wavelength, flux, and error columns in table.

        Args:
            table: FITS table data

        Returns:
            Tuple of (wavelength, flux, error) arrays
        """
        if table is None:
            msg = "Binary table HDU has no table data"
            raise ValueError(msg)

        # Common column names for wavelength and flux
        wave_names = ["WAVELENGTH", "WAVE", "LAMBDA", "WL"]
        flux_names = ["FLUX", "INTENSITY", "COUNTS", "DATA"]
        error_names = ["ERROR", "ERR", "SIGMA", "UNCERTAINTY"]

        wavelength = FitsReader._find_column_by_names(table, wave_names)
        flux = FitsReader._find_column_by_names(table, flux_names)
        error = FitsReader._find_column_by_names(table, error_names)  # Optional

        return wavelength, flux, error

    @staticmethod
    def _find_column_by_names(table: TableData, column_names: list[str]) -> FloatArray | None:
        """Find column by trying multiple possible names.

        Args:
            table: FITS table data
            column_names: List of possible column names to try

        Returns:
            Column data as array or None if not found
        """
        if table is None:
            return None

        for name in column_names:
            if name in table.columns.names:
                return np.asarray(table[name], dtype=np.float64)
        return None

    @staticmethod
    def _require_table_arrays(
        wavelength: FloatArray | None, flux: FloatArray | None
    ) -> tuple[FloatArray, FloatArray]:
        """Return validated wavelength and flux arrays.

        Args:
            wavelength: Wavelength array
            flux: Flux array

        Returns:
            Validated wavelength and flux arrays.
        """
        if wavelength is None:
            msg = "Binary table spectrum is missing a wavelength column"
            raise ValueError(msg)
        if flux is None:
            msg = "Binary table spectrum is missing a flux column"
            raise ValueError(msg)
        if len(wavelength) != len(flux):
            msg = (
                "Binary table wavelength and flux arrays have different lengths: "
                f"{len(wavelength)} vs {len(flux)}"
            )
            raise ValueError(msg)
        return wavelength, flux

    @staticmethod
    def _read_multi_extension(hdul: fits.HDUList, _filename: str) -> Spectrum | None:
        """Read spectrum from multi-extension FITS.

        Args:
            hdul: FITS HDU list
            filename: Filename for reference

        Returns:
            Spectrum if successful, None otherwise
        """
        wavelength, flux, error, header_dict = FitsReader._extract_multi_extension_data(hdul)

        if wavelength is not None and flux is not None:
            wavelength, flux, error = FitsReader._flatten_and_validate_arrays(
                wavelength, flux, error
            )
            if wavelength is not None and flux is not None:
                return Spectrum(
                    wavelength=np.asarray(wavelength, dtype=np.float64),
                    flux=np.asarray(flux, dtype=np.float64),
                    error=np.asarray(error, dtype=np.float64) if error is not None else None,
                    header=header_dict,
                )
        return None

    @staticmethod
    def _extract_multi_extension_data(
        hdul: fits.HDUList,
    ) -> tuple[FloatArray | None, FloatArray | None, FloatArray | None, dict[str, Any]]:
        """Extract wavelength, flux, error data from multi-extension FITS.

        Args:
            hdul: FITS HDU list

        Returns:
            Tuple of (wavelength, flux, error, header_dict)
        """
        wavelength = None
        flux = None
        error = None
        header_dict = {}

        for hdu in hdul:
            if hdu.data is None:
                continue

            extname = hdu.header.get("EXTNAME", "").upper()
            data_array = hdu.data.astype(np.float64)

            if extname in {"WAVELENGTH", "WAVE", "LAMBDA"}:
                wavelength = data_array
            elif extname in {"FLUX", "INTENSITY", "DATA"}:
                flux = data_array
            elif extname in {"ERROR", "ERR", "SIGMA"}:
                error = data_array

            # Merge headers
            header_dict.update(dict(hdu.header))

        return wavelength, flux, error, header_dict

    @staticmethod
    def _flatten_and_validate_arrays(
        wavelength: FloatArray, flux: FloatArray, error: FloatArray | None
    ) -> tuple[FloatArray | None, FloatArray | None, FloatArray | None]:
        """Flatten multi-dimensional arrays and validate lengths.

        Args:
            wavelength: Wavelength array
            flux: Flux array
            error: Error array (optional)

        Returns:
            Tuple of (wavelength, flux, error) or (None, None, None) if validation fails
        """
        # Ensure 1D arrays
        if wavelength.ndim > 1:
            wavelength = wavelength.flatten()
        if flux.ndim > 1:
            flux = flux.flatten()
        if error is not None and error.ndim > 1:
            error = error.flatten()

        if len(wavelength) != len(flux):
            msg = (
                "Multi-extension wavelength and flux arrays have different lengths: "
                f"{len(wavelength)} vs {len(flux)}"
            )
            raise ValueError(msg)

        return wavelength, flux, error

    @staticmethod
    def _construct_wavelength(
        header: fits.Header | Mapping[str, Any], n_pixels: int
    ) -> FloatArray:
        """Construct wavelength array from FITS header WCS information.

        Args:
            header: FITS header
            n_pixels: Number of pixels

        Returns:
            Wavelength array
        """
        header_obj = header if isinstance(header, fits.Header) else fits.Header(header)

        # Check for logarithmic wavelength scale indicators
        dc_flag = header_obj.get("DC-FLAG", 0)
        ctype1 = str(header_obj.get("CTYPE1", "")).upper()

        # Determine if logarithmic scale
        is_log_scale = (dc_flag == 1) or ("LOG" in ctype1)

        logger.debug(
            "Wavelength scale detection: DC-FLAG=%s, CTYPE1=%s, is_log=%s",
            dc_flag,
            ctype1,
            is_log_scale,
        )

        crval1 = FitsReader._required_header_float(header_obj, "CRVAL1")
        cdelt1 = FitsReader._required_cdelt1(header_obj)
        crpix1 = FitsReader._required_header_float(header_obj, "CRPIX1")

        if not is_log_scale:
            try:
                wcs = WCS(header_obj, naxis=1)
                pixels = np.arange(n_pixels)
                wavelength = wcs.pixel_to_world(pixels)

                if hasattr(wavelength, "value"):
                    wavelength_array = np.asarray(wavelength.value, dtype=np.float64)
                else:
                    wavelength_array = np.asarray(wavelength, dtype=np.float64)

                if FitsReader._validate_wavelength_range(wavelength_array):
                    logger.debug(
                        "WCS wavelength range: %.3f - %.3f",
                        wavelength_array[0],
                        wavelength_array[-1],
                    )
                    return wavelength_array

                logger.warning(
                    "WCS produced invalid wavelength range, falling back to manual calculation"
                )
            except (ValueError, TypeError, IndexError, KeyError) as exc:
                logger.debug(
                    "WCS construction failed: %s, falling back to manual calculation", exc
                )

        pixels = np.arange(1, n_pixels + 1)

        if is_log_scale:
            log_wavelength = crval1 + (pixels - crpix1) * cdelt1
            wavelength = np.power(10.0, log_wavelength)
            logger.debug(
                "Log scale: CRVAL1=%s, CDELT1=%s, range=%.3f-%.3f",
                crval1,
                cdelt1,
                wavelength[0],
                wavelength[-1],
            )
        else:
            wavelength = crval1 + (pixels - crpix1) * cdelt1
            logger.debug(
                "Linear scale: CRVAL1=%s, CDELT1=%s, range=%.3f-%.3f",
                crval1,
                cdelt1,
                wavelength[0],
                wavelength[-1],
            )

        wavelength_array = np.asarray(wavelength, dtype=np.float64)
        if not FitsReader._validate_wavelength_range(wavelength_array):
            msg = (
                "Invalid wavelength range detected: "
                f"{float(wavelength_array[0]):.3f} - {float(wavelength_array[-1]):.3f}"
            )
            raise ValueError(msg)

        logger.debug(
            "Final wavelength array: range=%.3f-%.3f, shape=%s",
            wavelength_array[0],
            wavelength_array[-1],
            wavelength_array.shape,
        )
        return wavelength_array

    @staticmethod
    def _required_header_float(header: fits.Header | Mapping[str, Any], key: str) -> float:
        """Return a required finite FITS header value as float."""
        value = header.get(key)
        if value is None:
            msg = f"FITS header is missing required wavelength key: {key}"
            raise ValueError(msg)
        try:
            numeric_value = float(value)
        except (TypeError, ValueError) as error:
            msg = f"FITS header has invalid wavelength key: {key}"
            raise ValueError(msg) from error
        if not np.isfinite(numeric_value):
            msg = f"FITS header has non-finite wavelength key: {key}"
            raise ValueError(msg)
        return numeric_value

    @staticmethod
    def _required_cdelt1(header: fits.Header | Mapping[str, Any]) -> float:
        """Return the required wavelength step from FITS header alternatives."""
        invalid_keys: list[str] = []
        for key in ("CDELT1", "CD1_1", "CD1"):
            value = header.get(key)
            if value is None:
                continue
            try:
                numeric_value = float(value)
            except (TypeError, ValueError):
                invalid_keys.append(key)
                continue
            if not np.isfinite(numeric_value):
                invalid_keys.append(key)
                continue
            return numeric_value
        if invalid_keys:
            msg = "FITS header has invalid wavelength step key: " + ", ".join(invalid_keys)
            raise ValueError(msg)
        msg = "FITS header is missing required wavelength step key: CDELT1/CD1_1/CD1"
        raise ValueError(msg)

    @staticmethod
    def _validate_wavelength_range(wavelength: FloatArray) -> bool:
        """Validate that wavelength array has reasonable astronomical values.

        Args:
            wavelength: Wavelength array in Angstroms

        Returns:
            True if wavelength range is reasonable, False otherwise
        """
        if len(wavelength) == 0:
            return False

        min_wave = np.min(wavelength)
        max_wave = np.max(wavelength)

        # Check for finite values
        if not (np.isfinite(min_wave) and np.isfinite(max_wave)):
            return False

        # Check for monotonic increase
        if not np.all(np.diff(wavelength) > 0):
            return False

        # Check for reasonable astronomical wavelength range (100 Å to 100,000 Å)
        # This covers UV through far-IR
        if min_wave < MIN_ASTRONOMICAL_WAVELENGTH or max_wave > MAX_ASTRONOMICAL_WAVELENGTH:
            return False

        # Check for reasonable wavelength spacing
        delta_wave = float(np.median(np.diff(wavelength)))
        # Return True if spacing is positive and reasonable
        return delta_wave > 0 and delta_wave <= MAX_WAVELENGTH_SPACING

    @staticmethod
    def get_fits_info(filename: str) -> dict[str, Any]:
        """Get information about a FITS file without reading full data.

        Args:
            filename: Path to FITS file

        Returns:
            Dictionary with file information
        """
        info = {
            "filename": filename,
            "n_extensions": 0,
            "extensions": [],
            "primary_shape": None,
            "primary_header_keys": [],
        }

        try:
            with fits.open(filename) as hdul:
                info["n_extensions"] = len(hdul)

                for i, hdu in enumerate(hdul):
                    header = dict(hdu.header)

                    shape = tuple(hdu.data.shape) if hdu.data is not None else None
                    n_columns = None
                    if isinstance(hdu, fits.BinTableHDU) and hdu.data is not None:
                        n_columns = len(hdu.data.columns.names)

                    ext_info = {
                        "index": i,
                        "type": type(hdu).__name__,
                        "name": header.get("EXTNAME", ""),
                        "shape": shape,
                        "n_columns": n_columns,
                    }

                    extensions = info["extensions"]
                    if isinstance(extensions, list):
                        extensions.append(ext_info)

                    if i == 0:
                        info["primary_shape"] = shape
                        info["primary_header_keys"] = list(header.keys())

        except (ValueError, TypeError, IndexError, KeyError, OSError) as e:
            info["error"] = str(e)

        return info

    @staticmethod
    def validate_fits_spectrum(filename: str) -> tuple[bool, list[str]]:
        """Validate if a FITS file contains readable spectrum data.

        Args:
            filename: Path to FITS file

        Returns:
            Tuple of (is_valid, list_of_issues)
        """
        issues = []

        try:
            spectrum = FitsReader.read_spectrum(filename)

            # Check for common issues
            if spectrum.n_pixels < MIN_SPECTRUM_PIXELS:
                issues.append(f"Very few pixels: {spectrum.n_pixels}")

            if np.all(spectrum.flux == 0):
                issues.append("All flux values are zero")

            if np.any(np.isnan(spectrum.flux)):
                n_nan = np.sum(np.isnan(spectrum.flux))
                issues.append(f"Contains {n_nan} NaN flux values")

            if np.any(np.isinf(spectrum.flux)):
                n_inf = np.sum(np.isinf(spectrum.flux))
                issues.append(f"Contains {n_inf} infinite flux values")

            # Check wavelength monotonicity
            if not np.all(np.diff(spectrum.wavelength) > 0):
                issues.append("Wavelength array is not monotonically increasing")

            # Check for reasonable wavelength range (optical/NIR)
            min_wave, max_wave = spectrum.wavelength_range
            if min_wave < MIN_ASTRONOMICAL_WAVELENGTH or max_wave > MAX_ASTRONOMICAL_WAVELENGTH:
                issues.append(f"Unusual wavelength range: {min_wave:.1f} - {max_wave:.1f} Å")

        except (ValueError, TypeError, IndexError, KeyError, OSError) as e:
            issues.append(f"Failed to read spectrum: {e}")

        return len(issues) == 0, issues
