"""Tests for absorber editor parameter intent routing."""

from __future__ import annotations

from pytestqt.qtbot import QtBot

from chappy.core.components.absorber import AbsorberComponent
from chappy.core.spectroscopy_project import SpectroscopyProject
from chappy.gui.shell.absorber_editor import AbsorberEditor


def _editor_with_absorber(qtbot: QtBot) -> tuple[AbsorberEditor, AbsorberComponent]:
    """Create an editor and one project-owned absorber."""
    project = SpectroscopyProject(name="Absorber Editor Routing Test")
    component = AbsorberComponent(
        name="H I", wavelength=1215.67, column_density=13.5, component_id="component-1"
    )
    project.model.add_component(component)
    editor = AbsorberEditor(project=project)
    qtbot.addWidget(editor)
    return editor, component


def test_parameter_controls_emit_intent_without_mutating_scientific_state(qtbot: QtBot) -> None:
    """Parameter controls should delegate mutation to the shell owner."""
    editor, component = _editor_with_absorber(qtbot)
    emitted: list[tuple[str, str, float]] = []
    editor.parameter_changed.connect(
        lambda absorber, parameter, value: emitted.append((absorber, parameter, value))
    )

    editor._on_parameter_changed_from_controls(component, "column_density", 14.0)

    assert component.parameters["column_density"].value == 13.5
    assert emitted == [(component.name, "column_density", 14.0)]


def test_table_edit_emits_intent_without_mutating_scientific_state(qtbot: QtBot) -> None:
    """Inline table edits should delegate mutation to the shell owner."""
    editor, component = _editor_with_absorber(qtbot)
    emitted: list[tuple[str, str, float]] = []
    editor.parameter_changed.connect(
        lambda absorber, parameter, value: emitted.append((absorber, parameter, value))
    )

    editor._on_table_absorber_edited(component.name, "column_density", 14.0)

    assert component.parameters["column_density"].value == 13.5
    assert emitted == [(component.name, "column_density", 14.0)]
