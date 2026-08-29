"""Optimize-mode runtime owning shared surface and velocity overlay workflows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from PySide6.QtCore import QCoreApplication

from chappy.gui.modes.analysis.region_detail.shared_surface_controller import (
    OptimizeSharedSurfaceController,
    OptimizeSharedSurfaceIntegrationPort,
)
from chappy.gui.modes.analysis.region_detail.velocity_overlay_adapter import (
    optimize_velocity_overlay_info,
)
from chappy.gui.modes.analysis.region_detail.velocity_plot_controller import (
    OptimizeVelocityPlotController,
    OptimizeVelocityPlotPorts,
)
from chappy.gui.modes.common import ModeRuntime, VelocityOverlayPort

if TYPE_CHECKING:
    from collections.abc import Callable

    from chappy.core.editing_mode import EditingMode
    from chappy.core.spectroscopy_project import SpectroscopyProject
    from chappy.gui.modes.analysis.region_detail.editor import OptimizeEditor
    from chappy.gui.modes.analysis.region_detail.velocity_plot_controller import (
        OptimizeVelocityOverlayContext,
    )
    from chappy.gui.protocols.context_menu import (
        ContextMenuActionDescriptor,
        ContextMenuActionIntent,
    )
    from chappy.gui.protocols.intent_types import ShowContextMenuIntent
    from chappy.gui.protocols.spectrum_intents import IdentifyModeIntent


class OptimizeVelocityOverlayRuntimePort(ModeRuntime):
    """Optimize runtime extension used by shell collaborators."""

    def fit_model(self) -> None:
        """Run the optimize fit workflow."""

    def is_fit_running(self) -> bool:
        """Return whether the optimize editor owns an active fit."""
        raise NotImplementedError

    def toggle_velocity_overlay(self) -> None:
        """Toggle the optimize velocity overlay."""

    def refresh_visible_velocity_overlay(self) -> None:
        """Refresh the optimize velocity overlay when visible."""


@dataclass(frozen=True, slots=True)
class OptimizeModeRuntimePorts:
    """Dependencies required to build the optimize mode runtime."""

    current_mode_provider: Callable[[], EditingMode | None]
    integration_provider: Callable[[], OptimizeSharedSurfaceIntegrationPort | None]
    spectrum_update_callback: Callable[[], None]
    project_provider: Callable[[], SpectroscopyProject | None]
    optimize_editor_provider: Callable[[], OptimizeEditor | None]
    selected_region_id_provider: Callable[[], str | None]
    velocity_visible_provider: Callable[[], bool]
    velocity_overlay_port: VelocityOverlayPort
    action_checked_callback: Callable[[bool], None]
    status_message_callback: Callable[[str, int], None]
    context_menu_action_provider: (
        Callable[[float], tuple[ContextMenuActionDescriptor, ...]] | None
    ) = None


class OptimizeModeRuntime(OptimizeVelocityOverlayRuntimePort):
    """Own optimize shared-surface routing and velocity overlay workflow."""

    def __init__(self, ports: OptimizeModeRuntimePorts) -> None:
        """Initialize the optimize runtime."""
        self._ports = ports
        self._velocity_overlay_port = ports.velocity_overlay_port
        self._shared_surface_controller = OptimizeSharedSurfaceController(
            integration_provider=ports.integration_provider,
            spectrum_update_callback=ports.spectrum_update_callback,
            context_menu_action_provider=ports.context_menu_action_provider,
        )
        self._velocity_plot_controller = OptimizeVelocityPlotController(
            OptimizeVelocityPlotPorts(
                current_mode_provider=ports.current_mode_provider,
                project_provider=ports.project_provider,
                selected_region_id_provider=ports.selected_region_id_provider,
                velocity_visible_provider=ports.velocity_visible_provider,
                show_velocity_plot_callback=self._show_velocity_plot,
                hide_velocity_plot_callback=self._hide_velocity_plot,
                action_checked_callback=ports.action_checked_callback,
            )
        )

    def handle_mode_click(self, wavelength: float, flux: float, modifiers: int) -> None:
        """Handle an optimize spectrum click."""
        self._shared_surface_controller.handle_mode_click(wavelength, flux, modifiers)

    def handle_mode_velocity_shortcut(self) -> None:
        """Handle optimize velocity shortcuts."""
        self._shared_surface_controller.handle_mode_velocity_shortcut()

    def handle_context_menu_intent(self, intent: ContextMenuActionIntent) -> None:
        """Handle a selected context-menu intent."""
        self._shared_surface_controller.handle_context_menu_intent(intent)

    def handle_identify_intent(self, intent: IdentifyModeIntent) -> None:
        """Ignore identify-only intents for optimize mode."""
        self._shared_surface_controller.handle_identify_intent(intent)

    def context_menu_actions(
        self, request: ShowContextMenuIntent
    ) -> tuple[ContextMenuActionDescriptor, ...]:
        """Return optimize context-menu actions."""
        return self._shared_surface_controller.context_menu_actions(request)

    def fit_model(self) -> None:
        """Run the optimize fit workflow."""
        if self._ports.project_provider() is None:
            return

        optimize_editor = self._ports.optimize_editor_provider()
        if optimize_editor is None:
            message = QCoreApplication.translate(
                "MainWindow", "Analysis Region Detail editor not available"
            )
            self._ports.status_message_callback(message, 3000)
            return
        optimize_editor.start_fit()

    def is_fit_running(self) -> bool:
        """Return the current editor fit state without starting work."""
        editor = self._ports.optimize_editor_provider()
        return editor is not None and editor.is_fitting()

    def toggle_velocity_overlay(self) -> None:
        """Toggle the optimize velocity overlay."""
        self._velocity_plot_controller.toggle()

    def refresh_visible_velocity_overlay(self) -> None:
        """Refresh the optimize velocity overlay when visible."""
        self._velocity_plot_controller.refresh_if_visible()

    def _show_velocity_plot(self, context: OptimizeVelocityOverlayContext) -> None:
        """Show the optimize velocity overlay."""
        self._velocity_overlay_port.show_velocity_overlay(
            optimize_velocity_overlay_info(context), context="optimize"
        )

    def _hide_velocity_plot(self) -> None:
        """Hide the optimize velocity overlay."""
        self._velocity_overlay_port.hide_velocity_overlay(context="optimize")
