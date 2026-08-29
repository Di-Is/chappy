"""Interactive continuum editor component."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol, runtime_checkable

from matplotlib.backend_bases import Event, MouseButton, MouseEvent
from matplotlib.lines import Line2D
from matplotlib.patches import Circle

from chappy.plotting.components.continuum_feedback_renderer import (
    ContinuumFeedbackRenderer,
    FeedbackScheduler,
)
from chappy.plotting.components.control_point_hit_tester import ControlPointHitTester
from chappy.presentation.interaction.interaction_contracts import (
    ContinuumContext,
    ContinuumOperationType,
    ContinuumPointPayload,
    InteractionChannel,
    InteractionEvent,
    InteractionEventKind,
    InteractionPhase,
    InteractionStateSnapshot,
)
from chappy.presentation.spectrum.visual_tokens import ContinuumControlPointVisuals

if TYPE_CHECKING:
    from collections.abc import Callable

    from matplotlib.artist import Artist
    from matplotlib.axes import Axes
    from matplotlib.collections import PathCollection
    from matplotlib.figure import Figure

logger = logging.getLogger(__name__)

ContinuumCursorShape = Literal["arrow", "pointing_hand", "closed_hand", "forbidden"]


@dataclass(frozen=True)
class ContinuumContextState:
    """Lightweight description of continuum context menu capabilities."""

    wavelength: float
    flux: float | None
    nearest_index: int | None
    can_add: bool
    can_delete: bool


class ContinuumInteractionPort(Protocol):
    """Interaction boundary required by the matplotlib continuum editor."""

    def can_process_continuum_event(self) -> bool:
        """Return whether a continuum event may start or continue now."""
        ...

    def process_continuum_interaction_event(self, event: InteractionEvent) -> bool:
        """Process a continuum interaction event."""
        ...


class ContinuumEditorUiPort(Protocol):
    """GUI-owned UI behaviours required by the continuum editor."""

    def set_cursor(self, cursor: ContinuumCursorShape) -> None:
        """Set the cursor shape for the plot canvas."""
        ...

    def show_coordinate_tooltip(self, text: str) -> None:
        """Show a coordinate tooltip at the current pointer position."""
        ...

    def clear_tooltip(self) -> None:
        """Hide the active coordinate tooltip."""
        ...

    def open_context_menu(
        self,
        *,
        context_state: ContinuumContextState | None,
        add_label: str,
        delete_label: str,
        request_add: Callable[[float, float], bool],
        request_delete: Callable[[int], bool],
    ) -> None:
        """Open the continuum context menu."""
        ...


class NoOpContinuumEditorUiPort:
    """No-op UI port used when no GUI adapter is injected."""

    def set_cursor(self, cursor: ContinuumCursorShape) -> None:
        """Ignore cursor updates."""

    def show_coordinate_tooltip(self, text: str) -> None:
        """Ignore tooltip display requests."""

    def clear_tooltip(self) -> None:
        """Ignore tooltip clear requests."""

    def open_context_menu(
        self,
        *,
        context_state: ContinuumContextState | None,
        add_label: str,
        delete_label: str,
        request_add: Callable[[float, float], bool],
        request_delete: Callable[[int], bool],
    ) -> None:
        """Ignore context menu requests."""


@runtime_checkable
class KeyEventWithCode(Protocol):
    """Event protocol that exposes a keyboard key string."""

    key: str | None


class MatplotlibContinuumEditor:
    """Continuum editor implementation for Matplotlib plots.

    This provides similar functionality to ContinuumEditor but for
    Matplotlib-based spectrum plots.
    """

    def __init__(
        self,
        axes: Axes,
        figure: Figure,
        *,
        ui_port: ContinuumEditorUiPort | None = None,
        feedback_scheduler: FeedbackScheduler | None = None,
        translate: Callable[[str], str] | None = None,
    ) -> None:
        """Initialize matplotlib continuum editor.

        Args:
            axes: Matplotlib axes object
            figure: Matplotlib figure object
            ui_port: Optional GUI-owned adapter for cursor, tooltip, and menus.
            feedback_scheduler: Optional GUI-owned scheduler for feedback cleanup.
            translate: Optional translation callback for source text.
        """
        self.axes = axes
        self.figure = figure
        self.canvas = figure.canvas
        self._ui_port = ui_port or NoOpContinuumEditorUiPort()
        self._translate = translate or (lambda text: text)

        # Current continuum points
        self.points: list[tuple[float, float]] = []

        # Visual elements

        self.scatter: PathCollection | None = None
        self.line: Line2D | None = None

        # Interaction state
        self.enabled = False
        self.dragging = False
        self.drag_index: int | None = None
        self.hover_index: int | None = None
        self.selected_index: int | None = None
        self.display_active = True
        self._drag_original_point: tuple[float, float] | None = None
        self._drag_current_point: tuple[float, float] | None = None
        self._drag_invalid = False
        self._pending_select_position: tuple[float, float] | None = None
        self._feedback_artists: list[Artist] = []
        self._origin_marker: Circle | None = None
        self._invalid_drag_artists: list[Line2D] = []
        self._use_internal_context_menu = False
        self._hit_tester = ControlPointHitTester()
        self._feedback_renderer = ContinuumFeedbackRenderer(
            hit_radius_px=ContinuumControlPointVisuals.HIT_RADIUS_PX,
            z_order=ContinuumControlPointVisuals.Z_ORDER + 2,
            scheduler=feedback_scheduler,
        )

        # Connect to matplotlib events
        self._cid_press: int | None = None
        self._cid_release: int | None = None
        self._cid_motion: int | None = None
        self._cid_key: int | None = None

        # Interaction port reference (set via set_interactor)
        self._interactor: ContinuumInteractionPort | None = None

        logger.debug("MatplotlibContinuumEditor initialized")

    def tr(self, text: str) -> str:
        """Translate source text through the injected translation callback."""
        return self._translate(text)

    def set_interactor(self, interactor: ContinuumInteractionPort | None) -> None:
        """Set the continuum interaction port for event routing.

        Args:
            interactor: Interaction port to route events to, or None while detached.
        """
        self._interactor = interactor
        logger.debug("MatplotlibContinuumEditor interactor set")

    def _require_interaction_port(self) -> ContinuumInteractionPort:
        """Return the required interaction port or raise a composition error."""
        if self._interactor is None:
            msg = "MatplotlibContinuumEditor requires a continuum interaction port."
            raise RuntimeError(msg)
        return self._interactor

    def _send_interaction_event(self, event: InteractionEvent) -> bool:
        """Send InteractionEvent to SpectrumInputAdapter.

        Args:
            event: InteractionEvent to send.

        Returns:
            True if the event was successfully processed, False otherwise.
        """
        interactor = self._require_interaction_port()

        # Check if another interaction channel is active before processing continuum events
        if not interactor.can_process_continuum_event():
            logger.debug("Continuum event ignored because another channel is active")
            return False

        return interactor.process_continuum_interaction_event(event)

    def set_points(self, points: list[tuple[float, float]]) -> None:
        """Replace current point set and refresh display, preserving selection."""
        previous_point = None
        if self.selected_index is not None and 0 <= self.selected_index < len(self.points):
            previous_point = self.points[self.selected_index]

        self.points = list(points)

        target_point = None
        if self._pending_select_position is not None:
            target_point = self._pending_select_position
            self._pending_select_position = None
        elif previous_point is not None:
            target_point = previous_point

        new_index: int | None = None
        if target_point is not None:
            new_index = self._closest_point_index(target_point)

        if new_index is not None:
            self.selected_index = new_index
        elif self.selected_index is not None:
            if not self.points:
                self.selected_index = None
            else:
                self.selected_index = min(self.selected_index, len(self.points) - 1)

        if self.hover_index is not None and (
            self.hover_index < 0 or self.hover_index >= len(self.points)
        ):
            self.hover_index = None

        self._update_display()

    def apply_interaction_state_snapshot(
        self, snapshot: InteractionStateSnapshot[ContinuumContext]
    ) -> None:
        """Apply interaction state snapshot to update UI state.

        Args:
            snapshot: InteractionStateSnapshot with ContinuumContext.
        """
        if snapshot.channel != InteractionChannel.CONTINUUM:
            return

        context = snapshot.context
        if context is None:
            return

        # Update state from snapshot
        if context.operation_type == ContinuumOperationType.MOVE:
            if context.point_index is not None:
                self.drag_index = context.point_index
                self.dragging = snapshot.phase == InteractionPhase.ACTIVE
                if context.current_position:
                    self._drag_current_point = context.current_position
                if context.start_position:
                    self._drag_original_point = context.start_position
                if context.validation_result:
                    # validation_result is not None means validation failed
                    self._drag_invalid = True
                else:
                    # validation_result is None means validation passed
                    self._drag_invalid = False
        elif context.operation_type == ContinuumOperationType.ADD:
            self.dragging = snapshot.phase == InteractionPhase.ACTIVE
        elif context.operation_type == ContinuumOperationType.DELETE:
            self._handle_delete_snapshot()
        elif context.operation_type == ContinuumOperationType.SELECT:
            if context.point_index is not None:
                self.selected_index = context.point_index
            else:
                self.selected_index = None

        # Update hover state (if available in context)
        # Note: hover state might be handled via InteractionOverlayProtocol

        # Update display
        self._update_display()

    def _extract_event_key(self, event: object) -> str | None:
        """Extract normalized key value from a Matplotlib key event."""
        if not isinstance(event, KeyEventWithCode):
            return None
        if event.key is None:
            return None
        return str(event.key).lower()

    def _figure_dpi(self) -> float:
        """Return the active figure DPI."""
        try:
            return float(self.figure.dpi)
        except (AttributeError, TypeError, ValueError) as exc:
            msg = "Failed to resolve figure DPI."
            raise RuntimeError(msg) from exc

    def _handle_delete_snapshot(self) -> None:
        """Delete operation does not require local editor state mutation."""

    def set_display_active(self, active: bool) -> None:
        """Show or hide control point visuals without dropping state."""
        if self.display_active == active:
            return

        self.display_active = active

        if not active:
            self._clear_hover_state()
            self._clear_origin_marker()
            self._clear_invalid_marker()
            self._clear_feedback_marker()

        self._update_display()

    def set_enabled(self, *, enabled: bool) -> None:
        """Enable or disable continuum editing mode."""
        self.enabled = enabled
        self.dragging = False
        self.drag_index = None

        if enabled:
            self._connect_events()
            self._set_cursor("arrow")
        else:
            self._disconnect_events()
            self._clear_hover_state()
            self._set_cursor("arrow")
            self._clear_origin_marker()
            self._clear_invalid_marker()
            self._clear_feedback_marker()

    def _connect_events(self) -> None:
        """Connect matplotlib event handlers."""
        self._cid_press = self.canvas.mpl_connect("button_press_event", self._on_press)
        self._cid_release = self.canvas.mpl_connect("button_release_event", self._on_release)
        self._cid_motion = self.canvas.mpl_connect("motion_notify_event", self._on_motion)
        self._cid_key = self.canvas.mpl_connect("key_press_event", self._on_key_press)

    def _disconnect_events(self) -> None:
        """Disconnect matplotlib event handlers."""
        if self._cid_press:
            self.canvas.mpl_disconnect(self._cid_press)
            self._cid_press = None
        if self._cid_release:
            self.canvas.mpl_disconnect(self._cid_release)
            self._cid_release = None
        if self._cid_motion:
            self.canvas.mpl_disconnect(self._cid_motion)
            self._cid_motion = None
        if self._cid_key:
            self.canvas.mpl_disconnect(self._cid_key)
            self._cid_key = None

    def _on_press(self, event: Event) -> None:
        if not isinstance(event, MouseEvent) or not self.enabled:
            return
        if event.inaxes != self.axes:
            return

        data = self._data_from_event(event)
        if data is None:
            return

        if event.button == MouseButton.LEFT:
            if event.dblclick:
                # Validate first, then emit event only if validation succeeds
                wavelength, flux = data
                if self.request_add_point(wavelength, flux, emit_event=False):
                    # Validation passed, now emit CONTINUUM_ADD_BEGIN event
                    add_event = InteractionEvent(
                        channel=InteractionChannel.CONTINUUM,
                        kind=InteractionEventKind.CONTINUUM_ADD_BEGIN,
                        position=data,
                    )
                    self._send_interaction_event(add_event)
                return

            index = self._point_index_near(event)
            if index is not None:
                # Generate CONTINUUM_MOVE_BEGIN event
                move_event = InteractionEvent(
                    channel=InteractionChannel.CONTINUUM,
                    kind=InteractionEventKind.CONTINUUM_MOVE_BEGIN,
                    position=data,
                    payload=ContinuumPointPayload(point_index=index),
                )
                # Only run legacy drag if event was successfully processed
                if self._send_interaction_event(move_event):
                    # Legacy: keep existing behavior for now
                    self._begin_drag(index)
            elif self.selected_index is not None:
                # Generate CONTINUUM_SELECT event (deselect)
                select_event = InteractionEvent(
                    channel=InteractionChannel.CONTINUUM,
                    kind=InteractionEventKind.CONTINUUM_SELECT,
                    position=data,
                    payload=ContinuumPointPayload(point_index=None),
                )
                self._send_interaction_event(select_event)

        elif event.button == MouseButton.RIGHT:
            if self._use_internal_context_menu:
                self._open_context_menu(event)

    def _on_release(self, event: Event) -> None:
        """Handle matplotlib mouse release event."""
        if not self.dragging:
            return

        data = None
        if isinstance(event, MouseEvent):
            data = self._data_from_event(event)

        if self._drag_invalid:
            # Generate CONTINUUM_CANCEL event
            cancel_event = InteractionEvent(
                channel=InteractionChannel.CONTINUUM,
                kind=InteractionEventKind.CONTINUUM_CANCEL,
                position=data,
            )
            self._send_interaction_event(cancel_event)
            # Legacy: keep existing behavior for now
            if self.drag_index is not None and self._drag_original_point is not None:
                self.points[self.drag_index] = self._drag_original_point
            self._drag_invalid = False
            self._update_display()
        elif self._drag_current_point and self.drag_index is not None:
            # Generate CONTINUUM_MOVE_COMPLETE event
            complete_event = InteractionEvent(
                channel=InteractionChannel.CONTINUUM,
                kind=InteractionEventKind.CONTINUUM_MOVE_COMPLETE,
                position=self._drag_current_point,
                payload=ContinuumPointPayload(point_index=self.drag_index),
            )
            self._send_interaction_event(complete_event)

        self.dragging = False
        self.drag_index = None
        self._drag_current_point = None
        self._drag_original_point = None
        self._update_display()
        self._clear_origin_marker()
        self._clear_invalid_marker()
        self._set_cursor("arrow")
        self._clear_tooltip()

    def _on_motion(self, event: Event) -> None:
        """Handle matplotlib mouse motion event."""
        if not isinstance(event, MouseEvent) or not self.enabled:
            return

        data = self._data_from_event(event)
        if data is None:
            return

        if self.dragging and self.drag_index is not None:
            # Generate CONTINUUM_MOVE_UPDATE event
            update_event = InteractionEvent(
                channel=InteractionChannel.CONTINUUM,
                kind=InteractionEventKind.CONTINUUM_MOVE_UPDATE,
                position=data,
                payload=ContinuumPointPayload(point_index=self.drag_index),
            )
            self._send_interaction_event(update_event)
            # Legacy: keep existing behavior for now
            self._update_drag_position(data)
            return

        if event.inaxes != self.axes:
            return

        hover_index = self._point_index_near(event)
        if hover_index != self.hover_index:
            # Hover state is handled via InteractionOverlayProtocol
            # Legacy: keep existing behavior for now
            self.hover_index = hover_index
            if hover_index is not None:
                self._set_cursor("pointing_hand")
            else:
                self._set_cursor("arrow")
            self._update_display()

    def _on_key_press(self, event: Event) -> None:
        if not self.enabled or not self.points:
            return
        key = self._extract_event_key(event)
        if key is None:
            return

        key = str(key).lower()

        if key == "escape" and self.dragging:
            # Generate CONTINUUM_CANCEL event
            cancel_event = InteractionEvent(
                channel=InteractionChannel.CONTINUUM,
                kind=InteractionEventKind.CONTINUUM_CANCEL,
                position=None,
            )
            self._send_interaction_event(cancel_event)
            # Legacy: keep existing behavior for now
            if self.drag_index is not None and self._drag_original_point is not None:
                self.points[self.drag_index] = self._drag_original_point
            self.dragging = False
            self.drag_index = None
            self._drag_current_point = None
            self._drag_original_point = None
            self._drag_invalid = False
            self._clear_origin_marker()
            self._clear_invalid_marker()
            self._set_cursor("arrow")
            self._update_display()
            self._clear_tooltip()
            return

        if self.selected_index is None:
            return

        if key in {"delete", "backspace"}:
            # Generate CONTINUUM_DELETE_BEGIN event
            delete_event = InteractionEvent(
                channel=InteractionChannel.CONTINUUM,
                kind=InteractionEventKind.CONTINUUM_DELETE_BEGIN,
                position=None,
                payload=ContinuumPointPayload(point_index=self.selected_index),
            )
            self._send_interaction_event(delete_event)
            return

        step_pixels = 10 if "shift" in key else 1

        # For arrow keys, calculate new position and emit move events
        if key.endswith("left"):
            self._nudge_selected_point(-step_pixels, 0)
            self._emit_arrow_key_move_events()
        elif key.endswith("right"):
            self._nudge_selected_point(step_pixels, 0)
            self._emit_arrow_key_move_events()
        elif key.endswith("up"):
            self._nudge_selected_point(0, step_pixels)
            self._emit_arrow_key_move_events()
        elif key.endswith("down"):
            self._nudge_selected_point(0, -step_pixels)
            self._emit_arrow_key_move_events()
        elif key == "tab":
            # Legacy: keep existing behavior for now
            self._cycle_selection(1)
        elif key == "shift+tab":
            # Legacy: keep existing behavior for now
            self._cycle_selection(-1)

    def request_add_point(
        self, wavelength: float, flux: float | None, emit_event: bool = True
    ) -> bool:
        """Request addition of a new control point.

        Args:
            wavelength: Wavelength coordinate for the new point.
            flux: Flux coordinate for the new point.
            emit_event: If True, emit CONTINUUM_ADD_BEGIN event. Set to False
                when called from _on_press (which already emits the event).

        Returns:
            True if the request was emitted to downstream handlers.
        """
        if flux is None:
            return False

        if len(self.points) >= ContinuumControlPointVisuals.LIMIT:
            # Validation handled by ContinuumInteractionController
            self._show_feedback_marker((wavelength, flux))
            return False

        if self._is_too_close_to_existing(wavelength):
            self._show_feedback_marker((wavelength, flux))
            return False

        # Store pending selection position for auto-selection after add
        self._pending_select_position = (wavelength, flux)

        # Generate CONTINUUM_ADD_BEGIN event for context menu workflow
        if emit_event:
            add_event = InteractionEvent(
                channel=InteractionChannel.CONTINUUM,
                kind=InteractionEventKind.CONTINUUM_ADD_BEGIN,
                position=(wavelength, flux),
            )
            self._send_interaction_event(add_event)
        return True

    def request_delete_point(self, index: int) -> bool:
        """Request deletion of an existing control point."""
        if index < 0 or index >= len(self.points):
            return False

        if not self._can_delete_points():
            return False

        # Generate CONTINUUM_DELETE_BEGIN event for context menu workflow
        delete_event = InteractionEvent(
            channel=InteractionChannel.CONTINUUM,
            kind=InteractionEventKind.CONTINUUM_DELETE_BEGIN,
            position=None,
            payload=ContinuumPointPayload(point_index=index),
        )
        self._send_interaction_event(delete_event)
        return True

    def get_context_state(self, wavelength: float, flux: float | None) -> ContinuumContextState:
        """Return capability flags for context menu construction."""
        nearest_index: int | None = None
        if flux is not None:
            nearest_index = self._point_index_near_coordinates(wavelength, flux)

        can_add = (
            flux is not None
            and len(self.points) < ContinuumControlPointVisuals.LIMIT
            and not self._is_too_close_to_existing(wavelength)
        )

        can_delete = bool(self.points) and nearest_index is not None and self._can_delete_points()

        return ContinuumContextState(
            wavelength=wavelength,
            flux=flux,
            nearest_index=nearest_index,
            can_add=can_add,
            can_delete=can_delete,
        )

    def _point_index_near_coordinates(
        self, wavelength: float, flux: float, *, tolerance_px: float | None = None
    ) -> int | None:
        if not self.points:
            return None

        target_display = self._data_to_display(wavelength, flux)
        if target_display is None:
            return None

        tolerance = tolerance_px or ContinuumControlPointVisuals.HIT_RADIUS_PX
        best_index = None
        best_distance = float("inf")

        for idx, point in enumerate(self.points):
            display_point = self._data_to_display(*point)
            if display_point is None:
                continue
            dx = display_point[0] - target_display[0]
            dy = display_point[1] - target_display[1]
            distance = math.hypot(dx, dy)
            if distance <= tolerance and distance < best_distance:
                best_distance = distance
                best_index = idx

        return best_index

    def _begin_drag(self, index: int) -> None:
        if index < 0 or index >= len(self.points):
            return

        self.dragging = True
        self.drag_index = index
        self.selected_index = index
        self._drag_original_point = self.points[index]
        self._drag_current_point = self.points[index]
        self._drag_invalid = False
        self._set_cursor("closed_hand")
        self._ensure_origin_marker(self.points[index])
        self._clear_invalid_marker()
        self._update_display()

    def _update_drag_position(self, data_point: tuple[float, float]) -> None:
        if self.drag_index is None or self._drag_original_point is None:
            return

        wavelength, flux = data_point
        self.points[self.drag_index] = (wavelength, flux)
        self._drag_current_point = (wavelength, flux)

        violates = self._violates_min_spacing(self.drag_index, wavelength)
        self._drag_invalid = violates

        if violates:
            self._set_cursor("forbidden")
            self._ensure_invalid_marker((wavelength, flux))
            self._clear_tooltip()
        else:
            self._set_cursor("closed_hand")
            self._clear_invalid_marker()
            self._show_coordinate_tooltip(wavelength, flux)

        self._update_display()

    def _nudge_selected_point(self, dx_pixels: int, dy_pixels: int) -> None:
        if self.selected_index is None or not self.points:
            return

        point = self.points[self.selected_index]
        delta = self._pixel_delta_to_data(point, dx_pixels, dy_pixels)
        if delta is None:
            return

        new_wavelength = point[0] + delta[0]
        new_flux = point[1] + delta[1]

        if self._violates_min_spacing(self.selected_index, new_wavelength):
            self._show_feedback_marker((new_wavelength, new_flux))
            return

        self._pending_select_position = (new_wavelength, new_flux)

    def _emit_arrow_key_move_events(self) -> None:
        """Emit move events for arrow key nudging operations.

        This method is called after _nudge_selected_point to emit the
        CONTINUUM_MOVE_BEGIN, CONTINUUM_MOVE_UPDATE, and CONTINUUM_MOVE_COMPLETE
        events if the nudge was successful (i.e., _pending_select_position is set).
        """
        if self.selected_index is None or not self.points:
            return

        if self._pending_select_position is None:
            # Validation failed, no events to emit
            return

        new_wavelength, new_flux = self._pending_select_position
        current_point = self.points[self.selected_index]
        start_position = (current_point[0], current_point[1])
        new_position = (new_wavelength, new_flux)

        # Emit BEGIN event with point_index and start position
        begin_event = InteractionEvent(
            channel=InteractionChannel.CONTINUUM,
            kind=InteractionEventKind.CONTINUUM_MOVE_BEGIN,
            position=start_position,
            payload=ContinuumPointPayload(point_index=self.selected_index),
        )
        self._send_interaction_event(begin_event)

        # Emit UPDATE event with new position
        update_event = InteractionEvent(
            channel=InteractionChannel.CONTINUUM,
            kind=InteractionEventKind.CONTINUUM_MOVE_UPDATE,
            position=new_position,
            payload=None,
        )
        self._send_interaction_event(update_event)

        # Emit COMPLETE event with new position
        complete_event = InteractionEvent(
            channel=InteractionChannel.CONTINUUM,
            kind=InteractionEventKind.CONTINUUM_MOVE_COMPLETE,
            position=new_position,
            payload=None,
        )
        self._send_interaction_event(complete_event)

        # Clear pending position after emitting events
        self._pending_select_position = None

    def _cycle_selection(self, step: int) -> None:
        if not self.points:
            return
        if self.selected_index is None:
            new_index = 0 if step > 0 else len(self.points) - 1
        else:
            new_index = (self.selected_index + step) % len(self.points)
        self.selected_index = new_index
        self._update_display()

    def _open_context_menu(self, event: MouseEvent) -> None:
        data = self._data_from_event(event)
        wavelength: float | None = None
        flux: float | None = None
        if data is not None:
            wavelength, flux = data

        context_state = None
        if wavelength is not None:
            context_state = self.get_context_state(wavelength, flux)

        self._ui_port.open_context_menu(
            context_state=context_state,
            add_label=self.tr("Add Control Point"),
            delete_label=self.tr("Delete Control Point"),
            request_add=self.request_add_point,
            request_delete=self.request_delete_point,
        )

    def _ensure_origin_marker(self, point: tuple[float, float]) -> None:
        self._clear_origin_marker()
        delta = self._pixel_delta_to_data(point, ContinuumControlPointVisuals.HIT_RADIUS_PX, 0)
        radius = abs(delta[0]) if delta else ContinuumControlPointVisuals.MIN_SEPARATION_ANGSTROM
        if radius <= 0:
            radius = ContinuumControlPointVisuals.MIN_SEPARATION_ANGSTROM
        circle = Circle(
            point,
            radius,
            facecolor="none",
            edgecolor=self._brighten_color(ContinuumControlPointVisuals.MARKER_COLOR, 0.4),
            linestyle="--",
            linewidth=1.0,
            alpha=0.45,
            zorder=ContinuumControlPointVisuals.Z_ORDER - 1,
        )
        self.axes.add_patch(circle)
        self._origin_marker = circle

    def _clear_origin_marker(self) -> None:
        if self._origin_marker is None:
            return
        self._origin_marker.remove()
        self._origin_marker = None
        self.canvas.draw_idle()

    def _ensure_invalid_marker(self, point: tuple[float, float]) -> None:
        self._clear_invalid_marker()
        display_point = self._data_to_display(*point)
        if display_point is None:
            return
        size = ContinuumControlPointVisuals.HIT_RADIUS_PX
        for dx1, dy1, dx2, dy2 in [(-size, -size, size, size), (-size, size, size, -size)]:
            start = self._display_to_data(display_point[0] + dx1, display_point[1] + dy1)
            end = self._display_to_data(display_point[0] + dx2, display_point[1] + dy2)
            if start is None or end is None:
                continue
            line = Line2D(
                [start[0], end[0]],
                [start[1], end[1]],
                color="#DC3545",
                linewidth=1.5,
                zorder=ContinuumControlPointVisuals.Z_ORDER + 1,
            )
            self.axes.add_line(line)
            self._invalid_drag_artists.append(line)

    def _clear_invalid_marker(self) -> None:
        if not self._invalid_drag_artists:
            return
        for line in self._invalid_drag_artists:
            line.remove()
        self._invalid_drag_artists.clear()
        self.canvas.draw_idle()

    def _show_feedback_marker(self, point: tuple[float, float]) -> None:
        self._feedback_renderer.show_cross(
            point=point,
            axes=self.axes,
            data_to_display=self._data_to_display,
            display_to_data=self._display_to_data,
            artists=self._feedback_artists,
            clear_callback=self._clear_feedback_marker,
        )

    def _clear_feedback_marker(self) -> None:
        if not self._feedback_artists:
            return
        self._feedback_renderer.clear(self._feedback_artists)
        self.canvas.draw_idle()

    def _show_coordinate_tooltip(self, wavelength: float, flux: float) -> None:
        template = self.tr("λ = {wavelength:.2f} Å\nFlux = {flux:.3f}")
        text = template.format(wavelength=wavelength, flux=flux)
        self._ui_port.show_coordinate_tooltip(text)

    def _clear_tooltip(self) -> None:
        self._ui_port.clear_tooltip()

    def _marker_area(self, scale: float = 1.0) -> float:
        """Calculate scatter marker area in points^2 for a given scale."""
        dpi = self._figure_dpi()
        radius_px = ContinuumControlPointVisuals.MARKER_RADIUS_PX * scale
        radius_points = radius_px * 72.0 / dpi
        return float(math.pi * radius_points**2)

    def _brighten_color(self, color: str, boost: float) -> str:
        """Return a brightened variant of a hex color."""
        color = color.lstrip("#")
        if len(color) != 6:
            return f"#{color}"
        r = int(color[0:2], 16)
        g = int(color[2:4], 16)
        b = int(color[4:6], 16)

        def _apply(component: int) -> int:
            return min(255, int(component + (255 - component) * boost))

        return f"#{_apply(r):02X}{_apply(g):02X}{_apply(b):02X}"

    def _can_delete_points(self) -> bool:
        return len(self.points) > 3

    def _closest_point_index(
        self, target: tuple[float, float], *, wavelength_tolerance: float = 0.2
    ) -> int | None:
        if not self.points:
            return None

        best_index = None
        best_distance = float("inf")
        target_wave, target_flux = target
        for idx, (wave, flux) in enumerate(self.points):
            wavelength_delta = abs(wave - target_wave)
            if wavelength_delta > wavelength_tolerance:
                continue
            distance = (wave - target_wave) ** 2 + (flux - target_flux) ** 2
            if distance < best_distance:
                best_distance = distance
                best_index = idx
        if best_index is not None:
            return best_index

        # If tolerance filter excluded all, fall back to global nearest by distance
        best_index = 0
        best_distance = float("inf")
        for idx, (wave, flux) in enumerate(self.points):
            distance = (wave - target_wave) ** 2 + (flux - target_flux) ** 2
            if distance < best_distance:
                best_distance = distance
                best_index = idx
        return best_index

    def _display_to_data(self, x_display: float, y_display: float) -> tuple[float, float] | None:
        if not self.axes:
            return None
        try:
            inv = self.axes.transData.inverted()
            data_x, data_y = inv.transform((x_display, y_display))
            return float(data_x), float(data_y)
        except (TypeError, ValueError, RuntimeError):
            return None

    def _data_to_display(self, wavelength: float, flux: float) -> tuple[float, float] | None:
        if not self.axes:
            return None
        try:
            disp_x, disp_y = self.axes.transData.transform((wavelength, flux))
            return float(disp_x), float(disp_y)
        except (TypeError, ValueError, RuntimeError):
            return None

    def _data_from_event(self, event: MouseEvent) -> tuple[float, float] | None:
        if event.xdata is not None and event.ydata is not None:
            return float(event.xdata), float(event.ydata)
        return self._display_to_data(event.x, event.y)

    def _pixel_delta_to_data(
        self, reference_point: tuple[float, float], dx_pixels: int, dy_pixels: int
    ) -> tuple[float, float] | None:
        reference_display = self._data_to_display(*reference_point)
        if reference_display is None:
            return None
        target = self._display_to_data(
            reference_display[0] + dx_pixels, reference_display[1] + dy_pixels
        )
        if target is None:
            return None
        return target[0] - reference_point[0], target[1] - reference_point[1]

    def _point_index_near(self, event: MouseEvent) -> int | None:
        if not self.points:
            return None

        data = self._data_from_event(event)
        if data is None:
            return None

        return self._hit_tester.point_index_near(
            points=self.points,
            target_display=(event.x, event.y),
            data_to_display=self._data_to_display,
            tolerance_pixels=ContinuumControlPointVisuals.HIT_RADIUS_PX,
        )

    def _is_too_close_to_existing(
        self, wavelength: float, *, exclude_index: int | None = None
    ) -> bool:
        return self._hit_tester.is_too_close_to_existing(
            points=self.points,
            wavelength=wavelength,
            min_separation=ContinuumControlPointVisuals.MIN_SEPARATION_ANGSTROM,
            exclude_index=exclude_index,
        )

    def _violates_min_spacing(self, index: int, candidate_wavelength: float) -> bool:
        return self._is_too_close_to_existing(candidate_wavelength, exclude_index=index)

    def _set_cursor(self, cursor: ContinuumCursorShape) -> None:
        self._ui_port.set_cursor(cursor)

    def _update_display(self) -> None:
        """Update matplotlib display."""
        # Clear existing plots
        if self.scatter:
            self.scatter.remove()
            self.scatter = None

        if not self.points or not self.display_active:
            self.canvas.draw_idle()
            return

        # Plot points and line
        wavelengths = [p[0] for p in self.points]
        fluxes = [p[1] for p in self.points]

        facecolors: list[str] = []
        edgecolors: list[str] = []
        sizes: list[float] = []
        linewidths: list[float] = []

        for idx, _point in enumerate(self.points):
            base_color = ContinuumControlPointVisuals.MARKER_COLOR
            edge_color = base_color
            linewidth = 1.0
            scale = 1.0

            if idx == self.selected_index:
                base_color = ContinuumControlPointVisuals.MARKER_COLOR_SELECTED

            if self.dragging and idx == self.drag_index:
                scale = ContinuumControlPointVisuals.MARKER_DRAG_SCALE
                edge_color = ContinuumControlPointVisuals.MARKER_OUTLINE_DRAGGING
                linewidth = 2.0
                base_color = self._brighten_color(base_color, 0.3)

            if self.hover_index == idx and self._can_delete_points():
                edge_color = "#DC3545"
                linewidth = 2.0

            if self._drag_invalid and idx == self.drag_index:
                base_color = "#DC3545"
                edge_color = "#DC3545"

            facecolors.append(base_color)
            edgecolors.append(edge_color)
            sizes.append(self._marker_area(scale))
            linewidths.append(linewidth)

        self.scatter = self.axes.scatter(
            wavelengths,
            fluxes,
            s=sizes,
            c=facecolors,
            edgecolors=edgecolors,
            linewidths=linewidths,
            alpha=1.0,
            picker=True,
            pickradius=ContinuumControlPointVisuals.HIT_RADIUS_PX,
            zorder=ContinuumControlPointVisuals.Z_ORDER,
        )

        self.canvas.draw_idle()

    def _clear_hover_state(self) -> None:
        """Clear hover state."""
        self.hover_index = None
        self._set_cursor("arrow")
