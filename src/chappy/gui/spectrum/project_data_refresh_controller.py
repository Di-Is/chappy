"""Project and data refresh coordination for the spectrum surface."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Callable

    from chappy.core.spectroscopy_project import SpectroscopyProject
    from chappy.gui.spectrum.spectrum_data_bridge import SpectrumDataBridge


@runtime_checkable
class ProjectStateReceiver(Protocol):
    """Component that can receive active project state."""

    def set_project(self, project: SpectroscopyProject) -> None:
        """Set the active project."""
        ...


@runtime_checkable
class DataRefreshReceiver(Protocol):
    """Component that can refresh its data state."""

    def refresh_data(self) -> None:
        """Refresh component data."""
        ...


@runtime_checkable
class VisualUpdateReceiver(Protocol):
    """Component that exposes a Qt-like update method."""

    def update(self) -> None:
        """Refresh visual state."""
        ...


@runtime_checkable
class ProjectRefreshReceiver(Protocol):
    """Component that refreshes from a full project context."""

    def update_from_project(self, project: SpectroscopyProject) -> None:
        """Refresh using a project."""
        ...


type ProjectDataRefreshComponent = (
    ProjectStateReceiver | DataRefreshReceiver | VisualUpdateReceiver | ProjectRefreshReceiver
)


class SpectrumProjectDataRefreshController:
    """Coordinate project and data refreshes outside the Facade."""

    def __init__(
        self,
        *,
        data_bridge_provider: Callable[[], SpectrumDataBridge | None],
        components_provider: Callable[[], tuple[object, ...]],
        range_changed_callback: Callable[[float, float, float, float], None],
        auto_scale_callback: Callable[[], None],
    ) -> None:
        """Initialize the controller."""
        self._data_bridge_provider = data_bridge_provider
        self._components_provider = components_provider
        self._range_changed_callback = range_changed_callback
        self._auto_scale_callback = auto_scale_callback

    def connect_data_bridge_signals(self, data_bridge: SpectrumDataBridge | None) -> None:
        """Connect data bridge signals to refresh handlers."""
        if data_bridge is None:
            return

        data_bridge.project_changed.connect(self.handle_project_changed)
        data_bridge.data_updated.connect(self.handle_data_updated)
        data_bridge.range_changed.connect(self.handle_range_changed)

    def synchronize_project_state(self) -> None:
        """Synchronize project state across project-aware components."""
        data_bridge = self._data_bridge_provider()
        if data_bridge is None or data_bridge.project is None:
            return

        project = data_bridge.project
        for component in self._components_provider():
            if isinstance(component, ProjectStateReceiver):
                component.set_project(project)

    def handle_project_changed(self, project: SpectroscopyProject | None) -> None:
        """Handle project changes from the data bridge."""
        self.synchronize_project_state()

        if project is not None:
            self._auto_scale_callback()
            self._refresh_project_receivers(project)

    def _refresh_project_receivers(self, project: SpectroscopyProject) -> None:
        """Render the newly attached project without fabricating a model event."""
        for component in self._components_provider():
            if isinstance(component, ProjectRefreshReceiver):
                component.update_from_project(project)

    def handle_data_updated(self) -> None:
        """Handle data updates from the data bridge."""
        data_bridge = self._data_bridge_provider()
        project = data_bridge.project if data_bridge is not None else None

        for component in self._components_provider():
            if isinstance(component, DataRefreshReceiver):
                component.refresh_data()
            elif isinstance(component, VisualUpdateReceiver):
                component.update()
            elif project is not None and isinstance(component, ProjectRefreshReceiver):
                component.update_from_project(project)

    def handle_range_changed(
        self, min_wave: float, max_wave: float, min_flux: float, max_flux: float
    ) -> None:
        """Handle range changes from the data bridge."""
        self._range_changed_callback(min_wave, max_wave, min_flux, max_flux)


__all__ = ["ProjectDataRefreshComponent", "SpectrumProjectDataRefreshController"]
