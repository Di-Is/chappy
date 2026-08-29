"""Tests for Spectrum data structure."""

import numpy as np
import pytest
from numpy.testing import assert_array_equal

from chappy.core.spectrum import Spectrum


class TestSpectrum:
    """Test suite for Spectrum class."""

    @pytest.fixture
    def sample_spectrum(self) -> Spectrum:
        """Create a sample spectrum for testing."""
        wavelength = np.linspace(4000, 5000, 1001)  # Use 1001 to include exact 4500.0
        rng = np.random.default_rng(42)
        flux = np.ones_like(wavelength) + 0.1 * rng.standard_normal(len(wavelength))
        error = 0.1 * np.ones_like(wavelength)

        return Spectrum(
            wavelength=wavelength, flux=flux, error=error, header={"OBJECT": "Test Star"}
        )

    def test_initialization(self) -> None:
        """Test spectrum initialization."""
        wavelength = np.array([4000, 4001, 4002])
        flux = np.array([1.0, 0.9, 1.1])

        spectrum = Spectrum(wavelength=wavelength, flux=flux)

        assert_array_equal(spectrum.wavelength, wavelength)
        assert_array_equal(spectrum.flux, flux)
        assert spectrum.error is None
        assert spectrum.n_pixels == 3

    def test_initialization_with_error(self) -> None:
        """Test spectrum initialization with errors."""
        wavelength = np.array([4000, 4001, 4002])
        flux = np.array([1.0, 0.9, 1.1])
        error = np.array([0.1, 0.1, 0.1])

        spectrum = Spectrum(wavelength=wavelength, flux=flux, error=error)

        assert spectrum.has_error
        assert_array_equal(spectrum.error, error)

    def test_validation_errors(self) -> None:
        """Test array length validation."""
        wavelength = np.array([4000, 4001, 4002])
        flux = np.array([1.0, 0.9])  # Wrong length

        with pytest.raises(ValueError, match="same length"):
            Spectrum(wavelength=wavelength, flux=flux)

    def test_wavelength_range(self, sample_spectrum: Spectrum) -> None:
        """Test wavelength range property."""
        min_wave, max_wave = sample_spectrum.wavelength_range

        assert min_wave == 4000.0
        assert max_wave == 5000.0

    def test_copy(self, sample_spectrum: Spectrum) -> None:
        """Test spectrum copying."""
        copy = sample_spectrum.copy()

        # Check it's a true copy
        assert copy is not sample_spectrum
        assert_array_equal(copy.wavelength, sample_spectrum.wavelength)
        assert_array_equal(copy.flux, sample_spectrum.flux)

        # Modify copy shouldn't affect original
        copy.flux[0] = 999.0
        assert sample_spectrum.flux[0] != 999.0

    def test_calculate_snr(self, sample_spectrum: Spectrum) -> None:
        """Test signal-to-noise calculation."""
        # Set known values
        sample_spectrum.flux[:] = 10.0
        sample_spectrum.error[:] = 1.0

        snr = sample_spectrum.calculate_snr()
        assert snr == pytest.approx(10.0)

        # Test with wavelength range
        sample_spectrum.flux[400:600] = 20.0
        snr_range = sample_spectrum.calculate_snr(wavelength_range=(4400, 4600))
        assert snr_range == pytest.approx(20.0)

    def test_no_error_snr(self) -> None:
        """Test SNR calculation without error array."""
        spectrum = Spectrum(wavelength=np.array([4000, 4001]), flux=np.array([1.0, 1.0]))

        with pytest.raises(ValueError, match="without error"):
            spectrum.calculate_snr()


class TestSpectrumSerialization:
    """Test spectrum serialization capabilities."""

    def test_header_preservation(self) -> None:
        """Test that FITS header info is preserved."""
        header = {"OBJECT": "HD 12345", "EXPTIME": 3600.0, "AIRMASS": 1.2}

        spectrum = Spectrum(
            wavelength=np.linspace(4000, 5000, 100), flux=np.ones(100), header=header
        )

        # Copy should preserve header
        copy = spectrum.copy()
        assert copy.header == header
        assert copy.header is not header  # Should be a copy
