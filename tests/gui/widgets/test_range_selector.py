"""Tests for the range selector widget."""

from __future__ import annotations

import math

import pytest
from pytestqt.qtbot import QtBot

from chappy.gui.common.range_selector import RangeSelectorWidget


def test_range_selector_starts_pending_without_default_wavelength_range(qtbot: QtBot) -> None:
    """Verify the selector does not expose a plausible range before data is loaded."""
    selector = RangeSelectorWidget()
    qtbot.addWidget(selector)

    assert not selector.isEnabled()
    assert selector.scene().sceneRect().isNull()


def test_range_selector_enables_only_after_spectrum_data_is_loaded(qtbot: QtBot) -> None:
    """Verify loaded spectrum data defines the selectable wavelength range."""
    selector = RangeSelectorWidget()
    qtbot.addWidget(selector)

    selector.set_spectrum_data([], [])

    assert not selector.isEnabled()
    assert selector.scene().sceneRect().isNull()

    selector.set_spectrum_data([4100.0, 4150.0, 4200.0], [1.0, 0.8, 1.1])

    scene_rect = selector.scene().sceneRect()
    assert selector.isEnabled()
    assert scene_rect.x() == 4100.0
    assert scene_rect.width() == 100.0


@pytest.mark.parametrize(
    ("wavelength", "flux", "match"),
    [
        ([4100.0], [], "matching"),
        ([], [1.0], "matching"),
        ([4100.0, math.nan], [1.0, 1.1], "finite"),
        ([4100.0, 4200.0], [1.0, math.inf], "finite"),
        ([4100.0, 4100.0], [1.0, 1.1], "non-zero"),
    ],
)
def test_range_selector_rejects_malformed_non_empty_data(
    qtbot: QtBot, wavelength: list[float], flux: list[float], match: str
) -> None:
    """Malformed non-empty selector input should fail before enabling selection."""
    selector = RangeSelectorWidget()
    qtbot.addWidget(selector)

    with pytest.raises(ValueError, match=match):
        selector.set_spectrum_data(wavelength, flux)

    assert not selector.isEnabled()
    assert selector.scene().sceneRect().isNull()
