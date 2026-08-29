"""Tests for project-key scoped Analysis navigation settings."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings

from chappy.core.analysis import AnalysisReadiness
from chappy.gui.adapters.analysis_navigation_settings import (
    AnalysisNavigationSettingsError,
    QSettingsAnalysisNavigationAdapter,
)
from chappy.gui.modes.common.analysis_navigation import AnalysisNavigationSnapshot, AnalysisSurface
from chappy.gui.modes.common.analysis_navigation import ANALYSIS_OVERVIEW_FULL_COLUMNS
from chappy.gui.modes.common.project_key import ProjectKey


def _settings(path: Path) -> QSettings:
    return QSettings(str(path), QSettings.Format.IniFormat)


def _project_key(path: Path) -> ProjectKey:
    """Create a saved-project file and return its persistent UI key."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    return ProjectKey.for_saved_path(path)


def _snapshot(region_id: str = "region-1") -> AnalysisNavigationSnapshot:
    return AnalysisNavigationSnapshot(
        surface=AnalysisSurface.REGION_DETAIL,
        focused_region_id=region_id,
        filter_text="stale",
        filter_readiness=(AnalysisReadiness.STALE,),
        sort_column_id="fit_result",
        sort_ascending=False,
        visible_column_ids=("region", "status"),
        column_order=("status", "region", "fit_result", "next_action"),
        top_visible_region_id=region_id,
        spectrum_wavelength_range=(1200.0, 1300.0),
        show_error_spectrum=False,
        show_component_profiles=True,
    )


class _SyncFailureSwitch:
    """Shared script failing every sync once its allowed successes are used up."""

    def __init__(self) -> None:
        self.remaining_successes: int | None = None

    def next_sync_fails(self) -> bool:
        if self.remaining_successes is None:
            return False
        if self.remaining_successes > 0:
            self.remaining_successes -= 1
            return False
        return True


class _SwitchedSettings(QSettings):
    """QSettings test double that persists normally while reporting scripted failures.

    The adapter retries a reported failure on factory-built fresh instances, so
    the switch is shared across the primary settings and every factory product.
    """

    def __init__(self, path: Path, switch: _SyncFailureSwitch) -> None:
        super().__init__(str(path), QSettings.Format.IniFormat)
        self._switch = switch
        self._last_sync_failed = False

    def sync(self) -> None:
        super().sync()
        self._last_sync_failed = self._switch.next_sync_fails()

    def status(self) -> QSettings.Status:
        if self._last_sync_failed:
            return QSettings.Status.AccessError
        return QSettings.Status.NoError


def _failing_adapter(
    path: Path,
) -> tuple[QSettingsAnalysisNavigationAdapter, _SwitchedSettings, _SyncFailureSwitch]:
    switch = _SyncFailureSwitch()
    settings = _SwitchedSettings(path, switch)
    adapter = QSettingsAnalysisNavigationAdapter(
        settings, settings_factory=lambda: _SwitchedSettings(path, switch)
    )
    return adapter, settings, switch


def test_adapter_round_trips_versioned_persistent_payload(tmp_path: Path) -> None:
    """All planned persistent fields should round-trip without runtime selections."""
    adapter = QSettingsAnalysisNavigationAdapter(_settings(tmp_path / "analysis.ini"))
    key = _project_key(tmp_path / "project.h5")
    snapshot = _snapshot()

    adapter.save(key, snapshot)

    assert adapter.load(key) == snapshot


def test_adapter_rejects_session_only_keys(tmp_path: Path) -> None:
    """Unsaved session UUIDs must never enter QSettings."""
    adapter = QSettingsAnalysisNavigationAdapter(_settings(tmp_path / "analysis.ini"))
    key = ProjectKey.for_unsaved_session()

    with pytest.raises(ValueError, match="Session-only"):
        adapter.save(key, _snapshot())


def test_adapter_unknown_version_degrades_to_missing_state(tmp_path: Path) -> None:
    """Unknown payload versions should not fail application startup."""
    settings = _settings(tmp_path / "analysis.ini")
    key = _project_key(tmp_path / "project.h5")
    settings.setValue(
        f"analysis/navigation/projects/{key.value}",
        json.dumps({"version": 99, "surface": "region_detail"}),
    )
    settings.sync()

    assert QSettingsAnalysisNavigationAdapter(settings).load(key) is None


def test_adapter_unknown_surface_degrades_to_overview(tmp_path: Path) -> None:
    """Unknown surface values should not restore a hidden or arbitrary detail target."""
    settings = _settings(tmp_path / "analysis.ini")
    key = _project_key(tmp_path / "project.h5")
    settings.setValue(
        f"analysis/navigation/projects/{key.value}",
        json.dumps({"version": 1, "surface": "future-surface", "focused_region_id": "region-1"}),
    )
    settings.sync()

    snapshot = QSettingsAnalysisNavigationAdapter(settings).load(key)

    assert snapshot is not None
    assert snapshot.surface is AnalysisSurface.OVERVIEW


