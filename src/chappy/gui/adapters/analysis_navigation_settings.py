"""QSettings adapter for project-key scoped Analysis navigation state."""

from __future__ import annotations

import json
import math
import time
from collections.abc import Callable, Mapping, Sequence
from typing import TYPE_CHECKING, Final

from PySide6.QtCore import QSettings

from chappy.core.analysis import AnalysisReadiness
from chappy.gui.modes.common.analysis_navigation import (
    AnalysisNavigationSettingsError,
    AnalysisNavigationSnapshot,
    AnalysisSurface,
    normalize_analysis_overview_column_state,
)

if TYPE_CHECKING:
    from chappy.gui.modes.common.project_key import ProjectKey

_PAYLOAD_VERSION: Final = 1
_SETTINGS_PREFIX: Final = "analysis/navigation/projects"
_LRU_KEY: Final = "analysis/navigation/lru"
_MAX_SAVED_PROJECTS: Final = 32
_FLUSH_ATTEMPTS: Final = 3
_FLUSH_RETRY_DELAY_SECONDS: Final = 0.05

SettingsFactory = Callable[[], QSettings]


class QSettingsAnalysisNavigationAdapter:
    """Persist the minimal Analysis navigation payload for saved projects."""

    def __init__(
        self, settings: QSettings | None = None, settings_factory: SettingsFactory | None = None
    ) -> None:
        """Initialize the adapter with injectable QSettings construction."""
        self._settings = settings if settings is not None else QSettings("Chappy", "Chappy")
        self._settings_factory = (
            settings_factory if settings_factory is not None else (self._fresh_settings)
        )

    def _fresh_settings(self) -> QSettings:
        return QSettings(self._settings.fileName(), self._settings.format())

    def load(self, key: ProjectKey) -> AnalysisNavigationSnapshot | None:
        """Load navigation state and mark the saved key as recently used."""
        self._require_persistent_key(key)
        raw_payload = self._settings.value(self._payload_key(key), None)
        snapshot = _decode_snapshot(raw_payload)
        if snapshot is None:
            return None
        original_lru = self._read_lru()
        touched_lru = self._touch_lru(original_lru, key.value)
        removed_values = self._remove_pruned_payloads(touched_lru)
        kept_lru = touched_lru[:_MAX_SAVED_PROJECTS]
        self._write_lru(kept_lru)
        written: dict[str, str | None] = {_LRU_KEY: _encode_lru(kept_lru)}
        written.update(dict.fromkeys(removed_values, None))
        try:
            self._sync_or_raise(written)
        except AnalysisNavigationSettingsError:
            self._restore_payloads(removed_values)
            self._write_lru(original_lru)
            self._flush_after_rollback()
            raise
        return snapshot

    def save(self, key: ProjectKey, snapshot: AnalysisNavigationSnapshot) -> None:
        """Persist navigation state and prune entries beyond the 32-key LRU."""
        self._require_persistent_key(key)
        payload_key = self._payload_key(key)
        original_payload = self._settings.value(payload_key, None)
        original_lru = self._read_lru()
        encoded_payload = _encode_snapshot(snapshot)
        self._settings.setValue(payload_key, encoded_payload)
        lru = self._touch_lru(original_lru, key.value)
        removed_values = self._remove_pruned_payloads(lru)
        kept_lru = lru[:_MAX_SAVED_PROJECTS]
        self._write_lru(kept_lru)
        written: dict[str, str | None] = {
            payload_key: encoded_payload,
            _LRU_KEY: _encode_lru(kept_lru),
        }
        written.update(dict.fromkeys(removed_values, None))
        try:
            self._sync_or_raise(written)
        except AnalysisNavigationSettingsError:
            self._restore_value(payload_key, original_payload)
            self._restore_payloads(removed_values)
            self._write_lru(original_lru)
            self._flush_after_rollback()
            raise

    def migrate(
        self, old_key: ProjectKey, new_key: ProjectKey, snapshot: AnalysisNavigationSnapshot
    ) -> None:
        """Copy and sync the new key before deleting the previous saved key."""
        self._require_persistent_key(old_key)
        self._require_persistent_key(new_key)
        if old_key == new_key:
            self.save(new_key, snapshot)
            return

        original_old = self._settings.value(self._payload_key(old_key), None)
        original_new = self._settings.value(self._payload_key(new_key), None)
        original_lru = self._read_lru()
        encoded_payload = _encode_snapshot(snapshot)
        self._settings.setValue(self._payload_key(new_key), encoded_payload)
        staged_lru = self._touch_lru(original_lru, new_key.value)
        self._write_lru(staged_lru)
        staged_written: dict[str, str | None] = {
            self._payload_key(new_key): encoded_payload,
            _LRU_KEY: _encode_lru(staged_lru),
        }
        try:
            self._sync_or_raise(staged_written)
        except AnalysisNavigationSettingsError:
            self._restore_value(self._payload_key(new_key), original_new)
            self._write_lru(original_lru)
            self._flush_after_rollback()
            raise

        self._settings.remove(self._payload_key(old_key))
        final_lru = [value for value in staged_lru if value != old_key.value]
        removed_values = self._remove_pruned_payloads(final_lru)
        kept_lru = final_lru[:_MAX_SAVED_PROJECTS]
        self._write_lru(kept_lru)
        final_written: dict[str, str | None] = {
            self._payload_key(old_key): None,
            _LRU_KEY: _encode_lru(kept_lru),
        }
        final_written.update(dict.fromkeys(removed_values, None))
        try:
            self._sync_or_raise(final_written)
        except AnalysisNavigationSettingsError:
            self._restore_value(self._payload_key(old_key), original_old)
            self._restore_value(self._payload_key(new_key), original_new)
            self._restore_payloads(removed_values)
            self._write_lru(original_lru)
            self._flush_after_rollback()
            raise

    def _read_lru(self) -> list[str]:
        raw_value = self._settings.value(_LRU_KEY, "[]")
        if not isinstance(raw_value, str):
            return []
        try:
            payload = json.loads(raw_value)
        except json.JSONDecodeError:
            return []
        if not isinstance(payload, list):
            return []
        return [value for value in payload if isinstance(value, str)]

    def _write_lru(self, values: Sequence[str]) -> None:
        self._settings.setValue(_LRU_KEY, _encode_lru(values))

    def _sync_or_raise(self, written: Mapping[str, str | None]) -> None:
        """Flush pending changes and raise only when they verifiably failed to persist.

        ``QSettings.status()`` keeps reporting the first error an instance ever
        met, even after later syncs succeed, so a reported error is re-checked
        on fresh instances: they share this process's pending-write cache, their
        ``sync()`` flushes it, and their status covers only that attempt. The
        read-back comparison guards immediate-write backends (Windows registry)
        where a fresh sync succeeds without re-applying the failed writes.
        """
        if self._flush(written):
            return
        message = "QSettings failed to persist Analysis navigation state"
        raise AnalysisNavigationSettingsError(message)

    def _flush(self, written: Mapping[str, str | None]) -> bool:
        self._settings.sync()
        if self._settings.status() == QSettings.Status.NoError:
            return True
        for attempt in range(_FLUSH_ATTEMPTS):
            if attempt:
                time.sleep(_FLUSH_RETRY_DELAY_SECONDS)
            fresh = self._settings_factory()
            fresh.sync()
            if fresh.status() != QSettings.Status.NoError:
                continue
            if all(fresh.value(key, None) == value for key, value in written.items()):
                return True
        return False

    def _flush_after_rollback(self) -> None:
        self._flush({})

    def _restore_value(self, key: str, value: object) -> None:
        if value is None:
            self._settings.remove(key)
            return
        self._settings.setValue(key, value)

    def _remove_pruned_payloads(self, values: Sequence[str]) -> dict[str, object]:
        """Remove payloads beyond the LRU limit and return rollback values."""
        removed_values: dict[str, object] = {}
        for value in values[_MAX_SAVED_PROJECTS:]:
            payload_key = self._payload_key_from_value(value)
            removed_values[payload_key] = self._settings.value(payload_key, None)
            self._settings.remove(payload_key)
        return removed_values

    def _restore_payloads(self, values: Mapping[str, object]) -> None:
        """Restore payload values captured before a transactional update."""
        for payload_key, value in values.items():
            self._restore_value(payload_key, value)

    @staticmethod
    def _require_persistent_key(key: ProjectKey) -> None:
        if key.persistent:
            return
        message = "Session-only ProjectKey must not be written to QSettings"
        raise ValueError(message)

    @staticmethod
    def _payload_key(key: ProjectKey) -> str:
        return QSettingsAnalysisNavigationAdapter._payload_key_from_value(key.value)

    @staticmethod
    def _payload_key_from_value(value: str) -> str:
        return f"{_SETTINGS_PREFIX}/{value}"

    @staticmethod
    def _touch_lru(values: Sequence[str], key_value: str) -> list[str]:
        return [key_value, *(value for value in values if value != key_value)]


