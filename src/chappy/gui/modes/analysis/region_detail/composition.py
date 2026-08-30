"""Optimize mode composition helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from chappy.application.optimize import (
    ApplyFitResultUseCase,
    EditLineAnalysisHalfWidthUseCase,
    FitResultPayloadParser,
    MaskMutationUseCase,
    OptimizeExportUseCase,
    OptimizeGroupAnalysisUseCase,
    OptimizeParameterMutationUseCase,
    TieSetEditUseCase,
    build_optimization_export_request,
)
from chappy.gui.modes.analysis.region_detail.adapters.confirm_dialog_adapter import (
    OptimizeConfirmDialogAdapter,
)
from chappy.gui.modes.analysis.region_detail.adapters.export_dialog_adapter import (
    OptimizeExportDialogAdapter,
)
from chappy.gui.modes.analysis.region_detail.adapters.history_adapter import OptimizeHistoryAdapter
from chappy.gui.modes.analysis.region_detail.adapters.line_analysis_half_width_transaction_adapter import (
    OptimizeLineAnalysisHalfWidthTransactionAdapter,
)
from chappy.gui.modes.analysis.region_detail.adapters.model_mutation_adapter import (
    OptimizeModelMutationAdapter,
)
from chappy.gui.modes.analysis.region_detail.adapters.settings_adapter import (
    OptimizeSettingsAdapter,
)
from chappy.gui.modes.analysis.region_detail.coordinator import OptimizeModeCoordinator
from chappy.gui.modes.analysis.region_detail.group_selection_controller import (
    OptimizeGroupSelectionController,
)
from chappy.gui.modes.analysis.region_detail.line_analysis_half_width_controller import (
    LineAnalysisHalfWidthController,
)
from chappy.gui.modes.analysis.region_detail.mask.mask_panel_adapter import (
    OptimizeMaskPanelAdapter,
)
from chappy.gui.modes.analysis.region_detail.mask.mask_workflow_controller import (
    OptimizeMaskWorkflowController,
)
from chappy.gui.modes.analysis.region_detail.model_addition_controller import (
    OptimizeModelAdditionController,
)
from chappy.gui.modes.analysis.region_detail.parameters.parameter_context_controller import (
    OptimizeParameterContextController,
)
from chappy.gui.modes.analysis.region_detail.parameters.parameter_delete_controller import (
    OptimizeParameterDeleteController,
)
from chappy.gui.modes.analysis.region_detail.parameters.parameter_edit_controller import (
    OptimizeParameterEditController,
)
from chappy.gui.modes.analysis.region_detail.parameters.parameter_fix_controller import (
    OptimizeParameterFixController,
)
from chappy.gui.modes.analysis.region_detail.parameters.parameter_value_controller import (
    OptimizeParameterValueController,
)
from chappy.gui.modes.analysis.region_detail.tie_set_edit_controller import (
    OptimizeTieSetEditController,
)
from chappy.gui.modes.analysis.region_detail.tree.tree_columns import (
    COL_ANALYSIS_HALF_WIDTH,
    COL_COMOVING,
    COL_ID,
    COL_LOOKBACK,
    COL_SPECIES,
    COL_WAVELENGTH,
    COL_Z,
    COLUMNS,
    PARAMETER_COLUMNS,
    PARAMETER_CONFIGS,
)
from chappy.gui.modes.analysis.region_detail.tree.tree_context_menu_controller import (
    OptimizeTreeContextMenuController,
)
from chappy.gui.modes.analysis.region_detail.tree.tree_header_controller import (
    OptimizeTreeHeaderController,
)
from chappy.gui.modes.analysis.region_detail.tree.tree_render_controller import (
    OptimizeTreeRenderController,
)
from chappy.gui.modes.analysis.region_detail.tree.tree_row_renderer import (
    OptimizeTreeParameterColumn,
    OptimizeTreeRowColumns,
    OptimizeTreeRowRenderer,
)
from chappy.gui.modes.analysis.region_detail.tree.tree_selection_controller import (
    OptimizeTreeSelectionController,
)
from chappy.gui.modes.analysis.region_detail.tree.tree_style_controller import (
    OptimizeTreeStyleColumns,
    OptimizeTreeStyleController,
)
from chappy.gui.modes.analysis.region_detail.tree.tree_view_adapter import OptimizeTreeViewAdapter
from chappy.gui.modes.analysis.region_detail.ui_facade import RegionDetailUi
from chappy.gui.modes.analysis.region_detail.workflows.export_workflow_controller import (
    OptimizeExportWorkflowController,
)
from chappy.gui.modes.analysis.region_detail.workflows.fit_workflow_controller import (
    OptimizeFitWorkflowController,
)
from chappy.infrastructure.csv_exporter import CsvExporter

if TYPE_CHECKING:
    from collections.abc import Callable

    from PySide6.QtCore import QObject
    from PySide6.QtWidgets import QTreeWidget, QWidget

    from chappy.application.optimize import MaskMutationHistoryRecorder
    from chappy.core.spectroscopy_project import SpectroscopyProject
    from chappy.gui.modes.analysis.region_detail.coordinator import (
        OptimizeEditorSignalPort,
        OptimizeModeCoordinatorPort,
    )
    from chappy.gui.modes.analysis.region_detail.editor import OptimizeEditor
    from chappy.gui.modes.analysis.region_detail.group_selection_controller import (
        RegionActionsViewPort,
        RegionMaskRefreshPort,
        RegionSelectorViewPort,
        RegionTreeRenderPort,
    )
    from chappy.gui.modes.analysis.region_detail.mask.mask_panel import OptimizeMaskPanel
    from chappy.gui.modes.analysis.region_detail.mask.mask_workflow_controller import (
        OptimizeMaskWorkflowPort,
    )
    from chappy.gui.modes.analysis.region_detail.model_addition_controller import (
        OptimizeModelAdditionPort,
        OptimizeModelAdditionUseCasePort,
    )
    from chappy.gui.modes.analysis.region_detail.parameters.parameter_delete_controller import (
        OptimizeParameterDeletePort,
    )
    from chappy.gui.modes.analysis.region_detail.parameters.parameter_edit_controller import (
        OptimizeParameterEditPort,
    )
    from chappy.gui.modes.analysis.region_detail.parameters.parameter_fix_controller import (
        OptimizeParameterFixPort,
    )
    from chappy.gui.modes.analysis.region_detail.parameters.parameter_value_controller import (
        OptimizeParameterValuePort,
    )
    from chappy.gui.modes.analysis.region_detail.tie_set_edit_controller import (
        OptimizeTieSetEditPort,
    )
    from chappy.gui.modes.analysis.region_detail.tree.tree_context_menu_controller import (
        OptimizeTreeContextMenuPort,
    )
    from chappy.gui.modes.analysis.region_detail.tree.tree_header_controller import (
        OptimizeTreeHeaderPort,
    )
    from chappy.gui.modes.analysis.region_detail.tree.tree_render_controller import (
        OptimizeTreeRenderPort,
    )
    from chappy.gui.modes.analysis.region_detail.tree.tree_row_renderer import (
        OptimizeTreeRowRenderPort,
    )
    from chappy.gui.modes.analysis.region_detail.tree.tree_selection_controller import (
        OptimizeTreeSelectionPort,
    )
    from chappy.gui.modes.analysis.region_detail.tree.tree_style_controller import (
        OptimizeTreeStylePort,
    )
    from chappy.gui.modes.analysis.region_detail.workflows.export_workflow_controller import (
        OptimizeExportWorkflowPort,
    )
    from chappy.gui.modes.analysis.region_detail.workflows.fit_workflow_controller import (
        OptimizeFitEditorPort,
        OptimizeFitWorkflowPort,
    )
    from chappy.gui.modes.common.analysis_navigation import AnalysisRegionFocusPort
    from chappy.gui.modes.mode_state_store import ModeStateStore

__all__ = [
    "MULTIPLET_REDSHIFT_TOLERANCE",
    "OptimizeParameterMutationUseCase",
    "TieSetEditUseCase",
    "build_region_detail",
]

MULTIPLET_REDSHIFT_TOLERANCE = 5e-5


def create_optimize_history_adapter() -> OptimizeHistoryAdapter:
    """Create the optimize history adapter."""
    return OptimizeHistoryAdapter()


def create_optimize_mask_panel_adapter(mask_panel: OptimizeMaskPanel) -> OptimizeMaskPanelAdapter:
    """Create the optimize mask panel adapter."""
    return OptimizeMaskPanelAdapter(mask_panel)


def create_optimize_settings_adapter() -> OptimizeSettingsAdapter:
    """Create the optimize settings adapter."""
    return OptimizeSettingsAdapter()


def create_optimize_model_mutation_adapter() -> OptimizeModelMutationAdapter:
    """Create the optimize model mutation adapter."""
    return OptimizeModelMutationAdapter()


def create_line_analysis_half_width_controller(
    *,
    project_provider: Callable[[], SpectroscopyProject | None],
    group_controller: OptimizeGroupSelectionController,
    history: OptimizeHistoryAdapter,
) -> LineAnalysisHalfWidthController:
    """Create the Optimize scientific range edit controller and transaction boundary."""
    adapter = OptimizeLineAnalysisHalfWidthTransactionAdapter(
        project_provider=project_provider, group_controller=group_controller, history=history
    )
    return LineAnalysisHalfWidthController(
        EditLineAnalysisHalfWidthUseCase(reader=adapter, transaction=adapter)
    )


def create_optimize_export_dialog_adapter(parent: QWidget) -> OptimizeExportDialogAdapter:
    """Create the optimize export dialog adapter."""
    return OptimizeExportDialogAdapter(parent)


def create_optimize_confirm_dialog_adapter(parent: QWidget) -> OptimizeConfirmDialogAdapter:
    """Create the optimize confirmation dialog adapter."""
    return OptimizeConfirmDialogAdapter(parent)


def create_optimize_mode_coordinator(
    *, panel: OptimizeModeCoordinatorPort, editor: OptimizeEditorSignalPort
) -> OptimizeModeCoordinator:
    """Create the optimize mode signal coordinator."""
    return OptimizeModeCoordinator(panel=panel, editor=editor)


def create_optimize_export_workflow_controller(
    *, port: OptimizeExportWorkflowPort, dialog_adapter: OptimizeExportDialogAdapter
) -> OptimizeExportWorkflowController:
    """Create the default optimize export workflow controller."""
    return OptimizeExportWorkflowController(
        port=port,
        dialog_adapter=dialog_adapter,
        export_usecase=OptimizeExportUseCase(),
        csv_exporter=CsvExporter(),
        request_builder=build_optimization_export_request,
    )


def create_optimize_fit_workflow_controller(
    editor: OptimizeFitEditorPort, port: OptimizeFitWorkflowPort
) -> OptimizeFitWorkflowController:
    """Create the default optimize fit workflow controller."""
    return OptimizeFitWorkflowController(
        editor, port, parser=FitResultPayloadParser(), usecase=ApplyFitResultUseCase()
    )


def create_optimize_parameter_mutation_usecase() -> OptimizeParameterMutationUseCase:
    """Create the shared optimize parameter mutation use case."""
    return OptimizeParameterMutationUseCase()


def create_optimize_parameter_value_controller(
    *, port: OptimizeParameterValuePort, usecase: OptimizeParameterMutationUseCase
) -> OptimizeParameterValueController:
    """Create the default optimize parameter value controller."""
    return OptimizeParameterValueController(port=port, usecase=usecase)


def create_optimize_tie_set_edit_usecase(
    *, redshift_tolerance: float, parameter_mutation: OptimizeParameterMutationUseCase
) -> TieSetEditUseCase:
    """Create the optimize tie set edit use case."""
    return TieSetEditUseCase(
        redshift_tolerance=redshift_tolerance, parameter_mutation=parameter_mutation
    )


def create_optimize_tie_set_edit_controller(
    *, usecase: TieSetEditUseCase, port: OptimizeTieSetEditPort
) -> OptimizeTieSetEditController:
    """Create the optimize tie set edit controller."""
    return OptimizeTieSetEditController(usecase=usecase, port=port)


def create_optimize_parameter_context_controller(
    *, multiplet_redshift_tolerance: float, min_redshift: float
) -> OptimizeParameterContextController:
    """Create the optimize parameter context controller."""
    return OptimizeParameterContextController(
        multiplet_redshift_tolerance=multiplet_redshift_tolerance, min_redshift=min_redshift
    )


def create_optimize_parameter_edit_controller(
    *, parent: QWidget, port: OptimizeParameterEditPort
) -> OptimizeParameterEditController:
    """Create the optimize parameter edit controller."""
    return OptimizeParameterEditController(parent=parent, port=port)


def create_optimize_parameter_delete_controller(
    *, port: OptimizeParameterDeletePort
) -> OptimizeParameterDeleteController:
    """Create the optimize parameter delete controller."""
    return OptimizeParameterDeleteController(port=port)


def create_optimize_parameter_fix_controller(
    *, port: OptimizeParameterFixPort
) -> OptimizeParameterFixController:
    """Create the optimize parameter fixed-state controller."""
    return OptimizeParameterFixController(port=port)


def create_optimize_group_selection_controller(
    *,
    selector: RegionSelectorViewPort,
    actions: RegionActionsViewPort,
    tree_render: RegionTreeRenderPort,
    mask_refresh: RegionMaskRefreshPort,
    analysis_focus: AnalysisRegionFocusPort,
) -> OptimizeGroupSelectionController:
    """Create the default optimize group selection controller."""
    return OptimizeGroupSelectionController(
        selector=selector,
        actions=actions,
        tree_render=tree_render,
        mask_refresh=mask_refresh,
        analysis_focus=analysis_focus,
        usecase=OptimizeGroupAnalysisUseCase(),
    )


def create_optimize_mask_workflow_controller(
    *,
    port: OptimizeMaskWorkflowPort,
    mask_adapter: OptimizeMaskPanelAdapter,
    history: MaskMutationHistoryRecorder,
    event_parent: QObject,
) -> OptimizeMaskWorkflowController:
    """Create the optimize mask workflow controller."""
    return OptimizeMaskWorkflowController(
        port=port,
        mask_adapter=mask_adapter,
        usecase=MaskMutationUseCase(),
        history=history,
        event_parent=event_parent,
    )


def create_optimize_tree_selection_controller(
    *, tree: QTreeWidget, port: OptimizeTreeSelectionPort
) -> OptimizeTreeSelectionController:
    """Create the optimize tree selection controller."""
    return OptimizeTreeSelectionController(tree=tree, port=port)


def create_optimize_tree_style_controller(
    *, port: OptimizeTreeStylePort
) -> OptimizeTreeStyleController:
    """Create the optimize tree style controller."""
    return OptimizeTreeStyleController(
        columns=OptimizeTreeStyleColumns(parameter_columns=PARAMETER_COLUMNS), port=port
    )


def create_optimize_tree_row_renderer(
    *, port: OptimizeTreeRowRenderPort
) -> OptimizeTreeRowRenderer:
    """Create the optimize tree row renderer."""
    return OptimizeTreeRowRenderer(
        columns=OptimizeTreeRowColumns(
            column_count=len(COLUMNS),
            id_column=COL_ID,
            species_column=COL_SPECIES,
            redshift_column=COL_Z,
            wavelength_column=COL_WAVELENGTH,
            lookback_column=COL_LOOKBACK,
            comoving_column=COL_COMOVING,
            analysis_half_width_column=COL_ANALYSIS_HALF_WIDTH,
            parameter_columns=tuple(
                OptimizeTreeParameterColumn(
                    name=param_name,
                    value_column=value_column,
                    value_format=value_format,
                    default_value=default_value,
                )
                for (param_name, value_column, value_format, default_value) in PARAMETER_CONFIGS
            ),
        ),
        port=port,
    )


def create_optimize_tree_view_adapter(
    *,
    tree: QTreeWidget,
    row_renderer: OptimizeTreeRowRenderer,
    set_item_changed_suppressed: Callable[[bool], None],
    on_selection_changed: Callable[[], None],
) -> OptimizeTreeViewAdapter:
    """Create the optimize tree view adapter."""
    return OptimizeTreeViewAdapter(
        tree=tree,
        row_renderer=row_renderer,
        set_item_changed_suppressed=set_item_changed_suppressed,
        on_selection_changed=on_selection_changed,
    )


def create_optimize_tree_render_controller(
    *, port: OptimizeTreeRenderPort
) -> OptimizeTreeRenderController:
    """Create the optimize tree render controller."""
    return OptimizeTreeRenderController(port=port)


def create_optimize_tree_context_menu_controller(
    *,
    tree: QTreeWidget,
    parent: QWidget,
    port: OptimizeTreeContextMenuPort,
    tie_set_edit: OptimizeTieSetEditController,
    tie_label_for_uid: Callable[[str], str | None],
) -> OptimizeTreeContextMenuController:
    """Create the optimize tree context-menu controller."""
    return OptimizeTreeContextMenuController(
        tree=tree,
        parent=parent,
        port=port,
        tie_set_edit=tie_set_edit,
        tie_label_for_uid=tie_label_for_uid,
    )


def create_optimize_tree_header_controller(
    *, tree: QTreeWidget, parent: QWidget, port: OptimizeTreeHeaderPort
) -> OptimizeTreeHeaderController:
    """Create the optimize tree header controller."""
    return OptimizeTreeHeaderController(tree=tree, parent=parent, port=port)


def create_optimize_model_addition_controller(
    *, port: OptimizeModelAdditionPort, usecase: OptimizeModelAdditionUseCasePort
) -> OptimizeModelAdditionController:
    """Create the optimize model-addition controller."""
    return OptimizeModelAdditionController(port=port, usecase=usecase)


def build_region_detail(
    *,
    optimize_editor: OptimizeEditor,
    analysis_focus: AnalysisRegionFocusPort,
    mode_state: ModeStateStore | None,
    model_addition_usecase: OptimizeModelAdditionUseCasePort,
    velocity_plot_active_provider: Callable[[], bool],
    project_file_path_provider: Callable[[], str | None],
    parent: QWidget | None = None,
) -> RegionDetailUi:
    """Compose the Region Detail panel and its use cases behind the UI facade.

    Fit region resolution must follow the Detail panel's selection: the editor
    has no widgets of its own, so its active-region provider is wired here,
    right after the panel exists.
    """
    # Local import: panel.py imports create_optimize_* factories from this module at
    # top level, so a module-level import of RegionDetailPanel here would cycle.
    from chappy.gui.modes.analysis.region_detail.panel import RegionDetailPanel  # noqa: PLC0415

    parameter_mutation_usecase = create_optimize_parameter_mutation_usecase()
    panel = RegionDetailPanel(
        optimize_editor=optimize_editor,
        analysis_focus=analysis_focus,
        mode_state=mode_state,
        model_addition_usecase=model_addition_usecase,
        parameter_mutation_usecase=parameter_mutation_usecase,
        tie_set_edit_usecase=create_optimize_tie_set_edit_usecase(
            redshift_tolerance=MULTIPLET_REDSHIFT_TOLERANCE,
            parameter_mutation=parameter_mutation_usecase,
        ),
        velocity_plot_active_provider=velocity_plot_active_provider,
        project_file_path_provider=project_file_path_provider,
        parent=parent,
    )
    optimize_editor.set_active_region_id_provider(panel.current_region_id)
    return RegionDetailUi(panel)
