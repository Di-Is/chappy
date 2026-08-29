"""Tests for FITS file reading functionality."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits  # type: ignore[import-untyped]

from chappy.infrastructure.fits_reader import FitsReader
from tests.helpers.simple_fits_builder import (
    write_binary_table,
    write_empty_primary,
    write_multi_extension,
    write_primary_image,
)


class TestFitsReader:
    """Test suite for FitsReader class."""

    @pytest.fixture
    def sample_fits_1d(self, tmp_path: Path) -> str:
        """Create a sample 1D FITS spectrum file."""
        fits_path = tmp_path / "sample_1d.fits"
        wavelength = np.linspace(4000, 5000, 1000)
        rng = np.random.default_rng(42)
        flux = np.ones_like(wavelength) + 0.1 * rng.standard_normal(len(wavelength))

        write_primary_image(
            fits_path,
            flux,
            crval1=4000.0,
            cdelt1=1.0,
            crpix1=1,
            extra_cards=[("OBJECT", "Test Star"), ("EXPTIME", 3600.0)],
        )

        return str(fits_path)

    @pytest.fixture
    def sample_fits_table(self, tmp_path: Path) -> str:
        """Create a sample FITS file with binary table."""
        fits_path = tmp_path / "sample_table.fits"
        wavelength = np.linspace(4000, 5000, 1000)
        rng = np.random.default_rng(42)
        flux = np.ones_like(wavelength) + 0.1 * rng.standard_normal(len(wavelength))
        error = 0.1 * np.ones_like(wavelength)

        write_binary_table(
            fits_path, {"WAVELENGTH": wavelength, "FLUX": flux, "ERROR": error}, extname="SPECTRUM"
        )

        return str(fits_path)

    def test_read_1d_spectrum(self, sample_fits_1d: str) -> None:
        """Test reading 1D spectrum from FITS file."""
        spectrum = FitsReader.read_spectrum(sample_fits_1d)

        assert spectrum.n_pixels == 1000
        assert spectrum.wavelength_range == (4000.0, 4999.0)
        assert spectrum.crval1 == 4000.0
        assert spectrum.cdelt1 == 1.0
        assert spectrum.crpix1 == 1

        expected_wavelength = np.linspace(4000, 4999, 1000)
        np.testing.assert_array_almost_equal(spectrum.wavelength, expected_wavelength)

        assert len(spectrum.flux) == 1000
        assert np.all(np.isfinite(spectrum.flux))

        assert spectrum.header["OBJECT"] == "Test Star"
        assert spectrum.header["EXPTIME"] == 3600.0

    def test_read_table_spectrum(self, sample_fits_table: str) -> None:
        """Test reading spectrum from binary table."""
        spectrum = FitsReader.read_spectrum(sample_fits_table)

        assert spectrum.n_pixels == 1000
        assert spectrum.has_error
        assert len(spectrum.wavelength) == 1000
        assert len(spectrum.flux) == 1000
        assert len(spectrum.error) == 1000

        min_wave, max_wave = spectrum.wavelength_range
        assert abs(min_wave - 4000.0) < 1.0
        assert abs(max_wave - 5000.0) < 1.0

    def test_file_not_found(self) -> None:
        """Test handling of non-existent files."""
        with pytest.raises(FileNotFoundError):
            FitsReader.read_spectrum("nonexistent_file.fits")

    def test_get_fits_info(self, sample_fits_1d: str) -> None:
        """Test getting FITS file information."""
        info = FitsReader.get_fits_info(sample_fits_1d)

        assert info["n_extensions"] == 1
        assert info["primary_shape"] == (1000,)
        assert "OBJECT" in info["primary_header_keys"]

    def test_validate_fits_spectrum(self, sample_fits_1d: str) -> None:
        """Test FITS spectrum validation."""
        is_valid, issues = FitsReader.validate_fits_spectrum(sample_fits_1d)

        assert is_valid
        assert len(issues) == 0

    def test_validate_bad_spectrum(self, tmp_path: Path) -> None:
        """Test validation of problematic spectrum."""
        fits_path = tmp_path / "bad_spectrum.fits"
        flux = np.zeros(100)
        write_primary_image(fits_path, flux, crval1=4000.0, cdelt1=1.0, crpix1=1)

        is_valid, issues = FitsReader.validate_fits_spectrum(str(fits_path))

        assert not is_valid
        assert any("zero" in issue.lower() for issue in issues)

    def test_logarithmic_wavelength(self, tmp_path: Path) -> None:
        """Test reading spectrum with logarithmic wavelength scale."""
        fits_path = tmp_path / "log_wavelength.fits"
        rng = np.random.default_rng(42)
        flux = np.ones(1000) + 0.1 * rng.standard_normal(1000)

        write_primary_image(
            fits_path, flux, crval1=float(np.log10(4000.0)), cdelt1=0.0001, crpix1=1, dc_flag=True
        )

        spectrum = FitsReader.read_spectrum(str(fits_path))

        assert spectrum.dc_flag
        assert spectrum.wavelength[0] > 3000
        assert spectrum.wavelength[-1] > spectrum.wavelength[0]

    def test_multi_extension_fits(self, tmp_path: Path) -> None:
        """Test reading multi-extension FITS file."""
        fits_path = tmp_path / "multi_extension.fits"
        wavelength = np.linspace(4000, 5000, 1000)
        rng = np.random.default_rng(42)
        flux = np.ones_like(wavelength) + 0.1 * rng.standard_normal(len(wavelength))

        write_multi_extension(fits_path, [("WAVELENGTH", wavelength), ("FLUX", flux)])

        spectrum = FitsReader.read_spectrum(str(fits_path))

        assert spectrum.n_pixels == 1000
        assert len(spectrum.wavelength) == 1000
        assert len(spectrum.flux) == 1000

    def test_binary_table_missing_flux_reports_diagnostic(self, tmp_path: Path) -> None:
        """Malformed binary tables should report the missing required flux column."""
        fits_path = tmp_path / "missing_flux.fits"
        wavelength = np.linspace(4000, 5000, 100)
        write_binary_table(
            fits_path,
            {"WAVELENGTH": wavelength, "ERROR": np.ones_like(wavelength)},
            extname="SPECTRUM",
        )

        with pytest.raises(ValueError, match="missing a flux column"):
            FitsReader.read_spectrum(str(fits_path))

        is_valid, issues = FitsReader.validate_fits_spectrum(str(fits_path))
        assert not is_valid
        assert any("missing a flux column" in issue for issue in issues)

    def test_multi_extension_length_mismatch_reports_diagnostic(self, tmp_path: Path) -> None:
        """Malformed multi-extension arrays should report wavelength/flux length mismatch."""
        fits_path = tmp_path / "length_mismatch.fits"
        write_multi_extension(
            fits_path, [("WAVELENGTH", np.linspace(4000, 5000, 100)), ("FLUX", np.ones(99))]
        )

        with pytest.raises(ValueError, match="different lengths: 100 vs 99"):
            FitsReader.read_spectrum(str(fits_path))

        is_valid, issues = FitsReader.validate_fits_spectrum(str(fits_path))
        assert not is_valid
        assert any("different lengths: 100 vs 99" in issue for issue in issues)


class TestFitsReaderEdgeCases:
    """Test edge cases and error conditions."""

    @staticmethod
    def _replace_header_value(filename: str, key: str, value: object) -> None:
        """Replace a FITS header value in-place."""
        with fits.open(filename, mode="update") as hdul:
            hdul[0].header[key] = value
            hdul.flush()

    def test_empty_fits_file(self, tmp_path: Path) -> None:
        """Test handling of empty FITS file."""
        fits_path = tmp_path / "empty.fits"
        write_empty_primary(fits_path)

        with pytest.raises(ValueError, match="Could not read FITS file"):
            FitsReader.read_spectrum(str(fits_path))

    def test_malformed_wcs_header_fails_fast(self, tmp_path: Path) -> None:
        """Invalid wavelength WCS metadata should not fall back to defaults."""
        fits_path = tmp_path / "malformed_wcs.fits"
        flux = np.ones(100)
        write_primary_image(
            fits_path, flux, crval1=0.0, cdelt1=1.0, crpix1=1, extra_cards=[("CRVAL1", "invalid")]
        )
        self._replace_header_value(str(fits_path), "CRVAL1", "invalid")

        with pytest.raises(ValueError, match="CRVAL1"):
            FitsReader.read_spectrum(str(fits_path))

    def test_invalid_wavelength_step_fails_fast(self, tmp_path: Path) -> None:
        """Invalid CDELT metadata should not be replaced with a default step."""
        fits_path = tmp_path / "invalid_cdelt.fits"
        flux = np.ones(100)
        write_primary_image(
            fits_path,
            flux,
            crval1=4000.0,
            cdelt1=1.0,
            crpix1=1,
            extra_cards=[("CDELT1", "invalid")],
        )
        self._replace_header_value(str(fits_path), "CDELT1", "invalid")

        with pytest.raises(ValueError, match="CDELT1"):
            FitsReader.read_spectrum(str(fits_path))

    def test_ambiguous_2d_primary_image_fails_fast(self, tmp_path: Path) -> None:
        """Ambiguous 2D primary image data should not default to the first row."""
        fits_path = tmp_path / "ambiguous_2d.fits"
        flux = np.ones((2, 100), dtype=np.float64)
        hdu = fits.PrimaryHDU(flux)
        hdu.header["CRVAL1"] = 4000.0
        hdu.header["CDELT1"] = 1.0
        hdu.header["CRPIX1"] = 1
        hdu.writeto(fits_path, overwrite=True)

        with pytest.raises(ValueError, match="Ambiguous 2D primary image"):
            FitsReader.read_spectrum(str(fits_path))

    def test_very_large_spectrum(self) -> None:
        """Test handling of very large spectrum (memory efficiency)."""
        pytest.skip("Skipping large spectrum test")


class TestErrorNormalisation:
    """Reading FITS error data must normalise invalid entries to NaN."""

    def test_sentinel_and_nonpositive_errors_become_nan(self, tmp_path: Path) -> None:
        """Sentinel nulls, negatives, zeros, and Inf carry no uncertainty."""
        fits_path = tmp_path / "sentinel_errors.fits"
        wavelength = np.linspace(4000.0, 4005.0, 6)
        flux = np.ones_like(wavelength)
        error = np.array([0.1, -9999.0, -1.0e32, 0.0, np.inf, 0.2])
        write_binary_table(
            fits_path, {"WAVELENGTH": wavelength, "FLUX": flux, "ERROR": error}, extname="SPECTRUM"
        )

        spectrum = FitsReader.read_spectrum(str(fits_path))

        assert spectrum.error is not None
        np.testing.assert_allclose(spectrum.error[[0, 5]], [0.1, 0.2])
        assert np.isnan(spectrum.error[1:5]).all()

    def test_large_positive_errors_are_preserved(self, tmp_path: Path) -> None:
        """Statistically large but valid errors must pass through unchanged."""
        fits_path = tmp_path / "heteroscedastic_errors.fits"
        wavelength = np.linspace(4000.0, 4099.0, 100)
        flux = np.ones_like(wavelength)
        error = np.full_like(wavelength, 0.01)
        error[90:] = np.linspace(0.1, 0.5, 10)
        write_binary_table(
            fits_path, {"WAVELENGTH": wavelength, "FLUX": flux, "ERROR": error}, extname="SPECTRUM"
        )

        spectrum = FitsReader.read_spectrum(str(fits_path))

        assert spectrum.error is not None
        np.testing.assert_allclose(spectrum.error, error)
