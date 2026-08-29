"""Velocity prompt feedback controller for spectrum interactions."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from PySide6.QtCore import QObject, Qt

from chappy.presentation.interaction.interaction_contracts import InteractionPhase

if TYPE_CHECKING:
    from collections.abc import Callable

    from chappy.gui.protocols import VelocityInteractionProvider
    from chappy.presentation.interaction.interaction_contracts import (
        InteractionStateSnapshot,
        VelocityContext,
    )

logger = logging.getLogger(__name__)


@runtime_checkable
class CursorTarget(Protocol):
    """Widget-like endpoint that accepts cursor updates."""

    def setCursor(self, cursor: Qt.CursorShape) -> None:  # noqa: N802
        """Set the cursor shape."""
        ...


@runtime_checkable
class CanvasOwner(Protocol):
    """Widget-like endpoint that exposes a cursor-aware canvas."""

    canvas: CursorTarget


@runtime_checkable
class StatusControllerPort(Protocol):
    """Status controller methods used by velocity prompt feedback."""

    def show_message(self, message: str, *, timeout_ms: int | None = None) -> None:
        """Show a status message."""
        ...

    def clear_message(self) -> None:
        """Clear the active status message."""
        ...


@runtime_checkable
class VelocityOriginPlotPort(Protocol):
    """Plot widget methods used by velocity prompt feedback."""

    def show_velocity_origin_line(self, wavelength: float) -> None:
        """Show the velocity origin line."""
        ...

    def hide_velocity_origin_line(self) -> None:
        """Hide the velocity origin line."""
        ...

    def update_velocity_origin_line(self, wavelength: float) -> None:
        """Update the velocity origin line."""
        ...


@runtime_checkable
class SpectrumPlotHostPort(Protocol):
    """Plot host subset used by velocity prompt feedback."""

    plot_widget: VelocityPromptWidget | None


type VelocityPromptWidget = CursorTarget | CanvasOwner | VelocityOriginPlotPort
type VelocityPromptLogValue = str | int | float | bool | None


class VelocityPromptController(QObject):
    """Coordinate cursor, status, and origin-line feedback for velocity prompt mode."""

    def __init__(
        self,
        *,
        plot_host_provider: Callable[[], SpectrumPlotHostPort | None],
        plot_widget_provider: Callable[[], VelocityPromptWidget | None],
        interactor_provider: Callable[[], VelocityInteractionProvider | None],
        status_controller_provider: Callable[[], StatusControllerPort | None],
        parent: QObject | None = None,
    ) -> None:
        """Initialize the controller with presenter-owned dependency providers."""
        super().__init__(parent)
        self._plot_host_provider = plot_host_provider
        self._plot_widget_provider = plot_widget_provider
        self._interactor_provider = interactor_provider
        self._status_controller_provider = status_controller_provider
        self._active = False

    @property
    def active(self) -> bool:
        """Return whether the velocity prompt is currently active."""
        return self._active

    def activate(self, *, source: str) -> None:
        """Enable crosshair cursor and show the pending velocity status message."""
        if self._active:
            return

        self._active = True
        self._set_plot_cursor(Qt.CursorShape.CrossCursor)

        controller = self._status_controller()
        if controller is not None:
            controller.show_message(self.tr("Click to confirm velocity plot"), timeout_ms=0)

        target_wavelength = self._target_wavelength()
        if target_wavelength is not None:
            self._show_velocity_origin_line(target_wavelength)

        logger.debug("Velocity prompt activated", extra={"source": source})

    def deactivate(
        self, *, source: str, show_cancelled_status: bool, cancel_reason: str | None = None
    ) -> None:
        """Restore the default cursor and optionally display a follow-up status message."""
        was_active = self._active
        self._active = False

        if was_active:
            self._set_plot_cursor(Qt.CursorShape.ArrowCursor)
            self._hide_velocity_origin_line()

        controller = self._status_controller()
        if controller is not None:
            if show_cancelled_status:
                controller.show_message(
                    self.tr("Velocity plot creation cancelled"), timeout_ms=3000
                )
            elif was_active:
                controller.clear_message()

        payload: dict[str, VelocityPromptLogValue] = {"source": source, "was_active": was_active}
        if cancel_reason:
            payload["cancel_reason"] = cancel_reason
        logger.debug("Velocity prompt deactivated", extra=payload)

    def apply_snapshot(
        self,
        snapshot: InteractionStateSnapshot[VelocityContext],
        *,
        snapshot_callback: Callable[[InteractionStateSnapshot[VelocityContext]], None],
    ) -> None:
        """Apply a velocity interaction snapshot and notify observers."""
        self._log_velocity_snapshot(snapshot)

        if snapshot.phase in {InteractionPhase.ARMED, InteractionPhase.ACTIVE}:
            self.activate(source="snapshot")
        elif snapshot.phase in {InteractionPhase.IDLE, InteractionPhase.CANCELLED}:
            cancel_reason = snapshot.context.cancel_reason if snapshot.context else None
            self.deactivate(
                source="snapshot",
                show_cancelled_status=snapshot.phase is InteractionPhase.CANCELLED,
                cancel_reason=cancel_reason,
            )

        snapshot_callback(snapshot)

    def update_origin_for_cursor(self, wavelength: float, _flux: float, _modifiers: int) -> None:
        """Update velocity origin line position while prompt mode is active."""
        if self._active:
            self._update_velocity_origin_line(wavelength)

    def _plot_widgets(self) -> list[CursorTarget]:
        """Return plot widgets that should mirror the active cursor state."""
        widgets: list[CursorTarget] = []

        plot_widget = self._plot_widget()
        self._append_cursor_target(widgets, plot_widget)
        if isinstance(plot_widget, CanvasOwner):
            self._append_cursor_target(widgets, plot_widget.canvas)
        return widgets

    @staticmethod
    def _append_cursor_target(
        widgets: list[CursorTarget], candidate: VelocityPromptWidget | None
    ) -> None:
        """Append candidate when it accepts cursor updates."""
        if isinstance(candidate, CursorTarget):
            widgets.append(candidate)

    def _set_plot_cursor(self, cursor: Qt.CursorShape) -> None:
        """Set the cursor for all spectrum plot widgets."""
        for widget in self._plot_widgets():
            widget.setCursor(cursor)

    def _status_controller(self) -> StatusControllerPort | None:
        """Return the main-window status controller when available."""
        return self._status_controller_provider()

    def _target_wavelength(self) -> float | None:
        """Return the target wavelength for velocity plot from the interactor."""
        interactor = self._interactor_provider()
        return interactor.current_velocity_target_wavelength() if interactor is not None else None

    def _plot_widget(self) -> VelocityPromptWidget | None:
        """Return the active plot widget if available."""
        plot_host = self._plot_host_provider()
        if isinstance(plot_host, SpectrumPlotHostPort) and plot_host.plot_widget is not None:
            return plot_host.plot_widget
        return self._plot_widget_provider()

    def _show_velocity_origin_line(self, wavelength: float) -> None:
        """Show a vertical dashed line at the given wavelength."""
        plot_widget = self._plot_widget()
        if isinstance(plot_widget, VelocityOriginPlotPort):
            plot_widget.show_velocity_origin_line(wavelength)

    def _hide_velocity_origin_line(self) -> None:
        """Hide the velocity origin line if visible."""
        plot_widget = self._plot_widget()
        if isinstance(plot_widget, VelocityOriginPlotPort):
            plot_widget.hide_velocity_origin_line()

    def _update_velocity_origin_line(self, wavelength: float) -> None:
        """Update the velocity origin line position."""
        plot_widget = self._plot_widget()
        if isinstance(plot_widget, VelocityOriginPlotPort):
            plot_widget.update_velocity_origin_line(wavelength)

    def _log_velocity_snapshot(self, snapshot: InteractionStateSnapshot[VelocityContext]) -> None:
        """Emit structured debug logs for velocity interaction snapshots."""
        context = snapshot.context
        payload: dict[str, VelocityPromptLogValue] = {
            "phase": snapshot.phase.value,
            "interaction_id": str(snapshot.interaction_id),
        }
        if context:
            payload["target_wavelength"] = context.target_wavelength
            payload["confirmed_wavelength"] = context.confirmed_wavelength
            payload["trigger"] = context.trigger
            payload["modifiers"] = context.modifiers
            payload["cancel_reason"] = context.cancel_reason

        if snapshot.phase is InteractionPhase.CANCELLED:
            logger.info("Velocity interaction cancelled", extra=payload)
            return

        if snapshot.phase is InteractionPhase.IDLE:
            logger.info("Velocity interaction completed", extra=payload)
            return

        logger.debug("Velocity interaction pending", extra=payload)
