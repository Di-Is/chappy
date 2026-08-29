"""Absorber drag coordinator for the spectrum surface."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Protocol, TypedDict

from chappy.application.history import component_parameter_state
from chappy.core.components.tie_set import effective_tie_set_for_parameter
from chappy.core.constants import LIGHT_SPEED_KMS
from chappy.gui.protocols.interaction_overlay import (
    AbsorberDragBeginOverlayProtocol,
    AbsorberDragFinishOverlayProtocol,
    AbsorberDragUpdateOverlayProtocol,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from chappy.application.history import ComponentParameterState
    from chappy.core.components.absorber import AbsorberComponent
    from chappy.gui.protocols.intent_types import (
        EndAbsorberDragIntent,
        StartAbsorberDragIntent,
        UpdateAbsorberDragIntent,
    )
    from chappy.gui.spectrum.spectrum_plot import SpectrumPlotSurfaceProtocol
    from chappy.presentation.velocity import VelocityOverlayInfo

logger = logging.getLogger(__name__)


class DraggingAbsorberState(TypedDict):
    """State tracked during an absorber drag interaction."""

    is_velocity_mode: bool
    rest_wavelength: float | None
    center_z: float | None
    before_states: tuple[ComponentParameterState, ...]


class AbsorberDragApplyPort(Protocol):
    """Callable port that applies a completed absorber drag."""

    def __call__(
        self,
        component_id: str,
        new_redshift: float,
        before_states: tuple[ComponentParameterState, ...],
    ) -> None:
        """Apply the completed drag redshift."""
        ...


class SpectrumAbsorberDragCoordinator:
    """Coordinate absorber drag state, overlays, and completion callbacks."""

    def __init__(
        self,
        *,
        absorber_provider: Callable[[str], AbsorberComponent | None],
        velocity_overlay_provider: Callable[[], VelocityOverlayInfo | None],
        plot_widget_provider: Callable[[], SpectrumPlotSurfaceProtocol | None],
        drag_apply_callback: AbsorberDragApplyPort,
        cursor_reset_callback: Callable[[], None],
    ) -> None:
        """Initialize the drag coordinator.

        Args:
            absorber_provider: Provider resolving absorber components by identifier.
            velocity_overlay_provider: Provider for active velocity overlay metadata.
            plot_widget_provider: Provider for the active plot widget.
            drag_apply_callback: Port applying completed drag redshift changes.
            cursor_reset_callback: Callback that restores the default cursor.
        """
        self._absorber_provider = absorber_provider
        self._velocity_overlay_provider = velocity_overlay_provider
        self._plot_widget_provider = plot_widget_provider
        self._drag_apply_callback = drag_apply_callback
        self._cursor_reset_callback = cursor_reset_callback
        self._dragging_absorber_data: dict[str, DraggingAbsorberState] = {}

    def handle_drag_start(self, intent: StartAbsorberDragIntent) -> None:
        """Handle the start of an absorber drag."""
        absorber = self._absorber_provider(intent.absorber_id)
        rest_wavelength = absorber.wavelength if absorber is not None else None

        velocity_info = self._velocity_overlay_provider()
        is_velocity_mode = velocity_info is not None
        center_z: float | None = velocity_info.center_z if velocity_info else None

        initial_wavelength = intent.initial_wavelength
        if (
            velocity_info is not None
            and rest_wavelength
            and center_z is not None
            and not intent.wavelength_already_converted
        ):
            initial_wavelength = self._convert_velocity_to_wavelength(
                intent.initial_wavelength, rest_wavelength, center_z
            )
            logger.debug(
                "Velocity mode: converted v=%.2f km/s to wavelength %.2f",
                intent.initial_wavelength,
                initial_wavelength,
            )
        elif intent.wavelength_already_converted:
            is_velocity_mode = False
            logger.debug("Velocity mode: using pre-converted wavelength %.2f", initial_wavelength)

        plot_widget = self._plot_widget_provider()
        if isinstance(plot_widget, AbsorberDragBeginOverlayProtocol):
            plot_widget.begin_absorber_drag(intent.absorber_id, initial_wavelength)

        self._dragging_absorber_data[intent.absorber_id] = {
            "is_velocity_mode": is_velocity_mode,
            "rest_wavelength": rest_wavelength,
            "center_z": center_z,
            "before_states": self._capture_before_states(absorber),
        }
        logger.debug("Started dragging absorber %s", intent.absorber_id)

    def handle_drag_update(self, intent: UpdateAbsorberDragIntent) -> None:
        """Handle an absorber drag position update."""
        drag_data = self._dragging_absorber_data.get(intent.absorber_id)
        current_wavelength = intent.current_wavelength

        if drag_data is not None:
            current_wavelength = self._convert_drag_position(current_wavelength, drag_data)

        plot_widget = self._plot_widget_provider()
        if isinstance(plot_widget, AbsorberDragUpdateOverlayProtocol):
            plot_widget.update_dragging_absorber_position(intent.absorber_id, current_wavelength)

    def handle_drag_end(self, intent: EndAbsorberDragIntent) -> None:
        """Handle the end of an absorber drag."""
        drag_data = self._dragging_absorber_data.get(intent.absorber_id)
        if drag_data is None:
            return

        final_wavelength = self._convert_drag_position(intent.final_wavelength, drag_data)

        if intent.calculate_redshift:
            absorber = self._absorber_provider(intent.absorber_id)
            if absorber and absorber.wavelength:
                new_redshift = (final_wavelength / absorber.wavelength) - 1.0
                self._drag_apply_callback(
                    intent.absorber_id, new_redshift, drag_data["before_states"]
                )

        plot_widget = self._plot_widget_provider()
        if isinstance(plot_widget, AbsorberDragFinishOverlayProtocol):
            plot_widget.finish_absorber_drag(intent.absorber_id)

        del self._dragging_absorber_data[intent.absorber_id]

    def cancel_active_drags(self) -> bool:
        """Cancel all active absorber drag operations."""
        if not self._dragging_absorber_data:
            return False

        plot_widget = self._plot_widget_provider()
        if isinstance(plot_widget, AbsorberDragFinishOverlayProtocol):
            for absorber_id in tuple(self._dragging_absorber_data):
                plot_widget.finish_absorber_drag(absorber_id)

        self._dragging_absorber_data.clear()
        self._cursor_reset_callback()
        logger.debug("Cancelled all absorber drags")
        return True

    def has_active_drag(self, absorber_id: str) -> bool:
        """Return whether the absorber is currently being dragged."""
        return absorber_id in self._dragging_absorber_data

    def _convert_drag_position(self, position: float, drag_data: DraggingAbsorberState) -> float:
        """Convert a velocity drag coordinate to wavelength when needed."""
        rest_wavelength = drag_data["rest_wavelength"]
        center_z = drag_data["center_z"]
        if drag_data["is_velocity_mode"] and rest_wavelength and center_z is not None:
            return self._convert_velocity_to_wavelength(position, rest_wavelength, center_z)
        return position

    def _capture_before_states(
        self, absorber: AbsorberComponent | None
    ) -> tuple[ComponentParameterState, ...]:
        """Capture parameter history state for the dragged absorber group."""
        if absorber is None:
            return ()

        before_states = [component_parameter_state(absorber)]
        tie_set = effective_tie_set_for_parameter(absorber, "redshift")
        if tie_set is not None:
            before_states.extend(
                component_parameter_state(component)
                for component in tie_set.components
                if component.id != absorber.id
            )
        return tuple(before_states)

    @staticmethod
    def _convert_velocity_to_wavelength(
        velocity: float, rest_wavelength: float, center_z: float
    ) -> float:
        """Convert a velocity coordinate to observed wavelength."""
        rest_observed = rest_wavelength * (1.0 + center_z)
        return rest_observed * (velocity / LIGHT_SPEED_KMS + 1.0)
