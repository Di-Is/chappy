"""Port adapters backed by named mask-workflow collaborators."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from chappy.presentation.interaction.interaction_contracts import OptimizeMaskFocusChange

if TYPE_CHECKING:
    from collections.abc import Callable

    from PySide6.QtGui import QShortcut

    from chappy.core.masking import MaskDefinition
    from chappy.core.spectroscopy_project import SpectroscopyProject
    from chappy.gui.modes.analysis.region_detail.adapters.confirm_dialog_adapter import (
        OptimizeConfirmDialogAdapter,
    )
    from chappy.gui.modes.analysis.region_detail.group_selection_controller import (
        OptimizeGroupSelectionController,
    )
    from chappy.gui.modes.analysis.region_detail.mask.mask_panel import OptimizeMaskPanel
    from chappy.gui.modes.analysis.region_detail.mask.mask_panel_adapter import (
        OptimizeMaskPanelAdapter,
    )
    from chappy.gui.modes.analysis.region_detail.mask.mask_workflow_controller import (
        OptimizeMaskWorkflowController,
    )
    from chappy.gui.modes.analysis.region_detail.tree.tree_view import RegionDetailTreeView
    from chappy.presentation.interaction.interaction_contracts import (
        MaskSelectionRequest,
        OptimizeMaskGroupChange,
    )


@dataclass(frozen=True, slots=True)
class OptimizeRegionMaskRefreshPortAdapter:
    """Adapt named collaborators for mask panel refresh after group changes."""

    project_provider: Callable[[], SpectroscopyProject | None]
    group_selection_controller_provider: Callable[[], OptimizeGroupSelectionController]
    mask_workflow_controller: OptimizeMaskWorkflowController
    emit_mask_group_changed: Callable[[OptimizeMaskGroupChange], None]

    def update_group_mask_panel_state(self) -> None:
        """Refresh mask panel state after group changes."""
        has_regions = self.group_selection_controller_provider().has_regions_with_lines(
            self.project_provider()
        )
        self.mask_workflow_controller.update_panel_state(has_regions=has_regions)

    def refresh_group_masks(self) -> None:
        """Refresh rendered masks for the selected group."""
        self.mask_workflow_controller.on_masks_changed()

    def emit_group_mask_changed(self, change: OptimizeMaskGroupChange) -> None:
        """Emit a group change signal for mask-aware collaborators."""
        self.emit_mask_group_changed(change)


class OptimizeMaskWorkflowPortAdapter:
    """Adapt named collaborators for mask workflows.

    Holds mask interaction lifecycle state (active flag, active mask id) that
    used to live on the panel, since nothing outside the mask workflow reads
    it.
    """

    def __init__(  # noqa: PLR0913 - collaborators are injected explicitly, one per responsibility
        self,
        *,
        group_selection_controller_provider: Callable[[], OptimizeGroupSelectionController],
        mask_panel_adapter: OptimizeMaskPanelAdapter,
        mask_panel: OptimizeMaskPanel,
        tree_view: RegionDetailTreeView,
        confirm_dialog_adapter: OptimizeConfirmDialogAdapter,
        project_provider: Callable[[], SpectroscopyProject | None],
        velocity_plot_active_provider: Callable[[], bool],
        mask_cancel_shortcut: QShortcut | None,
        emit_mask_selection_request: Callable[[MaskSelectionRequest], None],
        emit_mask_focus_changed: Callable[[OptimizeMaskFocusChange], None],
        emit_mask_cancel_requested: Callable[[], None],
        focused_region_id_provider: Callable[[], str | None],
    ) -> None:
        """Initialize the adapter.

        Args:
            group_selection_controller_provider: Return the group selection controller.
            mask_panel_adapter: Mask editor view boundary.
            mask_panel: Mask editor panel widget.
            tree_view: Parameter tree view.
            confirm_dialog_adapter: Mask-related message dialogs.
            project_provider: Return the active project.
            velocity_plot_active_provider: Return whether the velocity plot is visible.
            mask_cancel_shortcut: Escape shortcut toggled while mask interaction is active.
            emit_mask_selection_request: Emit a mask selection request.
            emit_mask_focus_changed: Emit a mask focus change.
            emit_mask_cancel_requested: Emit a mask cancel request.
            focused_region_id_provider: Return the canonical Analysis focus region ID.
        """
        self._group_selection_controller_provider = group_selection_controller_provider
        self._mask_panel_adapter = mask_panel_adapter
        self._mask_panel = mask_panel
        self._tree_view = tree_view
        self._confirm_dialog_adapter = confirm_dialog_adapter
        self._project_provider = project_provider
        self._velocity_plot_active_provider = velocity_plot_active_provider
        self._mask_cancel_shortcut = mask_cancel_shortcut
        self._emit_mask_selection_request = emit_mask_selection_request
        self._emit_mask_focus_changed = emit_mask_focus_changed
        self._emit_mask_cancel_requested = emit_mask_cancel_requested
        self._focused_region_id_provider = focused_region_id_provider
        self._active_mask_id: str | None = None
        self._mask_interaction_active = False

    def current_mask_group_id(self) -> str | None:
        """Return the canonical Analysis focus region ID that owns the mask panel."""
        return self._focused_region_id_provider()

    def show_mask_group_masks(
        self, masks: list[MaskDefinition], active_mask_id: str | None
    ) -> None:
        """Render mask definitions for the selected group."""
        self._mask_panel_adapter.show_current_region_masks(masks, active_mask_id)

    def set_mask_panel_available(self, available: bool) -> None:
        """Set whether mask editing controls are available."""
        self._mask_panel_adapter.set_available(available)

    def expand_mask_panel(self) -> None:
        """Expand the mask editor panel."""
        self._mask_panel.expand()

    def set_mask_interaction_active(self, active: bool) -> None:
        """Reflect whether mask selection interaction is active."""
        if self._mask_interaction_active == active:
            return
        self._mask_interaction_active = active
        self._mask_panel.set_add_button_active(active)
        if not active:
            self._mask_panel.clear_add_button_focus()
        if self._mask_cancel_shortcut is not None:
            self._mask_cancel_shortcut.setEnabled(active)

    def is_mask_interaction_active(self) -> bool:
        """Return whether mask selection interaction is active."""
        return self._mask_interaction_active

    def is_velocity_plot_active(self) -> bool:
        """Return whether velocity plot mode is currently active."""
        return self._velocity_plot_active_provider()

    def show_mask_velocity_disabled_message(self) -> None:
        """Notify the user that mask editing is unavailable in velocity mode."""
        self._confirm_dialog_adapter.show_mask_velocity_disabled_message()

    def show_mask_group_missing_message(self) -> None:
        """Notify the user that no maskable group is selected."""
        self._confirm_dialog_adapter.show_mask_group_missing_message()

    def emit_mask_selection_request(self, request: MaskSelectionRequest) -> None:
        """Emit a mask selection request."""
        self._emit_mask_selection_request(request)

    def emit_mask_focus_changed(self, mask_id: str | None) -> None:
        """Emit a mask focus change."""
        self._emit_mask_focus_changed(OptimizeMaskFocusChange(mask_id=mask_id))

    def emit_mask_cancel_requested(self) -> None:
        """Emit a mask cancel request."""
        self._emit_mask_cancel_requested()

    def refresh_mask_analysis_state(self) -> None:
        """Refresh export and parameter styles after committed mask science."""
        self._group_selection_controller_provider().update_export_controls(
            self._project_provider()
        )
        self._tree_view.refresh_parameter_styles()

    def sync_active_mask_id(self, mask_id: str | None) -> None:
        """Synchronize the active mask identifier for legacy view state."""
        self._active_mask_id = mask_id
