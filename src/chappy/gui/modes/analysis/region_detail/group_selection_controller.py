"""Group selection and analysis-ready controller for optimize mode."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from chappy.core.absorption.models import UNASSIGNED_REGION_ID, AbsorptionRegion
from chappy.core.absorption_display import format_region_display, sort_lines_for_display
from chappy.gui.utils.region_sorting import sort_regions_for_display
from chappy.presentation.interaction.interaction_contracts import OptimizeMaskGroupChange

if TYPE_CHECKING:
    from contextlib import AbstractContextManager

    from chappy.application.optimize import OptimizeGroupAnalysisUseCase
    from chappy.core.absorption.models import AbsorptionLine
    from chappy.core.analysis import AnalysisReadiness, FitSummary
    from chappy.core.components.absorber import AbsorberComponent
    from chappy.core.spectroscopy_project import SpectroscopyProject
    from chappy.gui.modes.common.analysis_navigation import AnalysisRegionFocusPort


@dataclass(frozen=True, slots=True)
class OptimizeGroupChoice:
    """Display entry for an optimize group selector."""

    region_id: str
    display_name: str


class RegionSelectorViewPort(Protocol):
    """Region selector widget operations required by the group selection controller."""

    def can_select_optimize_groups(self) -> bool:
        """Return whether group selection can interact with a mode state store."""
        ...

    def blocked_group_selector(self) -> AbstractContextManager[None]:
        """Return a context manager that suppresses selector change signals."""
        ...

    def clear_group_selector(self) -> None:
        """Clear all group selector entries."""
        ...

    def add_empty_group_choice(self) -> None:
        """Add the localized empty-group placeholder."""
        ...

    def add_group_choice(self, choice: OptimizeGroupChoice) -> None:
        """Add one selectable group choice."""
        ...

    def set_group_selector_enabled(self, enabled: bool) -> None:
        """Set whether the group selector is enabled."""
        ...

    def group_selector_count(self) -> int:
        """Return the number of selector entries."""
        ...

    def current_group_selector_index(self) -> int:
        """Return the current selector index."""
        ...

    def set_current_group_selector_index(self, index: int) -> None:
        """Set the current selector index."""
        ...

    def group_id_at_selector_index(self, index: int) -> str | None:
        """Return the group id stored at a selector index."""
        ...

    def current_group_id_from_selector(self) -> str | None:
        """Return the currently selected group id from the selector."""
        ...


class RegionActionsViewPort(Protocol):
    """Export/fit action-area operations required by the group selection controller."""

    def set_export_controls_state(self, *, export_enabled: bool, needs_visible: bool) -> None:
        """Apply export button and needs badge state."""
        ...

    def update_group_optimize_button_state(self) -> None:
        """Refresh optimize button state after group list changes."""
        ...

    def clear_group_summary(self) -> None:
        """Clear the group summary label."""
        ...


class RegionTreeRenderPort(Protocol):
    """Tree rendering operations required by the group selection controller."""

    def clear_group_tree(self) -> None:
        """Clear the optimize tree."""
        ...

    def render_group_region_tree(self, region: AbsorptionRegion) -> None:
        """Render the tree for the selected region."""
        ...

    def refresh_group_parameter_styles(self) -> None:
        """Refresh parameter styles tied to optimization state."""
        ...


class RegionMaskRefreshPort(Protocol):
    """Mask panel refresh operations required by the group selection controller."""

    def update_group_mask_panel_state(self) -> None:
        """Refresh mask panel state after group changes."""
        ...

    def refresh_group_masks(self) -> None:
        """Refresh rendered masks for the selected group."""
        ...

    def emit_group_mask_changed(self, change: OptimizeMaskGroupChange) -> None:
        """Emit a group change signal for mask-aware collaborators."""
        ...


class OptimizeGroupSelectionController:
    """Coordinate group selection and analysis-ready state."""

    def __init__(
        self,
        *,
        selector: RegionSelectorViewPort,
        actions: RegionActionsViewPort,
        tree_render: RegionTreeRenderPort,
        mask_refresh: RegionMaskRefreshPort,
        analysis_focus: AnalysisRegionFocusPort,
        usecase: OptimizeGroupAnalysisUseCase,
    ) -> None:
        """Initialize the controller.

        Args:
            selector: Region selector widget operations.
            actions: Export/fit action-area operations.
            tree_render: Tree rendering operations.
            mask_refresh: Mask panel refresh operations.
            analysis_focus: Canonical Analysis focus write boundary.
            usecase: UI-independent group analysis state transitions.
        """
        self._selector = selector
        self._actions = actions
        self._tree_render = tree_render
        self._mask_refresh = mask_refresh
        self._analysis_focus = analysis_focus
        self._usecase = usecase

    def refresh_group_choices(self, project: SpectroscopyProject | None) -> None:
        """Refresh group selector entries from the project.

        Args:
            project: Active project, or ``None`` when no project is loaded.
        """
        if not self._selector.can_select_optimize_groups() or project is None:
            self._selector.clear_group_selector()
            self._selector.set_group_selector_enabled(False)
            self._actions.update_group_optimize_button_state()
            self.update_export_controls(project)
            self._mask_refresh.update_group_mask_panel_state()
            return

        with self._selector.blocked_group_selector():
            self._selector.clear_group_selector()

            choices = self._build_group_choices(project)
            if not choices:
                self._selector.add_empty_group_choice()
                self._selector.set_group_selector_enabled(False)
                self._actions.update_group_optimize_button_state()
                self._mask_refresh.update_group_mask_panel_state()
                return

            for choice in choices:
                self._selector.add_group_choice(choice)

            self._selector.set_group_selector_enabled(self._selector.group_selector_count() > 0)
            self.update_export_controls(project)

        self._mask_refresh.update_group_mask_panel_state()

    def reconcile_focus_with_selector(self, project: SpectroscopyProject | None) -> None:
        """Make canonical Analysis focus and the selector's display agree.

        Call once a project context change has fully settled (canonical
        focus already restored/validated) or after a group removal has
        repopulated the selector. When canonical focus already names a
        region, it wins and is projected into the selector. Otherwise the
        selector's currently displayed region, if any, is promoted to
        canonical focus.
        """
        if project is None:
            return
        canonical_region_id = self._analysis_focus.focused_region_id()
        if canonical_region_id is not None:
            self.select_group_id(project, canonical_region_id)
            return
        displayed_region_id = self.current_group_id()
        if displayed_region_id is not None:
            self._analysis_focus.focus_region(displayed_region_id)

    def current_group_id(self) -> str | None:
        """Return the current selected group identifier."""
        return self._selector.current_group_id_from_selector()

    def select_group_id(self, project: SpectroscopyProject | None, group_id: str | None) -> None:
        """Project canonical Analysis focus into the selector without writing it back."""
        if project is None or group_id is None:
            return
        for index in range(self._selector.group_selector_count()):
            if self._selector.group_id_at_selector_index(index) != group_id:
                continue
            if self._selector.current_group_selector_index() == index:
                return
            with self._selector.blocked_group_selector():
                self._selector.set_current_group_selector_index(index)
            self._apply_group_choice(project, index, activate_region=False)
            return

    def render_region(self, project: SpectroscopyProject | None, region_id: str) -> None:
        """Sync the selector to a region and unconditionally rebuild its tree.

        Unlike `select_group_id`, this always re-renders even when the selector
        index is already at `region_id`, so callers can force a rebuild from
        current project state on every Region Detail surface entry.
        """
        if project is None:
            return
        for index in range(self._selector.group_selector_count()):
            if self._selector.group_id_at_selector_index(index) != region_id:
                continue
            with self._selector.blocked_group_selector():
                self._selector.set_current_group_selector_index(index)
            self._apply_group_choice(project, index, activate_region=False)
            return

    def update_export_controls(self, project: SpectroscopyProject | None) -> None:
        """Update export controls from current selection and analysis state.

        Args:
            project: Active project, or ``None``.
        """
        group_id = self.current_group_id()
        if not group_id or project is None:
            self._actions.set_export_controls_state(export_enabled=False, needs_visible=False)
            return

        state = self._usecase.export_controls_state(project, group_id)
        self._actions.set_export_controls_state(
            export_enabled=state.export_enabled, needs_visible=state.needs_visible
        )

    def region_needs_optimization(
        self, project: SpectroscopyProject | None, region: AbsorptionRegion
    ) -> bool:
        """Return whether a region needs optimization.

        Args:
            project: Active project.
            region: Region to inspect.

        Returns:
            Whether optimization is needed.
        """
        if project is None:
            return True
        return self._usecase.region_needs_optimization(project, region.region_id)

    def record_successful_fit(
        self, project: SpectroscopyProject | None, group_id: str, summary: FitSummary
    ) -> None:
        """Record successful fit evidence for a group.

        Args:
            project: Active project.
            group_id: Group identifier.
            summary: Fit evidence produced by the successful analysis.
        """
        self._usecase.record_successful_analysis(project, group_id, summary)

        if group_id == self.current_group_id():
            self.update_export_controls(project)
            self._tree_render.refresh_group_parameter_styles()

    def mark_region_needs_optimization(
        self, project: SpectroscopyProject | None, region_id: str | None
    ) -> None:
        """Mark a region as needing optimization and update dependent state.

        Args:
            project: Active project.
            region_id: Region identifier.
        """
        if not self._usecase.mark_region_needs_optimization(project, region_id):
            return
        self.update_export_controls(project)
        self._tree_render.refresh_group_parameter_styles()

    def refresh_group_analysis_views(
        self, project: SpectroscopyProject | None, group_id: str
    ) -> None:
        """Refresh UI derived from an already committed region invalidation."""
        if project is None or group_id not in project.absorption_regions:
            return
        self.update_export_controls(project)
        self._tree_render.refresh_group_parameter_styles()

    def region_id_for_component(
        self, project: SpectroscopyProject | None, component: AbsorberComponent | None
    ) -> str | None:
        """Return the absorption region identifier tied to a component.

        Args:
            project: Active project.
            component: Component to inspect.

        Returns:
            Region identifier if available.
        """
        if project is None or component is None:
            return None

        group_id = component.group_id
        if isinstance(group_id, str) and group_id in project.absorption_regions:
            return group_id

        line = self._usecase.line_for_component(project, component.id)
        if (
            line is not None
            and isinstance(line.region_id, str)
            and line.region_id in project.absorption_regions
        ):
            return line.region_id
        return None

    def group_combo_changed(self, project: SpectroscopyProject | None, index: int) -> None:
        """Handle selected group changes.

        Args:
            project: Active project.
            index: Selected combo-box index.
        """
        self._apply_group_choice(project, index, activate_region=True)

    def _apply_group_choice(
        self, project: SpectroscopyProject | None, index: int, *, activate_region: bool
    ) -> None:
        """Render a selector choice and optionally publish user-originated focus."""
        if not self._selector.can_select_optimize_groups() or project is None:
            return

        group_id = self._selector.group_id_at_selector_index(index)
        if not group_id:
            self._tree_render.clear_group_tree()
            self._mask_refresh.emit_group_mask_changed(OptimizeMaskGroupChange(group_id=None))
            return

        region = project.absorption_regions.get(group_id)
        if region is None:
            self._tree_render.clear_group_tree()
            return

        self._actions.clear_group_summary()
        self._tree_render.render_group_region_tree(region)
        if activate_region:
            self._analysis_focus.focus_region(region.region_id)
        self._mask_refresh.refresh_group_masks()
        self.update_export_controls(project)
        self._mask_refresh.emit_group_mask_changed(OptimizeMaskGroupChange(group_id=group_id))

    def handle_group_removed(self, project: SpectroscopyProject | None) -> None:
        """Refresh UI after a group removal notification.

        Args:
            project: Active project.
        """
        self.refresh_group_choices(project)
        self._tree_render.clear_group_tree()
        self.update_export_controls(project)

    def fit_summary(self, project: SpectroscopyProject | None, group_id: str) -> FitSummary | None:
        """Return stored fit summary for a group.

        Args:
            project: Active project.
            group_id: Group identifier.

        Returns:
            Stored fit summary, or None when no artifact exists.
        """
        return self._usecase.fit_summary(project, group_id)

    def analysis_readiness(
        self, project: SpectroscopyProject | None, group_id: str
    ) -> AnalysisReadiness:
        """Re-evaluate one region's analysis readiness from current project facts."""
        return self._usecase.analysis_readiness(project, group_id)

    def region_lines(
        self, project: SpectroscopyProject | None, region_id: str | None
    ) -> tuple[AbsorptionLine, ...]:
        """Return the display-ordered absorption lines of one region."""
        return self._usecase.region_lines_for_display(project, region_id)

    def component_count(self, project: SpectroscopyProject | None, region_id: str | None) -> int:
        """Return the number of distinct live components across a region's lines."""
        return self._usecase.component_count_for_region(project, region_id)

    def has_regions_with_lines(self, project: SpectroscopyProject | None) -> bool:
        """Return whether the project has any assigned region containing lines."""
        return self._usecase.has_regions_with_lines(project)

    def line_for_component(
        self, project: SpectroscopyProject | None, component_id: str | None
    ) -> AbsorptionLine | None:
        """Return the first absorption line referencing a component id."""
        return self._usecase.line_for_component(project, component_id)

    def line_for_wavelength(
        self, project: SpectroscopyProject | None, region_id: str | None, wavelength: float
    ) -> AbsorptionLine | None:
        """Return the focused region's line whose accepted range covers `wavelength`."""
        return self._usecase.line_for_wavelength(project, region_id, wavelength)

    def tie_member_ids_for_redshift(
        self, project: SpectroscopyProject | None, component_id: str
    ) -> frozenset[str]:
        """Return the ids of components sharing redshift with the given component."""
        return self._usecase.tie_member_ids_for_redshift(project, component_id)

    def _build_group_choices(
        self, project: SpectroscopyProject
    ) -> tuple[OptimizeGroupChoice, ...]:
        """Build display choices for selectable absorption regions."""
        choices: list[OptimizeGroupChoice] = []
        for region_id, region in sort_regions_for_display(
            list(project.absorption_regions.items())
        ):
            if region_id == UNASSIGNED_REGION_ID:
                continue

            lines = [
                project.absorption_lines[line_id]
                for line_id in region.line_ids
                if line_id in project.absorption_lines
            ]
            sorted_lines = sort_lines_for_display(lines)
            if not sorted_lines:
                continue

            display_info = format_region_display(sorted_lines, region.analysis_range)
            choices.append(
                OptimizeGroupChoice(region_id=region_id, display_name=display_info.display_name)
            )
        return tuple(choices)
