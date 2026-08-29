"""Tests for GUI shell project session coordination."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest
from PySide6.QtWidgets import QWidget
from pytest import MonkeyPatch
from pytestqt.qtbot import QtBot

from chappy.core.spectroscopy_project import SpectroscopyProject
from chappy.infrastructure.project_io_factory import create_default_project_io_usecase
from chappy.application.project_io_usecase import ProjectIOUseCase
import chappy.gui.shell.project_session_controller as project_session_controller
from chappy.gui.modes.common.analysis_navigation import AnalysisNavigationSnapshot
from chappy.gui.shell.analysis_navigation_coordinator import AnalysisNavigationCoordinator
from chappy.gui.shell.project_session_controller import ProjectSessionController
from chappy.gui.shell.project_context import (
    ProjectContextChangeReason,
    ProjectContextChanged,
    ProjectKey,
)

if TYPE_CHECKING:
    from chappy.gui.shell.main_window import MainWindow


class _ProjectSignal:
    """Small signal test double for project emissions."""

    def __init__(self) -> None:
        """Initialize callback storage."""
        self._callbacks: list[Callable[[SpectroscopyProject], None]] = []

    def connect(self, callback: Callable[[SpectroscopyProject], None]) -> None:
        """Register a callback."""
        self._callbacks.append(callback)

    def emit(self, project: SpectroscopyProject) -> None:
        """Emit a project to callbacks."""
        for callback in self._callbacks:
            callback(project)


class _VoidSignal:
    """Small signal test double for no-argument emissions."""

    def __init__(self) -> None:
        """Initialize callback storage."""
        self._callbacks: list[Callable[[], None]] = []

    def connect(self, callback: Callable[[], None]) -> None:
        """Register a callback."""
        self._callbacks.append(callback)

    def emit(self) -> None:
        """Emit to callbacks."""
        for callback in self._callbacks:
            callback()


class _MessageSignal:
    """Small signal test double for status message emissions."""

    def __init__(self) -> None:
        """Initialize callback storage."""
        self._callbacks: list[Callable[[str], None]] = []

    def connect(self, callback: Callable[[str], None]) -> None:
        """Register a callback."""
        self._callbacks.append(callback)

    def emit(self, message: str) -> None:
        """Emit a status message to callbacks."""
        for callback in self._callbacks:
            callback(message)


class _ProjectPathSignal:
    """Small signal test double for project file path emissions."""

    def __init__(self) -> None:
        """Initialize callback storage."""
        self._callbacks: list[Callable[[str | None], None]] = []

    def connect(self, callback: Callable[[str | None], None]) -> None:
        """Register a callback."""
        self._callbacks.append(callback)

    def emit(self, path: str | None) -> None:
        """Emit a path to callbacks."""
        for callback in self._callbacks:
            callback(path)


class _ProjectFileCoordinatorSpy:
    """Project file coordinator test double."""

    last_instance: _ProjectFileCoordinatorSpy | None = None

    def __init__(self, _main_window: MainWindow, *, project_io: ProjectIOUseCase) -> None:
        """Initialize spy state and fake signals."""
        type(self).last_instance = self
        self.project_created = _ProjectSignal()
        self.project_loaded = _ProjectSignal()
        self.project_saved = _VoidSignal()
        self.project_path_recorded = _ProjectPathSignal()
        self.status_message = _MessageSignal()
        self.calls: list[str] = []
        self.save_as_result = True

    def open_observation_data(self) -> None:
        """Record observation-data project creation dispatch."""
        self.calls.append("open_observation_data")

    def open_project(self) -> None:
        """Record project open dispatch."""
        self.calls.append("open_project")

    def save_project(self, project: SpectroscopyProject | None) -> bool:
        """Record project save dispatch."""
        self.calls.append(f"save_project:{project.name if project else 'none'}")
        return project is not None

    def save_project_as(self, project: SpectroscopyProject | None) -> bool:
        """Record save-as dispatch."""
        self.calls.append(f"save_project_as:{project.name if project else 'none'}")
        return project is not None and self.save_as_result

    def check_save_current_project(self, *, reason: str = "generic") -> bool:
        """Record save prompt checks."""
        self.calls.append(f"check_save_current_project:{reason}")
        return True


class _NavigationSettings:
    """Minimal settings port for project-switch rollback integration."""

    def load(self, _key: ProjectKey) -> AnalysisNavigationSnapshot | None:
        return None

    def save(self, _key: ProjectKey, _snapshot: AnalysisNavigationSnapshot) -> None:
        return None

    def migrate(
        self, _old_key: ProjectKey, _new_key: ProjectKey, _snapshot: AnalysisNavigationSnapshot
    ) -> None:
        return None


def test_project_session_controller_routes_file_lifecycle_actions(
    monkeypatch: MonkeyPatch, qtbot: QtBot
) -> None:
    """Verify project file lifecycle actions are owned by the shell coordinator."""
    monkeypatch.setattr(
        project_session_controller, "ProjectFileCoordinator", _ProjectFileCoordinatorSpy
    )
    main_window = QWidget()
    qtbot.addWidget(main_window)
    refreshed: list[SpectroscopyProject | None] = []
    coordinator = ProjectSessionController(
        cast("MainWindow", main_window),
        project_io=create_default_project_io_usecase(),
        refresh_callback=refreshed.append,
    )
    coordinator.setup_project_handling()
    project = SpectroscopyProject(name="session-test")
    coordinator.set_current_project(project)

    coordinator.open_observation_data()
    coordinator.open_project()
    coordinator.save_project()
    coordinator.save_project_as()
    coordinator.close_project()

    handler = _ProjectFileCoordinatorSpy.last_instance
    assert handler is not None
    assert handler.calls == [
        "open_observation_data",
        "open_project",
        "save_project:session-test",
        "save_project_as:session-test",
        "check_save_current_project:close",
    ]
    assert refreshed == [None]


def test_project_session_controller_buffers_project_until_matching_path(
    monkeypatch: MonkeyPatch, qtbot: QtBot, tmp_path: Path
) -> None:
    """Project activation should wait until its matching path context is available."""
    monkeypatch.setattr(
        project_session_controller, "ProjectFileCoordinator", _ProjectFileCoordinatorSpy
    )
    main_window = QWidget()
    qtbot.addWidget(main_window)
    refreshed: list[SpectroscopyProject | None] = []
    coordinator = ProjectSessionController(
        cast("MainWindow", main_window),
        project_io=create_default_project_io_usecase(),
        refresh_callback=refreshed.append,
    )
    coordinator.setup_project_handling()

    created = SpectroscopyProject(name="created")
    loaded = SpectroscopyProject(name="loaded")
    handler = _ProjectFileCoordinatorSpy.last_instance
    assert handler is not None

    handler.project_created.emit(created)
    assert refreshed == []
    handler.project_path_recorded.emit(None)
    handler.project_loaded.emit(loaded)
    assert refreshed == [created]
    loaded_path = tmp_path / "loaded.h5"
    loaded_path.touch()
    handler.project_path_recorded.emit(str(loaded_path))

    assert refreshed == [created, loaded]


def test_project_context_is_published_after_project_and_path_are_applied(
    monkeypatch: MonkeyPatch, qtbot: QtBot, tmp_path: Path
) -> None:
    """Observers must never see a new project paired with the previous path."""
    monkeypatch.setattr(
        project_session_controller, "ProjectFileCoordinator", _ProjectFileCoordinatorSpy
    )
    main_window = QWidget()
    qtbot.addWidget(main_window)
    observations: list[tuple[str, object, object]] = []
    coordinator: ProjectSessionController

    def refresh(project: SpectroscopyProject | None) -> None:
        observations.append(
            ("refresh", coordinator.current_project, coordinator.project_file_path)
        )
        assert coordinator.current_project is project

    coordinator = ProjectSessionController(
        cast("MainWindow", main_window),
        project_io=create_default_project_io_usecase(),
        refresh_callback=refresh,
    )
    coordinator.project_context_changing.connect(
        lambda: observations.append(
            ("changing", coordinator.current_project, coordinator.project_file_path)
        )
    )
    coordinator.project_context_changed.connect(
        lambda event: observations.append(
            ("changed", event.project, coordinator.project_file_path)
        )
    )
    coordinator.setup_project_handling()
    handler = _ProjectFileCoordinatorSpy.last_instance
    assert handler is not None
    project = SpectroscopyProject(name="ordered")
    path = str(tmp_path / "ordered.h5")
    Path(path).touch()

    handler.project_loaded.emit(project)
    assert observations == []
    handler.project_path_recorded.emit(path)

    assert observations == [
        ("changing", None, None),
        ("refresh", project, path),
        ("changed", project, path),
    ]
    assert coordinator.project_key == ProjectKey.for_saved_path(path)


def test_save_as_rekeys_context_only_after_path_is_recorded(qtbot: QtBot, tmp_path: Path) -> None:
    """A successful Save As path event should atomically replace the local key."""
    main_window = QWidget()
    qtbot.addWidget(main_window)
    coordinator = ProjectSessionController(
        cast("MainWindow", main_window),
        project_io=create_default_project_io_usecase(),
        refresh_callback=lambda _project: None,
    )
    project = SpectroscopyProject(name="save-as")
    coordinator.switch_project(project)
    original_key = coordinator.project_key
    events: list[ProjectContextChanged] = []
    coordinator.project_context_changed.connect(events.append)

    new_path = str(tmp_path / "save-as.h5")
    Path(new_path).touch()
    coordinator._on_project_path_recorded(new_path)

    assert original_key is not None and original_key.persistent is False
    assert coordinator.project_key == ProjectKey.for_saved_path(new_path)
    assert events == [
        ProjectContextChanged(
            project=project,
            old_key=original_key,
            new_key=ProjectKey.for_saved_path(new_path),
            old_path=None,
            new_path=new_path,
            reason=ProjectContextChangeReason.SAVE_AS,
        )
    ]


def test_failed_save_as_without_path_event_leaves_context_unchanged(
    monkeypatch: MonkeyPatch, qtbot: QtBot, tmp_path: Path
) -> None:
    """A cancelled or failed Save As must not alter the project path or local key."""
    monkeypatch.setattr(
        project_session_controller, "ProjectFileCoordinator", _ProjectFileCoordinatorSpy
    )
    main_window = QWidget()
    qtbot.addWidget(main_window)
    coordinator = ProjectSessionController(
        cast("MainWindow", main_window),
        project_io=create_default_project_io_usecase(),
        refresh_callback=lambda _project: None,
    )
    coordinator.setup_project_handling()
    project = SpectroscopyProject(name="save-as-failure")
    old_path = str(tmp_path / "original.h5")
    Path(old_path).touch()
    coordinator.switch_project(project, path=old_path, reason=ProjectContextChangeReason.OPEN)
    old_key = coordinator.project_key
    events: list[ProjectContextChanged] = []
    coordinator.project_context_changed.connect(events.append)
    handler = _ProjectFileCoordinatorSpy.last_instance
    assert handler is not None
    handler.save_as_result = False

    coordinator.save_project_as()

    assert coordinator.project_file_path == old_path
    assert coordinator.project_key == old_key
    assert events == []


def test_save_as_context_failure_restores_path_key_and_releases_consumers(
    qtbot: QtBot, tmp_path: Path
) -> None:
    """A failing Save As title update publishes only the reverse context."""
    main_window = QWidget()
    qtbot.addWidget(main_window)
    coordinator = ProjectSessionController(
        cast("MainWindow", main_window),
        project_io=create_default_project_io_usecase(),
        refresh_callback=lambda _project: None,
    )
    project = SpectroscopyProject(name="save-as-atomic")
    old_path = tmp_path / "old-save-as.h5"
    new_path = tmp_path / "new-save-as.h5"
    old_path.touch()
    new_path.touch()
    coordinator.switch_project(project, path=str(old_path), reason=ProjectContextChangeReason.OPEN)
    old_key = coordinator.project_key
    title_calls = [0]

    def update_title() -> None:
        title_calls[0] += 1
        if title_calls[0] == 1:
            raise RuntimeError("injected title failure")

    coordinator.set_window_title_update_callback(update_title)
    order: list[str] = []
    coordinator.project_context_changing.connect(lambda: order.append("changing"))
    coordinator.project_context_aborted.connect(lambda _event: order.append("aborted"))
    coordinator.project_context_changed.connect(lambda _event: order.append("changed"))

    with pytest.raises(RuntimeError, match="injected title failure"):
        coordinator._on_project_path_recorded(str(new_path))

    assert coordinator.current_project is project
    assert coordinator.project_file_path == str(old_path)
    assert coordinator.project_key == old_key
    assert order == ["changing", "aborted", "changed"]


def test_project_session_controller_records_and_clears_project_file_path(
    monkeypatch: MonkeyPatch, qtbot: QtBot
) -> None:
    """Verify the session records the coordinator-reported path and clears it on close."""
    monkeypatch.setattr(
        project_session_controller, "ProjectFileCoordinator", _ProjectFileCoordinatorSpy
    )
    main_window = QWidget()
    qtbot.addWidget(main_window)
    coordinator = ProjectSessionController(
        cast("MainWindow", main_window),
        project_io=create_default_project_io_usecase(),
        refresh_callback=lambda _project: None,
    )
    coordinator.setup_project_handling()
    handler = _ProjectFileCoordinatorSpy.last_instance
    assert handler is not None

    handler.project_path_recorded.emit("/tmp/project.h5")
    assert coordinator.project_file_path == "/tmp/project.h5"

    project = SpectroscopyProject(name="active")
    coordinator.set_current_project(project)
    coordinator.close_project()

    assert coordinator.project_file_path is None


def test_project_session_controller_updates_current_project_and_title(qtbot: QtBot) -> None:
    """Verify project switching uses the single project refresh entrypoint."""
    main_window = QWidget()
    qtbot.addWidget(main_window)
    refreshed: list[SpectroscopyProject | None] = []
    title_updates: list[str] = []
    coordinator = ProjectSessionController(
        cast("MainWindow", main_window),
        project_io=create_default_project_io_usecase(),
        refresh_callback=refreshed.append,
    )
    coordinator.set_window_title_update_callback(lambda: title_updates.append("updated"))
    project = SpectroscopyProject(name="active")

    coordinator.switch_project(project)
    coordinator.emit_project_changed(project)

    assert refreshed == [project]
    assert coordinator.current_project is project
    assert title_updates == ["updated"]


def test_refresh_failure_rolls_back_session_and_releases_navigation_switch(
    qtbot: QtBot, tmp_path: Path
) -> None:
    """A failed activation publishes a reverse context after restoring all owners."""
    main_window = QWidget()
    qtbot.addWidget(main_window)
    old_project = SpectroscopyProject(name="old")
    new_project = SpectroscopyProject(name="new")
    old_path = tmp_path / "old.h5"
    new_path = tmp_path / "new.h5"
    old_path.touch()
    new_path.touch()
    order: list[str] = []
    entered_modes: list[object] = []
    coordinator: ProjectSessionController

    navigation = AnalysisNavigationCoordinator(
        settings=_NavigationSettings(), enter_mode=entered_modes.append
    )

    def refresh(project: SpectroscopyProject | None) -> None:
        name = "none" if project is None else project.name
        order.append(f"refresh:{name}")
        if project is new_project:
            assert coordinator.current_project is new_project
            assert coordinator.project_file_path == str(new_path)
            assert navigation._context_switching is True
            assert len(entered_modes) == 1
            raise RuntimeError("injected refresh failure")
        assert coordinator.current_project is old_project
        assert coordinator.project_file_path == str(old_path)

    coordinator = ProjectSessionController(
        cast("MainWindow", main_window),
        project_io=create_default_project_io_usecase(),
        refresh_callback=refresh,
    )
    coordinator.project_context_changing.connect(
        lambda: (order.append("changing"), navigation.handle_project_context_changing())
    )
    coordinator.project_context_aborted.connect(lambda _event: order.append("aborted"))
    coordinator.project_context_changed.connect(
        lambda event: (
            order.append(f"changed:{event.project.name}"),
            navigation.handle_project_context_changed(event),
        )
    )
    coordinator.switch_project(
        old_project, path=str(old_path), reason=ProjectContextChangeReason.OPEN
    )
    old_key = coordinator.project_key
    order.clear()

    with pytest.raises(RuntimeError, match="injected refresh failure"):
        coordinator.switch_project(
            new_project, path=str(new_path), reason=ProjectContextChangeReason.OPEN
        )

    assert coordinator.current_project is old_project
    assert coordinator.project_file_path == str(old_path)
    assert coordinator.project_key == old_key
    assert navigation._context_switching is False
    assert order == ["changing", "refresh:new", "refresh:old", "aborted", "changed:old"]
    assert len(entered_modes) == 2
