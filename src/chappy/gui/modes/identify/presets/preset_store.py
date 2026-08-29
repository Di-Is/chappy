"""Qt-aware preset store facade for identify mode."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QT_TRANSLATE_NOOP, QCoreApplication, QObject, Signal, Slot

from chappy.i18n import get_language_switcher

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from chappy.application.ports import PresetStorePort
    from chappy.core.presets import (
        LineIdentifier,
        Preset,
        PresetImportSummary,
        PresetTieGroup,
        TranslateFunc,
    )
    from chappy.i18n.language_switcher import LanguageSwitcher

logger = logging.getLogger(__name__)

_PRESET_SOURCE_TEXTS = (
    str(QT_TRANSLATE_NOOP("PresetStore", "Lyman Series")),
    str(QT_TRANSLATE_NOOP("PresetStore", "Principal H I Lyman transitions for quick selection.")),
    str(QT_TRANSLATE_NOOP("PresetStore", "Metal Lines")),
    str(QT_TRANSLATE_NOOP("PresetStore", "Metal doublets.")),
)


class IdentifyPresetStore(QObject):
    """Expose preset operations with Qt signals for identify GUI consumers."""

    presets_changed = Signal()
    preset_updated = Signal(str)
    selection_changed = Signal(str)

    def __init__(
        self,
        store: PresetStorePort,
        parent: QObject | None = None,
        language_switcher: LanguageSwitcher | None = None,
    ) -> None:
        """Initialize the Qt preset store facade."""
        super().__init__(parent)

        self._language_switcher = language_switcher or get_language_switcher(self)
        translator = self._build_translator()

        store.set_translator(translator)
        self._store = store
        self._language_switcher.language_changed.connect(self._on_language_changed)

    def list_presets(self) -> list[Preset]:
        """Return snapshot list of all presets."""
        return self._store.list_presets()

    def get_preset(self, preset_id: str) -> Preset | None:
        """Return preset copy matching identifier if found."""
        return self._store.get_preset(preset_id)

    def preset_revision(self, preset_id: str) -> float | None:
        """Return the preset's updated-at token without cloning the preset."""
        return self._store.preset_revision(preset_id)

    @property
    def current_preset_id(self) -> str | None:
        """Return identifier of the currently selected preset."""
        return self._store.current_preset_id

    def set_current_preset(self, preset_id: str | None) -> None:
        """Update active preset selection and emit change signal."""
        if preset_id == self._store.current_preset_id:
            return
        self._store.set_current_preset(preset_id)
        self.selection_changed.emit(preset_id)

    def create_custom_preset(
        self, name: str, *, line_ids: Sequence[LineIdentifier] | None = None
    ) -> Preset:
        """Create a custom preset and broadcast creation events."""
        preset = self._store.create_custom_preset(name, line_ids=line_ids)
        self.presets_changed.emit()
        self.selection_changed.emit(preset.id)
        return preset

    def rename_preset(self, preset_id: str, new_name: str) -> Preset:
        """Rename preset and notify listeners."""
        preset = self._store.rename_preset(preset_id, new_name)
        self.presets_changed.emit()
        self.preset_updated.emit(preset_id)
        return preset

    def duplicate_preset(self, preset_id: str) -> Preset:
        """Duplicate an existing preset and select the copy."""
        preset = self._store.duplicate_preset(preset_id)
        self.presets_changed.emit()
        self.selection_changed.emit(preset.id)
        return preset

    def delete_preset(self, preset_id: str) -> None:
        """Remove a preset and adjust current selection as needed."""
        self._store.delete_preset(preset_id)
        self.presets_changed.emit()
        self.selection_changed.emit(self._store.current_preset_id)

    def add_tie_group(self, preset_id: str, line_ids: Sequence[LineIdentifier]) -> PresetTieGroup:
        """Add a tie group and notify identify-mode consumers."""
        group = self._store.add_tie_group(preset_id, line_ids)
        self.preset_updated.emit(preset_id)
        return group

    def replace_tie_group_members(
        self, preset_id: str, group_uid: str, line_ids: Sequence[LineIdentifier]
    ) -> PresetTieGroup:
        """Replace a tie group's members and notify identify-mode consumers."""
        group = self._store.replace_tie_group_members(preset_id, group_uid, line_ids)
        self.preset_updated.emit(preset_id)
        return group

    def remove_tie_group(self, preset_id: str, group_uid: str) -> None:
        """Remove a tie group and notify identify-mode consumers."""
        self._store.remove_tie_group(preset_id, group_uid)
        self.preset_updated.emit(preset_id)

    def add_lines(
        self, preset_id: str, line_ids: Sequence[LineIdentifier]
    ) -> list[LineIdentifier]:
        """Add line identifiers to a preset and emit update signal."""
        added = self._store.add_lines(preset_id, line_ids)
        if added:
            logger.debug("Added %d lines to preset %s", len(added), preset_id)
            self.preset_updated.emit(preset_id)
        return added

    def add_lines_with_tie_groups(
        self,
        preset_id: str,
        line_ids: Sequence[LineIdentifier],
        tie_groups: Sequence[Sequence[LineIdentifier]],
    ) -> list[LineIdentifier]:
        """Add lines and declarative groups in one operation."""
        before = self._store.preset_revision(preset_id)
        added = self._store.add_lines_with_tie_groups(preset_id, line_ids, tie_groups)
        if self._store.preset_revision(preset_id) != before:
            self.preset_updated.emit(preset_id)
        return added

    def remove_lines(
        self, preset_id: str, line_ids: Sequence[LineIdentifier]
    ) -> list[LineIdentifier]:
        """Remove line identifiers from a preset and emit update signal."""
        removed = self._store.remove_lines(preset_id, line_ids)
        if removed:
            logger.debug("Removed %d lines from preset %s", len(removed), preset_id)
            self.preset_updated.emit(preset_id)
        return removed

    def set_baseline(self, preset_id: str, line_id: LineIdentifier | None) -> None:
        """Persist baseline change and notify observers."""
        self._store.set_baseline(preset_id, line_id)
        self.preset_updated.emit(preset_id)

    def _build_translator(self) -> TranslateFunc:
        def _translate(source_text: str) -> str:
            return QCoreApplication.translate("PresetStore", source_text)

        return _translate

    @Slot(str)
    def _on_language_changed(self, _code: str) -> None:
        translator = self._build_translator()
        self._store.set_translator(translator)
        self.presets_changed.emit()
        self.selection_changed.emit(self._store.current_preset_id)

    def export_presets(
        self, destination: str | Path, preset_ids: Sequence[str] | None = None
    ) -> Path:
        """Delegate to store for exporting presets."""
        return self._store.export_presets(destination, preset_ids=preset_ids)

    def import_presets(self, source: str | Path) -> PresetImportSummary:
        """Import presets via the underlying store and emit change signals."""
        summary = self._store.import_presets(source)
        if summary.imported:
            self.presets_changed.emit()
        return summary


__all__ = ["IdentifyPresetStore"]
