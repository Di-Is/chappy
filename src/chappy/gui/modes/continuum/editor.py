"""Editor for continuum component parameters."""

from __future__ import annotations

import logging
import os
from contextlib import suppress
from typing import TYPE_CHECKING, Protocol

import numpy as np
from PySide6.QtCore import QEvent, QSettings, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDoubleSpinBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from chappy.application.analysis_artifacts import (
    AnalysisMutationImpact,
    GlobalAnalysisMutationUseCase,
    run_postcommit_actions_isolated,
)
from chappy.application.continuum import ContinuumComponentMutationUseCase
from chappy.core.components.base import ModelComponent
from chappy.core.components.continuum import DEFAULT_CONTINUUM_FLUX, ContinuumComponent
from chappy.core.editing_mode import EditingMode
from chappy.gui.adapters.model_event_adapter import SpectrumModelEventAdapter
from chappy.gui.common.side_panel_section import SidePanelSection
from chappy.gui.modes.continuum.controllers.interaction_controller import (
    ContinuumInteractionController,
)
from chappy.gui.modes.continuum.controllers.interaction_state_controller import (
    ContinuumStateController,
)
from chappy.gui.modes.continuum.history_adapter import ContinuumHistoryAdapter
from chappy.gui.spectrum.interaction.support.logging import InteractionLogEmitter
from chappy.gui.theme import (
    ButtonVariant,
    Colors,
    Fonts,
    apply_button_variant,
    empty_state_label_style,
)
from chappy.gui.visual_tokens import SidePanelMetrics
from chappy.i18n import get_language_switcher
from chappy.presentation.interaction.interaction_contracts import InteractionChannel

if TYPE_CHECKING:
    from collections.abc import Callable
    from contextlib import AbstractContextManager

    from chappy.core.spectroscopy_project import SpectroscopyProject
    from chappy.gui.modes.mode_state_store import ModeStateStore
    from chappy.gui.protocols.plotting import ContinuumPlotWidget
    from chappy.gui.spectrum.interaction.support.contexts import SnapshotContext
    from chappy.presentation.interaction.interaction_contracts import (
        Coordinate,
        InteractionStateSnapshot,
    )

logger = logging.getLogger(__name__)


class ContinuumHistoryRecorder(Protocol):
    """History recorder port used by continuum editing actions."""

    def atomic_recording(self) -> AbstractContextManager[None]:
        """Return a scope that restores history state when recording fails."""
        ...

    def record_cont_add_component(self, continuum: ContinuumComponent) -> None:
        """Record a continuum component addition."""
        ...

    def record_cont_add_point(
        self,
        continuum: ContinuumComponent,
        before_points: list[tuple[float, float]],
        after_points: list[tuple[float, float]],
    ) -> None:
        """Record a continuum point addition."""

    def record_cont_delete_point(
        self,
        continuum: ContinuumComponent,
        before_points: list[tuple[float, float]],
        after_points: list[tuple[float, float]],
    ) -> None:
        """Record a continuum point deletion."""

    def record_cont_move_point(
        self,
        continuum: ContinuumComponent,
        before_points: list[tuple[float, float]],
        after_points: list[tuple[float, float]],
    ) -> None:
        """Record a continuum point move."""

    def record_cont_reset(
        self,
        continuum: ContinuumComponent,
        old_points: list[tuple[float, float]],
        new_points: list[tuple[float, float]],
    ) -> None:
        """Record a continuum point replacement."""


