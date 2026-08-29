"""Tests for project-scoped Analysis navigation coordination."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QWidget
from pytest import MonkeyPatch

from chappy.application.project_io_usecase import ProjectIOUseCase
from chappy.core.absorption.models import AbsorptionLine, AbsorptionRegion
from chappy.core.analysis import AnalysisReadiness
from chappy.core.editing_mode import EditingMode
from chappy.core.spectroscopy_project import SpectroscopyProject
from chappy.gui.modes.common.analysis_navigation import (
    AnalysisNavigationPersistenceIssue,
    AnalysisNavigationPersistenceOperation,
    AnalysisNavigationSettingsError,
    AnalysisNavigationSnapshot,
    AnalysisNavigationState,
    AnalysisSurface,
    StructureSelectionIds,
)
from chappy.gui.adapters.analysis_navigation_settings import QSettingsAnalysisNavigationAdapter
from chappy.gui.modes.common import project_key as project_key_module
from chappy.gui.modes.common.project_key import ProjectKey, ProjectPathCanonicalizationError
from chappy.gui.shell.analysis_navigation_coordinator import AnalysisNavigationCoordinator
from chappy.gui.shell.display_menu_controller import DisplayMenuController
from chappy.gui.shell.project_context import ProjectContextChangeReason, ProjectContextChanged
from chappy.gui.shell.project_session_controller import ProjectSessionController
from chappy.infrastructure.project_io_factory import create_default_project_io_usecase
from chappy.presentation.spectrum import SpectrumDisplayOptions

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot

    from chappy.gui.shell.main_window import MainWindow


@dataclass
class _Settings:
    snapshots: dict[ProjectKey, AnalysisNavigationSnapshot] = field(default_factory=dict)
    saved: list[ProjectKey] = field(default_factory=list)
    migrations: list[tuple[ProjectKey, ProjectKey]] = field(default_factory=list)
    fail_load: bool = False
    fail_save: bool = False
    fail_migrate: bool = False

    def load(self, key: ProjectKey) -> AnalysisNavigationSnapshot | None:
        if self.fail_load:
            raise AnalysisNavigationSettingsError("injected load failure")
        return self.snapshots.get(key)

    def save(self, key: ProjectKey, snapshot: AnalysisNavigationSnapshot) -> None:
        if self.fail_save:
            raise AnalysisNavigationSettingsError("injected save failure")
        self.snapshots[key] = snapshot
        self.saved.append(key)

    def migrate(
        self, old_key: ProjectKey, new_key: ProjectKey, snapshot: AnalysisNavigationSnapshot
    ) -> None:
        if self.fail_migrate:
            raise AnalysisNavigationSettingsError("injected migrate failure")
        self.snapshots[new_key] = snapshot
        self.snapshots.pop(old_key, None)
        self.migrations.append((old_key, new_key))


class _SyncFailureSwitch:
    """Shared script failing every sync once armed."""

    def __init__(self) -> None:
        self.armed = False


class _SwitchedSettings(QSettings):
    """INI-backed QSettings double persisting normally while reporting scripted failures.

    The adapter retries a reported failure on factory-built fresh instances, so
    the switch is shared across the primary settings and every factory product.
    """

    def __init__(self, path: Path, switch: _SyncFailureSwitch) -> None:
        super().__init__(str(path), QSettings.Format.IniFormat)
        self._switch = switch
        self._last_sync_failed = False

    def sync(self) -> None:
        super().sync()
        self._last_sync_failed = self._switch.armed

    def status(self) -> QSettings.Status:
        if self._last_sync_failed:
            return QSettings.Status.AccessError
        return QSettings.Status.NoError


def _project(*region_ids: str) -> SpectroscopyProject:
    project = SpectroscopyProject(name="navigation")
    for index, region_id in enumerate(region_ids):
        line_id = f"line-{index + 1}"
        project.absorption_lines[line_id] = AbsorptionLine(
            line_id=line_id,
            species="H I",
            rest_wavelength=1215.67,
            center_z=1.0,
            window_kms=150.0,
            multiplet_label="Ly alpha",
            transition_name="Ly alpha",
            oscillator_strength=0.1,
            gamma_value=1e8,
            region_id=region_id,
        )
        project.absorption_regions[region_id] = AbsorptionRegion(
            region_id=region_id, line_ids=[line_id]
        )
    return project


def _project_key(path: Path) -> ProjectKey:
    """Create a saved-project file and return its persistent UI key."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    return ProjectKey.for_saved_path(path)


