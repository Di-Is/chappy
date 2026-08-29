"""Absorber component coordination and management for main window."""

# mypy: disable-error-code="attr-defined"
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from PySide6.QtCore import QObject, Signal

if TYPE_CHECKING:
    from chappy.gui.shell.main_window import MainWindow


@runtime_checkable
class AbsorberEditorSignalPort(Protocol):
    """Protocol for absorber editor signals used by the group tree."""

    component_added: Signal
    parameter_changed: Signal
    absorber_selected: Signal


@runtime_checkable
class NamedAbsorberComponent(Protocol):
    """Protocol for absorber components with stable display names."""

    name: str


@runtime_checkable
class ViewWithHighlight(Protocol):
    """Protocol for views with absorber highlight."""

    def highlight_absorber(self, absorber_name: str) -> None:
        """Highlight the absorber identified by name within the view.

        Args:
            absorber_name: Display name of the absorber to emphasize.
        """
        ...


logger = logging.getLogger(__name__)


class AbsorberCoordinator(QObject):
    """Manages absorber component operations and interactions.

    This class handles all absorber-related functionality including
    creation, selection, parameter management, and group assignment.
    """

    # Signals
    absorber_parameter_changed = Signal(str, float)  # param_name, value
    status_message = Signal(str)  # message

    def __init__(self, main_window: MainWindow) -> None:
        """Initialize absorber coordinator.

        Args:
            main_window: Parent main window instance
        """
        super().__init__()
        self.main_window = main_window

    def setup_absorber_signals(self) -> None:
        """Setup signal connections for absorber management."""
        if absorber_editor := self.main_window.absorber_editor:
            logger.info(
                "🔌 COORD: Setting up absorber signals with editor: %s",
                type(absorber_editor).__name__,
            )
            # Connect absorber editor signals
            absorber_editor.component_added.connect(self._on_absorber_added)
            absorber_editor.parameter_changed.connect(self._on_absorber_parameter_changed)
            absorber_editor.absorber_selected.connect(self._on_absorber_selected)

            logger.info("Absorber signals connected successfully")

    def _on_absorber_added(self, absorber: NamedAbsorberComponent) -> None:
        """Handle absorber component addition.

        Args:
            absorber: Added absorber component
        """
        self.status_message.emit(f"Added absorber: {absorber.name}")
        logger.info("Absorber added: %s", absorber.name)

        # Emit signal for external listeners

    def _on_absorber_selected(self, absorber_name: str) -> None:
        """Handle absorber selection from editor.

        Args:
            absorber_name: Name of the selected absorber
        """
        # Highlight the selected absorber in all spectrum views
        view_stack = self.main_window.view_stack
        if view_stack:
            for view in view_stack.get_all_views():
                if isinstance(view, ViewWithHighlight):
                    view.highlight_absorber(absorber_name)

        # Emit signal for external listeners

    def _on_absorber_parameter_changed(
        self,
        absorber: str | NamedAbsorberComponent,
        param_name: str | None = None,
        value: float | None = None,
    ) -> None:
        """Handle absorber parameter changes.

        Args:
            absorber: Absorber component (or absorber name if from AbsorberEditor)
            param_name: Name of the changed parameter
            value: New parameter value
        """
        # Handle signals from AbsorberEditor which sends (absorber_name, param_name, value)
        if isinstance(absorber, str) and param_name is not None and value is not None:
            absorber_name = absorber
            self.absorber_parameter_changed.emit(f"{absorber_name}.{param_name}", value)
        elif (
            isinstance(absorber, NamedAbsorberComponent)
            and param_name is not None
            and value is not None
        ):
            # Emit signal with absorber name for better tracking
            self.absorber_parameter_changed.emit(f"{absorber.name}.{param_name}", value)
