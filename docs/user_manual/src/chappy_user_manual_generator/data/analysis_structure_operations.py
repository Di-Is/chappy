"""Shared data for Analysis Structure operation documentation."""

from __future__ import annotations

from collections.abc import Callable

from chappy_user_manual_generator.template_engine import render_markdown_template
from chappy_user_manual_generator.translations import translate_manual_text
from PySide6.QtCore import QT_TRANSLATE_NOOP

from chappy.gui.common.shared_operations import SHARED_OPERATIONS_TR_CONTEXT, get_shared_operation

_EXPORTER_CONTEXT = "ManualExporter"

_RowRenderer = Callable[[], str]


def _shared_structure_row(op_id: str) -> _RowRenderer:
    """Return a three-column row from one scoped shared operation."""

    def render() -> str:
        operation = get_shared_operation(op_id)
        action = translate_manual_text(SHARED_OPERATIONS_TR_CONTEXT, operation.action_source)
        steps = translate_manual_text(SHARED_OPERATIONS_TR_CONTEXT, operation.expected_source)
        note = (
            translate_manual_text(SHARED_OPERATIONS_TR_CONTEXT, operation.note_source)
            if operation.note_source is not None
            else ""
        )
        return f"| {action} | {steps} | {note} |"

    return render


ANALYSIS_STRUCTURE_OPERATION_ROWS: tuple[_RowRenderer, ...] = (
    _shared_structure_row("analysis_structure_move"),
    _shared_structure_row("analysis_structure_split"),
    _shared_structure_row("analysis_structure_merge"),
    _shared_structure_row("analysis_structure_unlink"),
    _shared_structure_row("analysis_structure_delete"),
)


def render_analysis_structure_operations_table() -> str:
    """Render the Analysis Structure operations table as Markdown."""
    heading = translate_manual_text(
        _EXPORTER_CONTEXT, QT_TRANSLATE_NOOP("ManualExporter", "Side panel essentials")
    ).strip()
    intro = translate_manual_text(
        _EXPORTER_CONTEXT,
        QT_TRANSLATE_NOOP(
            "ManualExporter",
            "Everyday actions for organising absorption regions (regions) and absorption lines (lines).",
        ),
    ).strip()
    header = translate_manual_text(
        _EXPORTER_CONTEXT, QT_TRANSLATE_NOOP("ManualExporter", "| Action | Steps | Notes |")
    )
    divider = translate_manual_text(
        _EXPORTER_CONTEXT, QT_TRANSLATE_NOOP("ManualExporter", "|---|---|---|")
    )
    rows = [render() for render in ANALYSIS_STRUCTURE_OPERATION_ROWS]
    return render_markdown_template(
        "analysis_structure_operations_section.md.tmpl",
        heading=heading,
        intro=intro,
        table_header=header,
        table_divider=divider,
        table_rows="\n".join(rows),
    )
