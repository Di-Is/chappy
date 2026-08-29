"""Start mode operation scenarios."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QT_TRANSLATE_NOOP

from chappy_user_manual_generator.translations import translate_manual_text

if TYPE_CHECKING:
    from chappy_user_manual_generator.models import OperationFlow, ScenarioContext

_EXPORTER_CONTEXT = "ManualExporter"


def _tr(source_text: str) -> str:
    return translate_manual_text(_EXPORTER_CONTEXT, source_text)


def start_data_import(context: ScenarioContext) -> OperationFlow:
    """Workflow for importing data into the application from any mode."""
    context.add_prerequisite(
        _tr(
            QT_TRANSLATE_NOOP(
                "ManualExporter", "chappy is running and the main window is accessible."
            )
        )
    )
    context.add_prerequisite(
        _tr(
            QT_TRANSLATE_NOOP(
                "ManualExporter",
                "A FITS pair of observed flux and observed error, or a chappy project"
                " (.h5), is available.",
            )
        )
    )
    context.add_note(
        _tr(
            QT_TRANSLATE_NOOP(
                "ManualExporter",
                "Save any edits in progress in other modes before loading new data.",
            )
        )
    )
    context.add_note(
        _tr(
            QT_TRANSLATE_NOOP(
                "ManualExporter",
                "File pairs named `*_f.fits` / `*_e.fits` are assigned flux and error"
                " roles automatically. For other names, reselect the observed flux and"
                " error in the dialog.",
            )
        )
    )
    context.add_note(
        _tr(
            QT_TRANSLATE_NOOP(
                "ManualExporter",
                "Supported FITS layouts are a one-dimensional primary HDU (WCS"
                " supported), a binary table with WAVELENGTH/WAVE/LAMBDA/WL and"
                " FLUX/INTENSITY/COUNTS/DATA columns, or a multi-extension file with"
                " WAVELENGTH and FLUX extensions (optionally ERROR/ERR/SIGMA). Files"
                " whose column or extension names do not match cannot be loaded.",
            )
        )
    )
    context.add_note(
        _tr(
            QT_TRANSLATE_NOOP(
                "ManualExporter",
                "Menus are disabled while a dialog stays open. Close the dialog first and retry.",
            )
        )
    )
    context.add_related_link(
        _tr(QT_TRANSLATE_NOOP("ManualExporter", "Start Mode Overview")),
        "../screens/main_window/mode_start/MainWindow.md",
    )
    context.add_related_link(
        _tr(QT_TRANSLATE_NOOP("ManualExporter", "Common Screen Elements")),
        "../screens/main_window/common/MainWindow.md",
    )
    context.add_related_link(
        _tr(QT_TRANSLATE_NOOP("ManualExporter", "Menu List")), "../menus/main_window/menus.md"
    )

    context.add_step(
        _tr(
            QT_TRANSLATE_NOOP(
                "ManualExporter", "Start chappy and confirm the main window responds in any mode."
            )
        ),
        _tr(QT_TRANSLATE_NOOP("ManualExporter", "The File menu and drag & drop are available.")),
    )
    context.add_step(
        _tr(
            QT_TRANSLATE_NOOP(
                "ManualExporter",
                'Choose "File > Open Observation Data…" or "File > Open Project…" from'
                " the menu, or drag & drop files directly onto the start-mode drop zone"
                " or the spectrum view.",
            )
        ),
        _tr(
            QT_TRANSLATE_NOOP(
                "ManualExporter",
                "A file dialog opens, or validation of the dropped files starts, and"
                " the app switches to Analysis Overview for the new data.",
            )
        ),
    )
    context.add_step(
        _tr(
            QT_TRANSLATE_NOOP(
                "ManualExporter",
                "When you specified observed-flux and observed-error FITS files, review"
                " the assignment in the preview, swap the flux and error roles if"
                " needed, and finish loading. A project (.h5) opens as is.",
            )
        ),
        _tr(
            QT_TRANSLATE_NOOP(
                "ManualExporter",
                "The automatically detected pair is shown with radio buttons and can be"
                " swapped if wrong. Pressing OK continues loading.",
            )
        ),
    )
    context.add_step(
        _tr(
            QT_TRANSLATE_NOOP(
                "ManualExporter",
                "After loading completes, focus the spectrum view and confirm the"
                " observed flux, error, and project structure look as expected.",
            )
        ),
        _tr(
            QT_TRANSLATE_NOOP(
                "ManualExporter",
                "The spectrum and Analysis Overview update with the new project, and"
                " the status bar shows a completion message.",
            )
        ),
    )

    return context.build_flow()