def _event(
    *,
    project: SpectroscopyProject | None,
    key: ProjectKey | None,
    reason: ProjectContextChangeReason,
    old_key: ProjectKey | None = None,
) -> ProjectContextChanged:
    return ProjectContextChanged(
        project=project,
        old_key=old_key,
        new_key=key,
        old_path=None,
        new_path="/tmp/project.h5" if key is not None and key.persistent else None,
        reason=reason,
    )


def _coordinator(settings: _Settings) -> tuple[AnalysisNavigationCoordinator, list[EditingMode]]:
    entries: list[EditingMode] = []
    coordinator = AnalysisNavigationCoordinator(settings=settings, enter_mode=entries.append)
    return coordinator, entries


def _raise_project_path_identity_error(_path: str | Path) -> str:
    """Inject a deterministic existing-path canonicalization failure."""
    raise ProjectPathCanonicalizationError("injected path identity failure")


def test_open_restores_valid_detail_focus_and_enters_optimize(tmp_path) -> None:
    """A valid saved Detail target should project to legacy Optimize once."""
    settings = _Settings()
    key = _project_key(tmp_path / "project.h5")
    settings.snapshots[key] = AnalysisNavigationSnapshot(
        surface=AnalysisSurface.REGION_DETAIL, focused_region_id="region-2"
    )
    coordinator, entries = _coordinator(settings)
    project = _project("region-1", "region-2")

    coordinator.handle_project_context_changing()
    assert coordinator.focus_region("region-1") is False
    coordinator.handle_project_context_changed(
        _event(project=project, key=key, reason=ProjectContextChangeReason.OPEN)
    )

    assert coordinator.state.surface is AnalysisSurface.REGION_DETAIL
    assert coordinator.state.focused_region_id == "region-2"
    assert entries == [EditingMode.ANALYSIS]


def test_invalid_saved_detail_target_falls_back_to_overview(tmp_path) -> None:
    """A stale region ID must not select an arbitrary replacement region."""
    settings = _Settings()
    key = _project_key(tmp_path / "project.h5")
    settings.snapshots[key] = AnalysisNavigationSnapshot(
        surface=AnalysisSurface.REGION_DETAIL, focused_region_id="missing"
    )
    coordinator, entries = _coordinator(settings)

    coordinator.handle_project_context_changed(
        _event(project=_project("region-1"), key=key, reason=ProjectContextChangeReason.OPEN)
    )

    assert coordinator.state.surface is AnalysisSurface.OVERVIEW
    assert coordinator.state.focused_region_id is None
    assert entries == [EditingMode.ANALYSIS]


def test_focus_updates_canonical_navigation_and_persistence(tmp_path) -> None:
    """Focused region remains the single canonical Analysis selection."""
    settings = _Settings()
    key = _project_key(tmp_path / "project.h5")
    coordinator, _entries = _coordinator(settings)
    project = _project("region-1", "region-2")
    coordinator.handle_project_context_changed(
        _event(project=project, key=key, reason=ProjectContextChangeReason.OPEN)
    )

    assert coordinator.focus_region("region-1") is True
    assert coordinator.state.focused_region_id == "region-1"
    assert settings.snapshots[key].focused_region_id == "region-1"


def test_focused_region_id_reads_canonical_focus_and_clears(tmp_path) -> None:
    """`focused_region_id` mirrors the canonical state through set and clear."""
    settings = _Settings()
    key = _project_key(tmp_path / "project.h5")
    coordinator, _entries = _coordinator(settings)

    assert coordinator.focused_region_id() is None

    project = _project("region-1", "region-2")
    coordinator.handle_project_context_changed(
        _event(project=project, key=key, reason=ProjectContextChangeReason.OPEN)
    )
    assert coordinator.focused_region_id() is None

    assert coordinator.focus_region("region-1") is True
    assert coordinator.focused_region_id() == "region-1"

    assert coordinator.focus_region("region-2") is True
    assert coordinator.focused_region_id() == "region-2"

    coordinator.clear_focus_if("region-2")
    assert coordinator.focused_region_id() is None


