"""Tests for absorber component."""

import numpy as np
import pytest
from numpy.testing import assert_allclose
from numpy.typing import NDArray

from chappy.core.components.absorber import AbsorberComponent


class TestAbsorberComponent:
    """Test suite for AbsorberComponent."""

    @pytest.fixture
    def sample_absorber(self) -> AbsorberComponent:
        """Create a sample absorber component."""
        return AbsorberComponent(
            name="Test Absorber",
            wavelength=4861.0,  # H-beta
            column_density=11.0,  # Moderate column density for reasonable optical depth
            b_parameter=20.0,
            redshift=0.0,
            oscillator_strength=0.0121,  # H-beta oscillator strength (much weaker than Lyman-alpha)
            gamma=8.42e6,  # H-beta natural broadening
        )

    @pytest.fixture
    def wavelength_grid(self) -> NDArray[np.float64]:
        """Create a wavelength grid around H-beta."""
        return np.linspace(4850, 4870, 1000)

    def test_initialization(self, sample_absorber: AbsorberComponent) -> None:
        """Test absorber initialization."""
        assert sample_absorber.name == "Test Absorber"
        assert sample_absorber.enabled

        # Check parameters
        assert sample_absorber.wavelength == 4861.0
        assert sample_absorber.get_parameter_value("column_density") == 11.0
        assert sample_absorber.get_parameter_value("b_parameter") == 20.0
        assert sample_absorber.get_parameter_value("redshift") == 0.0

    def test_calculate_absorption(
        self, sample_absorber: AbsorberComponent, wavelength_grid: NDArray[np.float64]
    ) -> None:
        """Test absorption profile calculation."""
        transmission = sample_absorber.calculate(wavelength_grid)

        # Basic checks
        assert len(transmission) == len(wavelength_grid)
        assert np.all(transmission >= 0)  # Transmission should be non-negative
        assert np.all(transmission <= 1)  # Transmission should be <= 1

        # Check that minimum is at line center within the sampled grid resolution.
        center_idx = np.argmin(np.abs(wavelength_grid - 4861.0))

        # For very strong absorption, transmission may be zero over a wide range
        # Find the center of the absorption region instead of just the first minimum
        min_transmission = np.min(transmission)
        if min_transmission == 0.0:
            # Find all indices where transmission equals minimum
            min_indices = np.where(transmission == min_transmission)[0]
            # Take the middle of the absorption region
            min_idx = min_indices[len(min_indices) // 2]
        else:
            min_idx = np.argmin(transmission)

        grid_spacing = float(np.max(np.diff(wavelength_grid)))
        assert wavelength_grid[min_idx] == pytest.approx(
            wavelength_grid[center_idx], abs=grid_spacing
        )

        # Check that it approaches 1 far from line center
        far_wings = np.abs(wavelength_grid - 4861.0) > 5.0
        assert np.all(transmission[far_wings] > 0.99)

    def test_redshift_effect(self) -> None:
        """Test redshift effect on line position."""
        # Create absorber at rest (use H-beta parameters)
        absorber_rest = AbsorberComponent(
            wavelength=4861.0,
            column_density=12.0,
            redshift=0.0,
            oscillator_strength=0.0121,
            gamma=8.42e6,
        )

        # Create absorber with small redshift that stays in wavelength range
        z = 0.002  # Small redshift: 4861 * 1.002 = 4870.7 Å
        absorber_redshifted = AbsorberComponent(
            wavelength=4861.0,
            column_density=12.0,
            redshift=z,
            oscillator_strength=0.0121,
            gamma=8.42e6,
        )

        # Extend wavelength grid to include redshifted line
        extended_grid = np.linspace(4850, 4880, 1000)

        # Calculate profiles
        trans_rest = absorber_rest.calculate(extended_grid)
        trans_z = absorber_redshifted.calculate(extended_grid)

        # Find line centers using improved method
        def find_absorption_center(
            transmission: NDArray[np.float64], wavelength: NDArray[np.float64]
        ) -> float:
            min_val = np.min(transmission)
            if min_val == 0.0:
                min_indices = np.where(transmission == min_val)[0]
                return wavelength[min_indices[len(min_indices) // 2]]
            return wavelength[np.argmin(transmission)]

        center_rest = find_absorption_center(trans_rest, extended_grid)
        center_z = find_absorption_center(trans_z, extended_grid)

        # Redshifted line should be at (1+z) * rest wavelength
        expected_center = 4861.0 * (1 + z)

        grid_spacing = float(np.max(np.diff(extended_grid)))
        assert center_z == pytest.approx(expected_center, abs=grid_spacing / 2)
        assert center_z > center_rest  # Redshifted line is at longer wavelength

    def test_column_density_effect(self, wavelength_grid: NDArray[np.float64]) -> None:
        """Test effect of column density on line strength."""
        # Create absorbers with different column densities (use H-beta parameters)
        absorber_weak = AbsorberComponent(
            wavelength=4861.0,
            column_density=10.5,  # Very weak
            b_parameter=20.0,
            oscillator_strength=0.0121,
            gamma=8.42e6,
        )

        absorber_strong = AbsorberComponent(
            wavelength=4861.0,
            column_density=11.5,  # Moderate
            b_parameter=20.0,
            oscillator_strength=0.0121,
            gamma=8.42e6,
        )

        # Calculate profiles
        trans_weak = absorber_weak.calculate(wavelength_grid)
        trans_strong = absorber_strong.calculate(wavelength_grid)

        # Stronger absorber should have deeper line
        min_weak = np.min(trans_weak)
        min_strong = np.min(trans_strong)

        assert min_strong < min_weak
        assert min_weak > 0.5  # Weak line should be detectable but not saturated
        assert min_strong < min_weak  # Strong line should be deeper

    def test_b_parameter_effect(self, wavelength_grid: NDArray[np.float64]) -> None:
        """Test effect of b parameter on line width."""
        # Create absorbers with different b parameters (use H-beta parameters)
        absorber_narrow = AbsorberComponent(
            wavelength=4861.0,
            column_density=12.0,  # Lower column density for clearer width effect
            b_parameter=5.0,  # Narrow
            oscillator_strength=0.0121,
            gamma=8.42e6,
        )

        absorber_wide = AbsorberComponent(
            wavelength=4861.0,
            column_density=12.0,  # Lower column density for clearer width effect
            b_parameter=50.0,  # Wide
            oscillator_strength=0.0121,
            gamma=8.42e6,
        )

        # Calculate profiles
        trans_narrow = absorber_narrow.calculate(wavelength_grid)
        trans_wide = absorber_wide.calculate(wavelength_grid)

        # Measure line widths (FWHM approximation)
        def measure_width(
            transmission: NDArray[np.float64], wavelength: NDArray[np.float64]
        ) -> float:
            min_trans = np.min(transmission)
            half_depth = 1.0 - (1.0 - min_trans) / 2.0

            # Find points at half depth
            below_half = transmission < half_depth
            if not np.any(below_half):
                return 0.0

            indices = np.where(below_half)[0]
            return wavelength[indices[-1]] - wavelength[indices[0]]

        width_narrow = measure_width(trans_narrow, wavelength_grid)
        width_wide = measure_width(trans_wide, wavelength_grid)

        assert width_wide > width_narrow

    def test_covering_factor_effect(
        self, sample_absorber: AbsorberComponent, wavelength_grid: NDArray[np.float64]
    ) -> None:
        """Partial covering should reduce absorption depth."""

        baseline = sample_absorber.calculate(wavelength_grid)

        partial_cover = AbsorberComponent(
            name="Partial Cover",
            wavelength=sample_absorber.wavelength,
            column_density=sample_absorber.get_parameter_value("column_density"),
            b_parameter=sample_absorber.get_parameter_value("b_parameter"),
            redshift=sample_absorber.get_parameter_value("redshift"),
            oscillator_strength=sample_absorber.oscillator_strength,
            gamma=sample_absorber.gamma,
        )
        partial_cover.set_parameter("covering_factor", 0.5)
        partial_transmission = partial_cover.calculate(wavelength_grid)

        opaque_cover = AbsorberComponent(
            name="Opaque Cover",
            wavelength=sample_absorber.wavelength,
            column_density=sample_absorber.get_parameter_value("column_density"),
            b_parameter=sample_absorber.get_parameter_value("b_parameter"),
            redshift=sample_absorber.get_parameter_value("redshift"),
            oscillator_strength=sample_absorber.oscillator_strength,
            gamma=sample_absorber.gamma,
        )
        opaque_cover.set_parameter("covering_factor", 0.0)
        opaque_transmission = opaque_cover.calculate(wavelength_grid)

        assert np.min(partial_transmission) > np.min(baseline)
        assert np.allclose(opaque_transmission, 1.0)

    def test_calculate_fails_fast_when_covering_factor_is_missing(
        self, sample_absorber: AbsorberComponent, wavelength_grid: NDArray[np.float64]
    ) -> None:
        """A corrupted absorber must not silently assume full covering."""
        del sample_absorber.parameters["covering_factor"]

        with pytest.raises(KeyError, match="covering_factor"):
            sample_absorber.calculate(wavelength_grid)

    def test_calculate_fails_fast_when_covering_factor_is_out_of_range(
        self, sample_absorber: AbsorberComponent, wavelength_grid: NDArray[np.float64]
    ) -> None:
        """A corrupted covering-factor value must not be silently clamped."""
        parameter = sample_absorber.parameters["covering_factor"]
        parameter.max_val = 2.0
        parameter.set_value(1.5)

        with pytest.raises(ValueError, match="Invalid covering_factor"):
            sample_absorber.calculate(wavelength_grid)

    def test_parameter_validation(self) -> None:
        """Test parameter validation and bounds."""
        absorber = AbsorberComponent()

        # Test column density bounds
        with pytest.raises(ValueError, match="outside bounds"):
            absorber.set_parameter("column_density", 5.0)  # Too low

        with pytest.raises(ValueError, match="outside bounds"):
            absorber.set_parameter("column_density", 25.0)  # Too high

        # Test b parameter bounds
        with pytest.raises(ValueError, match="outside bounds"):
            absorber.set_parameter("b_parameter", 0.5)  # Too low

        with pytest.raises(ValueError, match="outside bounds"):
            absorber.set_parameter("b_parameter", 2000.0)  # Too high

    def test_change_event_dispatch(self, sample_absorber: AbsorberComponent) -> None:
        """Test that changing parameters dispatches change events."""
        event_count = 0

        def count_events(change_set: object) -> None:
            nonlocal event_count
            event_count += 1

        sample_absorber.events.subscribe(count_events)

        # Change parameters (use actual fittable parameters)
        sample_absorber.set_parameter("column_density", 15.0)
        sample_absorber.set_parameter("b_parameter", 25.0)

        assert event_count == 2

    def test_component_enable_disable(
        self, sample_absorber: AbsorberComponent, wavelength_grid: NDArray[np.float64]
    ) -> None:
        """Test enabling/disabling component."""
        # Calculate with enabled component
        trans_enabled = sample_absorber.calculate(wavelength_grid)

        # Disable component
        sample_absorber.enabled = False

        # Calculate again
        trans_disabled = sample_absorber.calculate(wavelength_grid)

        # When disabled, should still calculate (caller decides usage)
        assert len(trans_disabled) == len(trans_enabled)

        # But enabled state should be False
        assert not sample_absorber.enabled


class TestAbsorberPhysics:
    """Test physical correctness of absorber calculations."""

    def test_weak_line_limit(self) -> None:
        """Test weak line limit (optical depth << 1)."""
        # Very weak absorber
        absorber = AbsorberComponent(
            wavelength=5000.0,
            column_density=11.0,  # Very low column density
            b_parameter=20.0,
        )

        wavelength = np.linspace(4990, 5010, 1000)
        transmission = absorber.calculate(wavelength)

        # In weak limit, transmission ≈ 1 - τ
        # where τ is small everywhere
        max_absorption = 1.0 - np.min(transmission)
        assert max_absorption < 0.1  # Less than 10% absorption

        # Normalized absorption profile for symmetry checks
        profile = 1.0 - transmission
        profile_norm = profile / np.max(profile)

        grid_spacing = float(np.max(np.diff(wavelength)))
        offsets = np.arange(1, 50)
        wavelength_offsets = offsets * grid_spacing
        left_profile = np.interp(5000.0 - wavelength_offsets, wavelength, profile_norm)
        right_profile = np.interp(5000.0 + wavelength_offsets, wavelength, profile_norm)
        assert_allclose(left_profile, right_profile, rtol=0.0, atol=1e-12)

        sigma_wave = 5000.0 * 20.0 * 1e5 / 2.99792458e10
        far_region = np.abs(wavelength - 5000.0) > 5 * sigma_wave
        assert np.all(profile_norm[far_region] < 0.05)

    def test_saturated_line_limit(self) -> None:
        """Test saturated line limit (optical depth >> 1)."""
        # Very strong absorber (but not extreme)
        absorber = AbsorberComponent(
            wavelength=5000.0,
            column_density=16.0,  # High but reasonable column density
            b_parameter=15.0,  # Broader line to help recovery in wings
        )

        wavelength = np.linspace(4990, 5010, 1000)  # Wider range
        transmission = absorber.calculate(wavelength)

        # In saturated limit, transmission ≈ 0 at line center
        min_transmission = np.min(transmission)
        assert min_transmission < 0.01  # Nearly complete absorption

        # Should show significant recovery further out in the wings
        wing_indices = np.abs(wavelength - 5000.0) > 8.0  # Farther wings
        if np.any(wing_indices):
            wing_transmission = transmission[wing_indices]
            assert np.all(wing_transmission > 0.5)  # Significant recovery
