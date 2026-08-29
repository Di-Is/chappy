"""Tests for spectrum action intent types."""

from __future__ import annotations

import pytest

from chappy.gui.protocols.intent_types import (
    AddContinuumPointIntent,
    ModifyAbsorberIntent,
    PanIntent,
    SelectAbsorberIntent,
    SelectRangeIntent,
    ZoomFactorIntent,
    ZoomRectIntent,
)


class TestIntentTypes:
    """Test suite for intent data classes."""

    def test_pan_intent_creation(self) -> None:
        """Test PanIntent creation."""
        intent = PanIntent(fraction=0.25)
        assert intent.fraction == 0.25

    def test_zoom_rect_intent_creation(self) -> None:
        """Test ZoomRectIntent creation."""
        intent = ZoomRectIntent(
            min_wavelength=4000.0, max_wavelength=5000.0, min_flux=0.0, max_flux=1.0
        )
        assert intent.min_wavelength == 4000.0
        assert intent.max_wavelength == 5000.0
        assert intent.min_flux == 0.0
        assert intent.max_flux == 1.0

    def test_zoom_rect_intent_optional_flux(self) -> None:
        """Test ZoomRectIntent with optional flux parameters."""
        intent = ZoomRectIntent(min_wavelength=4000.0, max_wavelength=5000.0)
        assert intent.min_wavelength == 4000.0
        assert intent.max_wavelength == 5000.0
        assert intent.min_flux is None
        assert intent.max_flux is None

    def test_zoom_factor_intent_creation(self) -> None:
        """Test ZoomFactorIntent creation."""
        intent = ZoomFactorIntent(factor=1.5, center_wavelength=4500.0)
        assert intent.factor == 1.5
        assert intent.center_wavelength == 4500.0

    def test_zoom_factor_intent_no_center(self) -> None:
        """Test ZoomFactorIntent without center."""
        intent = ZoomFactorIntent(factor=0.8)
        assert intent.factor == 0.8
        assert intent.center_wavelength is None

    def test_select_range_intent_creation(self) -> None:
        """Test SelectRangeIntent creation."""
        intent = SelectRangeIntent(start_wavelength=4100.0, end_wavelength=4900.0)
        assert intent.start_wavelength == 4100.0
        assert intent.end_wavelength == 4900.0

    def test_select_absorber_intent_by_id(self) -> None:
        """Test SelectAbsorberIntent with ID."""
        intent = SelectAbsorberIntent(absorber_id="abs_123")
        assert intent.absorber_id == "abs_123"
        assert intent.direction is None

    def test_select_absorber_intent_by_direction(self) -> None:
        """Test SelectAbsorberIntent with direction."""
        intent = SelectAbsorberIntent(direction="next")
        assert intent.absorber_id is None
        assert intent.direction == "next"

    def test_modify_absorber_intent_creation(self) -> None:
        """Test ModifyAbsorberIntent creation."""
        intent = ModifyAbsorberIntent(absorber_id="abs_123", parameter="redshift", value=0.5)
        assert intent.absorber_id == "abs_123"
        assert intent.parameter == "redshift"
        assert intent.value == 0.5

    def test_add_continuum_point_intent_creation(self) -> None:
        """Test AddContinuumPointIntent creation."""
        intent = AddContinuumPointIntent(wavelength=4500.0, flux=0.8)
        assert intent.wavelength == 4500.0
        assert intent.flux == 0.8
