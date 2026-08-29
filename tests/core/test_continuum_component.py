"""Tests for ContinuumComponent.calculate_from_points static method."""

from __future__ import annotations

import numpy as np
import pytest
from numpy.typing import NDArray
from numpy.testing import assert_allclose

from chappy.core.components.continuum import DEFAULT_CONTINUUM_FLUX, ContinuumComponent


class TestCalculateFromPoints:
    """Test cases for ContinuumComponent.calculate_from_points static method."""

    def test_empty_points_returns_default(self) -> None:
        """Empty points list returns default continuum flux."""
        wavelength = np.array([4000.0, 4500.0, 5000.0])
        result = ContinuumComponent.calculate_from_points([], wavelength)

        assert_allclose(result, DEFAULT_CONTINUUM_FLUX)
        assert result.shape == wavelength.shape

    def test_single_point_returns_constant(self) -> None:
        """Single point returns constant flux value."""
        points = [(4500.0, 1.5)]
        wavelength = np.array([4000.0, 4500.0, 5000.0])

        result = ContinuumComponent.calculate_from_points(points, wavelength)

        assert_allclose(result, 1.5)
        assert result.shape == wavelength.shape

    def test_two_points_linear_interpolation(self) -> None:
        """Two points use linear interpolation."""
        points = [(4000.0, 1.0), (5000.0, 2.0)]
        wavelength = np.array([4000.0, 4500.0, 5000.0])

        result = ContinuumComponent.calculate_from_points(points, wavelength)

        assert_allclose(result[0], 1.0)
        assert_allclose(result[1], 1.5)  # Midpoint
        assert_allclose(result[2], 2.0)

    def test_three_points_linear_interpolation(self) -> None:
        """Three points still use linear interpolation (below MIN_POINTS_FOR_CUBIC_SPLINE)."""
        points = [(4000.0, 1.0), (4500.0, 1.5), (5000.0, 1.0)]
        wavelength = np.array([4000.0, 4250.0, 4500.0, 4750.0, 5000.0])

        result = ContinuumComponent.calculate_from_points(points, wavelength)

        # Endpoints should match
        assert_allclose(result[0], 1.0)
        assert_allclose(result[2], 1.5)
        assert_allclose(result[4], 1.0)

    def test_four_points_spline_interpolation(self) -> None:
        """Four or more points use cubic spline interpolation."""
        points = [(4000.0, 1.0), (4333.0, 1.2), (4666.0, 1.2), (5000.0, 1.0)]
        wavelength = np.array([4000.0, 4500.0, 5000.0])

        result = ContinuumComponent.calculate_from_points(points, wavelength)

        # Endpoints should be close to original values
        assert_allclose(result[0], 1.0, atol=0.01)
        assert_allclose(result[2], 1.0, atol=0.01)
        # Middle point should be interpolated (higher due to spline)
        assert result[1] > 1.0

    def test_duplicate_wavelengths_handled(self) -> None:
        """Duplicate wavelengths are averaged correctly."""
        # Two points at same wavelength with different fluxes
        points = [(4500.0, 1.0), (4500.0, 2.0), (5000.0, 1.5)]
        wavelength = np.array([4500.0, 5000.0])

        result = ContinuumComponent.calculate_from_points(points, wavelength)

        # Average of 1.0 and 2.0 at 4500.0
        assert_allclose(result[0], 1.5)
        assert_allclose(result[1], 1.5)

    def test_values_outside_range_use_edge_values(self) -> None:
        """Values outside point range use edge values (np.interp clamps)."""
        points = [(4500.0, 1.0), (5000.0, 2.0)]
        wavelength = np.array([4000.0, 5500.0])  # Outside range

        result = ContinuumComponent.calculate_from_points(points, wavelength)

        # np.interp clamps to edge values (not extrapolation)
        # At 4000 (before range): uses first point value = 1.0
        assert_allclose(result[0], 1.0)
        # At 5500 (after range): uses last point value = 2.0
        assert_allclose(result[1], 2.0)