def _encode_lru(values: Sequence[str]) -> str:
    return json.dumps(list(values), separators=(",", ":"))


def _encode_snapshot(snapshot: AnalysisNavigationSnapshot) -> str:
    sort_column_id, visible_column_ids, column_order = normalize_analysis_overview_column_state(
        sort_column_id=snapshot.sort_column_id,
        visible_column_ids=snapshot.visible_column_ids,
        column_order=snapshot.column_order,
    )
    payload = {
        "version": _PAYLOAD_VERSION,
        "surface": snapshot.surface.value,
        "focused_region_id": snapshot.focused_region_id,
        "filter_text": snapshot.filter_text,
        "filter_readiness": [readiness.value for readiness in snapshot.filter_readiness],
        "sort_column_id": sort_column_id,
        "sort_ascending": snapshot.sort_ascending,
        "visible_column_ids": list(visible_column_ids),
        "column_order": list(column_order),
        "top_visible_region_id": snapshot.top_visible_region_id,
        "spectrum_wavelength_range": (
            list(snapshot.spectrum_wavelength_range)
            if snapshot.spectrum_wavelength_range is not None
            else None
        ),
        "show_error_spectrum": snapshot.show_error_spectrum,
        "show_component_profiles": snapshot.show_component_profiles,
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _decode_snapshot(raw_payload: object) -> AnalysisNavigationSnapshot | None:
    if not isinstance(raw_payload, str):
        return None
    try:
        payload = json.loads(raw_payload)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, Mapping) or payload.get("version") != _PAYLOAD_VERSION:
        return None

    surface_raw = payload.get("surface")
    if isinstance(surface_raw, str):
        try:
            surface = AnalysisSurface(surface_raw)
        except ValueError:
            surface = AnalysisSurface.OVERVIEW
    else:
        surface = AnalysisSurface.OVERVIEW

    sort_column_id, visible_column_ids, column_order = normalize_analysis_overview_column_state(
        sort_column_id=_optional_id(payload.get("sort_column_id")),
        visible_column_ids=_string_tuple(payload.get("visible_column_ids")),
        column_order=_string_tuple(payload.get("column_order")),
    )
    return AnalysisNavigationSnapshot(
        surface=surface,
        focused_region_id=_optional_id(payload.get("focused_region_id")),
        filter_text=_string_or_default(payload.get("filter_text"), ""),
        filter_readiness=_readiness_tuple(payload.get("filter_readiness")),
        sort_column_id=sort_column_id,
        sort_ascending=_bool_or_default(payload.get("sort_ascending"), True),
        visible_column_ids=visible_column_ids,
        column_order=column_order,
        top_visible_region_id=_optional_id(payload.get("top_visible_region_id")),
        spectrum_wavelength_range=_wavelength_range(payload.get("spectrum_wavelength_range")),
        show_error_spectrum=_bool_or_default(payload.get("show_error_spectrum"), True),
        show_component_profiles=_bool_or_default(payload.get("show_component_profiles"), False),
    )


