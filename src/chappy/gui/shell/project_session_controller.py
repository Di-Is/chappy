"""Coordinate project session lifecycle for the GUI shell."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Literal
from weakref import WeakKeyDictionary

from PySide6.QtCore import QObject, Signal

from chappy.core.spectroscopy_project import SpectroscopyProject
from chappy.gui.shell.project_context import (
    ProjectContextChanged,
    ProjectContextChangeReason,
    ProjectKey,
    ProjectPathCanonicalizationError,
)
from chappy.gui.shell.project_file_coordinator import ProjectFileCoordinator

if TYPE_CHECKING:
    from collections.abc import Callable

    from PySide6.QtGui import QDragEnterEvent, QDropEvent

    from chappy.application.project_io_usecase import ProjectIOUseCase
    from chappy.gui.shell.main_window import MainWindow

logger = logging.getLogger(__name__)

SavePromptReason = Literal["generic", "close", "shutdown"]


class ProjectSessionController(QObject):
    """Coordinate project lifecycle actions through a single shell entrypoint."""

    project_changed = Signal(SpectroscopyProject)
    project_context_changing = Signal()
    project_context_changed = Signal(object)  # ProjectContextChanged
    project_context_aborted = Signal(object)  # ProjectContextChanged rollback
    status_message = Signal(str, int)

    def __init__(
        self,
        main_window: MainWindow,
        *,
        project_io: ProjectIOUseCase,
        refresh_callback: Callable[[SpectroscopyProject | None], None],
    ) -> None:
        """Initialize the project session coordinator.

        Args:
            main_window: The application shell that owns the project session.
            project_io: Project I/O use case used by file I/O operations.
            refresh_callback: Callback that preserves current UI refresh order.
        """
        super().__init__(main_window)
        self._main_window = main_window
        self._project_io = project_io
        self._refresh_callback = refresh_callback
        self._current_project: SpectroscopyProject | None = None
        self._project_file_path: str | None = None
        self._project_key: ProjectKey | None = None
        self._session_project_keys: WeakKeyDictionary[SpectroscopyProject, ProjectKey] = (
            WeakKeyDictionary()
        )
        self._pending_project_activation: (
            tuple[SpectroscopyProject, ProjectContextChangeReason] | None
        ) = None
        self._project_file_coordinator: ProjectFileCoordinator | None = None
        self._window_title_update_callback: Callable[[], None] | None = None

    @property
    def current_project(self) -> SpectroscopyProject | None:
        """Return the active project."""
        return self._current_project

    @property
    def project_file_path(self) -> str | None:
        """Return the file path recorded for the active project, if any."""
        return self._project_file_path

    @property
    def project_key(self) -> ProjectKey | None:
        """Return the local UI restoration key for the active project."""
        return self._project_key

    def set_project_file_path(self, path: str | None) -> None:
        """Record the file path associated with the active project.

        Args:
            path: File path to record, or None when the project has no file yet.
        """
        self._project_file_path = path

    def set_window_title_update_callback(self, callback: Callable[[], None]) -> None:
        """Set the callback used when the project title state changes.

        Args:
            callback: Function to call when the window title needs updating.
        """
        self._window_title_update_callback = callback

    def setup_project_handling(self) -> None:
        """Create and connect the project file operation owner."""
        self._project_file_coordinator = ProjectFileCoordinator(
            self._main_window, project_io=self._project_io
        )
        self._connect_project_file_signals()

    def open_observation_data(self) -> None:
        """Dispatch observation-data project creation."""
        self._project_file_coordinator_or_raise().open_observation_data()

    def open_sample_data(self, flux_path: str, error_path: str, *, resolving_power: float) -> None:
        """Dispatch sample-data project creation.

        Args:
            flux_path: Path to the sample flux spectrum.
            error_path: Path to the sample error spectrum.
            resolving_power: Known instrumental resolving power of the sample.
        """
        self._project_file_coordinator_or_raise().open_sample_data(
            flux_path, error_path, resolving_power=resolving_power
        )

    def open_project(self) -> None:
        """Dispatch project opening."""
        self._project_file_coordinator_or_raise().open_project()

    def save_project(self) -> None:
        """Save the active project."""
        self._project_file_coordinator_or_raise().save_project(self.current_project)

    def save_project_as(self) -> None:
        """Save the active project with a new path."""
        self._project_file_coordinator_or_raise().save_project_as(self.current_project)

    def close_project(self) -> None:
        """Close the active project after offering to save changes."""
        if self.current_project is None:
            logger.debug("No project to close")
            return

        if not self.check_save_current_project(reason="close"):
            logger.debug("User cancelled project close")
            return

        self.switch_project(None, reason=ProjectContextChangeReason.CLOSE)
        self.status_message.emit(self.tr("Project closed"), 2000)

    def switch_project(
        self,
        project: SpectroscopyProject | None,
        *,
        path: str | None = None,
        reason: ProjectContextChangeReason | None = None,
    ) -> None:
        """Atomically switch project/path state and then refresh project-bound UI."""
        resolved_reason = reason
        if resolved_reason is None:
            resolved_reason = (
                ProjectContextChangeReason.CLOSE
                if project is None
                else ProjectContextChangeReason.CREATE
            )
        self._activate_project(project, path=path, reason=resolved_reason)

    def set_current_project(self, project: SpectroscopyProject | None) -> None:
        """Set the current project state.

        Args:
            project: Project to set as current, or None to clear.
        """
        self._current_project = project
        if self._window_title_update_callback is not None:
            self._window_title_update_callback()

    def emit_project_changed(self, project: SpectroscopyProject | None) -> None:
        """Notify observers that the active project changed.

        Args:
            project: Active project, or None when the shell was cleared.
        """
        self.project_changed.emit(project)

    def check_save_current_project(self, *, reason: SavePromptReason = "generic") -> bool:
        """Return whether it is safe to continue after save prompts.

        Args:
            reason: Context for triggering the save check.

        Returns:
            True when the caller may continue, otherwise False.
        """
        if self._project_file_coordinator is None:
            return True
        return self._project_file_coordinator.check_save_current_project(reason=reason)

    def handle_drag_enter_event(self, event: QDragEnterEvent) -> None:
        """Process drag enter events for project resources.

        Args:
            event: The drag enter event.
        """
        if self._project_file_coordinator is not None:
            self._project_file_coordinator.handle_drag_enter_event(event)

    def handle_drop_event(self, event: QDropEvent) -> None:
        """Process drop events for project resources.

        Args:
            event: The drop event.
        """
        if self._project_file_coordinator is not None:
            self._project_file_coordinator.handle_drop_event(event)

    def _connect_project_file_signals(self) -> None:
        """Connect project file operation signals to session actions."""
        project_file_coordinator = self._project_file_coordinator_or_raise()
        project_file_coordinator.project_created.connect(self._on_project_created)
        project_file_coordinator.project_loaded.connect(self._on_project_loaded)
        project_file_coordinator.project_saved.connect(self._on_project_saved)
        project_file_coordinator.project_path_recorded.connect(self._on_project_path_recorded)
        project_file_coordinator.status_message.connect(self._forward_status_message)

        logger.debug("Project file signals connected")

    def _project_file_coordinator_or_raise(self) -> ProjectFileCoordinator:
        """Return the project file operation owner or raise."""
        if self._project_file_coordinator is None:
            msg = "Project file handler not initialized"
            raise RuntimeError(msg)
        return self._project_file_coordinator

    def _forward_status_message(self, message: str) -> None:
        """Forward project file status messages with the shell timeout.

        Args:
            message: Status message to forward.
        """
        self.status_message.emit(message, 3000)

    def _on_project_created(self, project: SpectroscopyProject) -> None:
        """Handle project creation from file operations.

        Args:
            project: Newly created project.
        """
        self._stage_project_activation(project, ProjectContextChangeReason.CREATE)

    def _on_project_loaded(self, project: SpectroscopyProject) -> None:
        """Handle project loading from file operations.

        Args:
            project: Loaded project.
        """
        self._stage_project_activation(project, ProjectContextChangeReason.OPEN)

    def _on_project_saved(self) -> None:
        """Handle project save completion."""
        if self._window_title_update_callback is not None:
            self._window_title_update_callback()

    def _on_project_path_recorded(self, path: str | None) -> None:
        """Record the file path associated with the active project.

        Args:
            path: File path recorded by the project file operation owner.
        """
        pending = self._pending_project_activation
        if pending is not None:
            self._pending_project_activation = None
            project, reason = pending
            self._activate_project(project, path=path, reason=reason)
            return

        if self.current_project is None:
            self.set_project_file_path(path)
            return

        if path == self.project_file_path and (
            path is None or (self._project_key is not None and self._project_key.persistent)
        ):
            return
        self._rekey_current_project(path)

    def _stage_project_activation(
        self, project: SpectroscopyProject, reason: ProjectContextChangeReason
    ) -> None:
        """Wait for the matching path signal before applying a file operation."""
        if self._pending_project_activation is not None:
            message = "A project activation is already waiting for its path context"
            raise RuntimeError(message)
        self._pending_project_activation = (project, reason)

    def _activate_project(
        self,
        project: SpectroscopyProject | None,
        *,
        path: str | None,
        reason: ProjectContextChangeReason,
    ) -> None:
        """Apply a complete project context and publish it after UI refresh.

        Once ``project_context_changing`` is emitted, either the forward context
        or a typed reverse context is always published. A failed refresh restores
        session facts before refreshing the previous project, so consumers never
        observe a new project paired with an old path or navigation state.
        """
        old_project = self._current_project
        old_key = self._project_key
        old_path = self._project_file_path
        new_key = self._key_for_project(project, path, reason=reason)

        self.project_context_changing.emit()
        try:
            self.set_current_project(project)
            self.set_project_file_path(path)
            self._project_key = new_key
            self._refresh_callback(project)
        except Exception as original_error:
            rollback_event = self._rollback_project_activation(
                old_project=old_project,
                old_key=old_key,
                old_path=old_path,
                attempted_key=new_key,
                attempted_path=path,
                original_error=original_error,
            )
            self.project_context_aborted.emit(rollback_event)
            self.project_context_changed.emit(rollback_event)
            raise
        self.project_context_changed.emit(
            ProjectContextChanged(
                project=project,
                old_key=old_key,
                new_key=new_key,
                old_path=old_path,
                new_path=path,
                reason=reason,
            )
        )

    def _rollback_project_activation(
        self,
        *,
        old_project: SpectroscopyProject | None,
        old_key: ProjectKey | None,
        old_path: str | None,
        attempted_key: ProjectKey | None,
        attempted_path: str | None,
        original_error: Exception,
    ) -> ProjectContextChanged:
        """Restore exact session facts and best-effort the previous UI context."""
        self._current_project = old_project
        self._project_file_path = old_path
        self._project_key = old_key
        try:
            if self._window_title_update_callback is not None:
                self._window_title_update_callback()
            self._refresh_callback(old_project)
        except Exception as rollback_error:  # noqa: BLE001 - preserve triggering failure
            original_error.add_note(
                "Project context rollback refresh failed: "
                f"{type(rollback_error).__name__}: {rollback_error}"
            )
        return ProjectContextChanged(
            project=old_project,
            old_key=attempted_key,
            new_key=old_key,
            old_path=attempted_path,
            new_path=old_path,
            reason=(
                ProjectContextChangeReason.CLOSE
                if old_project is None
                else ProjectContextChangeReason.OPEN
            ),
        )

    def _rekey_current_project(self, path: str | None) -> None:
        """Publish a Save As context after the new path is recorded."""
        project = self.current_project
        if project is None:
            message = "Cannot re-key a project context without an active project"
            raise RuntimeError(message)

        old_key = self._project_key
        old_path = self._project_file_path
        new_key = self._key_for_project(project, path, reason=ProjectContextChangeReason.SAVE_AS)
        self.project_context_changing.emit()
        try:
            self.set_project_file_path(path)
            self._project_key = new_key
            if self._window_title_update_callback is not None:
                self._window_title_update_callback()
        except Exception as original_error:
            self._project_file_path = old_path
            self._project_key = old_key
            if self._window_title_update_callback is not None:
                try:
                    self._window_title_update_callback()
                except Exception as rollback_error:  # noqa: BLE001 - preserve original failure
                    original_error.add_note(
                        "Save As context rollback title update failed: "
                        f"{type(rollback_error).__name__}: {rollback_error}"
                    )
            rollback_event = ProjectContextChanged(
                project=project,
                old_key=new_key,
                new_key=old_key,
                old_path=path,
                new_path=old_path,
                reason=ProjectContextChangeReason.OPEN,
            )
            self.project_context_aborted.emit(rollback_event)
            self.project_context_changed.emit(rollback_event)
            raise
        self.project_context_changed.emit(
            ProjectContextChanged(
                project=project,
                old_key=old_key,
                new_key=new_key,
                old_path=old_path,
                new_path=path,
                reason=ProjectContextChangeReason.SAVE_AS,
            )
        )

    def _key_for_project(
        self,
        project: SpectroscopyProject | None,
        path: str | None,
        *,
        reason: ProjectContextChangeReason,
    ) -> ProjectKey | None:
        """Resolve a UI key without allowing local identity failure to block project use."""
        if project is None:
            return None
        if path is not None:
            try:
                return ProjectKey.for_saved_path(path)
            except (OSError, ProjectPathCanonicalizationError, ValueError):
                logger.warning(
                    "Falling back to a session-only Analysis UI key for %s (%s)",
                    path,
                    reason.value,
                    exc_info=True,
                )
                self._emit_project_key_fallback_status(reason)
        return self._session_key_for_project(project)

    def _session_key_for_project(self, project: SpectroscopyProject) -> ProjectKey:
        """Return the stable in-process UI key for one project object."""
        key = self._session_project_keys.get(project)
        if key is None:
            key = ProjectKey.for_unsaved_session()
            self._session_project_keys[project] = key
        return key

    def _emit_project_key_fallback_status(self, reason: ProjectContextChangeReason) -> None:
        """Explain a non-fatal local view-state identity failure."""
        if reason is ProjectContextChangeReason.OPEN:
            message = self.tr(
                "Previous Analysis view settings could not be restored. Overview is shown; project data is unchanged."
            )
        else:
            message = self.tr(
                "Analysis view settings could not be saved for this file. You can keep working; project data is unchanged, but this view may not be restored next time."
            )
        self.status_message.emit(message, 5000)