def test_clear_focus_if_returns_to_overview_and_emits_surface_changed(tmp_path) -> None:
    """Clearing focus while in Detail must also emit the surface change (P1 addendum)."""
    settings = _Settings()
    key = _project_key(tmp_path / "project.h5")
    coordinator, _entries = _coordinator(settings)
    project = _project("region-1")
    coordinator.handle_project_context_changed(
        _event(project=project, key=key, reason=ProjectContextChangeReason.OPEN)
    )
    assert coordinator.focus_region("region-1") is True
    coordinator.set_surface(AnalysisSurface.REGION_DETAIL)

    surfaces: list[AnalysisSurface] = []
    focused: list[object] = []
    coordinator.surface_changed.connect(surfaces.append)
    coordinator.focused_region_changed.connect(focused.append)

    coordinator.clear_focus_if("region-1")

    assert coordinator.state.surface is AnalysisSurface.OVERVIEW
    assert coordinator.focused_region_id() is None
    assert surfaces == [AnalysisSurface.OVERVIEW]
    assert focused == [None]


def test_clear_focus_only_if_clears_focus_without_touching_surface(tmp_path) -> None:
    """The panel deletion path must clear focus while leaving the surface untouched (P1)."""
    settings = _Settings()
    key = _project_key(tmp_path / "project.h5")
    coordinator, _entries = _coordinator(settings)
    project = _project("region-1")
    coordinator.handle_project_context_changed(
        _event(project=project, key=key, reason=ProjectContextChangeReason.OPEN)
    )
    assert coordinator.focus_region("region-1") is True
    coordinator.set_surface(AnalysisSurface.REGION_DETAIL)

    surfaces: list[AnalysisSurface] = []
    focused: list[object] = []
    coordinator.surface_changed.connect(surfaces.append)
    coordinator.focused_region_changed.connect(focused.append)

    coordinator.clear_focus_only_if("region-1")

    assert coordinator.state.surface is AnalysisSurface.REGION_DETAIL
    assert coordinator.focused_region_id() is None
    assert surfaces == []
    assert focused == [None]


def test_clear_focus_only_if_ignores_non_matching_region(tmp_path) -> None:
    """A mismatched region id must leave canonical focus and surface untouched."""
    settings = _Settings()
    key = _project_key(tmp_path / "project.h5")
    coordinator, _entries = _coordinator(settings)
    project = _project("region-1", "region-2")
    coordinator.handle_project_context_changed(
        _event(project=project, key=key, reason=ProjectContextChangeReason.OPEN)
    )
    assert coordinator.focus_region("region-1") is True
    coordinator.set_surface(AnalysisSurface.REGION_DETAIL)

    coordinator.clear_focus_only_if("region-2")

    assert coordinator.state.surface is AnalysisSurface.REGION_DETAIL
    assert coordinator.focused_region_id() == "region-1"


def test_close_clears_canonical_focus_and_enters_start(tmp_path) -> None:
    """Closing a project with a focused region must leave no stale canonical focus."""
    settings = _Settings()
    key = _project_key(tmp_path / "project.h5")
    coordinator, entries = _coordinator(settings)
    project = _project("region-1")
    coordinator.handle_project_context_changed(
        _event(project=project, key=key, reason=ProjectContextChangeReason.OPEN)
    )
    assert coordinator.focus_region("region-1") is True

    coordinator.handle_project_context_changing()
    coordinator.handle_project_context_changed(
        _event(project=None, key=None, old_key=key, reason=ProjectContextChangeReason.CLOSE)
    )

    assert coordinator.state == AnalysisNavigationState()
    assert coordinator.focused_region_id() is None
    assert coordinator.project_key is None
    assert coordinator._context_switching is False
    assert entries == [EditingMode.ANALYSIS, EditingMode.START]


def test_unsaved_save_as_persists_current_state_under_new_key(tmp_path) -> None:
    """Save As should copy current session state into persistent settings."""
    settings = _Settings()
    coordinator, entries = _coordinator(settings)
    project = _project("region-1")
    session_key = ProjectKey.for_unsaved_session()
    coordinator.handle_project_context_changed(
        _event(project=project, key=session_key, reason=ProjectContextChangeReason.CREATE)
    )
    assert coordinator.focus_region("region-1") is True
    coordinator.set_surface(AnalysisSurface.REGION_DETAIL)
    saved_key = _project_key(tmp_path / "saved.h5")

    coordinator.handle_project_context_changing()
    coordinator.handle_project_context_changed(
        _event(
            project=project,
            key=saved_key,
            old_key=session_key,
            reason=ProjectContextChangeReason.SAVE_AS,
        )
    )

    assert settings.snapshots[saved_key].focused_region_id == "region-1"
    assert settings.snapshots[saved_key].surface is AnalysisSurface.REGION_DETAIL
    assert entries == [EditingMode.IDENTIFY]


