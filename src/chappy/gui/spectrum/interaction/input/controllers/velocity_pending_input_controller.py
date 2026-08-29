"""Input-side controller for velocity pending gestures."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt

from chappy.gui.protocols.intent_types import ToggleVelocityPlotIntent
from chappy.gui.spectrum.interaction.input.mapping.qt_input_mapper import KeyMouseIntentMapper
from chappy.gui.spectrum.interaction.support.errors import InteractionStateError
from chappy.presentation.interaction.interaction_contracts import (
    InteractionChannel,
    InteractionEvent,
    InteractionEventKind,
    InteractionPhase,
    VelocityInteractionPayload,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from PySide6.QtGui import QMouseEvent

    from chappy.gui.spectrum.interaction.channels.ports import InteractionChannelControllerPort
    from chappy.gui.spectrum.interaction.input.mapping.pointer_coordinate_mapper import (
        SpectrumPointerCoordinateMapper,
    )
    from chappy.gui.spectrum.interaction.input.ports import SpectrumPlotWidgetPort
    from chappy.gui.utils.plot_coordinate_transform import PlotCoordinateTransform


class VelocityPendingInputController:
    """Convert velocity pending input phases into interaction events."""

    def __init__(
        self,
        *,
        state_controller: InteractionChannelControllerPort,
        coordinate_mapper: SpectrumPointerCoordinateMapper,
        transform_provider: Callable[[], PlotCoordinateTransform | None],
        plot_widget_provider: Callable[[], SpectrumPlotWidgetPort | None],
        velocity_toggle_intent_emitter: Callable[[ToggleVelocityPlotIntent], None],
    ) -> None:
        """Initialize the controller."""
        self._state_controller = state_controller
        self._coordinate_mapper = coordinate_mapper
        self._transform_provider = transform_provider
        self._plot_widget_provider = plot_widget_provider
        self._velocity_toggle_intent_emitter = velocity_toggle_intent_emitter
        self._target_wavelength: float | None = None

    def is_pending(self) -> bool:
        """Return whether velocity interaction is waiting for confirmation."""
        return self._state_controller.phase is InteractionPhase.ARMED

    def current_target_wavelength(self) -> float | None:
        """Return the latest wavelength used for velocity prompt feedback."""
        return self._target_wavelength

    def set_target_wavelength(self, wavelength: float) -> None:
        """Update the latest target wavelength."""
        self._target_wavelength = wavelength

    def clear_target_wavelength(self) -> None:
        """Clear the latest target wavelength."""
        self._target_wavelength = None

    def resolve_toggle_wavelength(self) -> float | None:
        """Estimate wavelength for velocity toggle using current cursor position."""
        data_position = self._coordinate_mapper.optional_global_cursor_data_position(
            transform=self._transform_provider(), plot_widget=self._plot_widget_provider()
        )
        if data_position is not None:
            self._target_wavelength = data_position.wavelength
            return self._target_wavelength
        return self._target_wavelength

    def enter(self, wavelength: float | None, modifiers: int | None, *, trigger: str) -> None:
        """Enter velocity pending mode and notify observers."""
        event = InteractionEvent(
            channel=InteractionChannel.VELOCITY,
            kind=InteractionEventKind.VELOCITY_PENDING,
            position=(wavelength, 0.0) if wavelength is not None else None,
            modifiers=modifiers,
            payload=VelocityInteractionPayload(trigger=trigger),
        )
        self._state_controller.process_event(event)

    def complete(self, wavelength: float, modifiers: int | None, *, trigger: str) -> None:
        """Complete velocity pending mode and emit toggle intent."""
        event = InteractionEvent(
            channel=InteractionChannel.VELOCITY,
            kind=InteractionEventKind.VELOCITY_COMMIT,
            position=(wavelength, 0.0),
            modifiers=modifiers,
            payload=VelocityInteractionPayload(trigger=trigger),
        )
        handled = self._state_controller.process_event(event)
        if not handled:
            msg = "Velocity commit was rejected while pending interaction was expected."
            raise InteractionStateError(msg)

        self._velocity_toggle_intent_emitter(ToggleVelocityPlotIntent(wavelength=wavelength))

    def cancel(self, *, reason: str) -> None:
        """Cancel velocity pending mode and restore idle state."""
        if not self.is_pending():
            return

        event = InteractionEvent(
            channel=InteractionChannel.VELOCITY,
            kind=InteractionEventKind.VELOCITY_CANCEL,
            payload=VelocityInteractionPayload(reason=reason),
        )
        handled = self._state_controller.process_event(event)
        if not handled:
            msg = "Velocity cancel was rejected while pending interaction was expected."
            raise InteractionStateError(msg)

    def handle_pending_mouse_press(self, event: QMouseEvent) -> bool:
        """Handle mouse press events when velocity pending mode is active."""
        button = event.button()
        if button == Qt.MouseButton.LeftButton:
            transform = self._transform_provider()
            if transform is None:
                self.cancel(reason="missing-transform")
                return True

            data_position = self._coordinate_mapper.optional_event_data_position(transform, event)
            data_pos = data_position.as_tuple() if data_position is not None else None

            if data_pos is None:
                self.cancel(reason="transform-failed")
                return True

            wavelength = float(data_pos[0])
            self._target_wavelength = wavelength
            modifiers = KeyMouseIntentMapper.modifier_mask(event.modifiers())
            self.complete(wavelength, modifiers, trigger="mouse-press-bridge")
            return True

        if button == Qt.MouseButton.RightButton:
            self.cancel(reason="context-menu")
            return True

        self.cancel(reason="mouse-press-other")
        return True
