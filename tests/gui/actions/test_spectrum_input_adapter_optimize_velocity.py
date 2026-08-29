"""Tests for SpectrumInputAdapter OPTIMIZE mode V key handling."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent

from chappy.core.editing_mode import EditingMode
from chappy.gui.modes.analysis.contracts import SpectrumProfile
from chappy.gui.shell.analysis_surface_ui_adapter import analysis_spectrum_policy
from chappy.gui.shell.spectrum_mode_policy import spectrum_interaction_mode_policy
from chappy.gui.spectrum.interaction.input.spectrum_input_adapter import SpectrumInputAdapter


@dataclass(slots=True)
class _InteractorView:
    """Minimal view dependency for SpectrumInputAdapter key tests."""

    coordinator: object | None = None
    wavelength_range: tuple[float, float] = (4000.0, 5000.0)

    def get_wavelength_range(self) -> tuple[float, float]:
        """Return the configured wavelength range."""
        return self.wavelength_range


@pytest.fixture
def interactor() -> Iterator[SpectrumInputAdapter]:
    """Create a SpectrumInputAdapter instance for testing."""
    yield SpectrumInputAdapter(view=_InteractorView())


def _v_key_event(modifier: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier) -> QKeyEvent:
    """Build a concrete V key press event."""
    return QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_V, modifier)


class TestOptimizeVelocityKeyHandling:
    """Test suite for OPTIMIZE mode V key handling."""

    def test_v_key_in_optimize_mode_emits_mode_shortcut_signal(
        self, interactor: SpectrumInputAdapter
    ) -> None:
        """V key in OPTIMIZE mode should emit a raw mode velocity shortcut."""
        interactor.set_mode_capabilities(
            analysis_spectrum_policy(SpectrumProfile.REGION_DETAIL).input_capabilities
        )
        emitted: list[object] = []
        interactor.sig_mode_velocity_shortcut_requested.connect(lambda: emitted.append(True))

        result = interactor.handle_key_event(_v_key_event())

        assert result is True
        assert emitted == [True]

    @pytest.mark.parametrize("mode", [EditingMode.ANALYSIS, EditingMode.CONTINUUM])
    def test_v_key_outside_optimize_mode_does_not_emit_mode_shortcut_signal(
        self, interactor: SpectrumInputAdapter, mode: EditingMode
    ) -> None:
        """V key outside OPTIMIZE mode should not emit the mode shortcut signal."""
        interactor.set_mode_capabilities(spectrum_interaction_mode_policy(mode).input_capabilities)
        emitted: list[object] = []
        interactor.sig_mode_velocity_shortcut_requested.connect(lambda: emitted.append(True))

        interactor.handle_key_event(_v_key_event())

        assert emitted == []

    def test_v_key_in_identify_mode_routes_to_identify_runtime(
        self, interactor: SpectrumInputAdapter
    ) -> None:
        """Identify owns V so active preview and pending paths can converge."""
        interactor.set_mode_capabilities(
            spectrum_interaction_mode_policy(EditingMode.IDENTIFY).input_capabilities
        )
        emitted: list[object] = []
        interactor.sig_mode_velocity_shortcut_requested.connect(lambda: emitted.append(True))

        result = interactor.handle_key_event(_v_key_event())

        assert result is True
        assert emitted == [True]

    @pytest.mark.parametrize(
        "modifier",
        [
            Qt.KeyboardModifier.ShiftModifier,
            Qt.KeyboardModifier.ControlModifier,
            Qt.KeyboardModifier.AltModifier,
            Qt.KeyboardModifier.MetaModifier,
        ],
    )
    def test_v_key_with_modifier_does_not_emit_mode_shortcut_signal(
        self, interactor: SpectrumInputAdapter, modifier: Qt.KeyboardModifier
    ) -> None:
        """V key with modifier keys should not emit the mode shortcut signal."""
        interactor.set_mode_capabilities(
            analysis_spectrum_policy(SpectrumProfile.REGION_DETAIL).input_capabilities
        )
        emitted: list[object] = []
        interactor.sig_mode_velocity_shortcut_requested.connect(lambda: emitted.append(True))

        interactor.handle_key_event(_v_key_event(modifier))

        assert emitted == []