def test_surface_updates_are_explicit_and_do_not_switch_top_level_mode() -> None:
    """Surface changes remain inside the single Analysis top-level mode."""
    settings = _Settings()
    coordinator, _entries = _coordinator(settings)
    project = _project("region-1")
    key = ProjectKey.for_unsaved_session()
    coordinator.handle_project_context_changed(
        _event(project=project, key=key, reason=ProjectContextChangeReason.CREATE)
    )

    assert coordinator.state.surface is AnalysisSurface.OVERVIEW
    assert coordinator.focus_region("region-1") is True
    coordinator.set_surface(AnalysisSurface.REGION_DETAIL)
    assert coordinator.state.surface is AnalysisSurface.REGION_DETAIL


def test_saved_project_revisit_prefers_same_session_navigation_state(tmp_path) -> None:
    """A same-process revisit should take precedence over an older persistent payload."""
    settings = _Settings()
    first_key = _project_key(tmp_path / "first.h5")
    second_key = _project_key(tmp_path / "second.h5")
    first_project = _project("region-1")
    coordinator, _entries = _coordinator(settings)
    coordinator.handle_project_context_changed(
        _event(project=first_project, key=first_key, reason=ProjectContextChangeReason.OPEN)
    )
    assert coordinator.focus_region("region-1") is True
    coordinator.set_surface(AnalysisSurface.REGION_DETAIL)
    coordinator._state = replace(
        coordinator.state, structure_selection=StructureSelectionIds(region_ids=("region-1",))
    )

    coordinator.handle_project_context_changed(
        _event(
            project=_project("region-2"),
            key=second_key,
            old_key=first_key,
            reason=ProjectContextChangeReason.OPEN,
        )
    )
    settings.snapshots[first_key] = AnalysisNavigationSnapshot()

    coordinator.handle_project_context_changed(
        _event(
            project=first_project,
            key=first_key,
            old_key=second_key,
            reason=ProjectContextChangeReason.OPEN,
        )
    )

    assert coordinator.state.surface is AnalysisSurface.REGION_DETAIL
    assert coordinator.state.focused_region_id == "region-1"
    assert coordinator.state.structure_selection.region_ids == ("region-1",)


def test_same_path_new_project_object_restores_only_persistent_subset(tmp_path) -> None:
    """Reloading one path into a new object must not restore transient selections."""
    settings = _Settings()
    first_key = _project_key(tmp_path / "first.h5")
    second_key = _project_key(tmp_path / "second.h5")
    first_project = _project("region-1")
    coordinator, _entries = _coordinator(settings)
    coordinator.handle_project_context_changed(
        _event(project=first_project, key=first_key, reason=ProjectContextChangeReason.OPEN)
    )
    assert coordinator.focus_region("region-1") is True
    coordinator.set_surface(AnalysisSurface.REGION_DETAIL)
    coordinator._state = replace(
        coordinator.state, structure_selection=StructureSelectionIds(region_ids=("region-1",))
    )
    coordinator.handle_project_context_changed(
        _event(
            project=_project("region-2"),
            key=second_key,
            old_key=first_key,
            reason=ProjectContextChangeReason.OPEN,
        )
    )

    reloaded_project = _project("region-1")
    coordinator.handle_project_context_changed(
        _event(
            project=reloaded_project,
            key=first_key,
            old_key=second_key,
            reason=ProjectContextChangeReason.OPEN,
        )
    )

    assert coordinator.state.surface is AnalysisSurface.REGION_DETAIL
    assert coordinator.state.focused_region_id == "region-1"
    assert coordinator.state.structure_selection == StructureSelectionIds()


