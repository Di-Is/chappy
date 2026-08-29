"""Tests for key and mouse intent mapping helpers."""

from __future__ import annotations

import pytest
from PySide6.QtCore import QPoint, Qt

from chappy.gui.spectrum.interaction.input.mapping.qt_input_mapper import KeyMouseIntentMapper
from chappy.gui.protocols.intent_types import PanIntent, SelectAbsorberIntent, ZoomFactorIntent


def test_zoom_key_intent_requires_configured_modifier() -> None:
    """Zoom key mapping should require a configured primary modifier."""
    mapper = KeyMouseIntentMapper()

    bare = mapper.zoom_key_intent(
        int(Qt.Key.Key_Plus),
        Qt.KeyboardModifier.NoModifier,
        (Qt.KeyboardModifier.ControlModifier,),
    )
    modified = mapper.zoom_key_intent(
        int(Qt.Key.Key_Plus),
        Qt.KeyboardModifier.ControlModifier,
        (Qt.KeyboardModifier.ControlModifier,),
    )

    assert bare is None
    assert isinstance(modified, ZoomFactorIntent)
    assert modified.factor == pytest.approx(1.1)


def test_navigation_key_intent_maps_pan_and_selection() -> None:
    """Navigation keys should map to mode-independent intent objects."""
    pan = KeyMouseIntentMapper.navigation_key_intent(int(Qt.Key.Key_Left))
    selection = KeyMouseIntentMapper.navigation_key_intent(int(Qt.Key.Key_N))

    assert isinstance(pan, PanIntent)
    assert pan.fraction == pytest.approx(-0.1)
    assert isinstance(selection, SelectAbsorberIntent)
    assert selection.direction == "next"


def test_wheel_delta_normalization_preserves_horizontal_axis() -> None:
    """Wheel delta normalization should expose both axes to callers."""
    assert KeyMouseIntentMapper.normalize_wheel_delta(QPoint(40, 120)) == (40.0, 120.0)
    assert KeyMouseIntentMapper.wheel_pan_fraction(120.0) == pytest.approx(0.08)
    assert KeyMouseIntentMapper.wheel_zoom_factor(120.0) == pytest.approx(1.1)
