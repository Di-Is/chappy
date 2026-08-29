"""Shell runtime dependencies, composition parts, and caller-side command ports."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Callable

    from PySide6.QtWidgets import QWidget

    from chappy.application.project_io_usecase import ProjectIOUseCase
    from chappy.core.atomic_data import AtomicLineData
    from chappy.core.editing_mode import EditingMode
    from chappy.core.spectroscopy_project import SpectroscopyProject
    from chappy.gui.modes.analysis.region_detail.editor import OptimizeEditor
    from chappy.gui.modes.analysis.region_detail.model_addition_controller import (
        OptimizeModelAdditionUseCasePort,
    )
    from chappy.gui.modes.analysis.region_detail.runtime import OptimizeVelocityOverlayRuntimePort
    from chappy.gui.modes.analysis.region_detail.ui_facade import RegionDetailUi
    from chappy.gui.modes.common.analysis_navigation import AnalysisRegionFocusPort
    from chappy.gui.modes.common.runtime import ModeRuntime
    from chappy.gui.modes.continuum.coordinator import ContinuumCoordinator
    from chappy.gui.modes.continuum.shared_surface_context_controller import (
        ContinuumSharedSurfaceContextController,
    )
    from chappy.gui.modes.identify.presets.preset_store import IdentifyPresetStore
    from chappy.gui.modes.identify.runtime import IdentifyVelocityOverlayRuntimePort
    from chappy.gui.modes.identify.workflow_ports import IdentifyModeCoordinatorPort
    from chappy.gui.modes.mode_state_store import ModeStateStore
    from chappy.gui.shell.absorber_coordinator import AbsorberCoordinator
    from chappy.gui.shell.actions.dispatcher import ActionDispatcher
    from chappy.gui.shell.analysis_navigation_coordinator import AnalysisNavigationCoordinator
    from chappy.gui.shell.dialog_workflow_coordinator import DialogWorkflowCoordinator
    from chappy.gui.shell.history_wiring_coordinator import HistoryWiringCoordinator
    from chappy.gui.shell.mode_shell_coordinator import ModeShellCoordinator
    from chappy.gui.shell.project_session_controller import ProjectSessionController
    from chappy.gui.shell.signal_connector import ShellSignalConnector
    from chappy.gui.shell.spectrum_surface_coordinator import SpectrumSurfaceCoordinator
    from chappy.gui.shell.velocity_overlay_port_adapter import SpectrumVelocityOverlayPort
    from chappy.gui.shell.window_bootstrapper import WindowBootstrapper, WindowLifecycleCoordinator


@dataclass(frozen=True, slots=True)
class ShellDependencies:
    """Immutable dependency bundle required to compose the GUI shell."""

    project_io_usecase: ProjectIOUseCase
    atomic_data: AtomicLineData
    preset_store: IdentifyPresetStore
    optimize_model_addition_usecase: OptimizeModelAdditionUseCasePort


@dataclass(frozen=True, slots=True)
class ShellRuntimeParts:
    """Prebuilt shell collaborators injected into the main window."""

    window_bootstrapper: WindowBootstrapper
    project_session: ProjectSessionController
    signal_connector: ShellSignalConnector
    window_lifecycle: WindowLifecycleCoordinator
    action_dispatcher: ActionDispatcher
    mode_shell_coordinator: ModeShellCoordinator
    analysis_navigation: AnalysisNavigationCoordinator
    absorber_coordinator: AbsorberCoordinator
    continuum_coordinator: ContinuumCoordinator
    identify_coordinator: IdentifyModeCoordinatorPort
    dialog_workflow: DialogWorkflowCoordinator
    history_wiring: HistoryWiringCoordinator
    spectrum_surface: SpectrumSurfaceCoordinator
    velocity_overlay_port: SpectrumVelocityOverlayPort
    continuum_mode_runtime: ContinuumSharedSurfaceContextController
    identify_velocity_runtime: IdentifyVelocityOverlayRuntimePort
    optimize_velocity_runtime: OptimizeVelocityOverlayRuntimePort
    mode_runtimes: dict[EditingMode, ModeRuntime]


class StatusMessagePort(Protocol):
    """Status-bar message operations available to shell callers."""

    def show_status_message(self, message: str, timeout_ms: int = 3000) -> None:
        """Display a transient shell status message.

        Args:
            message: Message to display.
            timeout_ms: Display duration in milliseconds.
        """


class ProjectCommandPort(Protocol):
    """Project lifecycle commands exposed by the shell."""

    def open_observation_data(self) -> None:
        """Open observation data through the shell workflow."""

    def open_project(self) -> None:
        """Open an existing project."""

    def save_project(self) -> None:
        """Save the active project."""

    def save_project_as(self) -> None:
        """Save the active project to a new location."""

    def close_project(self) -> None:
        """Close the active project."""

    def set_current_project(self, project: SpectroscopyProject | None) -> None:
        """Replace the active project.

        Args:
            project: New active project, or None to clear it.
        """


class ModeCommandPort(Protocol):
    """Mode and mode-owned workflow commands exposed by the shell."""

    def switch_mode(self, mode: EditingMode) -> None:
        """Switch the active editing mode.

        Args:
            mode: Target mode.
        """

    def add_continuum(self) -> None:
        """Add a continuum component through the active workflow."""

    def fit_model(self) -> None:
        """Run the optimize fit workflow."""

    def back_to_analysis_overview(self) -> None:
        """Return from Region Detail to the Analysis Overview."""

    def delete_selection(self) -> None:
        """Delete the current selection through its active mode workflow."""


class DialogCommandPort(Protocol):
    """Global dialog commands exposed by the shell."""

    def open_user_manual(self) -> None:
        """Open the user manual."""

    def show_cosmology_dialog(self) -> None:
        """Open the cosmology settings dialog."""

    def show_resolution_dialog(self) -> None:
        """Open the resolution settings dialog."""

    def open_line_database_folder(self) -> None:
        """Open the folder holding the spectral line CSV."""

    def show_language_dialog(self) -> None:
        """Open the language settings dialog."""

    def show_preset_list_dialog(self) -> None:
        """Open the identify preset management dialog."""


class SpectrumNavigationPort(Protocol):
    """Shared spectrum navigation commands exposed by the shell."""

    def zoom_in(self) -> None:
        """Zoom in on the active spectrum view."""

    def zoom_out(self) -> None:
        """Zoom out on the active spectrum view."""

    def reset_view(self) -> None:
        """Reset the active spectrum ranges."""

    def auto_adjust_flux(self) -> None:
        """Auto-adjust the flux range."""

    def toggle_velocity_plot_optimize(self) -> None:
        """Toggle the Analysis Detail velocity-plot workflow."""

    def toggle_velocity_plot_identify(self) -> None:
        """Toggle the Identify velocity-plot workflow."""


class RegionDetailFactory(Protocol):
    """Construct the composed Region Detail UI facade for the dock coordinator."""

    def __call__(
        self,
        *,
        optimize_editor: OptimizeEditor,
        analysis_focus: AnalysisRegionFocusPort,
        mode_state: ModeStateStore | None,
        model_addition_usecase: OptimizeModelAdditionUseCasePort,
        velocity_plot_active_provider: Callable[[], bool],
        project_file_path_provider: Callable[[], str | None],
        parent: QWidget | None = None,
    ) -> RegionDetailUi:
        """Build the Region Detail panel and its collaborators, returning the facade.

        Args:
            optimize_editor: Optimize editor collaborator wired to the panel.
            analysis_focus: Analysis region focus port for cross-mode navigation.
            mode_state: Shared editing-mode state signals, if available.
            model_addition_usecase: Use case for adding models at a wavelength.
            velocity_plot_active_provider: Reports whether the velocity plot is visible.
            project_file_path_provider: Reports the active project's file path.
            parent: Parent widget hosting the panel.
        """


class WindowChromePort(Protocol):
    """Top-level window chrome commands exposed by the shell."""

    @property
    def current_project(self) -> SpectroscopyProject | None:
        """Return the active project."""

    def show(self) -> None:
        """Show the top-level shell window."""

    def close(self) -> bool:
        """Close the top-level shell window.

        Returns:
            True when the window accepted the close request.
        """
