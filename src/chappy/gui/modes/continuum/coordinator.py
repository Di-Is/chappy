"""Continuum component coordination and interactive editing for main window."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtWidgets import QMessageBox, QWidget

from chappy.application.continuum import ContinuumComponentMutationUseCase
from chappy.core.components.continuum import ContinuumComponent
from chappy.core.editing_mode import EditingMode
from chappy.gui.modes.continuum.controllers.point_controller import (
    ContinuumPointMutationController,
    ContinuumPointMutationPorts,
)
from chappy.gui.modes.continuum.controllers.preview_controller import (
    ContinuumPreviewController,
    ContinuumPreviewPorts,
)
from chappy.gui.modes.continuum.history_adapter import ContinuumHistoryAdapter
from chappy.gui.modes.continuum.plot_adapter import (
    ContinuumPlotAdapter,
    ContinuumPlotAdapterPorts,
    ContinuumViewStackPort,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from collections.abc import Callable

    from chappy.core.spectroscopy_project import SpectroscopyProject
    from chappy.gui.modes.continuum.editor import ContinuumHistoryRecorder
    from chappy.presentation.interaction.interaction_contracts import (
        ContinuumContext,
        InteractionStateSnapshot,
    )


class ContinuumComponentSignal(Protocol):
    """Signal carrying a continuum component."""

    def connect(self, slot: Callable[[ContinuumComponent], None], /) -> None:
        """Connect a component slot."""
        ...


class ContinuumEditorPort(Protocol):
    """Continuum editor endpoint required by the coordinator."""

    component_added: ContinuumComponentSignal

    def get_current_continuum(self) -> ContinuumComponent | None:
        """Return the active continuum component."""
        ...

    def refresh_anchor_points_table(self) -> None:
        """Refresh the continuum side-panel point table."""
        ...


class ContinuumModeStatePort(Protocol):
    """Mode state endpoint required by continuum visualization."""

    current_mode: EditingMode | None


@runtime_checkable
class ContinuumCoordinatorShell(Protocol):
    """Shell collaborators required by the continuum workflow coordinator."""

    current_project: SpectroscopyProject | None
    view_stack: ContinuumViewStackPort | None
    continuum_editor: ContinuumEditorPort | None
    mode_state_store: ContinuumModeStatePort | None
    continuum_history_recorder: ContinuumHistoryRecorder | None


class ContinuumCoordinator(QObject):
    """Manages continuum component operations and interactive editing.

    This class handles all continuum-related functionality including
    creation, parameter management, and interactive plot editing.
    """

    # Signals
    status_message = Signal(str)  # message

    def __init__(
        self, main_window: ContinuumCoordinatorShell, message_parent: QWidget | None = None
    ) -> None:
        """Initialize continuum coordinator.

        Args:
            main_window: Shell endpoint that owns the continuum workflow.
            message_parent: Optional widget used as the parent for modal messages.
        """
        super().__init__()
        self.main_window = main_window
        self._message_parent = message_parent
        self._history_adapter = ContinuumHistoryAdapter(
            recorder_provider=lambda: self.main_window.continuum_history_recorder
        )
        self._component_mutations = ContinuumComponentMutationUseCase()
        self._plot_adapter = ContinuumPlotAdapter(
            ContinuumPlotAdapterPorts(
                project_provider=lambda: self.main_window.current_project,
                view_stack_provider=lambda: self.main_window.view_stack,
                table_refresh_callback=self._refresh_anchor_points_table,
            )
        )
        self._preview_controller = ContinuumPreviewController(
            ContinuumPreviewPorts(
                project_provider=lambda: self.main_window.current_project,
                preview_display_callback=self._plot_adapter.update_preview,
            )
        )
        self._point_mutation_controller = ContinuumPointMutationController(
            ContinuumPointMutationPorts(
                project_provider=lambda: self.main_window.current_project,
                continuum_provider=self._current_continuum,
                history=self._history_adapter,
                preview_callback=self._preview_controller.update_preview,
                refresh_callback=self._plot_adapter.refresh_display,
                error_callback=self.status_message.emit,
            )
        )

    def setup_continuum_signals(self) -> None:
        """Setup signal connections for continuum management."""
        if self.main_window.continuum_editor:
            # Connect continuum editor signals
            self.main_window.continuum_editor.component_added.connect(self._on_continuum_added)

            logger.info("Continuum signals connected successfully")

        # Connect to spectrum presenter for snapshot-based continuum editing
        self._connect_presenter_snapshots()

    def add_continuum(self) -> None:
        """Add a new continuum component."""
        current_project = self.main_window.current_project
        if not current_project:
            return

        try:
            n_continua = sum(
                isinstance(component, ContinuumComponent)
                for component in current_project.model.components
            )
            result = self._component_mutations.add_component(
                current_project,
                name=f"Continuum {n_continua + 1}",
                points=[],
                record_history=self._history_adapter.record_add_component,
                history_scope=self._history_adapter.atomic_recording,
            )
            if not result.impact.changed:
                return
            self.status_message.emit("Added continuum component")
            logger.info("Added continuum component")

        except Exception as e:
            QMessageBox.warning(
                self._message_parent, "Error Adding Continuum", f"Could not add continuum:\n{e}"
            )
            logger.exception("Failed to add continuum")

    @Slot(ContinuumComponent)
    def _on_continuum_added(self, continuum: ContinuumComponent) -> None:
        """Handle continuum component addition.

        Args:
            continuum: Added continuum component
        """
        self.status_message.emit(f"Added continuum: {continuum.name}")
        logger.info("Continuum added: %s", continuum.name)

        # Emit signal for external listeners

    @Slot(ContinuumComponent)
    def on_continuum_updated(self, continuum: ContinuumComponent) -> None:
        """Handle continuum updates for visualization updates.

        Args:
            continuum: Updated continuum component
        """
        # Update visualization if needed
        mode_state_store = self.main_window.mode_state_store
        current_mode = mode_state_store.current_mode if mode_state_store else None
        if current_mode is not None:
            self._update_continuum_visualization(current_mode)

        # Refresh display data (plot curve and side panel table)
        if current_mode == EditingMode.CONTINUUM:
            self._plot_adapter.refresh_display(continuum)

    def _update_continuum_visualization(self, mode: EditingMode) -> None:
        """Update continuum visualization based on current mode.

        Args:
            mode: Current editing mode
        """
        self._plot_adapter.update_visibility(mode)

    def update_continuum_visualization(self, mode: EditingMode) -> None:
        """Update continuum visualization based on current mode.

        Args:
            mode: Current editing mode
        """
        self._plot_adapter.apply_mode_visualization(mode)

    def set_continuum_visible(self, visible: bool) -> None:
        """Show or hide continuum visualization without a non-active sentinel."""
        self._plot_adapter.apply_mode_visualization(
            EditingMode.CONTINUUM if visible else EditingMode.ANALYSIS
        )

    def _connect_presenter_snapshots(self) -> None:
        """Connect to spectrum presenter for snapshot-based continuum editing."""
        view_stack = self.main_window.view_stack
        if not view_stack:
            return

        spectrum_view = view_stack.spectrum_view
        if not spectrum_view:
            return

        # Connect to interaction snapshot signal
        spectrum_view.coordinator.interaction_snapshot_applied.connect(self._on_continuum_snapshot)

    def _on_continuum_snapshot(self, snapshot: InteractionStateSnapshot[ContinuumContext]) -> None:
        """Handle continuum editing snapshot from interaction state controller.

        Args:
            snapshot: Snapshot describing the current continuum editing state.
        """
        self._point_mutation_controller.apply_snapshot(snapshot)

    def _current_continuum(self) -> ContinuumComponent | None:
        """Return the currently selected continuum component."""
        continuum_editor = self.main_window.continuum_editor
        if continuum_editor is None:
            return None
        return continuum_editor.get_current_continuum()

    def _refresh_anchor_points_table(self) -> None:
        """Refresh the continuum side-panel point table."""
        continuum_editor = self.main_window.continuum_editor
        if continuum_editor:
            continuum_editor.refresh_anchor_points_table()