def test_adapter_normalizes_unknown_duplicate_and_incomplete_column_ids(tmp_path: Path) -> None:
    """Persisted semantic columns must decode to one canonical full-table configuration."""
    settings = _settings(tmp_path / "analysis.ini")
    key = _project_key(tmp_path / "project.h5")
    settings.setValue(
        f"analysis/navigation/projects/{key.value}",
        json.dumps(
            {
                "version": 1,
                "surface": "overview",
                "sort_column_id": "future-sort",
                "visible_column_ids": ["status", "future", "status", 1],
                "column_order": ["next_action", "future", "next_action", "region"],
            }
        ),
    )
    settings.sync()

    snapshot = QSettingsAnalysisNavigationAdapter(settings).load(key)

    assert snapshot is not None
    assert snapshot.sort_column_id == "region"
    assert snapshot.visible_column_ids == ("status",)
    assert snapshot.column_order == ("next_action", "region", "status", "fit_result")


def test_adapter_empty_or_nonapplicable_columns_degrade_to_safe_defaults(tmp_path: Path) -> None:
    """An unusable visibility set and compact-only sort must become full-table defaults."""
    settings = _settings(tmp_path / "analysis.ini")
    key = _project_key(tmp_path / "project.h5")
    settings.setValue(
        f"analysis/navigation/projects/{key.value}",
        json.dumps(
            {
                "version": 1,
                "sort_column_id": "status_and_reasons",
                "visible_column_ids": ["status_and_reasons", "unknown"],
                "column_order": [],
            }
        ),
    )
    settings.sync()

    snapshot = QSettingsAnalysisNavigationAdapter(settings).load(key)

    assert snapshot is not None
    canonical = tuple(column.value for column in ANALYSIS_OVERVIEW_FULL_COLUMNS)
    assert snapshot.sort_column_id == "region"
    assert snapshot.visible_column_ids == canonical
    assert snapshot.column_order == canonical


def test_adapter_display_options_default_when_absent_from_legacy_payload(tmp_path: Path) -> None:
    """A payload saved before display options existed must decode to their defaults."""
    settings = _settings(tmp_path / "analysis.ini")
    key = _project_key(tmp_path / "project.h5")
    settings.setValue(
        f"analysis/navigation/projects/{key.value}",
        json.dumps({"version": 1, "surface": "overview"}),
    )
    settings.sync()

    snapshot = QSettingsAnalysisNavigationAdapter(settings).load(key)

    assert snapshot is not None
    assert snapshot.show_error_spectrum is True
    assert snapshot.show_component_profiles is False


def test_adapter_display_options_ignore_non_bool_values(tmp_path: Path) -> None:
    """Corrupted or future-typed display option values must degrade to defaults."""
    settings = _settings(tmp_path / "analysis.ini")
    key = _project_key(tmp_path / "project.h5")
    settings.setValue(
        f"analysis/navigation/projects/{key.value}",
        json.dumps(
            {
                "version": 1,
                "surface": "overview",
                "show_error_spectrum": "false",
                "show_component_profiles": 1,
            }
        ),
    )
    settings.sync()

    snapshot = QSettingsAnalysisNavigationAdapter(settings).load(key)

    assert snapshot is not None
    assert snapshot.show_error_spectrum is True
    assert snapshot.show_component_profiles is False


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"version": 99, "surface": "overview"}, None),
        (
            {"version": 1, "surface": "future", "future_field": {"nested": True}},
            AnalysisSurface.OVERVIEW,
        ),
        (
            {
                "version": 1,
                "surface": ["region_detail"],
                "filter_readiness": ["future", 1, "stale", "stale"],
                "sort_ascending": "false",
                "spectrum_wavelength_range": [1300.0, 1200.0],
            },
            AnalysisSurface.OVERVIEW,
        ),
    ],
)
def test_adapter_forward_compatibility_matrix(
    tmp_path: Path, payload: dict[str, object], expected: AnalysisSurface | None
) -> None:
    """Unknown versions, fields, values, and surface shapes have deterministic outcomes."""
    settings = _settings(tmp_path / "analysis.ini")
    key = _project_key(tmp_path / "project.h5")
    settings.setValue(f"analysis/navigation/projects/{key.value}", json.dumps(payload))
    settings.sync()

    snapshot = QSettingsAnalysisNavigationAdapter(settings).load(key)

    if expected is None:
        assert snapshot is None
        return
    assert snapshot is not None
    assert snapshot.surface is expected
    assert snapshot.sort_ascending is True
    assert snapshot.spectrum_wavelength_range is None


def test_adapter_prunes_saved_projects_to_32_lru_entries(tmp_path: Path) -> None:
    """Saving a 33rd project should remove the least-recent payload."""
    settings = _settings(tmp_path / "analysis.ini")
    adapter = QSettingsAnalysisNavigationAdapter(settings)
    keys = [_project_key(tmp_path / f"project-{index}.h5") for index in range(33)]

    for index, key in enumerate(keys):
        adapter.save(key, _snapshot(f"region-{index}"))

    assert adapter.load(keys[0]) is None
    assert adapter.load(keys[-1]) == _snapshot("region-32")


