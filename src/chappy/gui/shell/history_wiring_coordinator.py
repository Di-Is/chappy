"""Wire history collaborators to the shared shell surface."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from chappy.gui.spectrum.spectrum_interaction_coordinator import SpectrumInteractionCoordinator

if TYPE_CHECKING:
    from collections.abc import Callable

    from chappy.application.history import HistoryRecorder
    from chappy.core.history import HistoryState
    from chappy.core.spectroscopy_project import SpectroscopyProject
    from chappy.gui.history.bridge import HistoryBridge
    from chappy.gui.modes.continuum import ContinuumEditor
    from chappy.gui.shell.dock_layout_coordinator import DockLayoutCoordinator
    from chappy.gui.shell.menu_action_factory import MenuActionFactory
    from chappy.gui.shell.view_stack import ViewStack


@dataclass(frozen=True, slots=True)
class HistoryWiringPorts:
    """Dependencies required to wire history across shell collaborators."""

    history_bridge: HistoryBridge
    history_recorder: HistoryRecorder
    view_stack_provider: Callable[[], ViewStack | None]
    continuum_editor_provider: Callable[[], ContinuumEditor | None]
    dock_coordinator_provider: Callable[[], DockLayoutCoordinator]
    current_project_provider: Callable[[], SpectroscopyProject | None]
    action_factory_provider: Callable[[], MenuActionFactory | None]
    state_changed_callback: Callable[[HistoryState], None]


class HistoryWiringCoordinator:
    """Connect the shared history bridge to current shell surfaces."""

    def __init__(self, ports: HistoryWiringPorts) -> None:
        """Store wiring dependencies."""
        self._ports = ports

    def setup(self) -> None:
        """Attach the history bridge to the current shell collaborators."""
        view_stack = self._ports.view_stack_provider()
        if view_stack is None:
            msg = "History setup requires a view stack."
            raise RuntimeError(msg)
        if view_stack.spectrum_view is None:
            msg = "History setup requires a spectrum view."
            raise RuntimeError(msg)

        presenter = view_stack.spectrum_view.coordinator
        if not isinstance(presenter, SpectrumInteractionCoordinator):
            msg = (
                "History setup requires SpectrumInteractionCoordinator, "
                f"got {type(presenter).__name__}."
            )
            raise TypeError(msg)

        history_bridge = self._ports.history_bridge
        action_factory = self._ports.action_factory_provider()
        if action_factory is None:
            msg = "History setup requires a menu action factory."
            raise RuntimeError(msg)
        action_factory.set_history_bridge(history_bridge)
        history_bridge.state_changed.connect(self._ports.state_changed_callback)
        presenter.set_history_recorder(self._ports.history_recorder)
        history_bridge.set_spectrum_range_port(presenter)

        continuum_editor = self._ports.continuum_editor_provider()
        if continuum_editor is not None:
            continuum_editor.set_history_recorder(self._ports.history_recorder)
            history_bridge.set_continuum_editor(continuum_editor)

        dock_coordinator = self._ports.dock_coordinator_provider()
        history_bridge.set_dock_layout_coordinator(dock_coordinator)

        region_detail_ui = dock_coordinator.region_detail_ui()
        if region_detail_ui is not None:
            region_detail_ui.set_history_recorder(self._ports.history_recorder)

        if dock_coordinator.optimize_editor:
            dock_coordinator.optimize_editor.set_history_recorder(self._ports.history_recorder)

        current_project = self._ports.current_project_provider()
        if current_project is not None:
            history_bridge.set_project(current_project)
