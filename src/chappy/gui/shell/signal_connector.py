"""Connect shell-level signals across prebuilt collaborators."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from PySide6.QtCore import QObject

from chappy.core.editing_mode import EditingMode
from chappy.gui.modes.continuum.coordinator import ContinuumCoordinatorShell
from chappy.gui.protocols.plotting import ContinuumPlotWidget

if TYPE_CHECKING:
    from collections.abc import Callable

    from PySide6.QtWidgets import QWidget

    from chappy.application.optimize import FitResultRawPayload
    from chappy.gui.modes.analysis.region_detail.editor import OptimizeEditor
    from chappy.gui.modes.analysis.region_detail.ui_facade import RegionDetailUi
    from chappy.gui.modes.continuum.coordinator import ContinuumCoordinator
    from chappy.gui.modes.continuum.editor import ContinuumEditor
    from chappy.gui.modes.identify.panel.panel import IdentifySidePanel
    from chappy.gui.modes.identify.workflow_ports import IdentifyModeCoordinatorPort
    from chappy.gui.shell.absorber_coordinator import AbsorberCoordinator, AbsorberEditorSignalPort
    from chappy.gui.shell.main_window import MainWindow
    from chappy.gui.shell.mode_shell_coordinator import ModeShellCoordinator
    from chappy.gui.shell.view_stack import ViewStack
    from chappy.presentation.interaction.interaction_contracts import OptimizeMaskGroupChange
    from chappy.presentation.velocity import VelocityOverlayInfo, VelocitySliceInfo

logger = logging.getLogger(__name__)


@runtime_checkable
class _CursorCoordinateShell(Protocol):
    """Shell API for cursor coordinate display updates."""

    def handle_cursor_coordinates_changed(self, wavelength: float, flux: float) -> None:
        """Update the displayed cursor coordinates."""
        ...

    def handle_cursor_coordinates_cleared(self) -> None:
        """Clear the displayed cursor coordinates."""
        ...


@dataclass(frozen=True, slots=True)
class ShellSignalConnectorPorts:
    """Typed shell callbacks consumed by signal connection wiring."""

    status_message: Callable[[str], None]
    mode_changed: Callable[[EditingMode], None]
    hide_velocity_plot: Callable[[], None] | None = None
    confirm_velocity_plot_selection: (
        Callable[[VelocityOverlayInfo | None, list[VelocitySliceInfo]], None] | None
    ) = None
    active_view_changed: Callable[[str, QWidget], None] | None = None
    cursor_coordinates_changed: Callable[[float, float], None] | None = None
    cursor_coordinates_cleared: Callable[[], None] | None = None
    fit_started: Callable[[], None] | None = None
    fit_completed: Callable[[FitResultRawPayload], None] | None = None
    optimize_region_changed: Callable[[OptimizeMaskGroupChange], None] | None = None


@dataclass(frozen=True, slots=True)
class ShellSignalConnectorBindings:
    """Runtime-owned surfaces that expose Qt signals to the shell connector."""

    absorber_editor: AbsorberEditorSignalPort | None
    continuum_editor: ContinuumEditor | None
    optimize_editor: OptimizeEditor | None
    view_stack: ViewStack | None
    identify_panel: IdentifySidePanel | None
    optimize_panel: RegionDetailUi | None


class ShellSignalConnector(QObject):
    """Connect shell-owned collaborators without constructing them."""

    def __init__(self, main_window: MainWindow) -> None:
        """Initialize the connector with its QObject parent."""
        super().__init__(main_window)
        self._main_window = main_window
        self._bindings: ShellSignalConnectorBindings | None = None

        self.absorber_coordinator: AbsorberCoordinator | None = None
        self.continuum_coordinator: ContinuumCoordinator | None = None
        self.identify_coordinator: IdentifyModeCoordinatorPort | None = None
        self.mode_shell_coordinator: ModeShellCoordinator | None = None

        self._ports: ShellSignalConnectorPorts | None = None
        self._mode_shell_signals_connected = False

    def set_ports(self, ports: ShellSignalConnectorPorts) -> None:
        """Set typed shell callbacks."""
        self._ports = ports
        if self.mode_shell_coordinator is not None:
            self._connect_mode_shell_coordinator_signals()

    def set_coordinators(
        self,
        *,
        absorber_coordinator: AbsorberCoordinator,
        continuum_coordinator: ContinuumCoordinator,
        identify_coordinator: IdentifyModeCoordinatorPort,
        mode_shell_coordinator: ModeShellCoordinator,
    ) -> None:
        """Attach prebuilt coordinators and connect their shared signals."""
        if not isinstance(self._main_window, ContinuumCoordinatorShell):
            msg = "Main window does not implement ContinuumCoordinatorShell."
            raise TypeError(msg)

        self.absorber_coordinator = absorber_coordinator
        self.continuum_coordinator = continuum_coordinator
        self.identify_coordinator = identify_coordinator
        self.mode_shell_coordinator = mode_shell_coordinator

        self._connect_coordinator_signals()
        if self._ports is not None:
            self._connect_mode_shell_coordinator_signals()

    def bind_runtime_surfaces(self, bindings: ShellSignalConnectorBindings) -> None:
        """Store shell surfaces whose Qt signals must be connected."""
        self._bindings = bindings

    def connect_signals(self) -> None:
        """Connect internal signals between already-built collaborators."""
        bindings = self._require_bindings()

        if bindings.view_stack is not None:
            self._connect_view_signals(bindings.view_stack)

        self._connect_editor_signals(bindings.continuum_editor)

        if bindings.optimize_editor is not None:
            self._connect_optimizer_signals(bindings.optimize_editor)

        if bindings.optimize_panel is not None:
            optimize_region_changed = self._require_ports().optimize_region_changed
            if optimize_region_changed is not None:
                bindings.optimize_panel.mask_group_changed.connect(optimize_region_changed)

        if self.absorber_coordinator is not None:
            self.absorber_coordinator.setup_absorber_signals()

        if self.continuum_coordinator is not None:
            self.continuum_coordinator.setup_continuum_signals()

        if self.identify_coordinator is not None:
            self.identify_coordinator.set_panel(bindings.identify_panel)

    def _connect_coordinator_signals(self) -> None:
        """Connect coordinator-emitted signals to shell callbacks."""
        self._connect_absorber_coordinator_signals()
        self._connect_continuum_coordinator_signals()
        self._connect_identify_coordinator_signals()

    def _connect_absorber_coordinator_signals(self) -> None:
        if self.absorber_coordinator is None:
            msg = "Absorber coordinator not initialized"
            raise RuntimeError(msg)
        self.absorber_coordinator.status_message.connect(self._emit_status_message)

    def _connect_continuum_coordinator_signals(self) -> None:
        if self.continuum_coordinator is None:
            msg = "Continuum coordinator not initialized"
            raise RuntimeError(msg)
        self.continuum_coordinator.status_message.connect(self._emit_status_message)
        logger.debug("Continuum coordinator signals connected")

    def _connect_identify_coordinator_signals(self) -> None:
        self._require_identify_coordinator().connect_status_message(self._emit_status_message)
        logger.debug("Identify coordinator signals connected")

    def _connect_mode_shell_coordinator_signals(self) -> None:
        self._require_identify_coordinator()
        if self.mode_shell_coordinator is None:
            msg = "Mode coordinator not initialized"
            raise RuntimeError(msg)
        if self._mode_shell_signals_connected:
            return

        self.mode_shell_coordinator.mode_changed.connect(self._require_ports().mode_changed)
        self.mode_shell_coordinator.mode_changed.connect(self._handle_mode_changed_for_identify)
        self._mode_shell_signals_connected = True
        logger.debug("Mode coordinator signals connected")

    def _require_identify_coordinator(self) -> IdentifyModeCoordinatorPort:
        if self.identify_coordinator is None:
            msg = "Identify coordinator is required for shell signal coordination."
            raise RuntimeError(msg)
        return self.identify_coordinator

    def _require_ports(self) -> ShellSignalConnectorPorts:
        if self._ports is None:
            msg = "Shell signal connector ports are required before connecting signals."
            raise RuntimeError(msg)
        return self._ports

    def _require_bindings(self) -> ShellSignalConnectorBindings:
        if self._bindings is None:
            msg = "Shell signal connector bindings are required before connecting signals."
            raise RuntimeError(msg)
        return self._bindings

    def _handle_mode_changed_for_identify(self, mode: EditingMode) -> None:
        """Refresh identify panel when entering identify mode."""
        identify_coordinator = self._require_identify_coordinator()
        if mode == EditingMode.IDENTIFY:
            identify_coordinator.refresh()
        else:
            identify_coordinator.handle_cursor_left()

    def _connect_view_signals(self, view_stack: ViewStack) -> None:
        """Connect view-owned signals to shell callbacks and coordinators."""
        active_view_changed = self._require_ports().active_view_changed
        if active_view_changed is None:
            msg = "Active-view callback is required for shell signal coordination."
            raise RuntimeError(msg)
        view_stack.activeViewChanged.connect(active_view_changed)

        spectrum_view = view_stack.spectrum_view
        if spectrum_view is None:
            logger.info("View signals connected without a spectrum view")
            return

        spectrum_view.velocity_plot_exit_requested.connect(self._hide_velocity_plot)
        spectrum_view.velocity_plot_add_requested.connect(self._confirm_velocity_plot_selection)

        optimize_panel = self._require_bindings().optimize_panel
        if optimize_panel is not None:
            spectrum_view.velocity_context_menu_requested.connect(
                optimize_panel.handle_velocity_context_menu
            )
            spectrum_view.velocity_shift_click_requested.connect(
                optimize_panel.handle_velocity_shift_click
            )

        if self.absorber_coordinator is not None:
            self.absorber_coordinator.absorber_parameter_changed.connect(
                self._forward_absorber_parameter_to_coordinator
            )
            logger.debug("Connected absorber parameter changes to spectrum coordinator")

        spectrum_view.cursor_position_changed.connect(self._handle_cursor_position_changed)
        spectrum_view.cursor_left.connect(self._handle_cursor_left)
        spectrum_view.identify_preview_shift_released.connect(
            self._handle_identify_preview_shift_released
        )
        logger.info("View signals connected via ShellSignalConnector")

    def _connect_editor_signals(self, continuum_editor: ContinuumEditor | None) -> None:
        """Connect editor-owned signals to existing coordinators."""
        if continuum_editor is None or self.continuum_coordinator is None:
            return

        continuum_editor.continuum_updated.connect(self.continuum_coordinator.on_continuum_updated)

        bindings = self._require_bindings()
        if bindings.view_stack is not None:
            spectrum_plot = bindings.view_stack.get_spectrum_plot()
            if isinstance(spectrum_plot, ContinuumPlotWidget):
                continuum_editor.connect_plot_widget(spectrum_plot)

        continuum_editor.status_message.connect(self._emit_status_message)

    def _connect_optimizer_signals(self, optimize_editor: OptimizeEditor) -> None:
        """Connect optimizer lifecycle signals to shell callbacks."""
        ports = self._require_ports()
        if ports.fit_started is None:
            msg = "Fit-start callback is required for shell signal coordination."
            raise RuntimeError(msg)
        if ports.fit_completed is None:
            msg = "Fit-complete callback is required for shell signal coordination."
            raise RuntimeError(msg)
        optimize_editor.fit_started.connect(ports.fit_started)
        optimize_editor.fit_completed.connect(ports.fit_completed)

    def _emit_status_message(self, message: str) -> None:
        """Emit status message through the configured shell callback."""
        self._require_ports().status_message(message)

    def _hide_velocity_plot(self) -> None:
        """Hide the shared velocity plot through the configured shell callback."""
        callback = self._require_ports().hide_velocity_plot
        if callback is not None:
            callback()
            return
        self._main_window.identify_velocity_runtime.hide_velocity_plot()

    def _confirm_velocity_plot_selection(
        self, overlay_info: VelocityOverlayInfo | None, selections: list[VelocitySliceInfo]
    ) -> None:
        """Forward velocity-plot selection through the configured shell callback."""
        callback = self._require_ports().confirm_velocity_plot_selection
        if callback is not None:
            callback(overlay_info, selections)
            return
        self._main_window.identify_velocity_runtime.confirm_velocity_plot_selection(
            overlay_info, selections
        )

    def _handle_cursor_position_changed(
        self, wavelength: float, flux: float, modifiers: int
    ) -> None:
        """Forward cursor movement events to interested coordinators."""
        logger.debug(
            "ShellSignalConnector._handle_cursor_position_changed: wavelength=%.2f", wavelength
        )

        if isinstance(self._main_window, _CursorCoordinateShell):
            cursor_coordinates_changed = self._require_ports().cursor_coordinates_changed
            if cursor_coordinates_changed is not None:
                cursor_coordinates_changed(wavelength, flux)

        if self.identify_coordinator is not None:
            self.identify_coordinator.handle_cursor_position(wavelength, flux, modifiers)
        else:
            logger.debug("Identify coordinator is not initialized")

    def _handle_cursor_left(self) -> None:
        """Clear cursor-driven UI state when exiting the spectrum plot."""
        if isinstance(self._main_window, _CursorCoordinateShell):
            cursor_coordinates_cleared = self._require_ports().cursor_coordinates_cleared
            if cursor_coordinates_cleared is not None:
                cursor_coordinates_cleared()

        if self.identify_coordinator is not None:
            self.identify_coordinator.handle_cursor_left()

    def _handle_identify_preview_shift_released(self) -> None:
        """Clear only transient Shift-derived Identify preview state."""
        if self.identify_coordinator is not None:
            self.identify_coordinator.handle_preview_shift_released()

    def _forward_absorber_parameter_to_coordinator(self, param: str, value: float) -> None:
        """Forward absorber parameter changes to the spectrum presenter."""
        bindings = self._require_bindings()
        if bindings.view_stack is None or bindings.view_stack.spectrum_view is None:
            return
        absorber_name, separator, parameter_name = param.rpartition(".")
        if not separator or not absorber_name or not parameter_name:
            msg = f"Invalid absorber parameter route: {param}"
            raise ValueError(msg)
        spectrum_view = bindings.view_stack.spectrum_view
        spectrum_view.coordinator.update_absorber_param(absorber_name, parameter_name, value)


__all__ = ["ShellSignalConnector", "ShellSignalConnectorBindings", "ShellSignalConnectorPorts"]
