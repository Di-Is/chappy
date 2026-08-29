"""User manual documentation profile."""

from __future__ import annotations

from PySide6.QtCore import QT_TRANSLATE_NOOP

from chappy.core.editing_mode import EditingMode
from chappy.gui.modes.common.analysis_navigation import AnalysisSurface
from chappy.i18n import get_language_switcher
from chappy_user_manual_generator.line_database_guide import (
    PAGE_RELATIVE_PATH as LINE_DATABASE_PAGE_PATH,
)
from chappy_user_manual_generator.line_database_guide import (
    SUMMARY_SOURCE as LINE_DATABASE_SUMMARY,
)
from chappy_user_manual_generator.line_database_guide import TITLE_SOURCE as LINE_DATABASE_TITLE
from chappy_user_manual_generator.menu_metadata import MENU_ORDER, menu_action_metadata
from chappy_user_manual_generator.models import (
    CaptureDestination,
    DocManifest,
    IndexEntry,
    IndexSection,
    ManualIndexSpec,
    MenuDocSpec,
    OperationScenarioSpec,
    PanelDestination,
    ScreenDocSpec,
)
from chappy_user_manual_generator.scenarios import (
    analysis_region_detail_workflow,
    analysis_structure_guide,
    continuum_adjustment,
    identify_candidate_workflow,
    start_data_import,
)
from chappy_user_manual_generator.translations import translate_manual_text
from chappy_user_manual_generator.tutorial_guide import (
    PAGE_RELATIVE_PATH as TUTORIAL_GUIDE_PAGE_PATH,
)
from chappy_user_manual_generator.tutorial_guide import SUMMARY_SOURCE as TUTORIAL_GUIDE_SUMMARY
from chappy_user_manual_generator.tutorial_guide import TITLE_SOURCE as TUTORIAL_GUIDE_TITLE

_EXPORTER_CONTEXT = "ManualExporter"

_START = CaptureDestination(EditingMode.START)
_IDENTIFY = CaptureDestination(EditingMode.IDENTIFY)
_ANALYSIS_OVERVIEW = CaptureDestination(
    EditingMode.ANALYSIS, PanelDestination.ANALYSIS_OVERVIEW, AnalysisSurface.OVERVIEW
)
_ANALYSIS_DETAIL = CaptureDestination(
    EditingMode.ANALYSIS, PanelDestination.ANALYSIS_REGION_DETAIL, AnalysisSurface.REGION_DETAIL
)
_ANALYSIS_STRUCTURE = CaptureDestination(
    EditingMode.ANALYSIS, PanelDestination.ANALYSIS_STRUCTURE, AnalysisSurface.OVERVIEW
)
_CONTINUUM = CaptureDestination(EditingMode.CONTINUUM)