def test_detail_focus_rejects_unassigned_empty_dangling_and_mismatched_regions(tmp_path) -> None:
    """Every non-analysis-capable focus should safely enter Overview."""
    invalid_projects: list[tuple[str, SpectroscopyProject]] = []

    unassigned = _project("unassigned")
    invalid_projects.append(("unassigned", unassigned))

    empty = SpectroscopyProject(name="empty")
    empty.absorption_regions["empty"] = AbsorptionRegion(region_id="empty")
    invalid_projects.append(("empty", empty))

    dangling = SpectroscopyProject(name="dangling")
    dangling.absorption_regions["dangling"] = AbsorptionRegion(
        region_id="dangling", line_ids=["missing-line"]
    )
    invalid_projects.append(("dangling", dangling))

    mismatched = _project("actual")
    mismatched.absorption_regions["mismatched"] = AbsorptionRegion(
        region_id="mismatched", line_ids=["line-1"]
    )
    invalid_projects.append(("mismatched", mismatched))

    for region_id, project in invalid_projects:
        settings = _Settings()
        key = _project_key(tmp_path / f"{region_id}.h5")
        settings.snapshots[key] = AnalysisNavigationSnapshot(
            surface=AnalysisSurface.REGION_DETAIL, focused_region_id=region_id
        )
        coordinator, entries = _coordinator(settings)

        coordinator.handle_project_context_changed(
            _event(project=project, key=key, reason=ProjectContextChangeReason.OPEN)
        )

        assert coordinator.state.surface is AnalysisSurface.OVERVIEW
        assert coordinator.state.focused_region_id is None
        assert entries == [EditingMode.ANALYSIS]


def test_open_persistence_failure_falls_back_and_releases_context_guard(tmp_path) -> None:
    """Failed LRU persistence during open must still resolve a usable Overview entry."""
    settings = _Settings(fail_load=True)
    coordinator, entries = _coordinator(settings)
    issues: list[AnalysisNavigationPersistenceIssue] = []
    coordinator.persistence_error.connect(issues.append)
    key = _project_key(tmp_path / "project.h5")

    coordinator.handle_project_context_changing()
    coordinator.handle_project_context_changed(
        _event(project=_project("region-1"), key=key, reason=ProjectContextChangeReason.OPEN)
    )

    assert coordinator.state == AnalysisNavigationState()
    assert coordinator.project_key == key
    assert coordinator._context_switching is False
    assert entries == [EditingMode.ANALYSIS]
    assert [issue.operation for issue in issues] == [AnalysisNavigationPersistenceOperation.LOAD]


def test_save_persistence_failure_keeps_runtime_focus(tmp_path) -> None:
    """A local settings write failure must not undo current runtime navigation."""
    settings = _Settings()
    coordinator, _entries = _coordinator(settings)
    issues: list[AnalysisNavigationPersistenceIssue] = []
    coordinator.persistence_error.connect(issues.append)
    key = _project_key(tmp_path / "project.h5")
    project = _project("region-1")
    coordinator.handle_project_context_changed(
        _event(project=project, key=key, reason=ProjectContextChangeReason.OPEN)
    )
    settings.fail_save = True

    assert coordinator.focus_region("region-1") is True

    assert coordinator.state.focused_region_id == "region-1"
    assert [issue.operation for issue in issues] == [AnalysisNavigationPersistenceOperation.SAVE]


def test_real_settings_save_failure_is_nonfatal_and_preserves_all_owners(tmp_path: Path) -> None:
    """Adapter rollback must not roll back runtime navigation or mutate scientific state."""
    ini_path = tmp_path / "analysis.ini"
    switch = _SyncFailureSwitch()
    raw_settings = _SwitchedSettings(ini_path, switch)
    adapter = QSettingsAnalysisNavigationAdapter(
        raw_settings, settings_factory=lambda: _SwitchedSettings(ini_path, switch)
    )
    key = _project_key(tmp_path / "project.h5")
    adapter.save(key, AnalysisNavigationSnapshot(filter_text="durable"))
    payload_key = f"analysis/navigation/projects/{key.value}"
    durable_payload = raw_settings.value(payload_key)
    project = _project("region-1")
    coordinator, entries = _coordinator(adapter)
    issues: list[AnalysisNavigationPersistenceIssue] = []
    coordinator.persistence_error.connect(issues.append)
    coordinator.handle_project_context_changed(
        _event(project=project, key=key, reason=ProjectContextChangeReason.OPEN)
    )

    switch.armed = True
    assert coordinator.focus_region("region-1") is True
    switch.armed = False

    assert coordinator.state.focused_region_id == "region-1"
    assert coordinator.state.filter_text == "durable"
    assert coordinator.project_key == key
    assert project.absorption_regions["region-1"].line_ids == ["line-1"]
    assert entries == [EditingMode.ANALYSIS]
    assert len(issues) == 1
    assert isinstance(issues[0], AnalysisNavigationPersistenceIssue)
    assert issues[0].operation is AnalysisNavigationPersistenceOperation.SAVE
    assert issues[0].project_key == key
    assert raw_settings.value(payload_key) == durable_payload


