"""Reference page describing the in-app guided tutorial (tutorial tour)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QT_TRANSLATE_NOOP

from chappy_user_manual_generator.markdown import MarkdownTableBuilder, format_markdown_text
from chappy_user_manual_generator.translations import translate_manual_text

if TYPE_CHECKING:
    from pathlib import Path

_EXPORTER_CONTEXT = "ManualExporter"

PAGE_RELATIVE_PATH = "reference/tutorial.md"

TITLE_SOURCE = QT_TRANSLATE_NOOP("ManualExporter", "Guided Tutorial")
SUMMARY_SOURCE = QT_TRANSLATE_NOOP(
    "ManualExporter",
    "What the in-app guided tour teaches, how it starts, and how to run it again from the"
    " Help menu.",
)

_INTRO = QT_TRANSLATE_NOOP(
    "ManualExporter",
    "chappy includes a guided tour: coach-mark bubbles that highlight one widget at a time and"
    " walk you through the analysis workflow on the bundled sample spectrum of quasar"
    " Q0329-385. It never touches your own data, because it opens the sample spectrum itself"
    " before it starts.",
)

_STARTING_HEADING = QT_TRANSLATE_NOOP("ManualExporter", "Starting the Tour")
_STARTING_INTRO = QT_TRANSLATE_NOOP(
    "ManualExporter",
    "The tour is offered through the same [Welcome to chappy] dialog on both occasions below.",
)
_STARTING_ITEMS = (
    QT_TRANSLATE_NOOP(
        "ManualExporter",
        "On the very first launch, chappy shows the dialog automatically, once. If the bundled"
        " sample spectrum is not part of this installation, the dialog still appears but its"
        " two walkthrough buttons are disabled; you can still open your own data from [File] >"
        " [Open Observation Data].",
    ),
    QT_TRANSLATE_NOOP(
        "ManualExporter",
        "Afterward, select [Help] > [Tutorial] to reopen the same dialog at any time and start"
        " the tour again.",
    ),
)
_STARTING_NOTE = QT_TRANSLATE_NOOP(
    "ManualExporter",
    "Choosing a walkthrough opens the sample spectrum (flux and error FITS pair, resolving"
    " power already set) before the first coach mark appears, replacing whatever project was"
    " open.",
)

_WALKTHROUGHS_HEADING = QT_TRANSLATE_NOOP(
    "ManualExporter", "Short Walkthrough or Full Walkthrough"
)
_WALKTHROUGHS_INTRO = QT_TRANSLATE_NOOP(
    "ManualExporter", "The dialog offers two lengths; both start from the same first chapter."
)
_WALKTHROUGH_COLUMN = QT_TRANSLATE_NOOP("ManualExporter", "Dialog Button")
_COVERAGE_COLUMN = QT_TRANSLATE_NOOP("ManualExporter", "Coverage")
_CHAPTER_COUNT_COLUMN = QT_TRANSLATE_NOOP("ManualExporter", "Chapters")
_WALKTHROUGHS = (
    (
        QT_TRANSLATE_NOOP("ManualExporter", "[Try the Essential Workflow]"),
        QT_TRANSLATE_NOOP(
            "ManualExporter",
            "The minimal loop: load data, identify one absorption system, fit it, save the"
            " project.",
        ),
        "5",
    ),
    (
        QT_TRANSLATE_NOOP("ManualExporter", "[Explore All Features]"),
        QT_TRANSLATE_NOOP(
            "ManualExporter",
            "Everything in the essential workflow plus building a custom preset, the velocity"
            " plot, merging regions, tying ions together, and continuum correction.",
        ),
        "10",
    ),
)

_CHAPTERS_HEADING = QT_TRANSLATE_NOOP("ManualExporter", "Chapters")
_CHAPTERS_INTRO = QT_TRANSLATE_NOOP(
    "ManualExporter",
    "Chapters run in the order below. A chapter marked Full only is skipped in the essential"
    " workflow.",
)
_NUMBER_COLUMN = QT_TRANSLATE_NOOP("ManualExporter", "No.")
_CHAPTER_COLUMN = QT_TRANSLATE_NOOP("ManualExporter", "Chapter")
_INCLUDED_COLUMN = QT_TRANSLATE_NOOP("ManualExporter", "Included In")
_LEARN_COLUMN = QT_TRANSLATE_NOOP("ManualExporter", "What You Learn")
_BOTH_WALKTHROUGHS = QT_TRANSLATE_NOOP("ManualExporter", "Essential and Full")
_FULL_ONLY = QT_TRANSLATE_NOOP("ManualExporter", "Full only")
_CHAPTERS = (
    (
        QT_TRANSLATE_NOOP("ManualExporter", "Getting Started"),
        _BOTH_WALKTHROUGHS,
        QT_TRANSLATE_NOOP(
            "ManualExporter",
            "Navigating the loaded spectrum: wheel/keyboard zoom and pan, rectangle zoom,"
            " undo/redo, typing an exact wavelength range, [Auto Adjust], [Reset View], and"
            " where to open your own data instead.",
        ),
    ),
    (
        QT_TRANSLATE_NOOP("ManualExporter", "Identifying Absorption Systems"),
        _BOTH_WALKTHROUGHS,
        QT_TRANSLATE_NOOP(
            "ManualExporter",
            'Selecting the built-in "Metal Lines" preset, choosing a reference line, marking'
            " a candidate absorption system on the spectrum, and confirming it as a region.",
        ),
    ),
    (
        QT_TRANSLATE_NOOP("ManualExporter", "Reviewing Analysis Readiness"),
        _BOTH_WALKTHROUGHS,
        QT_TRANSLATE_NOOP(
            "ManualExporter",
            "Selecting the confirmed region in Analysis Overview and reading its fit readiness.",
        ),
    ),
    (
        QT_TRANSLATE_NOOP("ManualExporter", "Fitting a Region in Detail"),
        _BOTH_WALKTHROUGHS,
        QT_TRANSLATE_NOOP(
            "ManualExporter",
            "Opening Analysis Region Detail, adding a fit component to a line, running the"
            " optimizer, and reading the fit outcome.",
        ),
    ),
    (
        QT_TRANSLATE_NOOP("ManualExporter", "Building a Custom Preset"),
        _FULL_ONLY,
        QT_TRANSLATE_NOOP(
            "ManualExporter",
            "Creating a named preset, adding Fe II and Mg II lines to it, linking and"
            " unlinking lines into tie groups, and choosing its reference line.",
        ),
    ),
    (
        QT_TRANSLATE_NOOP("ManualExporter", "Identifying with the Velocity Plot"),
        _FULL_ONLY,
        QT_TRANSLATE_NOOP(
            "ManualExporter",
            "Selecting the custom preset, moving to a second, hidden absorption system in the"
            " sample, and using the velocity plot to identify and confirm it.",
        ),
    ),
    (
        QT_TRANSLATE_NOOP("ManualExporter", "Merging Regions"),
        _FULL_ONLY,
        QT_TRANSLATE_NOOP(
            "ManualExporter",
            "Opening Analysis Structure for a region and merging it with another so a single"
            " region spans more than one ion species.",
        ),
    ),
    (
        QT_TRANSLATE_NOOP("ManualExporter", "Tying Ions and Fitting Together"),
        _FULL_ONLY,
        QT_TRANSLATE_NOOP(
            "ManualExporter",
            "Adding a fit component to one ion, tying its redshift to another ion in the same"
            " region, and running a joint fit across both.",
        ),
    ),
    (
        QT_TRANSLATE_NOOP("ManualExporter", "Correcting the Continuum"),
        _FULL_ONLY,
        QT_TRANSLATE_NOOP(
            "ManualExporter",
            "Switching to Continuum mode and running [Auto Estimate] to fit the continuum"
            " around the spectrum.",
        ),
    ),
    (
        QT_TRANSLATE_NOOP("ManualExporter", "Saving Your Work"),
        _BOTH_WALKTHROUGHS,
        QT_TRANSLATE_NOOP(
            "ManualExporter",
            "Saving the project, and a recap of the load, identify, review, fit, and save"
            " loop just completed.",
        ),
    ),
)

_PREREQUISITES_HEADING = QT_TRANSLATE_NOOP("ManualExporter", "Chapter Prerequisites")
_PREREQUISITES_INTRO = QT_TRANSLATE_NOOP(
    "ManualExporter",
    "Five chapters open only after earlier chapters have left the project in the state they"
    " need. When a chapter's prerequisite is unmet, the tour shows a warning bubble instead of"
    " that chapter's first step, offering [Back] to return to the previous step or [Continue"
    " anyway] to skip straight past the chapter.",
)
_PREREQ_CHAPTER_COLUMN = QT_TRANSLATE_NOOP("ManualExporter", "Chapter")
_PREREQ_CONDITION_COLUMN = QT_TRANSLATE_NOOP("ManualExporter", "Needs")
_PREREQUISITES = (
    (
        QT_TRANSLATE_NOOP("ManualExporter", "Reviewing Analysis Readiness"),
        QT_TRANSLATE_NOOP("ManualExporter", "At least one confirmed absorption region."),
    ),
    (
        QT_TRANSLATE_NOOP("ManualExporter", "Fitting a Region in Detail"),
        QT_TRANSLATE_NOOP("ManualExporter", "At least one confirmed absorption region."),
    ),
    (
        QT_TRANSLATE_NOOP("ManualExporter", "Identifying with the Velocity Plot"),
        QT_TRANSLATE_NOOP("ManualExporter", "A custom preset created in an earlier chapter."),
    ),
    (
        QT_TRANSLATE_NOOP("ManualExporter", "Merging Regions"),
        QT_TRANSLATE_NOOP("ManualExporter", "At least two confirmed absorption regions."),
    ),
    (
        QT_TRANSLATE_NOOP("ManualExporter", "Tying Ions and Fitting Together"),
        QT_TRANSLATE_NOOP("ManualExporter", "A region that combines two or more ion species."),
    ),
)

_CONTROLS_HEADING = QT_TRANSLATE_NOOP("ManualExporter", "Step Controls")
_CONTROLS_INTRO = QT_TRANSLATE_NOOP(
    "ManualExporter",
    "Every coach-mark bubble carries the same controls, alongside the step's instruction and"
    " expected result.",
)
_CONTROL_COLUMN = QT_TRANSLATE_NOOP("ManualExporter", "Control")
_EFFECT_COLUMN = QT_TRANSLATE_NOOP("ManualExporter", "Effect")
_CONTROLS = (
    (
        "[Next]",
        QT_TRANSLATE_NOOP(
            "ManualExporter",
            "Advances to the next step. On a step that checks for a specific action (for"
            " example, confirming a region or linking preset lines), [Next] stays disabled and"
            " the expected-result line stays unchecked until that action is performed;"
            " performing it enables [Next] without advancing automatically, so you can read the"
            " confirmation first.",
        ),
    ),
    (
        "[Back]",
        QT_TRANSLATE_NOOP(
            "ManualExporter",
            "Returns to the previous step, or to the previous chapter's last step at a"
            " chapter's first step. It does not undo anything you did in the application.",
        ),
    ),
    (
        "[Exit Tour]",
        QT_TRANSLATE_NOOP(
            "ManualExporter",
            "Closes the tour immediately, keeping whatever the tour has done to the project so"
            " far.",
        ),
    ),
    (
        "[What is this?]",
        QT_TRANSLATE_NOOP(
            "ManualExporter",
            "Shown only on steps that carry background information beyond the instruction"
            " itself; expands or collapses that note in place.",
        ),
    ),
)

_ENDING_HEADING = QT_TRANSLATE_NOOP("ManualExporter", "Ending and Restarting")
_ENDING_NOTES = (
    QT_TRANSLATE_NOOP(
        "ManualExporter",
        "> [!NOTE]\n> The tour keeps no memory of where you stopped. Whether you close it with"
        " [Exit Tour] or quit chappy, the next walkthrough you start from [Help] > [Tutorial]"
        " begins again at the first chapter, [Getting Started], and reopens the sample"
        " spectrum. Switching modes yourself does not end the tour, but the widget the"
        " current step points at is no longer on screen; switch back to the mode the"
        " chapter is guiding to see the coach mark again.",
    ),
)

_NOTES_HEADING = QT_TRANSLATE_NOOP("ManualExporter", "Tips and Best Practices")
_NOTES = (
    QT_TRANSLATE_NOOP(
        "ManualExporter",
        "> [!TIP]\n> The tour targets specific widgets by name. If a step's highlighted area"
        " looks empty, the window may be too narrow to show that widget; enlarge the window or"
        " reveal the collapsed panel it belongs to.",
    ),
)

_RELATED_HEADING = QT_TRANSLATE_NOOP("ManualExporter", "Related References")
_RELATED_MENU_LABEL = QT_TRANSLATE_NOOP("ManualExporter", "Menu List")
_RELATED_MENU_PATH = "../menus/main_window/menus.md"
_RELATED_START_LABEL = QT_TRANSLATE_NOOP("ManualExporter", "Load Data into the Application")
_RELATED_START_PATH = "../operations/start-data-import.md"


def export_tutorial_guide(*, out_dir: Path) -> Path:
    """Write the guided-tutorial reference page under ``out_dir`` and return its path."""

    def tr(source_text: str) -> str:
        return translate_manual_text(_EXPORTER_CONTEXT, source_text)

    lines: list[str] = [f"# {tr(TITLE_SOURCE)}", "", tr(_INTRO), ""]

    lines.extend([f"## {tr(_STARTING_HEADING)}", "", tr(_STARTING_INTRO), ""])
    lines.extend(f"- {tr(item)}" for item in _STARTING_ITEMS)
    lines.extend(["", tr(_STARTING_NOTE)])

    lines.extend(["", f"## {tr(_WALKTHROUGHS_HEADING)}", "", tr(_WALKTHROUGHS_INTRO)])
    walkthrough_table = MarkdownTableBuilder(
        [tr(_WALKTHROUGH_COLUMN), tr(_COVERAGE_COLUMN), tr(_CHAPTER_COUNT_COLUMN)]
    )
    walkthrough_table.extend(
        (tr(button), tr(coverage), count) for button, coverage, count in _WALKTHROUGHS
    )
    lines.extend(walkthrough_table.lines())

    lines.extend(["", f"## {tr(_CHAPTERS_HEADING)}", "", tr(_CHAPTERS_INTRO)])
    chapters_table = MarkdownTableBuilder(
        [tr(_NUMBER_COLUMN), tr(_CHAPTER_COLUMN), tr(_INCLUDED_COLUMN), tr(_LEARN_COLUMN)]
    )
    chapters_table.extend(
        (str(number), tr(title), tr(included), tr(learn))
        for number, (title, included, learn) in enumerate(_CHAPTERS, 1)
    )
    lines.extend(chapters_table.lines())

    lines.extend(["", f"## {tr(_PREREQUISITES_HEADING)}", "", tr(_PREREQUISITES_INTRO)])
    prereq_table = MarkdownTableBuilder([tr(_PREREQ_CHAPTER_COLUMN), tr(_PREREQ_CONDITION_COLUMN)])
    prereq_table.extend((tr(chapter), tr(needs)) for chapter, needs in _PREREQUISITES)
    lines.extend(prereq_table.lines())

    lines.extend(["", f"## {tr(_CONTROLS_HEADING)}", "", tr(_CONTROLS_INTRO)])
    controls_table = MarkdownTableBuilder([tr(_CONTROL_COLUMN), tr(_EFFECT_COLUMN)])
    controls_table.extend((control, tr(effect)) for control, effect in _CONTROLS)
    lines.extend(controls_table.lines())

    lines.extend(["", f"## {tr(_ENDING_HEADING)}", ""])
    for index, note in enumerate(_ENDING_NOTES):
        if index:
            lines.append("")
        lines.append(tr(note))

    lines.extend(["", f"## {tr(_NOTES_HEADING)}", ""])
    for index, note in enumerate(_NOTES):
        if index:
            lines.append("")
        lines.append(tr(note))

    lines.extend(
        [
            "",
            f"## {tr(_RELATED_HEADING)}",
            "",
            f"- [{tr(_RELATED_START_LABEL)}]({_RELATED_START_PATH})",
            f"- [{tr(_RELATED_MENU_LABEL)}]({_RELATED_MENU_PATH})",
            "",
        ]
    )

    path = out_dir / "tutorial.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    content = format_markdown_text("\n".join(lines) + "\n")
    if not content.endswith("\n"):
        content += "\n"
    path.write_text(content, encoding="utf-8")
    return path
