"""Test z-value limit calculator utilities."""

import pytest

from chappy.core.redshift_limits import calculate_dynamic_z_limits, clamp_z_value


class TestCalculateDynamicZLimits:
    """Test dynamic z limits calculation."""

    def test_with_wavelength_range(self) -> None:
        """Test dynamic z limits with wavelength range."""
        rest_wavelength = 1215.67  # Lyman alpha
        lambda_range = (3500.0, 4000.0)

        z_min, z_max = calculate_dynamic_z_limits(rest_wavelength, lambda_range)

        # Expected: z_min = (3500.0 / 1215.67) - 1 ≈ 1.8791
        # Expected: z_max = (4000.0 / 1215.67) - 1 ≈ 2.2904
        assert abs(z_min - 1.8791) < 0.001
        assert abs(z_max - 2.2904) < 0.001

    def test_without_wavelength_range(self) -> None:
        """Test with no wavelength range (returns physical constraints)."""
        rest_wavelength = 1215.67
        lambda_range = None

        z_min, z_max = calculate_dynamic_z_limits(rest_wavelength, lambda_range)

        assert z_min == -0.1
        assert z_max == 10.0

    def test_physical_constraint_intersection(self) -> None:
        """Test that physical constraints are applied."""
        rest_wavelength = 1215.67
        lambda_range = (100.0, 20000.0)  # Very wide range

        z_min, z_max = calculate_dynamic_z_limits(rest_wavelength, lambda_range)

        # Should be limited by physical constraints
        assert z_min == -0.1
        assert z_max == 10.0

    def test_narrow_wavelength_range(self) -> None:
        """Test with narrow wavelength range."""
        rest_wavelength = 1548.2  # C IV
        lambda_range = (3870.0, 3900.0)  # Narrow range

        z_min, z_max = calculate_dynamic_z_limits(rest_wavelength, lambda_range)

        # Expected: z_min = (3870.0 / 1548.2) - 1 ≈ 1.500
        # Expected: z_max = (3900.0 / 1548.2) - 1 ≈ 1.519
        assert abs(z_min - 1.500) < 0.001
        assert abs(z_max - 1.519) < 0.001

    def test_zero_rest_wavelength(self) -> None:
        """Test handling of invalid rest wavelength."""
        rest_wavelength = 0.0
        lambda_range = (3500.0, 4000.0)

        z_min, z_max = calculate_dynamic_z_limits(rest_wavelength, lambda_range)

        # Should return physical constraints
        assert z_min == -0.1
        assert z_max == 10.0

    def test_negative_rest_wavelength(self) -> None:
        """Test handling of negative rest wavelength."""
        rest_wavelength = -1215.67
        lambda_range = (3500.0, 4000.0)

        z_min, z_max = calculate_dynamic_z_limits(rest_wavelength, lambda_range)

        # Should return physical constraints
        assert z_min == -0.1
        assert z_max == 10.0


class TestClampZValue:
    """Test z-value clamping."""

    def test_clamp_within_range(self) -> None:
        """Test clamping when value is already within range."""
        rest_wavelength = 1215.67
        lambda_range = (3500.0, 4000.0)

        # Value within range should not change
        assert clamp_z_value(2.0, rest_wavelength, lambda_range) == 2.0

    def test_clamp_below_minimum(self) -> None:
        """Test clamping when value is below minimum."""
        rest_wavelength = 1215.67
        lambda_range = (3500.0, 4000.0)

        # Value below range should be clamped to minimum
        clamped = clamp_z_value(1.5, rest_wavelength, lambda_range)
        assert abs(clamped - 1.8791) < 0.001

    def test_clamp_above_maximum(self) -> None:
        """Test clamping when value is above maximum."""
        rest_wavelength = 1215.67
        lambda_range = (3500.0, 4000.0)

        # Value above range should be clamped to maximum
        clamped = clamp_z_value(3.0, rest_wavelength, lambda_range)
        assert abs(clamped - 2.2904) < 0.001

    def test_clamp_to_physical_limits(self) -> None:
        """Test clamping to physical limits."""
        rest_wavelength = 1215.67
        lambda_range = None  # No range, use physical limits

        assert clamp_z_value(-1.0, rest_wavelength, lambda_range) == -0.1
        assert clamp_z_value(20.0, rest_wavelength, lambda_range) == 10.0
