"""Tests for SpectrumInputAdapter velocity drag and drop support."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

import pytest

from chappy.core.constants import LIGHT_SPEED_KMS
from chappy.gui.modes.analysis.contracts import SpectrumProfile
from chappy.gui.shell.analysis_surface_ui_adapter import analysis_spectrum_policy
from chappy.presentation.interaction.interaction_contracts import (
    AbsorberDragPayload,
    InteractionChannel,
    InteractionEvent,
    InteractionEventKind,
)
from chappy.gui.spectrum.interaction.channels.ports import InteractionChannelControllerPort
from chappy.gui.spectrum.interaction.input.ports import VelocityDragSignalPort
from chappy.gui.spectrum.interaction.input.spectrum_input_adapter import SpectrumInputAdapter
from chappy.presentation.velocity import VelocityDragRequest
from chappy.gui.spectrum.velocity import VelocityGridWidget

if TYPE_CHECKING:
    from PySide6.QtWidgets import QApplication


class _Signal:
    """Small callback signal used by velocity view fakes."""

    def __init__(self) -> None:
        self._callbacks: list[Callable[[object], None]] = []

    def connect(self, callback: Callable[[object], None]) -> object:
        """Register a callback."""
        self._callbacks.append(callback)
        return None

    def emit(self, payload: object) -> None:
        """Notify all registered callbacks."""
        for callback in list(self._callbacks):
            callback(payload)


class _VelocityView:
    """Velocity view fake exposing only drag signals."""

    def __init__(self) -> None:
        self.sig_velocity_drag_requested = _Signal()
        self.sig_velocity_drag_update = _Signal()
        self.sig_velocity_drag_complete = _Signal()


@dataclass(slots=True)
class _InteractorView:
    """Minimal view dependency for SpectrumInputAdapter velocity tests."""

    wavelength_range: tuple[float, float] = (4000.0, 5000.0)
    coordinator: object | None = None

    def get_wavelength_range(self) -> tuple[float, float]:
        """Return the configured wavelength range."""
        return self.wavelength_range


@dataclass(slots=True)
class _RecordingInteractionController:
    """Interaction controller fake that records events processed by the interactor."""

    events: list[InteractionEvent] = field(default_factory=list)

    def process_event(self, event: InteractionEvent) -> bool:
        """Record an interaction event."""
        self.events.append(event)
        return True


@dataclass(slots=True)
class _InteractorHarness:
    """Container for the interactor and recorded state."""

    interactor: SpectrumInputAdapter
    controller: _RecordingInteractionController


@pytest.fixture
def harness(qapp: "QApplication") -> _InteractorHarness:
    """Create a SpectrumInputAdapter with state-recording dependencies."""
    assert qapp is not None
    interactor = SpectrumInputAdapter(view=_InteractorView())
    interactor.set_mode_capabilities(
        analysis_spectrum_policy(SpectrumProfile.REGION_DETAIL).input_capabilities
    )
    controller = _RecordingInteractionController()
    interactor.set_absorber_drag_state_controller(
        cast(InteractionChannelControllerPort, controller)
    )
    return _InteractorHarness(interactor=interactor, controller=controller)


def _first_event(controller: _RecordingInteractionController) -> InteractionEvent:
    """Return the single recorded interaction event."""
    assert len(controller.events) == 1
    return controller.events[0]


def test_velocity_view_signal_starts_absorber_drag(harness: _InteractorHarness) -> None:
    """VelocityGridWidget drag request signal should begin absorber drag via the interactor."""
    velocity_view = _VelocityView()
    harness.interactor.connect_velocity_view(velocity_view)

    velocity_view.sig_velocity_drag_requested.emit(
        VelocityDragRequest("abs_001", 50.0, 1215.67, 0.5, 1.5)
    )

    event = _first_event(harness.controller)
    expected_wavelength = 1215.67 * (1.0 + 1.5) * (1.0 + 50.0 / LIGHT_SPEED_KMS)
    assert event.channel is InteractionChannel.ABSORBER_DRAG
    assert event.kind is InteractionEventKind.ABSORBER_DRAG_BEGIN
    assert event.payload == AbsorberDragPayload(absorber_id="abs_001")
    assert event.position == (pytest.approx(expected_wavelength), 0.5)
    assert harness.interactor.dragging_absorber_id() == "abs_001"


def test_velocity_view_signal_respects_selected_line_absorbers(
    harness: _InteractorHarness,
) -> None:
    """VelocityGridWidget drag request should respect optimize selected-line eligibility."""
    velocity_view = _VelocityView()
    harness.interactor.set_selected_line_absorbers({"allowed_absorber"})
    harness.interactor.connect_velocity_view(velocity_view)

    velocity_view.sig_velocity_drag_requested.emit(
        VelocityDragRequest("other_absorber", 50.0, 1215.67, 0.5, 1.5)
    )

    assert harness.controller.events == []
    assert harness.interactor.dragging_absorber_id() is None


def test_velocity_view_drag_signal_contract_uses_payload_object(qapp: "QApplication") -> None:
    """VelocityGridWidget drag signals should accept a single typed payload."""
    assert qapp is not None
    captured: list[object] = []
    view = VelocityGridWidget()
    view.sig_velocity_drag_requested.connect(captured.append)

    payload = VelocityDragRequest("abs_001", 50.0, 1215.67, 0.5, 1.5)
    view.sig_velocity_drag_requested.emit(payload)

    assert captured == [payload]


@pytest.mark.parametrize(
    ("velocity", "center_z", "rest_wavelength", "expected_wavelength"),
    [
        (0.0, 0.0, 1215.67, 1215.67),
        (100.0, 0.0, 1215.67, 1215.67 * (1.0 + 100.0 / LIGHT_SPEED_KMS)),
        (0.0, 1.72, 1215.67, 1215.67 * (1.0 + 1.72)),
    ],
)
def test_velocity_drag_request_converts_to_wavelength(
    harness: _InteractorHarness,
    velocity: float,
    center_z: float,
    rest_wavelength: float,
    expected_wavelength: float,
) -> None:
    """Velocity drag requests should be converted into wavelength-space drag events."""
    velocity_view = _VelocityView()
    harness.interactor.connect_velocity_view(velocity_view)

    velocity_view.sig_velocity_drag_requested.emit(
        VelocityDragRequest("abs_001", velocity, rest_wavelength, 0.5, center_z)
    )

    event = _first_event(harness.controller)
    assert event.channel is InteractionChannel.ABSORBER_DRAG
    assert event.kind is InteractionEventKind.ABSORBER_DRAG_BEGIN
    assert event.payload == AbsorberDragPayload(absorber_id="abs_001")
    assert event.position == (pytest.approx(expected_wavelength), 0.5)
    assert harness.interactor.dragging_absorber_id() == "abs_001"
