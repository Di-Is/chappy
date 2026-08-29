"""Refactored AbsorberEditor using modular architecture.

This is the new implementation of AbsorberEditor that coordinates specialized modules
following the Single Responsibility Principle. Each module handles a specific aspect
of absorber editing while this coordinator provides the public API.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import QWidget

from chappy.core.components.absorber import AbsorberComponent
from chappy.gui.shell.absorber_editor_layout import AbsorberEditorLayout
from chappy.gui.shell.absorber_parameter_controls import AbsorberParameterControls
from chappy.gui.shell.absorber_table_controller import AbsorberTableController

if TYPE_CHECKING:
    from chappy.core.spectroscopy_project import SpectroscopyProject
    from chappy.gui.modes.mode_state_store import ModeStateStore

logger = logging.getLogger(__name__)


class AbsorberEditor(QWidget):
    """AbsorberEditor using modular architecture.

    This class serves as the coordinator for specialized absorber editing modules:
    - AbsorberParameterControls: Parameter input controls and validation
    - AbsorberTableController: Table display and editing
    - Absorption region management
    - AbsorberEditorLayout: UI layout and styling

    Key Design Principles:
    - Single Responsibility: Each module handles one specific concern
    - Loose Coupling: Modules communicate through well-defined interfaces
    - High Cohesion: Related functionality is grouped together
    - Testability: Each module is independently testable

    Signals:
        parameter_changed: Emitted when any parameter changes
        component_added: Emitted when new absorber is added
        component_removed: Emitted when absorber is removed
    """

    # Qt signals for external communication
    parameter_changed = Signal(str, str, float)  # component_name, param_name, value
    component_added = Signal(AbsorberComponent)
    component_removed = Signal(AbsorberComponent)
    absorber_selected = Signal(str)  # component_name

    def __init__(
        self,
        parent: QWidget | None = None,
        project: SpectroscopyProject | None = None,
        mode_state_store: ModeStateStore | None = None,
    ) -> None:
        """Initialize refactored absorber editor.

        Args:
            parent: Parent widget
            project: Current project
            mode_state_store: Mode state store instance
        """
        super().__init__(parent)

        # Core state
        self.current_project: SpectroscopyProject | None = project
        self.current_absorber: AbsorberComponent | None = None
        self.mode_state_store: ModeStateStore | None = mode_state_store

        # Initialize specialized modules
        self._init_modules()

        # Setup module interactions
        self._connect_modules()

        # Setup UI using modular approach
        self._setup_modular_ui()

        logger.info("AbsorberEditor initialized with modular architecture")

    def _init_modules(self) -> None:
        """Initialize all specialized modules."""
        # Parameter controls module
        self.parameter_controls = AbsorberParameterControls(self)

        # Table management module
        self.table_controller = AbsorberTableController(self)

        # UI layout module
        self.editor_layout = AbsorberEditorLayout(self)

        logger.debug("Specialized modules initialized")

    def _connect_modules(self) -> None:
        """Connect modules together through signals and dependencies."""
        # Connect table controller signals
        self.table_controller.selection_changed.connect(self._on_absorber_selected_from_table)
        self.table_controller.absorber_edited.connect(self._on_table_absorber_edited)

        # Connect parameter controls signals
        self.parameter_controls.parameter_changed.connect(self._on_parameter_changed_from_controls)

        # Connect parameter changes to table updates
        self.parameter_controls.parameter_changed.connect(
            lambda absorber, param, value: self.table_controller.update_absorber_parameter(
                absorber.name, param, value
            )
        )

    def _setup_modular_ui(self) -> None:
        """Setup UI using modular UI setup component."""
        # Create main layout
        main_layout = self.editor_layout.setup_main_ui(self)

        # Create header section with controls
        header_layout, _header_buttons = self.editor_layout.create_header_section()
        main_layout.addLayout(header_layout)

        # Setup table widget
        table_widget = self.table_controller.create_table_widget()
        self.editor_layout.setup_absorber_table(table_widget)
        main_layout.addWidget(table_widget)

        # Add parameter controls directly beneath the table
        param_controls = self.parameter_controls.create_parameter_section()
        main_layout.addWidget(param_controls)

        # Apply styling
        self.editor_layout.apply_styling()

        logger.debug("Modular UI setup completed")

    def set_project(self, project: SpectroscopyProject | None) -> None:
        """Set current project and update absorber list.

        Args:
            project: Project to set (None to clear)
        """
        self.current_project = project

        # Clear current absorber selection
        self.current_absorber = None

        if project:
            # Refresh table display
            self.table_controller.refresh_table()
            logger.info("Project set", extra={"project": project})
        else:
            # Clear all displays
            self.table_controller.clear_table()
            logger.info("Project cleared")

    @Slot(str)
    def _on_absorber_selected_from_table(self, absorber_name: str) -> None:
        """Handle absorber selection from table.

        Args:
            absorber_name: Name of selected absorber
        """
        if not self.current_project:
            return

        # Find absorber in project
        absorber = None
        for component in self.current_project.model.components:
            if component.name == absorber_name and isinstance(
                component, AbsorberComponent
            ):  # Check if it's an absorber
                absorber = component
                break

        if absorber:
            self.current_absorber = absorber
            self.parameter_controls.set_current_absorber(absorber)

            # Emit signal for external listeners
            self.absorber_selected.emit(absorber_name)

            logger.debug("Absorber selected", extra={"absorber_name": absorber_name})
        else:
            logger.warning("Absorber not found", extra={"absorber_name": absorber_name})

    def _on_parameter_changed_from_controls(
        self, absorber: AbsorberComponent, param_name: str, value: float
    ) -> None:
        """Handle parameter changes from parameter controls.

        Args:
            absorber: Absorber component
            param_name: Parameter name
            value: New value
        """
        if absorber and param_name in absorber.parameters:
            self.parameter_changed.emit(absorber.name, param_name, value)

    @Slot(str, str, float)
    def _on_table_absorber_edited(self, absorber_name: str, param_name: str, value: float) -> None:
        """Handle absorber parameter edit from table.

        Args:
            absorber_name: Name of absorber being edited
            param_name: Name of parameter being edited
            value: New parameter value
        """
        if not self.current_project:
            return

        # Find absorber in project
        for component in self.current_project.model.components:
            if (
                (component.name == absorber_name)
                and isinstance(component, AbsorberComponent)
                and param_name in component.parameters
            ):
                try:
                    numeric_value = float(value)
                    self.parameter_changed.emit(absorber_name, param_name, numeric_value)

                    if self.current_absorber and self.current_absorber.name == absorber_name:
                        self.parameter_controls.set_current_absorber(component)

                    logger.debug(
                        "Parameter updated from table",
                        extra={
                            "absorber_name": absorber_name,
                            "parameter_name": param_name,
                            "value": numeric_value,
                        },
                    )
                except (ValueError, TypeError) as e:
                    logger.warning("Invalid parameter value", extra={"error": e})
                break
