"""Optimize mode module."""

from chappy.gui.modes.analysis.region_detail.adapters.export_dialog_adapter import (
    OptimizeExportDialogAdapter,
)
from chappy.gui.modes.analysis.region_detail.adapters.history_adapter import (
    OptimizeHistoryAdapter,
    OptimizeHistoryRecorder,
)
from chappy.gui.modes.analysis.region_detail.adapters.model_mutation_adapter import (
    OptimizeModelMutationAdapter,
)
from chappy.gui.modes.analysis.region_detail.adapters.settings_adapter import (
    OptimizeSettingsAdapter,
)
from chappy.gui.modes.analysis.region_detail.composition import build_region_detail
from chappy.gui.modes.analysis.region_detail.context_menu_controller import (
    OptimizeContextMenuController,
    OptimizeContextMenuRequest,
)
from chappy.gui.modes.analysis.region_detail.editor import OptimizeEditor
from chappy.gui.modes.analysis.region_detail.mask.mask_panel import OptimizeMaskPanel
from chappy.gui.modes.analysis.region_detail.mask.mask_panel_adapter import (
    OptimizeMaskPanelAdapter,
)
from chappy.gui.modes.analysis.region_detail.model_addition_controller import (
    OptimizeModelAdditionController,
    OptimizeModelAdditionPort,
)
from chappy.gui.modes.analysis.region_detail.panel import RegionDetailPanel
from chappy.gui.modes.analysis.region_detail.parameters.parameter_edit_controller import (
    OptimizeParameterDialogContext,
    OptimizeParameterEditController,
    OptimizeParameterEditPort,
)
from chappy.gui.modes.analysis.region_detail.runtime import (
    OptimizeModeRuntime,
    OptimizeModeRuntimePorts,
    OptimizeVelocityOverlayRuntimePort,
)
from chappy.gui.modes.analysis.region_detail.spectrum_integration import (
    OptimizeContextMenuActionProvider,
    OptimizeSpectrumIntegration,
    OptimizeSpectrumInteractionCoordinatorPort,
    OptimizeSpectrumPanelPort,
)
from chappy.gui.modes.analysis.region_detail.tree.tree_render_controller import (
    OptimizeTreeRenderController,
    OptimizeTreeRenderPort,
)
from chappy.gui.modes.analysis.region_detail.tree.tree_selection_controller import (
    OptimizeTreeSelectionController,
    OptimizeTreeSelectionPort,
)
from chappy.gui.modes.analysis.region_detail.velocity_overlay_adapter import (
    optimize_velocity_overlay_info,
)
from chappy.gui.modes.analysis.region_detail.velocity_plot_controller import (
    OptimizeVelocityComponentContext,
    OptimizeVelocityOverlayContext,
    OptimizeVelocityPlotController,
    OptimizeVelocityPlotPorts,
    OptimizeVelocitySliceContext,
)
from chappy.gui.modes.analysis.region_detail.workflows.export_workflow_controller import (
    OptimizeExportWorkflowController,
    OptimizeExportWorkflowPort,
)
from chappy.gui.modes.analysis.region_detail.workflows.fit_workflow_controller import (
    OptimizeFitEditorPort,
    OptimizeFitWorkflowController,
    OptimizeFitWorkflowPort,
)

__all__ = [
    "OptimizeContextMenuActionProvider",
    "OptimizeContextMenuController",
    "OptimizeContextMenuRequest",
    "OptimizeEditor",
    "OptimizeExportDialogAdapter",
    "OptimizeExportWorkflowController",
    "OptimizeExportWorkflowPort",
    "OptimizeFitEditorPort",
    "OptimizeFitWorkflowController",
    "OptimizeFitWorkflowPort",
    "OptimizeHistoryAdapter",
    "OptimizeHistoryRecorder",
    "OptimizeMaskPanel",
    "OptimizeMaskPanelAdapter",
    "OptimizeModeRuntime",
    "OptimizeModeRuntimePorts",
    "OptimizeModelAdditionController",
    "OptimizeModelAdditionPort",
    "OptimizeModelMutationAdapter",
    "OptimizeParameterDialogContext",
    "OptimizeParameterEditController",
    "OptimizeParameterEditPort",
    "OptimizeSettingsAdapter",
    "OptimizeSpectrumIntegration",
    "OptimizeSpectrumInteractionCoordinatorPort",
    "OptimizeSpectrumPanelPort",
    "OptimizeTreeRenderController",
    "OptimizeTreeRenderPort",
    "OptimizeTreeSelectionController",
    "OptimizeTreeSelectionPort",
    "OptimizeVelocityComponentContext",
    "OptimizeVelocityOverlayContext",
    "OptimizeVelocityOverlayRuntimePort",
    "OptimizeVelocityPlotController",
    "OptimizeVelocityPlotPorts",
    "OptimizeVelocitySliceContext",
    "RegionDetailPanel",
    "build_region_detail",
    "optimize_velocity_overlay_info",
]
