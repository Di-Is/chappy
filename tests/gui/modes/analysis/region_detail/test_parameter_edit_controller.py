"""Tests for optimize parameter edit controller."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from PySide6.QtWidgets import QWidget
from pytestqt.qtbot import QtBot

from chappy.core.absorption.models import AbsorptionLine
from chappy.core.components.absorber import AbsorberComponent
from chappy.gui.modes.analysis.region_detail.parameters import parameter_edit_controller
from chappy.gui.modes.analysis.region_detail.parameters.parameter_edit_controller import (
    OptimizeParameterDialogContext,
    OptimizeParameterEditController,
)


ValueCallback = Callable[[AbsorberComponent, str, float], None]
FixCallback = Callable[[AbsorberComponent, str, bool], None]
ClosedCallback = Callable[[], None]


class _ValueSignal:
    """Small typed replacement for the dialog value signal."""

    def __init__(self) -> None:
        self._callbacks: list[ValueCallback] = []

    def connect(self, callback: ValueCallback) -> None:
        """Store a value callback."""
        self._callbacks.append(callback)

    def emit(self, component: AbsorberComponent, param_name: str, value: float) -> None:
        """Emit to all stored callbacks."""
        for callback in self._callbacks:
            callback(component, param_name, value)


class _FixSignal:
    """Small typed replacement for the dialog fixed-state signal."""

    def __init__(self) -> None:
        self._callbacks: list[FixCallback] = []

    def connect(self, callback: FixCallback) -> None:
        """Store a fixed-state callback."""
        self._callbacks.append(callback)

    def emit(self, component: AbsorberComponent, param_name: str, fixed: bool) -> None:
        """Emit to all stored callbacks."""
        for callback in self._callbacks:
            callback(component, param_name, fixed)


class _ClosedSignal:
    """Small typed replacement for the dialog close signal."""

    def __init__(self) -> None:
        self._callbacks: list[ClosedCallback] = []

    def connect(self, callback: ClosedCallback) -> None:
        """Store a close callback."""
        self._callbacks.append(callback)

    def emit(self) -> None:
        """Emit to all stored callbacks."""
        for callback in self._callbacks:
            callback()


class _Dialog:
    """Dialog test double."""

    instances: list[_Dialog] = []

    def __init__(self, parent: QWidget) -> None:
        self.parent = parent
        self.value_changed = _ValueSignal()
        self.fix_toggled = _FixSignal()
        self.dialog_closed = _ClosedSignal()
        self.contexts: list[OptimizeParameterDialogContext] = []
        self.show_count = 0
        self.raise_count = 0
        self.activate_count = 0
        self.refresh_count = 0
        self.deleted = False
        _Dialog.instances.append(self)

    def set_component(
        self,
        component: AbsorberComponent,
        *,
        line: AbsorptionLine | None,
        z_bounds: tuple[float, float] | None,
        line_display_id: int | None,
        component_index: int | None,
    ) -> None:
        """Record the component context."""
        self.contexts.append(
            OptimizeParameterDialogContext(
                component=component,
                line=line,
                z_bounds=z_bounds,
                line_display_id=line_display_id,
                component_index=component_index,
            )
        )

    def show(self) -> None:
        """Record show requests."""
        self.show_count += 1

    def raise_(self) -> None:
        """Record raise requests."""
        self.raise_count += 1

    def activateWindow(self) -> None:
        """Record activation requests."""
        self.activate_count += 1

    def refresh(self) -> None:
        """Record refresh requests."""
        self.refresh_count += 1

    def deleteLater(self) -> None:
        """Record deferred deletion."""
        self.deleted = True


class _Port:
    """Panel-port test double."""

    def __init__(self, context: OptimizeParameterDialogContext) -> None:
        self.context = context
        self.value_result = True
        self.value_edits: list[tuple[AbsorberComponent, str, float]] = []
        self.fixed_edits: list[tuple[AbsorberComponent, str, bool]] = []

    def parameter_dialog_context(
        self, component: AbsorberComponent
    ) -> OptimizeParameterDialogContext:
        """Return the configured dialog context."""
        assert component is self.context.component
        return self.context

    def apply_parameter_dialog_value(
        self, component: AbsorberComponent, param_name: str, value: float
    ) -> bool:
        """Record value edits."""
        self.value_edits.append((component, param_name, value))
        return self.value_result

    def set_parameter_dialog_fixed_state(
        self, component: AbsorberComponent, param_name: str, fixed: bool
    ) -> None:
        """Record fixed-state edits."""
        self.fixed_edits.append((component, param_name, fixed))


@pytest.fixture(autouse=True)
def _replace_dialog(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace the Qt dialog with a typed test double."""
    _Dialog.instances = []
    monkeypatch.setattr(parameter_edit_controller, "ParameterAdjustmentDialog", _Dialog)