def load_user_manual_manifest(version: str) -> DocManifest:
    """Return the default user-manual manifest."""

    def tr(source_text: str) -> str:
        return translate_manual_text(_EXPORTER_CONTEXT, source_text)

    current_lang = get_language_switcher().current_language

    screens = (
        ScreenDocSpec(
            slug="main_window",
            window_type="main",
            fixtures=("analysis-demo",),
            destinations=(
                _START,
                _IDENTIFY,
                _ANALYSIS_OVERVIEW,
                _ANALYSIS_STRUCTURE,
                _ANALYSIS_DETAIL,
                _CONTINUUM,
            ),
            include_common=True,
            output_subdir="screens/main_window",
            destination_fixtures={_IDENTIFY: ("identify-demo",)},
        ),
    )

    start_flow = OperationScenarioSpec(
        slug="start-data-import",
        title=tr(QT_TRANSLATE_NOOP("ManualExporter", "Load Data into the Application")),
        summary=tr(
            QT_TRANSLATE_NOOP(
                "ManualExporter",
                "Steps for importing FITS spectra or project files from any mode.",
            )
        ),
        scenario=start_data_import,
        window_type="main",
        fixtures=(),
        destination=_START,
        output_dir="operations",
    )
    identify_flow = OperationScenarioSpec(
        slug="identify-workflow",
        title=tr(
            QT_TRANSLATE_NOOP("ManualExporter", "Identify Absorption Regions and Line Species")
        ),
        summary=tr(
            QT_TRANSLATE_NOOP(
                "ManualExporter",
                "Use Identify mode to link spectral regions with line species and build absorption regions and lines.",
            )
        ),
        scenario=identify_candidate_workflow,
        window_type="main",
        fixtures=("identify-demo",),
        destination=_IDENTIFY,
        output_dir="operations",
    )
    detail_flow = OperationScenarioSpec(
        slug="analysis-region-detail",
        title=tr(QT_TRANSLATE_NOOP("ManualExporter", "Analyze an Absorption Region")),
        summary=tr(
            QT_TRANSLATE_NOOP(
                "ManualExporter",
                "Fit absorption lines per region, run the optimizer, and deliver the final results.",
            )
        ),
        scenario=analysis_region_detail_workflow,
        window_type="main",
        fixtures=("analysis-demo",),
        destination=_ANALYSIS_DETAIL,
        output_dir="operations",
    )
    structure_flow = OperationScenarioSpec(
        slug="analysis-structure",
        title=tr(QT_TRANSLATE_NOOP("ManualExporter", "Review and Edit Analysis Structure")),
        summary=tr(
            QT_TRANSLATE_NOOP(
                "ManualExporter",
                "Analysis Overview and Structure let you review confirmed regions and edit their line hierarchy before opening Region Detail.",
            )
        ),
        scenario=analysis_structure_guide,
        window_type="main",
        fixtures=("analysis-demo",),
        destination=_ANALYSIS_STRUCTURE,
        output_dir="operations",
    )
    continuum_flow = OperationScenarioSpec(
        slug="continuum-adjustment",
        title=tr(
            QT_TRANSLATE_NOOP(
                "ManualExporter", "Adjust the Continuum Model to Stabilize the Baseline"
            )
        ),
        summary=tr(
            QT_TRANSLATE_NOOP(
                "ManualExporter",
                "Work in Continuum mode to adjust control points, review the interpolation, and stabilise the spectrum’s baseline. This step is normally unnecessary for already-normalized spectra; use it when fit residuals reveal a continuum error.",
            )
        ),
        scenario=continuum_adjustment,
        window_type="main",
        fixtures=("analysis-demo",),
        destination=_CONTINUUM,
        output_dir="operations",
    )

    primary_flows = (start_flow, identify_flow, detail_flow)
    supplemental_flows = (structure_flow, continuum_flow)
    flows = primary_flows + supplemental_flows

    action_meta = menu_action_metadata()

    menu_spec = MenuDocSpec(
        slug="main_menu",
        window_type="main",
        fixtures=("analysis-demo",),
        menu_keys=MENU_ORDER,
        output_subdir="menus/main_window",
        action_modes={key: meta.modes for key, meta in action_meta.items() if meta.modes},
        action_notes={
            "undo": tr(
                QT_TRANSLATE_NOOP("ManualExporter", "Work in progress. Not available yet.")
            ),
            "redo": tr(
                QT_TRANSLATE_NOOP("ManualExporter", "Work in progress. Not available yet.")
            ),
            "copy": tr(
                QT_TRANSLATE_NOOP("ManualExporter", "Work in progress. Not available yet.")
            ),
            "paste": tr(
                QT_TRANSLATE_NOOP("ManualExporter", "Work in progress. Not available yet.")
            ),
            "delete": tr(
                QT_TRANSLATE_NOOP("ManualExporter", "Work in progress. Not available yet.")
            ),
            "zoom_in": tr(
                QT_TRANSLATE_NOOP(
                    "ManualExporter",
                    "To zoom by dragging on the spectrum, turn on Zoom Area in the context bar.",
                )
            ),
            "auto_adjust_flux": tr(
                QT_TRANSLATE_NOOP(
                    "ManualExporter",
                    "Equivalent to the `Ctrl+A` shortcut (`⌘A` on macOS) on the spectrum view.",
                )
            ),
            "open_line_database_folder": tr(
                QT_TRANSLATE_NOOP(
                    "ManualExporter",
                    "Place `spectral_lines.csv` in this folder to replace the line database,"
                    " then restart Chappy.",
                )
            ),
            "resolution_settings": tr(
                QT_TRANSLATE_NOOP(
                    "ManualExporter",
                    "Use before fitting in Analysis Region Detail to confirm instrument resolution.",
                )
            ),
            "preset_management": tr(
                QT_TRANSLATE_NOOP(
                    "ManualExporter", "Opens the Preset Management dialog in Identify mode."
                )
            ),
        },
        menu_descriptions={
            "__overview__": tr(
                QT_TRANSLATE_NOOP(
                    "ManualExporter",
                    "This section summarises each menu's role and common shortcuts.",
                )
            ),
            "file": tr(
                QT_TRANSLATE_NOOP("ManualExporter", "Create, open, save, or exit a project.")
            ),
            "edit": tr(
                QT_TRANSLATE_NOOP(
                    "ManualExporter",
                    "Edit operations such as undo/redo (some items are not yet available).",
                )
            ),
            "view": tr(
                QT_TRANSLATE_NOOP(
                    "ManualExporter", "Adjust spectrum display ranges and related view settings."
                )
            ),
            "mode": tr(QT_TRANSLATE_NOOP("ManualExporter", "Switch analysis modes.")),
            "settings": tr(QT_TRANSLATE_NOOP("ManualExporter", "Open settings dialogs.")),
            "help": tr(
                QT_TRANSLATE_NOOP(
                    "ManualExporter", "Open the manual or view application information."
                )
            ),
        },
    )

    index_spec = ManualIndexSpec(
        filename="index.md",
        title=tr(QT_TRANSLATE_NOOP("ManualExporter", "Chappy User Manual")),
        overview=(
            tr(
                QT_TRANSLATE_NOOP(
                    "ManualExporter", "A guide to using Chappy and understanding each screen."
                )
            ),
        ),
        sections=(
            IndexSection(
                heading=tr(QT_TRANSLATE_NOOP("ManualExporter", "Quick Start")),
                intro=tr(
                    QT_TRANSLATE_NOOP(
                        "ManualExporter",
                        "Step-by-step walkthrough of common operations. To switch modes, click one of the mode buttons (Identify, Analysis, Continuum) in the context bar, or select from the Mode menu.",
                    )
                ),
                entries=tuple(
                    IndexEntry(
                        title=flow.title,
                        path=f"operations/{flow.slug}.md",
                        description=flow.summary,
                    )
                    for flow in primary_flows
                ),
            ),
            IndexSection(
                heading=tr(QT_TRANSLATE_NOOP("ManualExporter", "Supplemental Workflows")),
                intro=tr(
                    QT_TRANSLATE_NOOP(
                        "ManualExporter",
                        "Optional flows to review results or apply additional adjustments after completing the essentials.",
                    )
                ),
                entries=tuple(
                    IndexEntry(
                        title=flow.title,
                        path=f"operations/{flow.slug}.md",
                        description=flow.summary,
                    )
                    for flow in supplemental_flows
                ),
            ),
            IndexSection(
                heading=tr(QT_TRANSLATE_NOOP("ManualExporter", "Screen Guide")),
                intro=tr(
                    QT_TRANSLATE_NOOP(
                        "ManualExporter",
                        "Annotated screenshots with the roles of buttons, menus, and panels.",
                    )
                ),
                entries=(
                    IndexEntry(
                        title=tr(QT_TRANSLATE_NOOP("ManualExporter", "Common Screen Elements")),
                        path="screens/main_window/common/MainWindow.md",
                        description=tr(
                            QT_TRANSLATE_NOOP(
                                "ManualExporter", "Items commonly available in the main window."
                            )
                        ),
                    ),
                    IndexEntry(
                        title=tr(QT_TRANSLATE_NOOP("ManualExporter", "Start Mode Overview")),
                        path="screens/main_window/mode_start/MainWindow.md",
                        description=tr(
                            QT_TRANSLATE_NOOP(
                                "ManualExporter",
                                "Initial layout and primary actions shown before loading data. data.",
                            )
                        ),
                    ),
                    IndexEntry(
                        title=tr(QT_TRANSLATE_NOOP("ManualExporter", "Identify Mode Screen")),
                        path="screens/main_window/mode_identify/MainWindow.md",
                        description=tr(
                            QT_TRANSLATE_NOOP(
                                "ManualExporter",
                                "Candidate table and velocity plot used in identification.",
                            )
                        ),
                    ),
                    IndexEntry(
                        title=tr(QT_TRANSLATE_NOOP("ManualExporter", "Analysis Overview")),
                        path="screens/main_window/mode_analysis_overview/MainWindow.md",
                        description=tr(
                            QT_TRANSLATE_NOOP(
                                "ManualExporter",
                                "Review analysis readiness, fit results, and the next action for every region.",
                            )
                        ),
                    ),
                    IndexEntry(
                        title=tr(QT_TRANSLATE_NOOP("ManualExporter", "Analysis Structure")),
                        path="screens/main_window/mode_analysis_structure/MainWindow.md",
                        description=tr(
                            QT_TRANSLATE_NOOP(
                                "ManualExporter",
                                "Edit the region and line hierarchy from Analysis Overview.",
                            )
                        ),
                    ),
                    IndexEntry(
                        title=tr(QT_TRANSLATE_NOOP("ManualExporter", "Analysis Region Detail")),
                        path="screens/main_window/mode_analysis_region_detail/MainWindow.md",
                        description=tr(
                            QT_TRANSLATE_NOOP(
                                "ManualExporter",
                                "Tune parameters, masks, and fit results for one region.",
                            )
                        ),
                    ),
                    IndexEntry(
                        title=tr(QT_TRANSLATE_NOOP("ManualExporter", "Continuum Mode Screen")),
                        path="screens/main_window/mode_continuum/MainWindow.md",
                        description=tr(
                            QT_TRANSLATE_NOOP(
                                "ManualExporter", "Controls for editing the continuum."
                            )
                        ),
                    ),
                ),
            ),
            IndexSection(
                heading=tr(QT_TRANSLATE_NOOP("ManualExporter", "Menu Guide")),
                intro=tr(
                    QT_TRANSLATE_NOOP(
                        "ManualExporter", "Explanation of the top menus and shortcuts."
                    )
                ),
                entries=(
                    IndexEntry(
                        title=tr(QT_TRANSLATE_NOOP("ManualExporter", "Menu List")),
                        path="menus/main_window/menus.md",
                        description=tr(
                            QT_TRANSLATE_NOOP(
                                "ManualExporter",
                                "Review key items under File, Edit, View, Mode, Settings, and Help.",
                            )
                        ),
                    ),
                ),
            ),
            IndexSection(
                heading=tr(QT_TRANSLATE_NOOP("ManualExporter", "Shortcuts")),
                intro=tr(
                    QT_TRANSLATE_NOOP(
                        "ManualExporter", "Quick reference of frequently used shortcuts."
                    )
                ),
                entries=(
                    IndexEntry(
                        title=tr(QT_TRANSLATE_NOOP("ManualExporter", "Shortcut List")),
                        path="menus/main_window/shortcuts.md",
                        description=tr(
                            QT_TRANSLATE_NOOP(
                                "ManualExporter", "Review common shortcut keys at a glance."
                            )
                        ),
                    ),
                ),
            ),
            IndexSection(
                heading=tr(QT_TRANSLATE_NOOP("ManualExporter", "Guided Tutorial")),
                intro=tr(
                    QT_TRANSLATE_NOOP(
                        "ManualExporter",
                        "The in-app guided tour: what it teaches and how to run it again.",
                    )
                ),
                entries=(
                    IndexEntry(
                        title=tr(TUTORIAL_GUIDE_TITLE),
                        path=TUTORIAL_GUIDE_PAGE_PATH,
                        description=tr(TUTORIAL_GUIDE_SUMMARY),
                    ),
                ),
            ),
            IndexSection(
                heading=tr(QT_TRANSLATE_NOOP("ManualExporter", "Data Files")),
                intro=tr(
                    QT_TRANSLATE_NOOP(
                        "ManualExporter",
                        "Reference for the data files chappy reads when it starts.",
                    )
                ),
                entries=(
                    IndexEntry(
                        title=tr(LINE_DATABASE_TITLE),
                        path=LINE_DATABASE_PAGE_PATH,
                        description=tr(LINE_DATABASE_SUMMARY),
                    ),
                ),
            ),
            IndexSection(
                heading=tr(QT_TRANSLATE_NOOP("ManualExporter", "Troubleshooting")),
                intro=tr(
                    QT_TRANSLATE_NOOP(
                        "ManualExporter", "Checks and tips when something goes wrong."
                    )
                ),
                entries=(
                    IndexEntry(
                        title=tr(
                            QT_TRANSLATE_NOOP(
                                "ManualExporter", "Troubleshooting (Work in Progress)"
                            )
                        ),
                        path="../user_manual.md",
                        description=tr(
                            QT_TRANSLATE_NOOP(
                                "ManualExporter",
                                "Please refer to the interim troubleshooting notes.",
                            )
                        ),
                    ),
                ),
            ),
            IndexSection(
                heading=tr(QT_TRANSLATE_NOOP("ManualExporter", "Glossary")),
                intro=tr(
                    QT_TRANSLATE_NOOP(
                        "ManualExporter",
                        "Terms grouped by category (Data/Save, View/Check, Continuum, Identification, Analysis, Analysis Unit, Settings). Listed in Japanese and English.",
                    )
                ),
                entries=(
                    IndexEntry(
                        title=tr(QT_TRANSLATE_NOOP("ManualExporter", "Glossary (English)")),
                        path=(
                            "glossary/glossary.ja.md"
                            if current_lang == "ja"
                            else "glossary/glossary.en.md"
                        ),
                        description=tr(
                            QT_TRANSLATE_NOOP(
                                "ManualExporter", "Category-sorted glossary (English)."
                            )
                        ),
                    ),
                ),
            ),
        ),
        footer=(),
    )

    return DocManifest(
        version_label=version, screens=screens, flows=flows, menus=(menu_spec,), index=index_spec
    )