def _optional_id(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _string_or_default(value: object, default: str) -> str:
    return value if isinstance(value, str) else default


def _bool_or_default(value: object, default: bool) -> bool:
    return value if isinstance(value, bool) else default


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str) and item)


def _readiness_tuple(value: object) -> tuple[AnalysisReadiness, ...]:
    """Decode known unique readiness values and ignore future values safely."""
    if not isinstance(value, list):
        return ()
    readiness: list[AnalysisReadiness] = []
    for item in value:
        if not isinstance(item, str):
            continue
        try:
            decoded = AnalysisReadiness(item)
        except ValueError:
            continue
        if decoded not in readiness:
            readiness.append(decoded)
    return tuple(readiness)


def _wavelength_range(value: object) -> tuple[float, float] | None:
    if not isinstance(value, list) or len(value) != 2:
        return None
    low, high = value
    if not isinstance(low, int | float) or isinstance(low, bool):
        return None
    if not isinstance(high, int | float) or isinstance(high, bool):
        return None
    low_value = float(low)
    high_value = float(high)
    if not math.isfinite(low_value) or not math.isfinite(high_value) or low_value >= high_value:
        return None
    return (low_value, high_value)


__all__ = ["AnalysisNavigationSettingsError", "QSettingsAnalysisNavigationAdapter"]
