"""RegionDetailUi: the single object shell/spectrum code talks to."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtCore import SignalInstance
    from PySide6.QtWidgets import QWidget

    from chappy.core.absorption.models import AbsorptionLine, AbsorptionRegion
    from chappy.core.components.absorber import AbsorberComponent
    from chappy.core.spectroscopy_project import SpectroscopyProject
    from chappy.gui.modes.analysis.region_detail.adapters.history_adapter import (
        OptimizeHistoryRecorder,
    )
    from chappy.gui.modes.analysis.region_detail.panel import RegionDetailPanel
    from chappy.presentation.interaction.interaction_contracts import (
        InteractionStateSnapshot,
        MaskSelectionContext,
    )
    from chappy.presentation.velocity import (
        VelocityComponentCreateRequest,
        VelocityContextMenuRequest,
    )


class RegionDetailUi:
    """Window shell / spectrum integration face onto the Region Detail panel.

    Wraps the composed panel and exposes the external API shell and
    spectrum-integration code use. Callers must not reach past this facade
    into the panel or its collaborators.
    """

    def __init__(self, panel: RegionDetailPanel) -> None:
        """Store the composed panel this facade delegates to."""
        self._panel = panel

    @property
    def panel(self) -> QWidget:
        """Return the widget hosted by ``AnalysisWorkspacePages(detail=...)``."""
        return self._panel

    def parameter_tree_widget(self) -> QWidget:
        """Return the widget hosted by ``AnalysisWorkspacePages(parameters=...)``."""
        return self._panel.parameter_tree_widget()

    # --- signals -----------------------------------------------------

    @property
    def back_to_overview_requested(self) -> SignalInstance:
        """Signal emitted when the user requests a return to Overview."""
        return self._panel.back_to_overview_requested

    @property
    def export_feedback(self) -> SignalInstance:
        """Signal emitted with export status feedback."""
        return self._panel.export_feedback

    @property
    def operation_feedback(self) -> SignalInstance:
        """Signal emitted with general operation status feedback."""
        return self._panel.operation_feedback

    @property
    def line_analysis_half_width_changed(self) -> SignalInstance:
        """Signal emitted when a region's analysis half-width changes."""
        return self._panel.line_analysis_half_width_changed

    @property
    def line_selected(self) -> SignalInstance:
        """Signal emitted when the selected line changes."""
        return self._panel.line_selected

    @property
    def mask_selection_requested(self) -> SignalInstance:
        """Signal emitted when mask selection interaction is requested."""
        return self._panel.mask_selection_requested

    @property
    def mask_cancel_requested(self) -> SignalInstance:
        """Signal emitted when active mask selection is cancelled."""
        return self._panel.mask_cancel_requested

    @property
    def mask_focus_changed(self) -> SignalInstance:
        """Signal emitted when mask focus changes."""
        return self._panel.mask_focus_changed

    @property
    def mask_group_changed(self) -> SignalInstance:
        """Signal emitted when the active region/group changes."""
        return self._panel.mask_group_changed

    # --- project / lifecycle ------------------------------------------

    def set_project(self, project: SpectroscopyProject | None) -> None:
        """Set the active project."""
        self._panel.set_project(project)

    def refresh(self) -> None:
        """Refresh the panel display without mutating scientific project state."""
        self._panel.refresh()

    def set_history_recorder(self, recorder: OptimizeHistoryRecorder | None) -> None:
        """Set history recorder for undo/redo recording."""
        self._panel.set_history_recorder(recorder)

    def refresh_for_history(self, region_id: str | None = None) -> None:
        """Refresh UI after undo/redo without mutating scientific project state."""
        self._panel.refresh_for_history(region_id)

    def notify_cosmology_changed(self) -> None:
        """Rebuild the current region tree with freshly persisted cosmology parameters."""
        self._panel.notify_cosmology_changed()

    # --- navigation ------------------------------------------------------

    def current_region_id(self) -> str | None:
        """Return the region currently focused in Analysis Detail."""
        return self._panel.current_region_id()

    def select_focused_region(self, region: AbsorptionRegion | None) -> None:
        """Project the Analysis focus into the existing region selector."""
        self._panel.select_focused_region(region)

    def render_focused_region(self, region_id: str) -> None:
        """Rebuild this region's tree from current project state on surface entry."""
        self._panel.render_focused_region(region_id)

    def reconcile_focus_with_selector(self) -> None:
        """Make canonical Analysis focus and the selector's display agree."""
        self._panel.reconcile_focus_with_selector()

    # --- tie labels --------------------------------------------------------

    def tie_label_for_redshift(self, component: AbsorberComponent) -> str | None:
        """Return the tie-set display label for a component's redshift, if tied."""
        return self._panel.tie_label_for_redshift(component)

    def tie_member_ids_for_redshift(self, component_id: str) -> frozenset[str]:
        """Return the ids of components sharing redshift with the given component."""
        return self._panel.tie_member_ids_for_redshift(component_id)

    # --- velocity interactions --------------------------------------------

    def handle_velocity_context_menu(self, request: VelocityContextMenuRequest) -> None:
        """Handle a context menu request from the velocity plot."""
        self._panel.handle_velocity_context_menu(request)

    def handle_velocity_shift_click(self, request: VelocityComponentCreateRequest) -> None:
        """Handle Shift+click from the velocity plot."""
        self._panel.handle_velocity_shift_click(request)

    # --- spectrum integration surface --------------------------------------

    def add_model_at_wavelength(self, wavelength: float) -> None:
        """Add a model at the specified wavelength."""
        self._panel.add_model_at_wavelength(wavelength)

    def cancel_mask_selection(self) -> None:
        """Cancel active mask selection UI."""
        self._panel.cancel_mask_selection()

    def handle_mask_selection_snapshot(
        self, snapshot: InteractionStateSnapshot[MaskSelectionContext]
    ) -> None:
        """Apply a mask selection snapshot emitted by the state controller."""
        self._panel.handle_mask_selection_snapshot(snapshot)

    def find_line_by_wavelength(self, wavelength: float) -> AbsorptionLine | None:
        """Find the owning absorption line for a wavelength."""
        return self._panel.find_line_by_wavelength(wavelength)

    def get_line_wavelength_range(self) -> tuple[float, float] | None:
        """Return the wavelength range of the selected line."""
        return self._panel.get_line_wavelength_range()

    def get_line_for_component(self, component: AbsorberComponent | None) -> AbsorptionLine | None:
        """Return the absorption line associated with a component."""
        return self._panel.get_line_for_component(component)

    def update_model_parameters(self) -> None:
        """Refresh displayed model parameters."""
        self._panel.update_model_parameters()

    def focus_component(self, component_id: str) -> None:
        """Highlight the tree row corresponding to the component identifier."""
        self._panel.focus_component(component_id)


__all__ = ["RegionDetailUi"]
