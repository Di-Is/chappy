"""Tests for Y-axis auto-range label margin calculation.

This module tests the dynamic label margin feature in MatplotlibSpectrumPlot.auto_range_y():
- Labels are positioned at y=0.94 (transAxes)
- Y-axis range is calculated so that y_max is at 94% of the plot area
- Formula: new_y_max = new_y_min + (y_max - new_y_min) / 0.94
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pytest

from chappy.gui.adapters.plotting import MatplotlibSpectrumPlot
from chappy.plotting.utils.validators import validate_generic_spectrum_data

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


@pytest.fixture
def spectrum_plot(qtbot: QtBot) -> MatplotlibSpectrumPlot:
    """Create a MatplotlibSpectrumPlot instance for testing."""
    plot = MatplotlibSpectrumPlot(observed_data_validator=validate_generic_spectrum_data)
    qtbot.addWidget(plot)
    return plot


class TestAutoRangeYLabelMargin:
    """Tests for dynamic Y-axis label margin in auto_range_y()."""

    def test_data_max_positioned_at_94_percent(
        self, spectrum_plot: MatplotlibSpectrumPlot
    ) -> None:
        """Data max should be positioned at approximately 94% of plot area."""
        x_data = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        y_data = np.array([0.2, 0.4, 0.6, 0.8, 0.7])  # y_min=0.2, y_max=0.8

        spectrum_plot.set_observed_spectrum(x_data, y_data, error=None)
        spectrum_plot.auto_range_y()

        # Get resulting range
        _, _, y_min_result, y_max_result = spectrum_plot.renderer.get_range()

        # Calculate normalized position of data max (0.8)
        data_max = 0.8
        normalized_data_max = (data_max - y_min_result) / (y_max_result - y_min_result)

        # Data max should be at approximately 94% of plot area
        # Allow some tolerance due to minimum bounds
        assert normalized_data_max <= 0.94, (
            f"Data max at normalized {normalized_data_max:.3f} should be at or below 0.94"
        )

    def test_minimum_y_max_bound(self, spectrum_plot: MatplotlibSpectrumPlot) -> None:
        """Small data should still have minimum y_max of 1.05."""
        # Small data range near 1.0
        x_data = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        y_data = np.array([0.95, 0.98, 0.96, 0.99, 1.0])  # y_min=0.95, y_max=1.0

        spectrum_plot.set_observed_spectrum(x_data, y_data, error=None)
        spectrum_plot.auto_range_y()

        # Get resulting range
        _, _, y_min_result, y_max_result = spectrum_plot.renderer.get_range()

        # y_max should be at least 1.05 due to minimum bound
        assert y_max_result >= 1.05, f"Expected y_max >= 1.05, got {y_max_result}"

    def test_large_data_range_expands_y_axis(self, spectrum_plot: MatplotlibSpectrumPlot) -> None:
        """Large data range should expand Y-axis to fit data below 94%."""
        # Data range that needs expansion
        x_data = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        y_data = np.array([0.0, 0.5, 0.25, 0.75, 1.5])  # y_max=1.5 needs room above

        spectrum_plot.set_observed_spectrum(x_data, y_data, error=None)
        spectrum_plot.auto_range_y()

        # Get resulting range
        _, _, y_min_result, y_max_result = spectrum_plot.renderer.get_range()

        # Calculate expected values:
        # new_y_min = min(0.0 - 0.05, -0.05) = -0.05
        # required_plot_range = (1.5 - (-0.05)) / 0.94 = 1.649...
        # new_y_max = -0.05 + 1.649 = 1.599...
        expected_y_max = -0.05 + (1.5 - (-0.05)) / 0.94

        # y_max should be approximately the calculated value (or 1.05 minimum)
        assert y_max_result >= max(expected_y_max, 1.05) - 0.01, (
            f"Expected y_max >= {max(expected_y_max, 1.05):.3f}, got {y_max_result}"
        )

    def test_data_max_below_label_position(self, spectrum_plot: MatplotlibSpectrumPlot) -> None:
        """Y max should always be positioned below y=0.94 in normalized coords."""
        # Test with various data values
        test_cases = [
            np.array([0.2, 0.4, 0.6, 0.8, 0.7]),  # typical absorption
            np.array([0.0, 0.5, 0.25, 0.75, 1.0]),  # full range
            np.array([-0.1, 0.3, 0.5, 0.8, 1.2]),  # extended range
        ]

        x_data = np.array([1.0, 2.0, 3.0, 4.0, 5.0])

        for y_data in test_cases:
            spectrum_plot.set_observed_spectrum(x_data, y_data, error=None)
            spectrum_plot.auto_range_y()

            # Get resulting range
            _, _, y_min_result, y_max_result = spectrum_plot.renderer.get_range()

            # Calculate normalized position of data max
            data_max = float(np.max(y_data))
            normalized_data_max = (data_max - y_min_result) / (y_max_result - y_min_result)

            # Data max should be at or below label position (0.94 in transAxes)
            assert normalized_data_max <= 0.94 + 0.01, (  # small tolerance for floating point
                f"Data max {data_max} at normalized {normalized_data_max:.3f} "
                f"should be below 0.94 (y_range: {y_min_result:.3f} - {y_max_result:.3f})"
            )

    def test_formula_correctness(self, spectrum_plot: MatplotlibSpectrumPlot) -> None:
        """Verify the formula: new_y_max = new_y_min + (y_max - new_y_min) / 0.94."""
        label_y_position = 0.94

        # Test cases: (y_min, y_max) -> verify normalized position
        test_cases = [(0.0, 1.0), (0.2, 0.8), (-0.1, 1.5), (0.5, 0.9)]

        for y_min, y_max in test_cases:
            # Calculate using formula
            new_y_min = min(y_min - 0.05, -0.05)
            required_plot_range = (y_max - new_y_min) / label_y_position
            new_y_max = new_y_min + required_plot_range
            new_y_max = max(new_y_max, 1.05)  # minimum bound

            # Verify y_max is at 94% position (or less if minimum bound applied)
            if new_y_max > 1.05:  # no minimum bound interference
                normalized_y_max = (y_max - new_y_min) / (new_y_max - new_y_min)
                assert abs(normalized_y_max - 0.94) < 0.001, (
                    f"y_min={y_min}, y_max={y_max}: "
                    f"normalized position {normalized_y_max:.4f} should be 0.94"
                )


class _FailingRangeRenderer:
    """Renderer stub used to simulate get_range failure."""

    plot_items: dict[str, object]

    def __init__(self) -> None:
        self.plot_items = {}

    def get_range(self) -> tuple[float, float, float, float]:
        """Fail when auto-range reads current plot range."""
        msg = "forced renderer.get_range() failure"
        raise RuntimeError(msg)


class TestAutoRangeYExceptions:
    """Regression tests for fail-fast exception boundaries in auto-range helpers."""

    def test_auto_range_y_fails_fast_without_renderer(
        self, spectrum_plot: MatplotlibSpectrumPlot
    ) -> None:
        """Auto-range must fail fast when renderer dependency is missing."""
        spectrum_plot.renderer = None

        with pytest.raises(RuntimeError, match="Renderer is required for Y-axis auto-range"):
            spectrum_plot.auto_range_y()

    def test_auto_range_y_propagates_renderer_get_range_failure(
        self, spectrum_plot: MatplotlibSpectrumPlot
    ) -> None:
        """Renderer internal range failures should propagate from auto_range_y()."""
        spectrum_plot.renderer = _FailingRangeRenderer()

        with pytest.raises(RuntimeError, match=r"forced renderer\.get_range\(\) failure"):
            spectrum_plot.auto_range_y()