def test_save_as_persistence_failure_keeps_new_session_context(tmp_path, qtbot: QtBot) -> None:
    """File Save As success must win even when local navigation migration fails."""
    main_window = QWidget()
    qtbot.addWidget(main_window)
    session = ProjectSessionController(
        cast("MainWindow", main_window),
        project_io=cast("ProjectIOUseCase", create_default_project_io_usecase()),
        refresh_callback=lambda _project: None,
    )
    settings = _Settings()
    coordinator, entries = _coordinator(settings)
    issues: list[AnalysisNavigationPersistenceIssue] = []
    coordinator.persistence_error.connect(issues.append)
    session.project_context_changing.connect(coordinator.handle_project_context_changing)
    session.project_context_changed.connect(coordinator.handle_project_context_changed)
    old_path = str(tmp_path / "old.h5")
    new_path = str(tmp_path / "new.h5")
    Path(old_path).touch()
    Path(new_path).touch()
    project = _project("region-1")
    session.switch_project(project, path=old_path, reason=ProjectContextChangeReason.OPEN)
    assert coordinator.focus_region("region-1") is True
    coordinator.set_surface(AnalysisSurface.REGION_DETAIL)
    old_key = ProjectKey.for_saved_path(old_path)
    settings.fail_migrate = True

    session._on_project_path_recorded(new_path)

    new_key = ProjectKey.for_saved_path(new_path)
    assert session.current_project is project
    assert session.project_file_path == new_path
    assert session.project_key == new_key
    assert coordinator.project_key == new_key
    assert coordinator.state.surface is AnalysisSurface.REGION_DETAIL
    assert coordinator.state.focused_region_id == "region-1"
    assert coordinator._context_switching is False
    assert old_key in settings.snapshots
    assert new_key not in settings.snapshots
    assert entries == [EditingMode.ANALYSIS]
    assert [issue.operation for issue in issues] == [
        AnalysisNavigationPersistenceOperation.MIGRATE
    ]


