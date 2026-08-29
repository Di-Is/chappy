"""Analysis Structure operation scenarios."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QT_TRANSLATE_NOOP
from PySide6.QtWidgets import QTreeWidget

from chappy_user_manual_generator.data.analysis_structure_operations import (
    render_analysis_structure_operations_table,
)
from chappy_user_manual_generator.translations import translate_manual_text

if TYPE_CHECKING:
    from chappy_user_manual_generator.models import OperationFlow, ScenarioContext

_EXPORTER_CONTEXT = "ManualExporter"


def _tr(source_text: str) -> str:
    return translate_manual_text(_EXPORTER_CONTEXT, source_text)


def analysis_structure_guide(context: ScenarioContext) -> OperationFlow:
    """Catalog-style guidance for Analysis Structure management tasks."""
    window = context.window
    tree = window.findChild(QTreeWidget, "analysisStructureTree")
    if tree is None:
        msg = "analysisStructureTree was not found in the current window."
        raise RuntimeError(msg)
    if tree.topLevelItemCount() == 0:
        context.app.processEvents()

    context.add_prerequisite(
        _tr(QT_TRANSLATE_NOOP("ManualExporter", "A project containing regions and lines is open."))
    )
    context.add_prerequisite(
        _tr(QT_TRANSLATE_NOOP("ManualExporter", "Analysis Structure is open from Overview."))
    )

    overview = context.add_section(
        _tr(QT_TRANSLATE_NOOP("ManualExporter", "Reading the Screen")),
        _tr(
            QT_TRANSLATE_NOOP(
                "ManualExporter",
                "Overview of Analysis Structure and its relationship to the spectrum.",
            )
        ),
    )
    overview.add_item(
        _tr(QT_TRANSLATE_NOOP("ManualExporter", "Analysis Structure panel")),
        _tr(
            QT_TRANSLATE_NOOP(
                "ManualExporter",
                "Lists the hierarchy of regions and lines; status badges show counts"
                " and wavelength ranges.",
            )
        ),
    )
    overview.add_item(
        _tr(QT_TRANSLATE_NOOP("ManualExporter", "Spectrum view")),
        _tr(
            QT_TRANSLATE_NOOP(
                "ManualExporter",
                "Moves to the wavelength range of the selected region or line and"
                " overlays absorption-line profiles for checking.",
            )
        ),
    )
    overview.add_item(
        _tr(QT_TRANSLATE_NOOP("ManualExporter", "Detail panel")),
        _tr(
            QT_TRANSLATE_NOOP(
                "ManualExporter",
                "Shows the transition list and measurements to review parameters"
                " confirmed in Identify mode.",
            )
        ),
    )
    overview.add_item(
        _tr(QT_TRANSLATE_NOOP("ManualExporter", "Context menu")),
        _tr(
            QT_TRANSLATE_NOOP(
                "ManualExporter",
                "The Structure panel's right-click menu provides management operations"
                " such as rename, merge, and delete.",
            )
        ),
    )

    operations = context.add_section(
        _tr(QT_TRANSLATE_NOOP("ManualExporter", "Task-based Operation Guide")),
        _tr(
            QT_TRANSLATE_NOOP(
                "ManualExporter",
                "Pick the management operation you need. All are optional and help you"
                " inventory and organise regions and lines.",
            )
        ),
    )
    operations.add_block(render_analysis_structure_operations_table())

    context.add_related_link(
        _tr(QT_TRANSLATE_NOOP("ManualExporter", "Analysis Structure Screen")),
        "../screens/main_window/mode_analysis_structure/MainWindow.md",
    )
    context.add_related_link(
        _tr(QT_TRANSLATE_NOOP("ManualExporter", "Common Screen Elements")),
        "../screens/main_window/common/MainWindow.md",
    )
    context.add_related_link(
        _tr(QT_TRANSLATE_NOOP("ManualExporter", "Analysis Overview")),
        "../screens/main_window/mode_analysis_overview/MainWindow.md",
    )

    return context.build_flow()
