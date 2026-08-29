"""Tests for velocity pending input orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent

from chappy.gui.protocols.intent_types import ToggleVelocityPlotIntent
from chappy.gui.spectrum.interaction.input.mapping.pointer_coordinate_mapper import DataPosition
from chappy.gui.spectrum.interaction.input.controllers.velocity_pending_input_controller import (
    VelocityPendingInputController,
)
from chappy.gui.spectrum.interaction.support.errors import InteractionStateError
from chappy.presentation.interaction.interaction_contracts import (
    InteractionChannel,
    InteractionEvent,
    InteractionEventKind,
    InteractionPhase,
    VelocityInteractionPayload,
)


@dataclass
class _VelocityStateControllerFake:
    """Record velocity interaction events."""

    processed_events: list[InteractionEvent] = field(default_factory=list)
    phase_value: InteractionPhase = InteractionPhase.IDLE
    process_result: bool = True

    @property
    def phase(self) -> InteractionPhase:
        """Return the configured phase."""
        return self.phase_value

    def process_event(self, event: InteractionEvent) -> bool:
        """Record an interaction event and advance fake phase."""
        self.processed_events.append(event)
        if not self.process_result:
            return False
        if event.kind is InteractionEventKind.VELOCITY_PENDING:
            self.phase_value = InteractionPhase.ARMED
        elif event.kind is InteractionEventKind.VELOCITY_COMMIT:
            self.phase_value = InteractionPhase.IDLE
        elif event.kind is InteractionEventKind.VELOCITY_CANCEL:
            self.phase_value = InteractionPhase.CANCELLED
        return True

    def cancel_interaction(self, *, reason: str | None) -> bool:
        """Support the shared controller port."""
        return self.process_event(
            InteractionEvent(
                channel=InteractionChannel.VELOCITY,
                kind=InteractionEventKind.VELOCITY_CANCEL,
                payload=VelocityInteractionPayload(reason=reason),
            )
        )


@dataclass
class _CoordinateMapperFake:
    """Coordinate mapper fake for velocity pending tests."""

    event_position: DataPosition | None = None
    global_position: DataPosition | None = None

    def optional_event_data_position(
        self, _transform: object, _event: QMouseEvent
    ) -> DataPosition | None:
        """Return the configured event data position."""
        return self.event_position

    def optional_global_cursor_data_position(
        self, *, transform: object | None, plot_widget: object | None
    ) -> DataPosition | None:
        """Return the configured global cursor position when dependencies exist."""
        if transform is None or plot_widget is None:
            return None
        return self.global_position


def _mouse_event(button: Qt.MouseButton = Qt.MouseButton.LeftButton) -> QMouseEvent:
    """Build a concrete mouse press event."""
    return QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(10.0, 20.0),
        button,
        button,
        Qt.KeyboardModifier.NoModifier,
    )


def _controller(
    *,
    state_controller: _VelocityStateControllerFake | None = None,
    coordinate_mapper: _CoordinateMapperFake | None = None,
    transform: object | None = object(),
    plot_widget: object | None = object(),
    emitted: list[ToggleVelocityPlotIntent] | None = None,
) -> VelocityPendingInputController:
    """Create a velocity pending input controller with fakes."""
    emitted_intents = emitted if emitted is not None else []
    return VelocityPendingInputController(
        state_controller=state_controller or _VelocityStateControllerFake(),
        coordinate_mapper=coordinate_mapper or _CoordinateMapperFake(),
        transform_provider=lambda: transform,
        plot_widget_provider=lambda: plot_widget,
        velocity_toggle_intent_emitter=emitted_intents.append,
    )


def test_enter_sends_velocity_pending_event() -> None:
    """Enter should send a typed velocity pending event."""
    state_controller = _VelocityStateControllerFake()
    controller = _controller(state_controller=state_controller)

    controller.enter(5050.0, 7, trigger="shortcut")

    event = state_controller.processed_events[-1]
    assert event.kind is InteractionEventKind.VELOCITY_PENDING
    assert event.position == (5050.0, 0.0)
    assert event.modifiers == 7
    assert isinstance(event.payload, VelocityInteractionPayload)
    assert event.payload.trigger == "shortcut"
    assert controller.is_pending() is True


def test_complete_sends_commit_and_emits_toggle_intent() -> None:
    """Complete should send commit and emit the velocity toggle intent."""
    state_controller = _VelocityStateControllerFake(phase_value=InteractionPhase.ARMED)
    emitted: list[ToggleVelocityPlotIntent] = []
    controller = _controller(state_controller=state_controller, emitted=emitted)

    controller.complete(5100.0, 3, trigger="mouse")

    event = state_controller.processed_events[-1]
    assert event.kind is InteractionEventKind.VELOCITY_COMMIT
    assert event.position == (5100.0, 0.0)
    assert emitted == [ToggleVelocityPlotIntent(wavelength=5100.0)]


def test_complete_reject_raises_interaction_state_error() -> None:
    """Rejected commit should preserve fail-fast behavior."""
    state_controller = _VelocityStateControllerFake(
        phase_value=InteractionPhase.ARMED, process_result=False
    )
    controller = _controller(state_controller=state_controller)

    with pytest.raises(InteractionStateError, match="Velocity commit was rejected"):
        controller.complete(5100.0, None, trigger="test")


def test_cancel_without_pending_is_noop() -> None:
    """Cancel should not emit an event when velocity is not pending."""
    state_controller = _VelocityStateControllerFake(phase_value=InteractionPhase.IDLE)
    controller = _controller(state_controller=state_controller)

    controller.cancel(reason="escape-key")

    assert state_controller.processed_events == []


def test_cancel_pending_sends_reason() -> None:
    """Cancel should send the configured cancel reason."""
    state_controller = _VelocityStateControllerFake(phase_value=InteractionPhase.ARMED)
    controller = _controller(state_controller=state_controller)

    controller.cancel(reason="escape-key")

    event = state_controller.processed_events[-1]
    assert event.kind is InteractionEventKind.VELOCITY_CANCEL
    assert isinstance(event.payload, VelocityInteractionPayload)
    assert event.payload.reason == "escape-key"


def test_resolve_toggle_wavelength_prefers_global_cursor_position() -> None:
    """Global cursor data position should update the cached target wavelength."""
    mapper = _CoordinateMapperFake(global_position=DataPosition(5200.0, 0.8))
    controller = _controller(coordinate_mapper=mapper)
    controller.set_target_wavelength(5100.0)

    wavelength = controller.resolve_toggle_wavelength()

    assert wavelength == pytest.approx(5200.0)
    assert controller.current_target_wavelength() == pytest.approx(5200.0)


def test_resolve_toggle_wavelength_falls_back_to_cached_target() -> None:
    """Cached target wavelength should be used when cursor resolution fails."""
    controller = _controller(transform=None, plot_widget=None)
    controller.set_target_wavelength(5100.0)

    assert controller.resolve_toggle_wavelength() == pytest.approx(5100.0)


def test_left_mouse_press_commits_pending_velocity() -> None:
    """Left mouse press should resolve a wavelength and commit velocity pending."""
    state_controller = _VelocityStateControllerFake(phase_value=InteractionPhase.ARMED)
    mapper = _CoordinateMapperFake(event_position=DataPosition(5300.0, 0.7))
    emitted: list[ToggleVelocityPlotIntent] = []
    controller = _controller(
        state_controller=state_controller, coordinate_mapper=mapper, emitted=emitted
    )

    handled = controller.handle_pending_mouse_press(_mouse_event())

    assert handled is True
    assert state_controller.processed_events[-1].kind is InteractionEventKind.VELOCITY_COMMIT
    assert emitted == [ToggleVelocityPlotIntent(wavelength=5300.0)]
    assert controller.current_target_wavelength() == pytest.approx(5300.0)


def test_left_mouse_press_without_transform_cancels_pending() -> None:
    """Missing transform should cancel velocity pending mode."""
    state_controller = _VelocityStateControllerFake(phase_value=InteractionPhase.ARMED)
    controller = _controller(state_controller=state_controller, transform=None)

    controller.handle_pending_mouse_press(_mouse_event())

    event = state_controller.processed_events[-1]
    assert event.kind is InteractionEventKind.VELOCITY_CANCEL
    assert isinstance(event.payload, VelocityInteractionPayload)
    assert event.payload.reason == "missing-transform"


def test_right_mouse_press_cancels_pending_as_context_menu() -> None:
    """Right mouse press should cancel pending mode for context menu routing."""
    state_controller = _VelocityStateControllerFake(phase_value=InteractionPhase.ARMED)
    controller = _controller(state_controller=state_controller)

    controller.handle_pending_mouse_press(_mouse_event(Qt.MouseButton.RightButton))

    event = state_controller.processed_events[-1]
    assert event.kind is InteractionEventKind.VELOCITY_CANCEL
    assert isinstance(event.payload, VelocityInteractionPayload)
    assert event.payload.reason == "context-menu"