def test_adapter_load_recovers_orphan_payload_and_prunes_lru(tmp_path: Path) -> None:
    """Loading an unindexed payload should recover it without exceeding 32 entries."""
    settings = _settings(tmp_path / "analysis.ini")
    adapter = QSettingsAnalysisNavigationAdapter(settings)
    keys = [_project_key(tmp_path / f"project-{index}.h5") for index in range(32)]
    for index, key in enumerate(keys):
        adapter.save(key, _snapshot(f"region-{index}"))
    orphan_key = _project_key(tmp_path / "orphan.h5")
    settings.setValue(
        f"analysis/navigation/projects/{orphan_key.value}",
        json.dumps(
            {"version": 1, "surface": "region_detail", "focused_region_id": "orphan-region"}
        ),
    )
    settings.sync()

    restored = adapter.load(orphan_key)

    assert restored is not None
    assert restored.focused_region_id == "orphan-region"
    lru = json.loads(str(settings.value("analysis/navigation/lru")))
    assert len(lru) == 32
    assert lru[0] == orphan_key.value
    assert adapter.load(keys[0]) is None


class _StickyErrorSettings(QSettings):
    """QSettings double frozen in the first-error state the real status never leaves."""

    def __init__(self, path: Path) -> None:
        super().__init__(str(path), QSettings.Format.IniFormat)

    def status(self) -> QSettings.Status:
        return QSettings.Status.AccessError


def test_adapter_recovers_from_sticky_error_status_via_fresh_instances(tmp_path: Path) -> None:
    """A stale first-error status must not fail operations whose writes persist."""
    path = tmp_path / "analysis.ini"
    adapter = QSettingsAnalysisNavigationAdapter(
        _StickyErrorSettings(path), settings_factory=lambda: _settings(path)
    )
    key = _project_key(tmp_path / "project.h5")
    snapshot = _snapshot("recovered")

    adapter.save(key, snapshot)

    assert adapter.load(key) == snapshot
    assert QSettingsAnalysisNavigationAdapter(_settings(path)).load(key) == snapshot


def test_adapter_load_sync_failure_restores_lru_order(tmp_path: Path) -> None:
    """A persistently failing load-side LRU sync should restore the local settings."""
    adapter, settings, switch = _failing_adapter(tmp_path / "analysis.ini")
    first_key = _project_key(tmp_path / "first.h5")
    second_key = _project_key(tmp_path / "second.h5")
    adapter.save(first_key, _snapshot("first"))
    adapter.save(second_key, _snapshot("second"))
    original_lru = settings.value("analysis/navigation/lru")

    switch.remaining_successes = 0
    with pytest.raises(AnalysisNavigationSettingsError):
        adapter.load(first_key)
    switch.remaining_successes = None

    assert settings.value("analysis/navigation/lru") == original_lru


def test_adapter_save_sync_failure_preserves_previous_payload(tmp_path: Path) -> None:
    """A persistently failing update must roll back the payload and LRU durably."""
    adapter, settings, switch = _failing_adapter(tmp_path / "analysis.ini")
    key = _project_key(tmp_path / "project.h5")
    original = _snapshot("original")
    adapter.save(key, original)
    payload_key = f"analysis/navigation/projects/{key.value}"
    original_payload = settings.value(payload_key)
    original_lru = settings.value("analysis/navigation/lru")

    switch.remaining_successes = 0
    with pytest.raises(AnalysisNavigationSettingsError):
        adapter.save(key, _snapshot("replacement"))
    switch.remaining_successes = None

    assert settings.value(payload_key) == original_payload
    assert settings.value("analysis/navigation/lru") == original_lru
    assert (
        QSettingsAnalysisNavigationAdapter(_settings(tmp_path / "analysis.ini")).load(key)
        == original
    )


def test_adapter_save_as_copies_before_removing_old_key(tmp_path: Path) -> None:
    """A successful migration should leave only the new path-derived key."""
    settings = _settings(tmp_path / "analysis.ini")
    adapter = QSettingsAnalysisNavigationAdapter(settings)
    old_key = _project_key(tmp_path / "old.h5")
    new_key = _project_key(tmp_path / "new.h5")
    snapshot = _snapshot()
    adapter.save(old_key, snapshot)

    adapter.migrate(old_key, new_key, snapshot)

    assert adapter.load(old_key) is None
    assert adapter.load(new_key) == snapshot


@pytest.mark.parametrize("successful_migration_syncs", [0, 1])
def test_adapter_save_as_sync_failure_restores_old_state(
    tmp_path: Path, successful_migration_syncs: int
) -> None:
    """Either migration phase failure should leave the pre-migration settings intact."""
    adapter, _settings_double, switch = _failing_adapter(
        tmp_path / f"analysis-{successful_migration_syncs}.ini"
    )
    old_key = _project_key(tmp_path / "old.h5")
    new_key = _project_key(tmp_path / "new.h5")
    snapshot = _snapshot()
    adapter.save(old_key, snapshot)

    switch.remaining_successes = successful_migration_syncs
    with pytest.raises(AnalysisNavigationSettingsError):
        adapter.migrate(old_key, new_key, snapshot)
    switch.remaining_successes = None

    assert adapter.load(old_key) == snapshot
    assert adapter.load(new_key) is None
