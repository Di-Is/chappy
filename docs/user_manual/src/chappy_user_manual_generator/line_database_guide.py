"""Reference page describing how to replace the spectral line catalog CSV."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QT_TRANSLATE_NOOP

from chappy_user_manual_generator.markdown import MarkdownTableBuilder, format_markdown_text
from chappy_user_manual_generator.translations import translate_manual_text

if TYPE_CHECKING:
    from pathlib import Path

_EXPORTER_CONTEXT = "ManualExporter"

PAGE_RELATIVE_PATH = "reference/line_database.md"

TITLE_SOURCE = QT_TRANSLATE_NOOP("ManualExporter", "Replacing the Spectral Line Database")
SUMMARY_SOURCE = QT_TRANSLATE_NOOP(
    "ManualExporter",
    "Steps for putting your own line catalog CSV in place, and the columns it must carry.",
)

_INTRO = QT_TRANSLATE_NOOP(
    "ManualExporter",
    "chappy reads a bundled spectral line catalog once at startup. To analyse with a different"
    " catalog, you save your own CSV under a fixed name and start chappy again.",
)

_PREREQUISITES_HEADING = QT_TRANSLATE_NOOP("ManualExporter", "Prerequisites")
_PREREQUISITES = (
    QT_TRANSLATE_NOOP("ManualExporter", "chappy is running and the main window can be operated."),
    QT_TRANSLATE_NOOP(
        "ManualExporter",
        "The line data you want to use is available as a CSV, or you plan to edit a copy of the"
        " bundled catalog.",
    ),
)

_STEPS_HEADING = QT_TRANSLATE_NOOP("ManualExporter", "Procedure")
_STEP_COLUMN = QT_TRANSLATE_NOOP("ManualExporter", "Step")
_ACTION_COLUMN = QT_TRANSLATE_NOOP("ManualExporter", "Action")
_RESULT_COLUMN = QT_TRANSLATE_NOOP("ManualExporter", "Expected Result")
_STEPS = (
    (
        QT_TRANSLATE_NOOP(
            "ManualExporter", "Select [Settings] > [Open Line Database Folder] (`Ctrl+D` / `⌘D`)."
        ),
        QT_TRANSLATE_NOOP(
            "ManualExporter",
            "The folder that holds the replacement catalog opens in the file manager.",
        ),
    ),
    (
        QT_TRANSLATE_NOOP(
            "ManualExporter",
            "Copy `spectral_database/db_file/spectral_lines.csv` from the folder where chappy is"
            " placed, then edit the copy.",
        ),
        QT_TRANSLATE_NOOP(
            "ManualExporter",
            "You keep the column layout of the bundled catalog, which is the surest starting"
            " point for a valid file.",
        ),
    ),
    (
        QT_TRANSLATE_NOOP(
            "ManualExporter",
            "Save the edited file into the folder from step 1 under the name"
            " `spectral_lines.csv`.",
        ),
        QT_TRANSLATE_NOOP("ManualExporter", "The replacement catalog sits at the fixed location."),
    ),
    (
        QT_TRANSLATE_NOOP("ManualExporter", "Quit chappy and start it again."),
        QT_TRANSLATE_NOOP(
            "ManualExporter", "chappy loads the replaced catalog while starting up."
        ),
    ),
)

_COLUMNS_HEADING = QT_TRANSLATE_NOOP("ManualExporter", "Columns of the CSV")
_COLUMN_COLUMN = QT_TRANSLATE_NOOP("ManualExporter", "Column")
_RULE_COLUMN = QT_TRANSLATE_NOOP("ManualExporter", "Requirement")
_MEANING_COLUMN = QT_TRANSLATE_NOOP("ManualExporter", "Meaning")

_REQUIRED_SUBHEADING = QT_TRANSLATE_NOOP("ManualExporter", "Columns every row needs")
_REQUIRED_INTRO = QT_TRANSLATE_NOOP(
    "ManualExporter",
    "A row becomes a usable line only when all of the following hold. A row that falls short is"
    " skipped without a message, so a mistyped column name costs you lines silently.",
)
_REQUIRED_COLUMNS = (
    (
        "line_id",
        QT_TRANSLATE_NOOP(
            "ManualExporter",
            "Identifier of the row. It must not be empty, and it must be unique in the file"
            " because presets remember lines by this value.",
        ),
    ),
    (
        "wavelength",
        QT_TRANSLATE_NOOP("ManualExporter", "Rest wavelength in Å. It must be larger than 0."),
    ),
    (
        "f_value",
        QT_TRANSLATE_NOOP("ManualExporter", "Oscillator strength. It must be larger than 0."),
    ),
    (
        "gamma",
        QT_TRANSLATE_NOOP(
            "ManualExporter", "Natural damping constant in s⁻¹. It must be larger than 0."
        ),
    ),
    (
        "species / element_symbol / name",
        QT_TRANSLATE_NOOP(
            "ManualExporter",
            "At least one of the three, so that the species can be resolved. From"
            " element_symbol and charge_state the species is composed as `Mg II`; without them"
            " the first two words of name are used.",
        ),
    ),
)

_OPTIONAL_SUBHEADING = QT_TRANSLATE_NOOP("ManualExporter", "Columns you may add")
_OPTIONAL_INTRO = QT_TRANSLATE_NOOP(
    "ManualExporter", "These columns can be omitted or left empty."
)
_OPTIONAL_COLUMNS = (
    (
        "name",
        QT_TRANSLATE_NOOP("ManualExporter", "Display name of the line, for example `Mg II 2796`."),
    ),
    (
        "element_symbol",
        QT_TRANSLATE_NOOP("ManualExporter", "Element symbol such as `C`, `Mg`, `H`."),
    ),
    (
        "charge_state",
        QT_TRANSLATE_NOOP(
            "ManualExporter",
            "Charge as a number, where 0 is neutral and 1 is singly ionised. An ionisation stage"
            " in Roman numerals, for example `II`, is also accepted.",
        ),
    ),
    (
        "mutiplet_name",
        QT_TRANSLATE_NOOP(
            "ManualExporter",
            "Ties lines into one multiplet; every member carries the same value. The bundled"
            " catalog spells the column without the first `l`, and `multiplet_name` also works.",
        ),
    ),
    ("comment", QT_TRANSLATE_NOOP("ManualExporter", "Free note kept together with the line.")),
    (
        QT_TRANSLATE_NOOP("ManualExporter", "The other columns"),
        QT_TRANSLATE_NOOP(
            "ManualExporter",
            "The bundled catalog carries further NIST fields such as wavelength_ritz, Ei_eV,"
            " accuracy, and the term symbols. chappy shows them as line details and accepts them"
            " empty.",
        ),
    ),
)
_ALIAS_NOTE = QT_TRANSLATE_NOOP(
    "ManualExporter",
    "Alternative column names are accepted as well: wavelength_angstrom for wavelength,"
    " oscillator_strength for f_value, gamma_value for gamma, comments for comment.",
)

_HEADER_SUBHEADING = QT_TRANSLATE_NOOP("ManualExporter", "Comment lines at the top of the file")
_HEADER_NOTE = QT_TRANSLATE_NOOP(
    "ManualExporter",
    "Empty lines and lines starting with `#` are skipped. Two of them are read as the origin of"
    " the catalog and written into exported preset files.",
)
_HEADER_EXAMPLE = "# name: NIST ASD Lines\n# version: 1.0.0"

_NOTES_HEADING = QT_TRANSLATE_NOOP("ManualExporter", "Tips and Best Practices")
_NOTES = (
    QT_TRANSLATE_NOOP(
        "ManualExporter",
        "> [!WARNING]\n> When no row of the CSV can be used, chappy shows the path in an error"
        " dialog at startup and quits instead of running on an empty catalog. Save the file as"
        " UTF-8 and compare the column names against the bundled catalog.",
    ),
    QT_TRANSLATE_NOOP(
        "ManualExporter",
        "> [!NOTE]\n> The catalog is read only while chappy starts. A file replaced during a"
        " session takes effect at the next startup.",
    ),
    QT_TRANSLATE_NOOP(
        "ManualExporter",
        "> [!TIP]\n> To keep the catalog in another location, set the environment variable"
        " `CHAPPY_SPECTRAL_LINES_CSV` to its full path. That path is used ahead of the folder"
        " opened in step 1.",
    ),
)

_RELATED_HEADING = QT_TRANSLATE_NOOP("ManualExporter", "Related References")
_RELATED_MENU_LABEL = QT_TRANSLATE_NOOP("ManualExporter", "Menu List")
_RELATED_MENU_PATH = "../menus/main_window/menus.md"


def export_line_database_guide(*, out_dir: Path) -> Path:
    """Write the line database replacement page under ``out_dir`` and return its path."""

    def tr(source_text: str) -> str:
        return translate_manual_text(_EXPORTER_CONTEXT, source_text)

    lines: list[str] = [f"# {tr(TITLE_SOURCE)}", "", tr(_INTRO), ""]

    lines.extend([f"## {tr(_PREREQUISITES_HEADING)}", ""])
    lines.extend(f"- {tr(item)}" for item in _PREREQUISITES)

    lines.extend(["", f"## {tr(_STEPS_HEADING)}"])
    steps_table = MarkdownTableBuilder([tr(_STEP_COLUMN), tr(_ACTION_COLUMN), tr(_RESULT_COLUMN)])
    steps_table.extend(
        (str(number), tr(action), tr(result)) for number, (action, result) in enumerate(_STEPS, 1)
    )
    lines.extend(steps_table.lines())

    lines.extend(
        [
            "",
            f"## {tr(_COLUMNS_HEADING)}",
            "",
            f"### {tr(_REQUIRED_SUBHEADING)}",
            "",
            tr(_REQUIRED_INTRO),
        ]
    )
    required_table = MarkdownTableBuilder([tr(_COLUMN_COLUMN), tr(_RULE_COLUMN)])
    required_table.extend((column, tr(rule)) for column, rule in _REQUIRED_COLUMNS)
    lines.extend(required_table.lines())

    lines.extend(["", f"### {tr(_OPTIONAL_SUBHEADING)}", "", tr(_OPTIONAL_INTRO)])
    optional_table = MarkdownTableBuilder([tr(_COLUMN_COLUMN), tr(_MEANING_COLUMN)])
    optional_table.extend((tr(column), tr(meaning)) for column, meaning in _OPTIONAL_COLUMNS)
    lines.extend(optional_table.lines())
    lines.extend(["", tr(_ALIAS_NOTE)])

    lines.extend(
        [
            "",
            f"### {tr(_HEADER_SUBHEADING)}",
            "",
            tr(_HEADER_NOTE),
            "",
            "```csv",
            _HEADER_EXAMPLE,
            "```",
            "",
            f"## {tr(_NOTES_HEADING)}",
            "",
        ]
    )
    for index, note in enumerate(_NOTES):
        if index:
            lines.append("")
        lines.append(tr(note))

    lines.extend(
        [
            "",
            f"## {tr(_RELATED_HEADING)}",
            "",
            f"- [{tr(_RELATED_MENU_LABEL)}]({_RELATED_MENU_PATH})",
            "",
        ]
    )

    path = out_dir / "line_database.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    content = format_markdown_text("\n".join(lines) + "\n")
    if not content.endswith("\n"):
        content += "\n"
    path.write_text(content, encoding="utf-8")
    return path
