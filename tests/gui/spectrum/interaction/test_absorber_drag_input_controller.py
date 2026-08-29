"""Tests for absorber drag input orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from chappy.gui.spectrum.interaction.input.controllers.absorber_drag_input_controller import (
    AbsorberDragInputController,
)
from chappy.gui.spectrum.interaction.support.errors import InteractionStateError
from chappy.presentation.interaction.interaction_contracts import (
    AbsorberDragPayload,
    InteractionChannel,
    InteractionEvent,
    InteractionEventKind,
    InteractionPhase,
)


@dataclass
class _AbsorberDragStateControllerFake:
    """Record absorber drag interaction events."""

    processed_events: list[InteractionEvent] = field(default_factory=list)
    process_result: bool = True

    @property
    def phase(self) -> InteractionPhase:
        """Return a stable phase for the controller port."""
        return InteractionPhase.IDLE

    def process_event(self, event: InteractionEvent) -> bool:
        """Record a processed interaction event."""
        self.processed_events.append(event)
        return self.process_result

    def cancel_interaction(self, *, reason: str | None) -> bool:
        """Support the shared controller port."""
        cancel_event = InteractionEvent(
            channel=InteractionChannel.ABSORBER_DRAG,
            kind=InteractionEventKind.ABSORBER_DRAG_CANCEL,
            payload=AbsorberDragPayload(reason=reason),
        )
        return self.process_event(cancel_event)


@dataclass
class _AbsorberDragOwnerFake:
    """Owner fake for absorber drag input tests."""

    controller: _AbsorberDragStateControllerFake = field(
        default_factory=_AbsorberDragStateControllerFake
    )
    active_channel: InteractionChannel | None = None
    drag_enabled: bool = True
    active_absorber_id: str | None = None
    detected_absorber_id: str | None = "abs-1"
    cleared_count: int = 0
    detected_wavelengths: list[float] = field(default_factory=list)
    can_start_drag: bool = True

    def require_absorber_drag_controller(self) -> _AbsorberDragStateControllerFake:
        """Return the absorber drag state controller."""
        return self.controller

    def active_input_channel(self) -> InteractionChannel | None:
        """Return the currently active channel."""
        return self.active_channel

    def can_start_absorber_drag(self) -> bool:
        """Return whether absorber drag can start."""
        return self.can_start_drag

    def absorber_drag_enabled(self) -> bool:
        """Return whether absorber drag is enabled."""
        return self.drag_enabled

    def active_absorber_drag_id(self) -> str | None:
        """Return the active absorber id."""
        return self.active_absorber_id

    def acquire_absorber_drag(self, absorber_id: str) -> None:
        """Acquire the absorber drag channel."""
        self.active_absorber_id = absorber_id
        self.active_channel = InteractionChannel.ABSORBER_DRAG

    def clear_absorber_drag(self) -> None:
        """Record drag state clearing."""
        self.active_absorber_id = None
        self.active_channel = None
        self.cleared_count += 1

    def absorber_at_wavelength(self, wavelength: float) -> str | None:
        """Return the configured absorber id."""
        self.detected_wavelengths.append(wavelength)
        return self.detected_absorber_id


def test_begin_requires_absorber_drag_capability() -> None:
    """Absorber drag should not begin when drag capability is disabled."""
    owner = _AbsorberDragOwnerFake(drag_enabled=False)
    controller = AbsorberDragInputController(owner=owner)

    handled = controller.begin_drag_at(position=(4100.0, 0.2), modifiers=0)

    assert handled is False
    assert owner.controller.processed_events == []


def test_begin_requires_available_drag_channel() -> None:
    """Absorber drag should not begin when the channel owner rejects it."""
    owner = _AbsorberDragOwnerFake(can_start_drag=False)
    controller = AbsorberDragInputController(owner=owner)

    handled = controller.begin_drag_at(position=(4100.0, 0.2), modifiers=0)

    assert handled is False
    assert owner.controller.processed_events == []


def test_velocity_drag_owner_surface_delegates_to_owner_state() -> None:
    """Velocity drag adapter owner operations should delegate through this controller."""
    owner = _AbsorberDragOwnerFake(can_start_drag=True)
    controller = AbsorberDragInputController(owner=owner)

    assert controller.can_start_absorber_drag() is True

    controller.acquire_absorber_drag("abs-velocity")

    assert controller.active_absorber_drag_id() == "abs-velocity"
    assert owner.active_channel is InteractionChannel.ABSORBER_DRAG

    controller.clear_absorber_drag()

    assert controller.active_absorber_drag_id() is None
    assert owner.active_channel is None


def test_begin_respects_selected_line_absorbers() -> None:
    """Only selected-line absorbers should be draggable when restricted."""
    owner = _AbsorberDragOwnerFake(detected_absorber_id="abs-2")
    controller = AbsorberDragInputController(owner=owner)
    controller.set_selected_line_absorbers({"abs-1"})

    handled = controller.begin_drag_at(position=(4100.0, 0.2), modifiers=0)

    assert handled is False
    assert owner.detected_wavelengths == [4100.0]
    assert owner.controller.processed_events == []


def test_begin_sends_absorber_drag_begin_event() -> None:
    """Begin should send a typed absorber drag begin event."""
    owner = _AbsorberDragOwnerFake()
    controller = AbsorberDragInputController(owner=owner)

    handled = controller.begin_drag_at(position=(4100.0, 0.2), modifiers=3)

    assert handled is True
    event = owner.controller.processed_events[-1]
    assert event.kind is InteractionEventKind.ABSORBER_DRAG_BEGIN
    assert event.position == (4100.0, 0.2)
    assert event.modifiers == 3
    assert isinstance(event.payload, AbsorberDragPayload)
    assert event.payload.absorber_id == "abs-1"


def test_update_and_complete_require_active_absorber() -> None:
    """Update and complete should no-op when no drag is active."""
    owner = _AbsorberDragOwnerFake(active_absorber_id=None)
    controller = AbsorberDragInputController(owner=owner)

    assert controller.update_drag_at(position=(4200.0, 0.3), modifiers=0) is False
    assert controller.complete_drag_at(position=(4300.0, 0.4), modifiers=0) is False
    assert owner.controller.processed_events == []


def test_update_and_complete_send_typed_events() -> None:
    """Active drag update and complete should send typed events."""
    owner = _AbsorberDragOwnerFake(active_absorber_id="abs-1")
    controller = AbsorberDragInputController(owner=owner)

    assert controller.update_drag_at(position=(4200.0, 0.3), modifiers=1) is True
    assert controller.complete_drag_at(position=(4300.0, 0.4), modifiers=2) is True

    assert [event.kind for event in owner.controller.processed_events] == [
        InteractionEventKind.ABSORBER_DRAG_UPDATE,
        InteractionEventKind.ABSORBER_DRAG_COMPLETE,
    ]


def test_cancel_clears_state_when_rejected_without_raise() -> None:
    """Public-style cancel should clear owner state when rejected."""
    state_controller = _AbsorberDragStateControllerFake(process_result=False)
    owner = _AbsorberDragOwnerFake(
        controller=state_controller,
        active_channel=InteractionChannel.ABSORBER_DRAG,
        active_absorber_id="abs-1",
    )
    controller = AbsorberDragInputController(owner=owner)

    handled = controller.cancel_active_drag(reason="test")

    assert handled is False
    assert owner.cleared_count == 1


def test_cancel_can_raise_when_release_cancel_is_rejected() -> None:
    """Release-path cancel should preserve the previous fail-fast behavior."""
    state_controller = _AbsorberDragStateControllerFake(process_result=False)
    owner = _AbsorberDragOwnerFake(
        controller=state_controller,
        active_channel=InteractionChannel.ABSORBER_DRAG,
        active_absorber_id="abs-1",
    )
    controller = AbsorberDragInputController(owner=owner)

    with pytest.raises(InteractionStateError, match="cancellation was rejected"):
        controller.cancel_active_drag(reason="test", raise_on_rejected=True)
