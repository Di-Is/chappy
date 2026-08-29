"""Port adapters backed by named fit and export workflow collaborators."""

from __future__ import annotations

import typing
from dataclasses import dataclass
from typing import TYPE_CHECKING

from chappy.gui.modes.analysis.region_detail.workflows.fit_workflow_controller import (
    FitWorkflowStatusKind,
)
from chappy.presentation.optimize import (
    FitChi2View,
    FitCompleteView,
    FitCustomView,
    FitFailedView,
    FitReadyView,
    FitRunningView,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from chappy.core.analysis import AnalysisReadiness, FitSummary
    from chappy.core.cosmology import CosmologyParameters
    from chappy.core.spectroscopy_project import SpectroscopyProject
    from chappy.gui.modes.analysis.region_detail.adapters.settings_adapter import (
        OptimizeSettingsAdapter,
    )
    from chappy.gui.modes.analysis.region_detail.group_selection_controller import (
        OptimizeGroupSelectionController,
    )
    from chappy.gui.modes.analysis.region_detail.state import RegionDetailViewState
    from chappy.gui.modes.analysis.region_detail.tree.tree_view import RegionDetailTreeView
    from chappy.gui.modes.analysis.region_detail.workflows.fit_workflow_controller import (
        FitWorkflowStatus,
    )
    from chappy.presentation.optimize import FitStatusView


def _fit_status_view(status: FitWorkflowStatus) -> FitStatusView:
    """Convert an application fit workflow status to a presentation view."""
    if status.kind is FitWorkflowStatusKind.READY:
        return FitReadyView()
    if status.kind is FitWorkflowStatusKind.RUNNING:
        return FitRunningView()
    if status.kind is FitWorkflowStatusKind.CHI2:
        if status.value is None:
            msg = "CHI2 fit workflow status is missing a chi-squared value."
            raise ValueError(msg)
        return FitChi2View(chi2=status.value, reduced=status.reduced_value)
    if status.kind is FitWorkflowStatusKind.COMPLETE:
        return FitCompleteView()
    if status.kind is FitWorkflowStatusKind.FAILED:
        return FitFailedView()
    if status.kind is FitWorkflowStatusKind.CUSTOM:
        if status.message is None:
            msg = "CUSTOM fit workflow status is missing a message."
            raise ValueError(msg)
        return FitCustomView(message=status.message)
    typing.assert_never(status.kind)


@dataclass(frozen=True, slots=True)
class OptimizeFitWorkflowPortAdapter:
    """Adapt named collaborators for the fit workflow."""

    project_provider: Callable[[], SpectroscopyProject | None]
    group_selection_controller: OptimizeGroupSelectionController
    view_state: RegionDetailViewState
    tree_view: RegionDetailTreeView
    should_enable_fit: Callable[[], bool]
    update_button_state: Callable[[], None]
    refresh_fit_model_rows_display: Callable[[], None]
    focused_region_id_provider: Callable[[], str | None]

    def should_enable_fit_workflow(self) -> bool:
        """Return whether fit execution is currently allowed."""
        return self.should_enable_fit()

    def update_fit_button_workflow_state(self) -> None:
        """Refresh optimize button state for fit execution."""
        self.update_button_state()

    def current_fit_region_id(self) -> str | None:
        """Return the canonical Analysis focus region ID to fit."""
        return self.focused_region_id_provider()

    def apply_fit_workflow_status(self, status: FitWorkflowStatus) -> None:
        """Apply a fit workflow status to the panel."""
        self.view_state.set_fit_status(_fit_status_view(status))
        self.update_button_state()

    def has_fit_model_rows(self) -> bool:
        """Return whether model rows are visible."""
        return self.tree_view.has_rendered_rows()

    def refresh_fit_model_rows(self) -> None:
        """Refresh model rows after a fit."""
        self.refresh_fit_model_rows_display()

    def refresh_successful_fit(self, group_id: str) -> None:
        """Refresh analysis views after the editor committed fit evidence."""
        self.group_selection_controller.refresh_group_analysis_views(
            self.project_provider(), group_id
        )


@dataclass(frozen=True, slots=True)
class OptimizeExportWorkflowPortAdapter:
    """Adapt named collaborators for the export workflow."""

    project_provider: Callable[[], SpectroscopyProject | None]
    group_selection_controller: OptimizeGroupSelectionController
    settings_adapter: OptimizeSettingsAdapter
    project_file_path_provider: Callable[[], str | None]
    emit_export_feedback: Callable[[str, int, str], None]
    focused_region_id_provider: Callable[[], str | None]

    def current_export_region_id(self) -> str | None:
        """Return the canonical Analysis focus region ID to export."""
        return self.focused_region_id_provider()

    def export_project(self) -> SpectroscopyProject | None:
        """Return the active project."""
        return self.project_provider()

    def analysis_readiness(self, group_id: str) -> AnalysisReadiness:
        """Re-evaluate readiness from current project-owned state."""
        return self.group_selection_controller.analysis_readiness(
            self.project_provider(), group_id
        )

    def export_fit_summary(self, group_id: str) -> FitSummary | None:
        """Return fit summary for a group."""
        return self.group_selection_controller.fit_summary(self.project_provider(), group_id)

    def load_export_cosmology(self) -> CosmologyParameters:
        """Return cosmology parameters used by export."""
        return self.settings_adapter.load_cosmology_parameters()

    def emit_export_success(self, message: str) -> None:
        """Emit successful export feedback."""
        self.emit_export_feedback(message, 3500, "success")

    def project_file_path(self) -> str | None:
        """Return the file path hint for the active project, if any."""
        return self.project_file_path_provider()