@pytest.mark.parametrize(
    ("reason", "expected_mode", "expected_status"),
    [
        (
            ProjectContextChangeReason.CREATE,
            EditingMode.IDENTIFY,
            "Analysis view settings could not be saved for this file. You can keep working; project data is unchanged, but this view may not be restored next time.",
        ),
        (
            ProjectContextChangeReason.OPEN,
            EditingMode.ANALYSIS,
            "Previous Analysis view settings could not be restored. Overview is shown; project data is unchanged.",
        ),
    ],
)
def test_project_activation_continues_with_session_key_when_path_identity_fails(
    reason: ProjectContextChangeReason,
    expected_mode: EditingMode,
    expected_status: str,
    monkeypatch: MonkeyPatch,
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    """CREATE and OPEN must keep the scientific project usable after local-key failure."""
    main_window = QWidget()
    qtbot.addWidget(main_window)
    refreshed: list[SpectroscopyProject | None] = []
    statuses: list[tuple[str, int]] = []
    events: list[ProjectContextChanged] = []
    session = ProjectSessionController(
        cast("MainWindow", main_window),
        project_io=cast("ProjectIOUseCase", create_default_project_io_usecase()),
        refresh_callback=refreshed.append,
    )
    coordinator, entries = _coordinator(_Settings())
    session.project_context_changing.connect(coordinator.handle_project_context_changing)
    session.project_context_changed.connect(coordinator.handle_project_context_changed)
    session.project_context_changed.connect(events.append)
    session.status_message.connect(lambda message, timeout: statuses.append((message, timeout)))
    project = _project("region-1")
    project_path = tmp_path / f"{reason.value}.h5"
    project_path.touch()
    monkeypatch.setattr(
        project_key_module, "canonical_project_path", _raise_project_path_identity_error
    )

    session.switch_project(project, path=str(project_path), reason=reason)

    assert session.current_project is project
    assert session.project_file_path == str(project_path)
    assert session.project_key is not None and session.project_key.persistent is False
    assert coordinator.project_key == session.project_key
    assert coordinator.state == AnalysisNavigationState()
    assert coordinator._context_switching is False
    assert project.absorption_regions["region-1"].line_ids == ["line-1"]
    assert refreshed == [project]
    assert entries == [expected_mode]
    assert events[-1].project is project
    assert events[-1].new_key == session.project_key
    assert statuses == [(expected_status, 5000)]


def test_save_as_path_race_keeps_session_key_then_recovers_on_same_path(
    qtbot: QtBot, tmp_path: Path
) -> None:
    """A later same-path signal should promote fallback state to a persistent key."""
    main_window = QWidget()
    qtbot.addWidget(main_window)
    session = ProjectSessionController(
        cast("MainWindow", main_window),
        project_io=cast("ProjectIOUseCase", create_default_project_io_usecase()),
        refresh_callback=lambda _project: None,
    )
    settings = _Settings()
    coordinator, _entries = _coordinator(settings)
    statuses: list[tuple[str, int]] = []
    session.project_context_changing.connect(coordinator.handle_project_context_changing)
    session.project_context_changed.connect(coordinator.handle_project_context_changed)
    session.status_message.connect(lambda message, timeout: statuses.append((message, timeout)))
    old_path = tmp_path / "old.h5"
    old_path.touch()
    new_path = tmp_path / "new.h5"
    project = _project("region-1")
    session.switch_project(project, path=str(old_path), reason=ProjectContextChangeReason.OPEN)
    assert coordinator.focus_region("region-1") is True
    coordinator.set_surface(AnalysisSurface.REGION_DETAIL)

    session._on_project_path_recorded(str(new_path))
    fallback_key = session.project_key

    assert session.current_project is project
    assert session.project_file_path == str(new_path)
    assert fallback_key is not None and fallback_key.persistent is False
    assert coordinator.project_key == fallback_key
    assert coordinator.state.surface is AnalysisSurface.REGION_DETAIL
    assert coordinator.state.focused_region_id == "region-1"
    assert coordinator._context_switching is False

    session._on_project_path_recorded(str(new_path))
    assert session.project_key == fallback_key
    assert coordinator.project_key == fallback_key
    assert coordinator._context_switching is False

    new_path.touch()
    session._on_project_path_recorded(str(new_path))

    persistent_key = ProjectKey.for_saved_path(new_path)
    assert session.project_key == persistent_key
    assert coordinator.project_key == persistent_key
    assert coordinator.state.surface is AnalysisSurface.REGION_DETAIL
    assert coordinator.state.focused_region_id == "region-1"
    assert coordinator._context_switching is False
    assert settings.snapshots[persistent_key].surface is AnalysisSurface.REGION_DETAIL
    assert statuses == [
        (
            "Analysis view settings could not be saved for this file. You can keep working; project data is unchanged, but this view may not be restored next time.",
            5000,
        ),
        (
            "Analysis view settings could not be saved for this file. You can keep working; project data is unchanged, but this view may not be restored next time.",
            5000,
        ),
    ]


def test_overview_selection_and_view_context_use_ids_and_persist_only_view_state(
    tmp_path: Path,
) -> None:
    """Row selection updates canonical focus while view state also persists."""
    settings = _Settings()
    key = _project_key(tmp_path / "overview.h5")
    coordinator, _entries = _coordinator(settings)
    project = _project("region-1", "region-2")
    coordinator.handle_project_context_changed(
        _event(project=project, key=key, reason=ProjectContextChangeReason.OPEN)
    )

    assert coordinator.select_overview_region("region-2") is True
    assert coordinator.state.overview_selection == "region-2"
    assert settings.snapshots[key].focused_region_id == "region-2"

    coordinator.update_overview_view(
        filter_text="stale",
        filter_readiness=(AnalysisReadiness.STALE,),
        sort_column_id="status",
        sort_ascending=False,
        visible_column_ids=("region", "status", "next_action"),
        column_order=("next_action", "region", "status"),
        top_visible_region_id="region-1",
    )

    snapshot = settings.snapshots[key]
    assert snapshot.filter_text == "stale"
    assert snapshot.filter_readiness == (AnalysisReadiness.STALE,)
    assert snapshot.sort_column_id == "status"
    assert snapshot.sort_ascending is False
    assert snapshot.visible_column_ids == ("region", "status", "next_action")
    assert snapshot.column_order == ("next_action", "region", "status", "fit_result")
    assert snapshot.top_visible_region_id == "region-1"


def test_spectrum_range_round_trips_in_project_navigation_snapshot(tmp_path: Path) -> None:
    """Visible Analysis wavelength range is persisted with its project key."""
    settings = _Settings()
    key = _project_key(tmp_path / "range.h5")
    project = _project("region-1")
    coordinator, _entries = _coordinator(settings)
    coordinator.handle_project_context_changed(
        _event(project=project, key=key, reason=ProjectContextChangeReason.OPEN)
    )

    coordinator.update_spectrum_wavelength_range((4100.0, 4300.0))

    assert settings.snapshots[key].spectrum_wavelength_range == (4100.0, 4300.0)
    restored, _restored_entries = _coordinator(settings)
    restored.handle_project_context_changed(
        _event(project=project, key=key, reason=ProjectContextChangeReason.OPEN)
    )
    assert restored.state.spectrum_wavelength_range == (4100.0, 4300.0)


@pytest.mark.parametrize("value", [(1.0, 1.0), (2.0, 1.0), (float("nan"), 2.0)])
def test_spectrum_range_rejects_invalid_values(value: tuple[float, float], tmp_path: Path) -> None:
    coordinator, _entries = _coordinator(_Settings())
    coordinator.handle_project_context_changed(
        _event(
            project=_project("region-1"),
            key=_project_key(tmp_path / f"invalid-{value[0]}.h5"),
            reason=ProjectContextChangeReason.OPEN,
        )
    )

    with pytest.raises(ValueError, match="finite and increasing"):
        coordinator.update_spectrum_wavelength_range(value)


def test_display_options_round_trip_and_persist(tmp_path: Path) -> None:
    """Display options should be readable back and persisted under the project key."""
    settings = _Settings()
    key = _project_key(tmp_path / "display.h5")
    project = _project("region-1")
    coordinator, _entries = _coordinator(settings)
    coordinator.handle_project_context_changed(
        _event(project=project, key=key, reason=ProjectContextChangeReason.OPEN)
    )
    assert coordinator.display_options() == SpectrumDisplayOptions()

    options = SpectrumDisplayOptions(show_error_spectrum=False, show_component_profiles=True)
    coordinator.set_display_options(options)

    assert coordinator.display_options() == options
    assert settings.snapshots[key].show_error_spectrum is False
    assert settings.snapshots[key].show_component_profiles is True


def test_display_options_no_op_when_unchanged(tmp_path: Path) -> None:
    """Setting the already-active options must not trigger a redundant save."""
    settings = _Settings()
    key = _project_key(tmp_path / "display.h5")
    coordinator, _entries = _coordinator(settings)
    coordinator.handle_project_context_changed(
        _event(project=_project("region-1"), key=key, reason=ProjectContextChangeReason.OPEN)
    )
    settings.saved.clear()

    coordinator.set_display_options(SpectrumDisplayOptions())

    assert settings.saved == []


def test_display_options_changed_emits_restored_value_on_project_switch(tmp_path: Path) -> None:
    """Switching to a project with saved display options must emit them for the UI."""
    settings = _Settings()
    key = _project_key(tmp_path / "display.h5")
    stored_options = SpectrumDisplayOptions(
        show_error_spectrum=False, show_component_profiles=True
    )
    settings.snapshots[key] = AnalysisNavigationSnapshot(
        show_error_spectrum=stored_options.show_error_spectrum,
        show_component_profiles=stored_options.show_component_profiles,
    )
    coordinator, _entries = _coordinator(settings)
    emitted: list[SpectrumDisplayOptions] = []
    coordinator.display_options_changed.connect(emitted.append)

    coordinator.handle_project_context_changed(
        _event(project=_project("region-1"), key=key, reason=ProjectContextChangeReason.OPEN)
    )

    assert emitted == [stored_options]
    assert coordinator.display_options() == stored_options


def test_display_menu_controller_persists_and_restores_through_coordinator(
    qapp: QApplication, tmp_path: Path
) -> None:
    """A real Display menu wired exactly as the shell does must persist and restore choices."""
    settings = _Settings()
    key = _project_key(tmp_path / "display.h5")
    coordinator, _entries = _coordinator(settings)
    controller = DisplayMenuController(parent=qapp)
    controller.display_options_changed.connect(coordinator.set_display_options)
    coordinator.display_options_changed.connect(controller.set_options)

    coordinator.handle_project_context_changed(
        _event(project=_project("region-1"), key=key, reason=ProjectContextChangeReason.OPEN)
    )

    error_action, _component_action = controller.actions()
    error_action.setChecked(False)

    assert settings.snapshots[key].show_error_spectrum is False

    other_key = _project_key(tmp_path / "other.h5")
    settings.snapshots[other_key] = AnalysisNavigationSnapshot(
        show_error_spectrum=False, show_component_profiles=True
    )
    coordinator.handle_project_context_changed(
        _event(
            project=_project("region-2"),
            key=other_key,
            old_key=key,
            reason=ProjectContextChangeReason.OPEN,
        )
    )

    assert controller.options() == SpectrumDisplayOptions(
        show_error_spectrum=False, show_component_profiles=True
    )
