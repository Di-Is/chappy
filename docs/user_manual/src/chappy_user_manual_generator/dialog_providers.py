"""Factory functions that construct dialogs for documentation capture.

This module intentionally avoids executing modal dialog event loops. Providers
return a constructed widget that can be shown briefly for layout and then
captured by the generic exporter.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable  # noqa: UP035

from PySide6.QtCore import QT_TRANSLATE_NOOP
from PySide6.QtWidgets import QTableWidget

from chappy.gui.dialogs.close_project_dialog import CloseProjectDialog
from chappy.gui.dialogs.cosmology_dialog import CosmologyDialog
from chappy.gui.dialogs.language_settings_dialog import LanguageSettingsDialog
from chappy.gui.dialogs.line_selection_dialog import LineSelectionDialog
from chappy.gui.dialogs.observation_data_dialog import ObservationDataDialog
from chappy.gui.dialogs.resolution_dialog import ResolutionDialog
from chappy.gui.modes.identify.presets.preset_list_dialog import PresetListDialog
from chappy_user_manual_generator.translations import translate_manual_text

if TYPE_CHECKING:
    from PySide6.QtWidgets import QMainWindow, QWidget

    from chappy.core.atomic_data import AtomicLineData

_EXPORTER_CONTEXT = "ManualExporter"
_PRESET_DOC_LINKED_LINE_IDS = ("703f975612c284c7", "2f22adc74ae6712b")
_PRESET_DOC_SUGGESTED_LINE_IDS = ("9fe527b438587d9e", "6ef4702248c8800f")


@dataclass(frozen=True)
class DialogProvider:
    """Descriptor for exporting dialog documentation."""

    factory: Callable[[QMainWindow], QWidget]
    label: str | None = None
    label_getter: Callable[[QWidget], str] | None = None


def _resolution_dialog(parent: QMainWindow) -> QWidget:
    """Construct ResolutionDialog with lightweight defaults."""
    language_switcher = getattr(parent, "_language_switcher", None)
    settings = getattr(parent, "_resolution_settings", None)
    return ResolutionDialog(parent, settings=settings, language_switcher=language_switcher)


def _close_project_dialog(parent: QMainWindow) -> QWidget:
    """Construct CloseProjectDialog with a representative project name."""
    return CloseProjectDialog(parent, project_name="sample_project")


def _cosmology_dialog(parent: QMainWindow) -> QWidget:
    """Construct CosmologyDialog with defaults."""
    return CosmologyDialog(parent)


def _language_dialog(parent: QMainWindow) -> QWidget:
    """Construct LanguageSettingsDialog."""
    language_switcher = getattr(parent, "_language_switcher", None)
    return LanguageSettingsDialog(parent, language_switcher=language_switcher)


def _preset_list_dialog(parent: QMainWindow) -> QWidget:
    """Construct PresetListDialog with editable linked-line documentation data."""
    atomic_data = _atomic_data(parent)
    line_ids = (*_PRESET_DOC_LINKED_LINE_IDS, *_PRESET_DOC_SUGGESTED_LINE_IDS)
    missing_ids = [line_id for line_id in line_ids if atomic_data.get_line_by_id(line_id) is None]
    if missing_ids:
        msg = f"preset documentation fixture is missing atomic lines: {missing_ids}"
        raise RuntimeError(msg)

    preset_store = parent.preset_store
    preset_name = translate_manual_text(
        _EXPORTER_CONTEXT, QT_TRANSLATE_NOOP("ManualExporter", "Linked metal lines example")
    )
    preset = next(
        (candidate for candidate in preset_store.list_presets() if candidate.name == preset_name),
        None,
    )
    if preset is None:
        preset = preset_store.create_custom_preset(preset_name, line_ids=line_ids)
        preset_store.add_tie_group(preset.id, _PRESET_DOC_LINKED_LINE_IDS)
    preset_store.set_current_preset(preset.id)

    dialog = PresetListDialog(parent, preset_store, atomic_data=atomic_data)
    table = dialog.findChild(QTableWidget, "presetLineTable")
    if table is None:
        msg = "preset documentation dialog does not expose presetLineTable"
        raise RuntimeError(msg)
    table.selectRow(0)
    return dialog


def _line_selection_dialog(parent: QMainWindow) -> QWidget:
    """Construct LineSelectionDialog without preset context."""
    return LineSelectionDialog(parent, atomic_data=_atomic_data(parent))


def _atomic_data(parent: QMainWindow) -> AtomicLineData:
    """Fetch the atomic line repository the main window was built with."""
    atomic_data = getattr(parent, "_atomic_data", None)
    if atomic_data is None:
        msg = "main window does not expose atomic data for dialog capture"
        raise TypeError(msg)
    return atomic_data


def known_dialog_providers() -> dict[str, DialogProvider]:
    """Return mapping from action keys to dialog provider callables."""

    def tr(source_text: str) -> str:
        return translate_manual_text(_EXPORTER_CONTEXT, source_text)

    return {
        # File menu
        "open_observation_data": DialogProvider(
            factory=ObservationDataDialog,
            label=tr(QT_TRANSLATE_NOOP("ManualExporter", "Loading Observation Data")),
        ),
        "close_project": DialogProvider(
            factory=_close_project_dialog,
            label=tr(QT_TRANSLATE_NOOP("ManualExporter", "Closing a Project")),
        ),
        # Settings menu
        "resolution_settings": DialogProvider(
            factory=_resolution_dialog,
            label=tr(QT_TRANSLATE_NOOP("ManualExporter", "Instrument Resolution Settings")),
        ),
        "cosmology_settings": DialogProvider(
            factory=_cosmology_dialog,
            label=tr(QT_TRANSLATE_NOOP("ManualExporter", "Cosmology Parameter Settings")),
        ),
        "language_settings": DialogProvider(
            factory=_language_dialog,
            label=tr(QT_TRANSLATE_NOOP("ManualExporter", "Language Settings")),
        ),
        "preset_management": DialogProvider(
            factory=_preset_list_dialog,
            label=tr(QT_TRANSLATE_NOOP("ManualExporter", "Preset Management")),
        ),
        "line_selection": DialogProvider(
            factory=_line_selection_dialog, label_getter=lambda widget: widget.windowTitle()
        ),
    }