class ContinuumEditor(QWidget):
    """Editor widget for continuum components.

    Provides GUI controls for managing continuum fitting:
    - Model type selection (polynomial, spline, points)
    - Polynomial order control
    - Anchor point management for spline/point models
    - Normalization controls
    - Interactive point editing

    Signals:
        parameter_changed: Emitted when any parameter changes
        component_added: Emitted when new continuum is added
    """

    # Qt signals
    parameter_changed = Signal(  # Qt signal follows framework naming convention
        str, str, float
    )  # component_name, param_name, value
    component_added = Signal(ContinuumComponent)  # Qt signal follows framework naming convention
    continuum_updated = Signal(  # Qt signal follows framework naming convention
        ContinuumComponent
    )  # continuum component updated
    status_message = Signal(str)

    COLUMN_WAVELENGTH = 0
    COLUMN_FLUX = 1

    def __init__(
        self,
        parent: QWidget | None = None,
        project: SpectroscopyProject | None = None,
        mode_state_store: ModeStateStore | None = None,
    ) -> None:
        """Initialize continuum editor.

        Args:
            parent: Parent widget
            project: Current project
            mode_state_store: Mode state store instance
        """
        super().__init__(parent)

        # State
        self.current_project: SpectroscopyProject | None = project
        self.current_continuum: ContinuumComponent | None = None
        self.mode_state_store: ModeStateStore | None = mode_state_store
        self._model_event_adapter: SpectrumModelEventAdapter | None = None
        self._updating_controls = False
        self._language_switcher = get_language_switcher()
        self._selected_index: int | None = None
        self._auto_estimate_in_progress = False

        # Settings
        self._settings = QSettings("Chappy", "Chappy")
        self._auto_estimate_percentile = self._load_percentile_setting()

        # UI references for retranslation
        self._actions_title_label: QLabel | None = None
        self._anchor_title_label: QLabel | None = None
        self._anchor_placeholder: QLabel | None = None
        self._percentile_label: QLabel | None = None

        # Interactive editing state (simplified - move mode always enabled, add/delete via right-click)
        self._connected_plot: ContinuumPlotWidget | None = None

        # History recorder for undo/redo
        self._history_recorder: ContinuumHistoryRecorder | None = None
        self._history_adapter = ContinuumHistoryAdapter(
            recorder_provider=lambda: self._history_recorder
        )
        self._scientific_mutations = GlobalAnalysisMutationUseCase()
        self._component_mutations = ContinuumComponentMutationUseCase(
            mutations=self._scientific_mutations
        )

        # UI components (modern design) - interactive buttons removed

        # Quick action buttons
        self.guess_continuum_btn: QPushButton | None = None
        self.clear_all_btn: QPushButton | None = None
        # Note: _percentile_spinbox is guaranteed to be initialized in _setup_quick_actions_section
        self._percentile_spinbox: QDoubleSpinBox | None = None

        # Anchor points table
        self.anchor_points_table: QTableWidget | None = None

        # Setup UI
        self._setup_ui()
        self._connect_signals()
        self._language_switcher.language_changed.connect(self._on_language_changed)
        self._apply_translations()

    def _load_percentile_setting(self) -> float:
        """Load percentile setting from QSettings.

        Returns:
            Percentile value (default: 0.95)
        """
        value = self._settings.value("continuum_editor/auto_estimate_percentile", 0.95, type=float)
        if isinstance(value, (int, float)):
            percentile = float(value)
            # Validate range
            if 0.50 <= percentile <= 0.99:
                return percentile
            logger.warning(
                "Invalid percentile value %.2f in settings, using default 0.95", percentile
            )
        return 0.95

    def _save_percentile_setting(self, percentile: float) -> None:
        """Save percentile setting to QSettings.

        Args:
            percentile: Percentile value to save
        """
        self._settings.setValue("continuum_editor/auto_estimate_percentile", percentile)
        self._settings.sync()

    def _on_language_changed(self, _code: str) -> None:
        """Refresh all UI strings when language changes."""
        self._apply_translations()

    def changeEvent(self, event: QEvent) -> None:  # noqa: N802
        """Refresh Qt-managed translations when the application language changes."""
        if event.type() == QEvent.Type.LanguageChange:
            self._apply_translations()
        super().changeEvent(event)

    def _apply_translations(self) -> None:
        """Apply current language translations to UI widgets."""
        if self._actions_title_label:
            self._actions_title_label.setText(self.tr("Continuum Actions"))

        if self._anchor_title_label:
            self._anchor_title_label.setText(self.tr("Control points"))

        if self.guess_continuum_btn:
            if self._auto_estimate_in_progress:
                label = self.tr("Loading...")
            else:
                label = self.tr("Auto Estimate")
            self.guess_continuum_btn.setText(label)
            self.guess_continuum_btn.setToolTip(
                self.tr("Overwrite current control points with an automatic estimate")
            )

        if self.clear_all_btn:
            self.clear_all_btn.setText(self.tr("Clear Control Points"))

        if self.anchor_points_table:
            headers = [self.tr("Wavelength (Å)"), self.tr("Flux")]
            for index, text in enumerate(headers):
                header_item = self.anchor_points_table.horizontalHeaderItem(index)
                if header_item is not None:
                    header_item.setText(text)

        if self._anchor_placeholder:
            self._anchor_placeholder.setText(self.tr("Control points will appear here once"))

        if self._percentile_label:
            self._percentile_label.setText(self.tr("Percentile"))

        if self._percentile_spinbox:
            self._percentile_spinbox.setToolTip(
                self.tr(
                    "Percentile threshold for continuum estimation. Higher values (closer to "
                    "99%) capture peaks; lower values (closer to 50%) capture the median."
                )
            )

        # Update per-row controls to reflect new language
        self._update_anchor_points_table()

    def _ask_yes_no(
        self,
        title: str,
        message: str,
        *,
        icon: QMessageBox.Icon | None = None,
        yes_variant: ButtonVariant = "primary",
    ) -> bool:
        if os.getenv("PYTEST_CURRENT_TEST"):
            return True

        dialog = QMessageBox(self)
        dialog.setIcon(icon or QMessageBox.Icon.Question)
        dialog.setWindowTitle(title)
        dialog.setText(message)
        dialog.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        dialog.setDefaultButton(QMessageBox.StandardButton.No)
        dialog.setEscapeButton(QMessageBox.StandardButton.No)

        yes_button = dialog.button(QMessageBox.StandardButton.Yes)
        if isinstance(yes_button, QPushButton):
            yes_button.setText(self.tr("Yes"))
            apply_button_variant(yes_button, yes_variant)

        no_button = dialog.button(QMessageBox.StandardButton.No)
        if isinstance(no_button, QPushButton):
            no_button.setText(self.tr("No"))
            apply_button_variant(no_button, "secondary")

        dialog.exec()
        selected_button = dialog.clickedButton()
        return bool(yes_button and selected_button is yes_button)

    def _setup_ui(self) -> None:
        """Setup modern, simplified user interface."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(*SidePanelMetrics.OUTER_MARGIN)
        main_layout.setSpacing(SidePanelMetrics.SECTION_SPACING)

        # Interactive Mode Section removed - functionality moved to right-click menu

        # Quick Actions Section
        self._setup_quick_actions_section(main_layout)

        # Anchor Points Section
        self._setup_anchor_points_section(main_layout)

    # _setup_interactive_mode_section removed - functionality moved to right-click menu

    def _setup_quick_actions_section(self, layout: QVBoxLayout) -> None:
        """Setup quick action buttons section."""
        actions_frame = SidePanelSection(
            self,
            object_name="continuumActionsFrame",
            title="",
            spacing=SidePanelMetrics.ACTION_CARD_COMPACT_SPACING,
        )
        frame_layout = actions_frame.body
        self._actions_title_label = actions_frame.title_label

        # First row: percentile selection
        first_row = QHBoxLayout()
        first_row.setContentsMargins(0, 0, 0, 0)
        first_row.setSpacing(SidePanelMetrics.BUTTON_ROW_SPACING)

        self._percentile_label = QLabel(actions_frame)
        self._percentile_label.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; font-size: {Fonts.SIZE_NORMAL};"
        )
        first_row.addWidget(self._percentile_label)
        first_row.addStretch(1)

        self._percentile_spinbox = QDoubleSpinBox(actions_frame)
        self._percentile_spinbox.setObjectName("continuumPercentileSpinBox")
        # Display as percentage (50-99%), but store as decimal (0.50-0.99)
        self._percentile_spinbox.setMinimum(50.0)
        self._percentile_spinbox.setMaximum(99.0)
        self._percentile_spinbox.setSingleStep(1.0)
        self._percentile_spinbox.setDecimals(0)
        self._percentile_spinbox.setValue(self._auto_estimate_percentile * 100.0)
        self._percentile_spinbox.setSuffix("%")
        self._percentile_spinbox.valueChanged.connect(self._on_percentile_changed)
        self._percentile_spinbox.setMaximumWidth(80)  # Constrain width
        first_row.addWidget(self._percentile_spinbox)

        frame_layout.addLayout(first_row)

        self.guess_continuum_btn = QPushButton(actions_frame)
        self.guess_continuum_btn.setObjectName("continuumAutoEstimateButton")
        apply_button_variant(self.guess_continuum_btn, "primary")
        self.guess_continuum_btn.setSizePolicy(
            QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        )
        self.guess_continuum_btn.clicked.connect(self._on_auto_estimate_clicked)
        frame_layout.addWidget(self.guess_continuum_btn)

        self.clear_all_btn = QPushButton(actions_frame)
        self.clear_all_btn.setObjectName("continuumClearPointsButton")
        apply_button_variant(self.clear_all_btn, "secondary")
        self.clear_all_btn.setSizePolicy(
            QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        )
        self.clear_all_btn.clicked.connect(self._clear_all_points)
        frame_layout.addWidget(self.clear_all_btn)
        layout.addWidget(actions_frame)

    def _setup_anchor_points_section(self, layout: QVBoxLayout) -> None:
        """Setup anchor points table section."""
        anchor_frame = SidePanelSection(self, object_name="continuumAnchorFrame", title="")
        frame_layout = anchor_frame.body
        self._anchor_title_label = anchor_frame.title_label

        self.anchor_points_table = QTableWidget(0, 2)
        self.anchor_points_table.setParent(anchor_frame)
        self.anchor_points_table.setObjectName("continuumPointsTable")
        self.anchor_points_table.setHorizontalHeaderLabels(["", ""])
        self.anchor_points_table.setAlternatingRowColors(True)
        self.anchor_points_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.anchor_points_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.anchor_points_table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        self.anchor_points_table.setSizePolicy(
            QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        )
        vertical_header = self.anchor_points_table.verticalHeader()
        if vertical_header:
            vertical_header.setVisible(False)

        header = self.anchor_points_table.horizontalHeader()
        if header:
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

        frame_layout.addWidget(self.anchor_points_table)

        self._anchor_placeholder = QLabel(anchor_frame)
        self._anchor_placeholder.setObjectName("continuumPointsPlaceholder")
        self._anchor_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._anchor_placeholder.setWordWrap(True)
        self._anchor_placeholder.setStyleSheet(empty_state_label_style())
        frame_layout.addWidget(self._anchor_placeholder)

        layout.addWidget(anchor_frame, stretch=1)

        self._update_anchor_placeholder_visibility()

    def _connect_signals(self) -> None:
        """Connect signals for modern UI components."""
        # Interactive mode buttons removed - functionality moved to right-click menu

        # Connect anchor points table (for future context menu)
        if self.anchor_points_table:
            self.anchor_points_table.cellDoubleClicked.connect(self._on_table_cell_double_clicked)
            self.anchor_points_table.itemSelectionChanged.connect(self._on_table_selection_changed)
            self.anchor_points_table.itemChanged.connect(self._on_table_item_changed)

    def _update_anchor_placeholder_visibility(self) -> None:
        """Toggle placeholder to reflect table content availability."""
        if not self.anchor_points_table or self._anchor_placeholder is None:
            return

        has_rows = self.anchor_points_table.rowCount() > 0
        self.anchor_points_table.setVisible(has_rows)
        self._anchor_placeholder.setVisible(not has_rows)

    def set_project(self, project: SpectroscopyProject | None) -> None:
        """Set current project and update UI.

        Args:
            project: Project to set (None to clear)
        """
        self._detach_model_event_adapter()
        self.current_project = project
        self._selected_index = None

        if project is None:
            self.current_continuum = None
            if self.anchor_points_table:
                self.anchor_points_table.setRowCount(0)
                self._update_anchor_placeholder_visibility()
            return

        # Set first continuum as current if available
        continua = [
            comp for comp in project.model.components if isinstance(comp, ContinuumComponent)
        ]

        if continua:
            self.current_continuum = continua[0]
            self._update_anchor_points_table()
        else:
            self.current_continuum = None
        if project.model:
            self._model_event_adapter = SpectrumModelEventAdapter(project.model, self)
            self._model_event_adapter.component_added.connect(self._on_component_added)
            self._model_event_adapter.component_removed.connect(self._on_component_removed)

    def _detach_model_event_adapter(self) -> None:
        """Detach model event adapter from the current project."""
        if self._model_event_adapter is None:
            return
        with suppress(TypeError, RuntimeError):
            self._model_event_adapter.component_added.disconnect(self._on_component_added)
        with suppress(TypeError, RuntimeError):
            self._model_event_adapter.component_removed.disconnect(self._on_component_removed)
        self._model_event_adapter.close()
        self._model_event_adapter = None

    def set_history_recorder(self, recorder: ContinuumHistoryRecorder) -> None:
        """Set history recorder for undo/redo recording.

        Args:
            recorder: The history recorder instance.
        """
        self._history_recorder = recorder

    @Slot()
    def add_continuum(self) -> None:
        """Add new continuum component."""
        if not self.current_project:
            return

        try:
            continuum = self._add_continuum_component(points=[])
        except Exception as exc:
            logger.exception("Failed to add continuum component")
            message = f"Continuum editing error: {exc}"
            run_postcommit_actions_isolated(lambda: self._show_status_message(message))
            return

        self.current_continuum = continuum
        self._selected_index = None
        run_postcommit_actions_isolated(
            self._update_anchor_points_table, lambda: self._emit_component_added(continuum)
        )

    def _add_continuum_component(self, *, points: list[tuple[float, float]]) -> ContinuumComponent:
        """Commit one continuum component with its initial scientific points."""
        project = self.current_project
        if project is None:
            msg = "Continuum component creation requires an active project."
            raise RuntimeError(msg)
        n_continua = sum(
            isinstance(component, ContinuumComponent) for component in project.model.components
        )
        result = self._component_mutations.add_component(
            project,
            name=f"Continuum {n_continua + 1}",
            points=points,
            record_history=self._history_adapter.record_add_component,
            history_scope=self._history_adapter.atomic_recording,
        )
        if not result.impact.changed:
            msg = "A newly constructed continuum component must change the model."
            raise RuntimeError(msg)
        return result.component

    @Slot(ModelComponent)
    def _on_component_added(self, component: ModelComponent) -> None:
        """Handle component added to model.

        Args:
            component: Added component
        """
        if not isinstance(component, ContinuumComponent):
            return

        if self.current_continuum is None or component is self.current_continuum:
            self.current_continuum = component
            self._selected_index = None
            run_postcommit_actions_isolated(self._update_anchor_points_table)

    @Slot(ModelComponent)
    def _on_component_removed(self, component: ModelComponent) -> None:
        """Handle component removed from model.

        Args:
            component: Removed component
        """
        if not isinstance(component, ContinuumComponent):
            return

        if component is self.current_continuum:
            self.current_continuum = None
            if self.current_project:
                remaining = [
                    c
                    for c in self.current_project.model.components
                    if isinstance(c, ContinuumComponent)
                ]
                if remaining:
                    self.current_continuum = remaining[0]
            self._selected_index = None
            run_postcommit_actions_isolated(self._update_anchor_points_table)

    def get_current_continuum(self) -> ContinuumComponent | None:
        """Get currently selected continuum.

        Returns:
            Current continuum component or None
        """
        return self.current_continuum

    def refresh_anchor_points_table(self) -> None:
        """Refresh the displayed continuum anchor point table."""
        self._update_anchor_points_table()

    def _on_auto_estimate_clicked(self) -> None:
        if self._auto_estimate_in_progress:
            return

        if not self.current_project:
            logger.warning("Cannot auto-estimate continuum without a project")
            return

        existing_points = bool(self.current_continuum and self.current_continuum.continuum_points)

        if existing_points:
            title = self.tr("Auto Estimate")
            message = self.tr("Overwrite existing continuum points?")
            if not self._ask_yes_no(title, message, yes_variant="danger"):
                return

        self._run_auto_estimate()

    def _set_auto_estimate_running(self, running: bool) -> None:
        self._auto_estimate_in_progress = running
        if not self.guess_continuum_btn:
            return

        if running:
            processing_label = self.tr("Loading...")
            self.guess_continuum_btn.setText(processing_label)
        else:
            label = self.tr("Auto Estimate")
            self.guess_continuum_btn.setText(label)

        self.guess_continuum_btn.setEnabled(not running)

    def _show_status_message(self, message: str) -> None:
        if message:
            self.status_message.emit(message)

    def _emit_component_added(self, continuum: ContinuumComponent) -> None:
        """Publish a committed component addition to Qt observers."""
        self.component_added.emit(continuum)

    def _emit_continuum_updated(self, continuum: ContinuumComponent) -> None:
        """Publish a committed continuum update to Qt observers."""
        self.continuum_updated.emit(continuum)

    def _refresh_plot_display(self) -> None:
        plot_widget = self._connected_plot
        if not plot_widget:
            return

        anchor_points: list[tuple[float, float]] = []
        if self.current_continuum:
            anchor_points = self.current_continuum.get_continuum_points()

        if (
            self.mode_state_store
            and self.mode_state_store.current_mode is not None
            and self.mode_state_store.current_mode != EditingMode.CONTINUUM
        ):
            plot_widget.hide_continuum_display()
            return

        if not self.current_project or not self.current_continuum:
            empty = np.array([], dtype=float)
            plot_widget.set_continuum_data(empty, empty, anchor_points)
            return

        spectrum = self.current_project.model.observed_spectrum
        if spectrum is None or len(spectrum.wavelength) == 0:
            empty = np.array([], dtype=float)
            plot_widget.set_continuum_data(empty, empty, anchor_points)
            return

        wavelength_array = np.asarray(spectrum.wavelength, dtype=float)
        continuum_flux = self.current_continuum.calculate(wavelength_array)
        plot_widget.set_continuum_data(wavelength_array, continuum_flux, anchor_points)

    def _run_auto_estimate(self) -> None:
        """Automatically guess continuum level."""
        project = self.current_project
        if project is None:
            logger.warning("No project available for continuum guess")
            return

        spectrum = project.model.observed_spectrum
        if spectrum is None:
            logger.warning("No observed spectrum available for continuum estimation")
            self._show_status_message(
                self.tr("No observation data available for continuum fitting")
            )
            return

        current_continuum = self.current_continuum
        if current_continuum is None:
            continua = [c for c in project.model.components if isinstance(c, ContinuumComponent)]
            if continua:
                current_continuum = continua[0]
                self.current_continuum = current_continuum

        self._set_auto_estimate_running(True)

        try:
            component_created = False
            percentile = self._auto_estimate_percentile
            candidate = ContinuumComponent(
                name=current_continuum.name if current_continuum is not None else "Continuum"
            )
            candidate.guess_continuum(
                spectrum.wavelength, spectrum.flux, bin_size=100.0, cut_level=percentile
            )
            new_points = list(candidate.continuum_points)

            if current_continuum is None:
                current_continuum = self._add_continuum_component(points=new_points)
                self.current_continuum = current_continuum
                self._selected_index = None
                component_created = True
            else:
                old_points = list(current_continuum.continuum_points)
                impact = self._commit_continuum_points(
                    current_continuum,
                    before_points=old_points,
                    after_points=new_points,
                    record_history=lambda: self._history_adapter.record_reset(
                        current_continuum, old_points, new_points
                    ),
                )
                if not impact.changed:
                    return
        except Exception:
            logger.exception("Failed to guess continuum")
            run_postcommit_actions_isolated(
                lambda: self._show_status_message(self.tr("Continuum auto estimate failed"))
            )
            return
        else:
            actions: list[Callable[[], object]] = [self._update_anchor_points_table]
            if component_created:
                actions.append(lambda: self._emit_component_added(current_continuum))
            actions.extend(
                (
                    lambda: self._emit_continuum_updated(current_continuum),
                    self._refresh_plot_display,
                    lambda: self._show_status_message(self.tr("Continuum auto estimate complete")),
                )
            )
            run_postcommit_actions_isolated(*actions)
        finally:
            run_postcommit_actions_isolated(lambda: self._set_auto_estimate_running(False))

    def _on_percentile_changed(self, value: float) -> None:
        """Handle percentile value change.

        Args:
            value: New percentile value in percentage (50-99)
        """
        # Convert from percentage to decimal (50% -> 0.50)
        percentile_decimal = value / 100.0
        self._auto_estimate_percentile = percentile_decimal
        self._save_percentile_setting(percentile_decimal)

    # New action methods for modern UI
    def _clear_all_points(self) -> None:
        """Clear user-added anchor points while preserving defaults."""
        if not self.current_continuum:
            return

        title = self.tr("Clear Control Points")
        message = self.tr("Clears all custom control points and restores defaults. Continue?")
        if not self._ask_yes_no(
            title, message, icon=QMessageBox.Icon.Warning, yes_variant="danger"
        ):
            return

        try:
            if self._reset_continuum_points():
                return

            # Fallback when defaults are unavailable (e.g., no spectrum data)
            self._apply_continuum_points([])

        except Exception as exc:
            logger.exception("Failed to clear anchor points")
            self._show_status_message(f"Continuum editing error: {exc}")

    def _update_anchor_points_table(self) -> None:
        """Update anchor points table with current continuum data."""
        if not self.anchor_points_table or not self.current_continuum:
            return

        try:
            self._updating_controls = True
            # Clear existing rows
            self.anchor_points_table.setRowCount(0)

            # Add anchor points
            points = self.current_continuum.get_continuum_points()
            self.anchor_points_table.setRowCount(len(points))

            for row, (wavelength, flux) in enumerate(points):
                # Wavelength item
                wave_item = QTableWidgetItem(f"{wavelength:.2f}")
                wave_item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )
                self.anchor_points_table.setItem(row, self.COLUMN_WAVELENGTH, wave_item)

                # Flux item
                flux_item = QTableWidgetItem(f"{flux:.4f}")
                flux_item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )
                self.anchor_points_table.setItem(row, self.COLUMN_FLUX, flux_item)

            if self._selected_index is not None and 0 <= self._selected_index < len(points):
                self.anchor_points_table.selectRow(self._selected_index)

        finally:
            self._updating_controls = False

        self._update_anchor_placeholder_visibility()
        self._emit_point_count_changed()

    def _on_table_cell_double_clicked(self, row: int, column: int) -> None:
        """Handle table cell double-click for inline editing.

        Args:
            row: Row index
            column: Column index
        """
        if not self.anchor_points_table:
            return
        item = self.anchor_points_table.item(row, column)
        if item:
            self.anchor_points_table.editItem(item)

    def connect_plot_widget(self, plot_widget: ContinuumPlotWidget) -> None:
        """Connect to plotting widget for interactive continuum editing.

        Args:
            plot_widget: Plotting widget with continuum interaction signals
        """
        # This method is kept for shell signal wiring but no longer performs any connections.
        self._connected_plot = plot_widget

    def create_interaction_controller(
        self,
        *,
        snapshot_consumer: Callable[[InteractionStateSnapshot[SnapshotContext]], None],
        current_points: Callable[[], list[Coordinate]],
    ) -> ContinuumStateController:
        """Create the continuum-mode owned spectrum interaction controller."""
        log_emitter = InteractionLogEmitter(channel=InteractionChannel.CONTINUUM, logger=logger)
        interaction_controller = ContinuumInteractionController(
            log_emitter=log_emitter, current_points=current_points
        )
        return ContinuumStateController(
            snapshot_consumer=snapshot_consumer,
            continuum_interaction_controller=interaction_controller,
            logger=logger,
        )

    def _on_table_selection_changed(self) -> None:
        if self._updating_controls or not self.anchor_points_table:
            return

        indexes = self.anchor_points_table.selectionModel().selectedRows()
        if not indexes:
            self._selected_index = None
            return

        row = indexes[0].row()
        self._selected_index = row

    def _on_table_item_changed(self, item: QTableWidgetItem) -> None:
        if self._updating_controls or not self.current_continuum:
            return

        continuum = self.current_continuum
        row = item.row()
        column = item.column()
        points = continuum.continuum_points

        if row < 0 or row >= len(points):
            return

        old_wavelength, old_flux = points[row]
        text = item.text().strip()

        try:
            new_value = float(text)
        except ValueError:
            self._restore_table_value(row, column, old_wavelength, old_flux)
            return

        try:
            new_wavelength: float
            new_flux: float

            before_points = continuum.get_continuum_points()
            after_points = list(before_points)
            if column == self.COLUMN_WAVELENGTH:
                if self._has_duplicate_wavelength(new_value, exclude_row=row):
                    self._show_duplicate_wavelength_dialog(new_value)
                    self._restore_table_value(row, column, old_wavelength, old_flux)
                    return

                new_wavelength, new_flux = new_value, old_flux
            elif column == self.COLUMN_FLUX:
                new_wavelength, new_flux = old_wavelength, new_value
            else:
                return

            after_points[row] = (new_wavelength, new_flux)
            after_points.sort(key=lambda point: point[0])
            impact = self._commit_continuum_points(
                continuum,
                before_points=before_points,
                after_points=after_points,
                record_history=lambda: self._history_adapter.record_move_point(
                    continuum, before_points, after_points
                ),
            )
            if not impact.changed:
                self._restore_table_value(row, column, old_wavelength, old_flux)
                return
        except Exception as exc:
            logger.exception("Failed to apply table edit")
            message = f"Continuum editing error: {exc}"
            run_postcommit_actions_isolated(
                lambda: self._restore_table_value(row, column, old_wavelength, old_flux),
                lambda: self._show_status_message(message),
            )
            return

        self._selected_index = after_points.index((new_wavelength, new_flux))
        run_postcommit_actions_isolated(
            self._update_anchor_points_table,
            lambda: self._emit_continuum_updated(continuum),
            self._refresh_plot_display,
        )

    def _restore_table_value(self, row: int, column: int, wavelength: float, flux: float) -> None:
        if not self.anchor_points_table:
            return

        display = f"{wavelength:.2f}" if column == self.COLUMN_WAVELENGTH else f"{flux:.4f}"
        item = self.anchor_points_table.item(row, column)
        if item is None:
            return
        self._updating_controls = True
        try:
            item.setText(display)
        finally:
            self._updating_controls = False

    def _has_duplicate_wavelength(self, wavelength: float, *, exclude_row: int) -> bool:
        if not self.current_continuum:
            return False
        for idx, (existing_wave, _flux) in enumerate(self.current_continuum.continuum_points):
            if idx == exclude_row:
                continue
            if abs(existing_wave - wavelength) < 1e-6:
                return True
        return False

    def _show_duplicate_wavelength_dialog(self, wavelength: float) -> None:
        title = self.tr("Duplicate Wavelength")
        body_template = self.tr(
            "A control point already exists at wavelength {wavelength} Å.\n"
            "Wavelengths must be unique."
        )
        QMessageBox.warning(self, title, body_template.format(wavelength=wavelength))

    def _show_minimum_points_warning(self) -> None:
        title = self.tr("Minimum Control Points Required")
        body = self.tr(
            "The continuum requires at least 3 control points.\n"
            "Deletion was cancelled to keep 3 points."
        )
        QMessageBox.information(self, title, body)

    def _on_table_delete_clicked(self, row: int) -> None:
        if not self.current_continuum:
            return

        continuum = self.current_continuum
        if continuum.num_continuum_points() <= 3:
            self._show_minimum_points_warning()
            return

        if row < 0 or row >= len(continuum.continuum_points):
            return

        try:
            before_points = continuum.get_continuum_points()
            after_points = list(before_points)
            del after_points[row]
            impact = self._commit_continuum_points(
                continuum,
                before_points=before_points,
                after_points=after_points,
                record_history=lambda: self._history_adapter.record_delete_point(
                    continuum, before_points, after_points
                ),
            )
            if not impact.changed:
                return
        except Exception as exc:
            logger.exception("Failed to delete continuum point from table")
            message = f"Continuum editing error: {exc}"
            run_postcommit_actions_isolated(lambda: self._show_status_message(message))
            return

        remaining = len(after_points)
        if remaining == 0:
            self._selected_index = None
        else:
            self._selected_index = min(row, remaining - 1)

        run_postcommit_actions_isolated(
            self._update_anchor_points_table,
            lambda: self._emit_continuum_updated(continuum),
            self._refresh_plot_display,
        )

    def request_delete_point(self, index: int) -> None:
        """Delete continuum point at given index (called from context menu).

        Args:
            index: Index of the point to delete
        """
        self._on_table_delete_clicked(index)

    def request_add_point(self, wavelength: float, flux: float) -> None:
        """Add continuum point at given position (called from context menu).

        Args:
            wavelength: Wavelength of the new point
            flux: Flux value of the new point
        """
        if not self.current_continuum:
            return

        continuum = self.current_continuum
        try:
            before_points = continuum.get_continuum_points()
            after_points = [*before_points, (wavelength, flux)]
            after_points.sort(key=lambda point: point[0])
            impact = self._commit_continuum_points(
                continuum,
                before_points=before_points,
                after_points=after_points,
                record_history=lambda: self._history_adapter.record_add_point(
                    continuum, before_points, after_points
                ),
            )
            if not impact.changed:
                return
        except Exception as exc:
            logger.exception("Failed to add continuum point from context menu")
            message = f"Continuum editing error: {exc}"
            run_postcommit_actions_isolated(lambda: self._show_status_message(message))
            return

        run_postcommit_actions_isolated(
            self._update_anchor_points_table,
            lambda: self._emit_continuum_updated(continuum),
            self._refresh_plot_display,
        )

    def _reset_continuum_points(self) -> bool:
        if not self.current_continuum:
            return False

        default_points = self._get_default_anchor_points()
        if default_points is None:
            return False

        self._apply_continuum_points(default_points)
        return True

    def _emit_point_count_changed(self) -> None:
        if not self.current_continuum:
            return

    def _get_default_anchor_points(self) -> list[tuple[float, float]] | None:
        if not self.current_project:
            return None

        spectrum = self.current_project.model.observed_spectrum
        if spectrum is None or len(spectrum.wavelength) < 3:
            return None

        wavelengths = spectrum.wavelength
        min_wave = float(wavelengths[0])
        max_wave = float(wavelengths[-1])
        mid_wave = float(wavelengths[len(wavelengths) // 2])

        return [
            (min_wave, DEFAULT_CONTINUUM_FLUX),
            (mid_wave, DEFAULT_CONTINUUM_FLUX),
            (max_wave, DEFAULT_CONTINUUM_FLUX),
        ]

    def _apply_continuum_points(
        self, new_points: list[tuple[float, float]]
    ) -> AnalysisMutationImpact:
        if not self.current_continuum:
            return AnalysisMutationImpact.no_change()

        continuum = self.current_continuum
        old_points = list(continuum.continuum_points)
        impact = self._commit_continuum_points(
            continuum,
            before_points=old_points,
            after_points=new_points,
            record_history=lambda: self._history_adapter.record_reset(
                continuum, old_points, new_points
            ),
        )
        if not impact.changed:
            return impact

        if new_points:
            self._selected_index = len(new_points) // 2
        else:
            self._selected_index = None

        run_postcommit_actions_isolated(
            self._update_anchor_points_table,
            lambda: self._emit_continuum_updated(continuum),
            self._refresh_plot_display,
        )
        return impact

    def _commit_continuum_points(
        self,
        continuum: ContinuumComponent,
        *,
        before_points: list[tuple[float, float]],
        after_points: list[tuple[float, float]],
        record_history: Callable[[], None],
    ) -> AnalysisMutationImpact:
        """Commit continuum points, analysis invalidation, and history atomically."""
        project = self.current_project
        if project is None:
            msg = "Continuum point mutation requires an active project."
            raise RuntimeError(msg)
        return self._scientific_mutations.execute(
            project,
            mutate=lambda: self._replace_continuum_points(
                continuum, before_points=before_points, after_points=after_points
            ),
            rollback=lambda: self._restore_continuum_points(continuum, before_points),
            record_history=record_history,
            history_scope=self._history_adapter.atomic_recording,
        )

    @staticmethod
    def _replace_continuum_points(
        continuum: ContinuumComponent,
        *,
        before_points: list[tuple[float, float]],
        after_points: list[tuple[float, float]],
    ) -> bool:
        """Replace continuum points when their scientific state changed."""
        if before_points == after_points:
            return False
        continuum.continuum_points = list(after_points)
        return True

    @staticmethod
    def _restore_continuum_points(
        continuum: ContinuumComponent, before_points: list[tuple[float, float]]
    ) -> None:
        """Restore continuum points after a failed transaction."""
        continuum.continuum_points = list(before_points)
