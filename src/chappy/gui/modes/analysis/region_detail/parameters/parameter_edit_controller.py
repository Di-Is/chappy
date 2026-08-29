"""Controller for optimize parameter edit dialog lifecycle."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from chappy.gui.dialogs.parameter_adjustment_dialog import ParameterAdjustmentDialog

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget

    from chappy.core.absorption.models import AbsorptionLine
    from chappy.core.components.absorber import AbsorberComponent


@dataclass(frozen=True, slots=True)
class OptimizeParameterDialogContext:
    """Describe the component metadata displayed in the parameter dialog."""

    component: AbsorberComponent
    line: AbsorptionLine | None
    z_bounds: tuple[float, float] | None
    line_display_id: int | None
    component_index: int | None


class OptimizeParameterEditPort(Protocol):
    """Typed boundary implemented by the optimize panel."""

    def parameter_dialog_context(
        self, component: AbsorberComponent
    ) -> OptimizeParameterDialogContext:
        """Return display context for the parameter dialog.

        Args:
            component: Component selected by the user.

        Returns:
            Context required to populate the dialog.
        """

    def apply_parameter_dialog_value(
        self, component: AbsorberComponent, param_name: str, value: float
    ) -> bool:
        """Apply a value edited in the parameter dialog.

        Args:
            component: Component being edited.
            param_name: Parameter name.
            value: New parameter value.

        Returns:
            True when the value was accepted.
        """

    def set_parameter_dialog_fixed_state(
        self, component: AbsorberComponent, param_name: str, fixed: bool
    ) -> None:
        """Apply a fixed-state change edited in the parameter dialog.

        Args:
            component: Component being edited.
            param_name: Parameter name.
            fixed: Desired fixed state.
        """


class OptimizeParameterEditController:
    """Own the modeless parameter dialog and route edits through a typed port."""

    def __init__(self, *, parent: QWidget, port: OptimizeParameterEditPort) -> None:
        """Initialize the controller.

        Args:
            parent: Parent widget for the modeless dialog.
            port: Panel-facing edit operations.
        """
        self._parent = parent
        self._port = port
        self._dialog: ParameterAdjustmentDialog | None = None

    def show_dialog(self, component: AbsorberComponent) -> None:
        """Show the dialog for a component.

        Args:
            component: Component selected by the user.
        """
        dialog = self._ensure_dialog()
        context = self._port.parameter_dialog_context(component)
        dialog.set_component(
            context.component,
            line=context.line,
            z_bounds=context.z_bounds,
            line_display_id=context.line_display_id,
            component_index=context.component_index,
        )
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def refresh_dialog(self) -> None:
        """Refresh the dialog when it is currently open."""
        if self._dialog is not None:
            self._dialog.refresh()

    def _ensure_dialog(self) -> ParameterAdjustmentDialog:
        """Return the existing dialog, creating it if needed."""
        if self._dialog is not None:
            return self._dialog

        dialog = ParameterAdjustmentDialog(self._parent)
        dialog.value_changed.connect(self._on_value_changed)
        dialog.fix_toggled.connect(self._on_fix_toggled)
        dialog.dialog_closed.connect(self._on_dialog_closed)
        self._dialog = dialog
        return dialog

    def _on_value_changed(
        self, component: AbsorberComponent, param_name: str, value: float
    ) -> None:
        """Apply a value change from the dialog."""
        success = self._port.apply_parameter_dialog_value(component, param_name, value)
        if not success:
            self.refresh_dialog()

    def _on_fix_toggled(self, component: AbsorberComponent, param_name: str, fixed: bool) -> None:
        """Apply a fixed-state change from the dialog."""
        self._port.set_parameter_dialog_fixed_state(component, param_name, fixed)
        self.refresh_dialog()

    def _on_dialog_closed(self) -> None:
        """Release the dialog after the user closes it."""
        dialog = self._dialog
        if dialog is not None:
            dialog.deleteLater()
        self._dialog = None
