"""Long-form section prose for exporter-rendered manual sections."""

from __future__ import annotations

from PySide6.QtCore import QT_TRANSLATE_NOOP

ANALYSIS_STRUCTURE_HEADING = QT_TRANSLATE_NOOP("ManualExporter", "Analysis Structure")
ANALYSIS_STRUCTURE_INTRO = QT_TRANSLATE_NOOP(
    "ManualExporter",
    "Review and edit absorption region and line hierarchy while keeping spectrum overlays aligned. It corresponds to callout",
)

PARAMETER_DIALOG_HEADING = QT_TRANSLATE_NOOP("ManualExporter", "Parameter Adjustment Dialog")
PARAMETER_DIALOG_INTRO = QT_TRANSLATE_NOOP(
    "ManualExporter",
    'Right-click an absorber component and select "Adjust Parameters..." to open a dialog where you can intuitively adjust parameters with sliders and numeric inputs. Changes are applied to the model immediately. Use the "Fixed" checkbox for each parameter to freeze it during fitting.',
)

VELOCITY_PLOT_HEADING = QT_TRANSLATE_NOOP("ManualExporter", "Velocity Plot")
VELOCITY_PLOT_INTRO = QT_TRANSLATE_NOOP(
    "ManualExporter",
    'In Analysis Region Detail, select a line in the side panel and press the V key, or right-click on the spectrum and choose "Show Velocity Plot (V)", to compare absorption lines in velocity space. The "Display range" control changes the view for every subplot and page without changing the project or analysis settings. The line row\'s "Analysis range [km/s]" value independently defines the interval used for analysis. Compare several lines on the same velocity axis while adding and adjusting components to verify redshift consistency.',
)
VELOCITY_PLOT_OPERATIONS_HEADING = QT_TRANSLATE_NOOP("ManualExporter", "Main Operations")
VELOCITY_PLOT_OPERATION_SOURCES: tuple[str, ...] = (
    QT_TRANSLATE_NOOP(
        "ManualExporter",
        "**Shift+Click**: Hold Shift and click on a subplot to add a new component at that velocity position.",
    ),
    QT_TRANSLATE_NOOP(
        "ManualExporter",
        '**Right-click Menu**: Right-click on a subplot to display the "Add Component Here" menu option.',
    ),
    QT_TRANSLATE_NOOP(
        "ManualExporter",
        "**Drag Center Line**: Drag the component center (yellow for target line, orange for other lines) to adjust its redshift. An overlay shows the target position during the drag.",
    ),
    QT_TRANSLATE_NOOP(
        "ManualExporter",
        "**Page Navigation**: When there are many lines, use the navigation buttons at the bottom to switch between pages.",
    ),
    QT_TRANSLATE_NOOP(
        "ManualExporter",
        "**Display range**: Enter a symmetric view range for all subplots and pages. This display-only control does not change line analysis ranges and is not recorded in scientific Undo.",
    ),
    QT_TRANSLATE_NOOP(
        "ManualExporter",
        "**Fit view to analysis ranges**: Recalculate the display range from the current region's line analysis ranges.",
    ),
)