def test_show_dialog_populates_and_raises_dialog(qtbot: QtBot) -> None:
    """Controller should populate and display the modeless dialog."""
    parent = QWidget()
    qtbot.addWidget(parent)
    component = AbsorberComponent(component_id="component-1")
    context = OptimizeParameterDialogContext(
        component=component, line=None, z_bounds=(0.1, 0.2), line_display_id=3, component_index=2
    )
    port = _Port(context)
    controller = OptimizeParameterEditController(parent=parent, port=port)

    controller.show_dialog(component)

    dialog = _Dialog.instances[0]
    assert dialog.parent is parent
    assert dialog.contexts == [context]
    assert dialog.show_count == 1
    assert dialog.raise_count == 1
    assert dialog.activate_count == 1


def test_rejected_value_refreshes_dialog(qtbot: QtBot) -> None:
    """Controller should refresh the dialog when the port rejects a value."""
    parent = QWidget()
    qtbot.addWidget(parent)
    component = AbsorberComponent(component_id="component-1")
    port = _Port(
        OptimizeParameterDialogContext(
            component=component,
            line=None,
            z_bounds=None,
            line_display_id=None,
            component_index=None,
        )
    )
    controller = OptimizeParameterEditController(parent=parent, port=port)
    controller.show_dialog(component)
    dialog = _Dialog.instances[0]
    port.value_result = False

    dialog.value_changed.emit(component, "redshift", 0.15)

    assert port.value_edits == [(component, "redshift", 0.15)]
    assert dialog.refresh_count == 1


def test_fixed_state_change_applies_and_refreshes(qtbot: QtBot) -> None:
    """Controller should apply fixed-state changes and refresh the dialog."""
    parent = QWidget()
    qtbot.addWidget(parent)
    component = AbsorberComponent(component_id="component-1")
    port = _Port(
        OptimizeParameterDialogContext(
            component=component,
            line=None,
            z_bounds=None,
            line_display_id=None,
            component_index=None,
        )
    )
    controller = OptimizeParameterEditController(parent=parent, port=port)
    controller.show_dialog(component)
    dialog = _Dialog.instances[0]

    dialog.fix_toggled.emit(component, "b_parameter", True)

    assert port.fixed_edits == [(component, "b_parameter", True)]
    assert dialog.refresh_count == 1


def test_closed_dialog_is_released_before_next_show(qtbot: QtBot) -> None:
    """Controller should release a closed dialog before creating the next one."""
    parent = QWidget()
    qtbot.addWidget(parent)
    component = AbsorberComponent(component_id="component-1")
    port = _Port(
        OptimizeParameterDialogContext(
            component=component,
            line=None,
            z_bounds=None,
            line_display_id=None,
            component_index=None,
        )
    )
    controller = OptimizeParameterEditController(parent=parent, port=port)
    controller.show_dialog(component)
    first_dialog = _Dialog.instances[0]

    first_dialog.dialog_closed.emit()
    controller.show_dialog(component)

    assert first_dialog.deleted is True
    assert len(_Dialog.instances) == 2
