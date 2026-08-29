"""Continuum mode operation scenarios."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QT_TRANSLATE_NOOP

from chappy_user_manual_generator.translations import translate_manual_text

if TYPE_CHECKING:
    from chappy_user_manual_generator.models import OperationFlow, ScenarioContext

_EXPORTER_CONTEXT = "ManualExporter"


def _tr(source_text: str) -> str:
    return translate_manual_text(_EXPORTER_CONTEXT, source_text)


def continuum_adjustment(context: ScenarioContext) -> OperationFlow:
    """Workflow for adjusting continuum control points."""
    context.add_prerequisite(
        _tr(
            QT_TRANSLATE_NOOP(
                "ManualExporter", "Observation data is loaded and Continuum mode is active."
            )
        )
    )
    context.add_prerequisite(
        _tr(
            QT_TRANSLATE_NOOP(
                "ManualExporter",
                "Permission to edit the continuum model (the project is writable).",
            )
        )
    )
    context.add_note(
        _tr(
            QT_TRANSLATE_NOOP(
                "ManualExporter",
                "Auto estimate overwrites the existing control points; back them up"
                " first (for example as CSV) if needed.",
            )
        )
    )
    context.add_note(
        _tr(
            QT_TRANSLATE_NOOP(
                "ManualExporter",
                "After fine-tuning control points, inspect details with wavelength and"
                " flux ranges to keep the model accurate.",
            )
        )
    )
    context.add_related_link(
        _tr(QT_TRANSLATE_NOOP("ManualExporter", "Continuum Mode Screen Layout")),
        "../screens/main_window/mode_continuum/MainWindow.md",
    )
    context.add_related_link(
        _tr(QT_TRANSLATE_NOOP("ManualExporter", "Common Screen Elements")),
        "../screens/main_window/common/MainWindow.md",
    )

    context.add_step(
        _tr(
            QT_TRANSLATE_NOOP(
                "ManualExporter",
                'Open Continuum mode and run "Auto Estimate" from the quick actions card.',
            )
        ),
        _tr(
            QT_TRANSLATE_NOOP(
                "ManualExporter",
                "The continuum curve in the spectrum view and the control point list"
                " update with the estimate.",
            )
        ),
    )
    context.add_step(
        _tr(
            QT_TRANSLATE_NOOP(
                "ManualExporter",
                "Add control points at the wavelengths you need and drag them to adjust"
                " the flux values.",
            )
        ),
        _tr(
            QT_TRANSLATE_NOOP(
                "ManualExporter",
                "Added control points are reflected in the spectrum view immediately"
                " and appended to the list.",
            )
        ),
    )
    context.add_step(
        _tr(
            QT_TRANSLATE_NOOP(
                "ManualExporter",
                "Select control points you no longer need in the list and delete them.",
            )
        ),
        _tr(
            QT_TRANSLATE_NOOP(
                "ManualExporter",
                "The control points are removed and the continuum curve is recalculated.",
            )
        ),
    )
    context.add_step(
        _tr(
            QT_TRANSLATE_NOOP(
                "ManualExporter",
                "Finally, confirm the reset procedures with `Clear Control Points` or"
                " another `Auto Estimate`.",
            )
        ),
        _tr(
            QT_TRANSLATE_NOOP(
                "ManualExporter",
                "The control point list becomes empty or is replaced by the new"
                " estimate, showing how to return to a known state.",
            )
        ),
    )

    return context.build_flow()