class TestCalculateUsesContinuumPoints:
    """Test cases for calculate() using component continuum points."""

    def test_calculate_interpolates_component_points(self) -> None:
        """Instance calculate() interpolates the component's continuum points."""
        points = [(4000.0, 1.0), (4500.0, 1.5), (5000.0, 1.0)]
        wavelength = np.array([4000.0, 4250.0, 4500.0, 4750.0, 5000.0])

        component = ContinuumComponent("test")
        component.continuum_points = points.copy()

        instance_result = component.calculate(wavelength)
        static_result = ContinuumComponent.calculate_from_points(points, wavelength)

        assert_allclose(instance_result, static_result)

    def test_empty_component_returns_default(self) -> None:
        """Empty component returns default continuum flux."""
        wavelength = np.array([4000.0, 5000.0])

        component = ContinuumComponent("test")
        result = component.calculate(wavelength)

        assert_allclose(result, DEFAULT_CONTINUUM_FLUX)


class TestExportForAbsorption:
    """Test cases for exporting continuum data to absorption mode."""

    def test_not_shared_returns_none(self) -> None:
        """Disabled absorption sharing is a valid empty export."""
        component = ContinuumComponent("test")
        component.is_shared_with_absorption = False
        wavelength = np.array([4000.0, 5000.0])

        result = component.export_for_absorption(wavelength)

        assert result is None

    def test_invalid_continuum_returns_none(self) -> None:
        """User-editable invalid continuum points are rejected as no export."""
        component = ContinuumComponent("test")
        component.set_continuum_points([(4000.0, 1.0), (4050.0, 1.1)])
        wavelength = np.array([4000.0, 4050.0])

        result = component.export_for_absorption(wavelength)

        assert result is None

    def test_calculation_failure_propagates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Internal calculation failures are not converted to a missing export."""
        component = ContinuumComponent("test")
        component.set_continuum_points(
            [(4000.0, 1.0), (4200.0, 1.1), (4400.0, 1.2), (4600.0, 1.1)]
        )
        wavelength = np.array([4000.0, 4300.0, 4600.0])

        def fail_calculation(_wavelength: NDArray[np.float64]) -> NDArray[np.float64]:
            raise RuntimeError("broken continuum calculator")

        monkeypatch.setattr(component, "calculate", fail_calculation)

        with pytest.raises(RuntimeError, match="broken continuum calculator"):
            component.export_for_absorption(wavelength)


class TestGuessContinuum:
    """Test cases for automatic continuum point estimation."""

    def test_guess_continuum_creates_points(self) -> None:
        """Valid input should populate continuum anchor points."""
        component = ContinuumComponent("test")
        wavelength = np.linspace(4000.0, 4300.0, 40)
        flux = np.linspace(1.0, 1.2, 40)

        component.guess_continuum(wavelength, flux, bin_size=100.0, cut_level=0.95)

        assert component.continuum_points

    def test_guess_continuum_rejects_invalid_bin_size(self) -> None:
        """Invalid bin sizes should fail fast instead of entering fallback behavior."""
        component = ContinuumComponent("test")
        wavelength = np.linspace(4000.0, 4300.0, 40)
        flux = np.ones_like(wavelength)

        with pytest.raises(ValueError, match="bin size"):
            component.guess_continuum(wavelength, flux, bin_size=0.0)

    def test_guess_continuum_rejects_mismatched_arrays(self) -> None:
        """Mismatched input arrays are invalid core input."""
        component = ContinuumComponent("test")

        with pytest.raises(ValueError, match="same length"):
            component.guess_continuum(np.array([4000.0, 4100.0]), np.array([1.0]))

    def test_guess_continuum_rejects_nonfinite_wavelength_bounds(self) -> None:
        """Non-finite wavelength bounds should not be swallowed."""
        component = ContinuumComponent("test")

        with pytest.raises(ValueError, match="wavelength bounds"):
            component.guess_continuum(np.array([4000.0, np.nan]), np.array([1.0, 1.1]))
