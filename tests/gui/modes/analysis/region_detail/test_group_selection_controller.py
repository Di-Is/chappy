"""Tests for optimize group selection controller."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING

from chappy.application.optimize import OptimizeGroupAnalysisUseCase
from chappy.core.absorption.models import AbsorptionLine, AbsorptionRegion
from chappy.core.analysis import FitSummary
from chappy.core.components.absorber import AbsorberComponent
from chappy.core.spectroscopy_project import SpectroscopyProject
from chappy.gui.modes.analysis.region_detail.group_selection_controller import (
    OptimizeGroupChoice,
    OptimizeGroupSelectionController,
)
from chappy.presentation.interaction.interaction_contracts import OptimizeMaskGroupChange

if TYPE_CHECKING:
    from collections.abc import Iterator


class _SelectorPort:
    """Region selector widget test double."""

    def __init__(self) -> None:
        self.can_select = True
        self.choices: list[tuple[str, str | None]] = []
        self.current_index = -1
        self.enabled: bool | None = None
        self.block_depth = 0

    def can_select_optimize_groups(self) -> bool:
        """Return configured selection availability."""
        return self.can_select

    @contextmanager
    def blocked_group_selector(self) -> Iterator[None]:
        """Record signal-blocking scope."""
        self.block_depth += 1
        yield
        self.block_depth -= 1

    def clear_group_selector(self) -> None:
        """Clear stored choices."""
        self.choices.clear()
        self.current_index = -1

    def add_empty_group_choice(self) -> None:
        """Add empty placeholder, mirroring QComboBox.addItem's implicit index set."""
        self.choices.append(("No regions", None))
        if len(self.choices) == 1:
            self.current_index = 0

    def add_group_choice(self, choice: OptimizeGroupChoice) -> None:
        """Add a group choice, mirroring QComboBox.addItem's implicit index set."""
        self.choices.append((choice.display_name, choice.region_id))
        if len(self.choices) == 1:
            self.current_index = 0

    def set_group_selector_enabled(self, enabled: bool) -> None:
        """Record selector enabled state."""
        self.enabled = enabled

    def group_selector_count(self) -> int:
        """Return choice count."""
        return len(self.choices)

    def current_group_selector_index(self) -> int:
        """Return current index."""
        return self.current_index

    def set_current_group_selector_index(self, index: int) -> None:
        """Set current index."""
        self.current_index = index

    def group_id_at_selector_index(self, index: int) -> str | None:
        """Return choice group id."""
        if index < 0 or index >= len(self.choices):
            return None
        return self.choices[index][1]

    def current_group_id_from_selector(self) -> str | None:
        """Return current choice group id."""
        return self.group_id_at_selector_index(self.current_index)


class _ActionsPort:
    """Export/fit action-area test double."""

    def __init__(self) -> None:
        self.export_state: tuple[bool, bool] | None = None
        self.optimize_updates = 0
        self.summary_clears = 0

    def set_export_controls_state(self, *, export_enabled: bool, needs_visible: bool) -> None:
        """Record export controls state."""
        self.export_state = (export_enabled, needs_visible)

    def update_group_optimize_button_state(self) -> None:
        """Record optimize button refresh."""
        self.optimize_updates += 1

    def clear_group_summary(self) -> None:
        """Record summary clear."""
        self.summary_clears += 1


class _TreeRenderPort:
    """Group-scoped tree render test double."""

    def __init__(self) -> None:
        self.tree_clears = 0
        self.rendered_regions: list[str] = []
        self.style_refreshes = 0

    def clear_group_tree(self) -> None:
        """Record tree clear."""
        self.tree_clears += 1

    def render_group_region_tree(self, region: AbsorptionRegion) -> None:
        """Record rendered region."""
        self.rendered_regions.append(region.region_id)

    def refresh_group_parameter_styles(self) -> None:
        """Record style refresh."""
        self.style_refreshes += 1


class _MaskRefreshPort:
    """Mask panel refresh test double."""

    def __init__(self) -> None:
        self.mask_updates = 0
        self.mask_refreshes = 0
        self.group_changes: list[str | None] = []

    def update_group_mask_panel_state(self) -> None:
        """Record mask panel refresh."""
        self.mask_updates += 1

    def refresh_group_masks(self) -> None:
        """Record mask refresh."""
        self.mask_refreshes += 1

    def emit_group_mask_changed(self, change: OptimizeMaskGroupChange) -> None:
        """Record emitted group changes."""
        self.group_changes.append(change.group_id)


class _AnalysisFocus:
    """Canonical Analysis focus test double."""

    def __init__(self) -> None:
        self.activated_regions: list[str] = []
        self._focused_region_id: str | None = None

    def focus_region(self, region_id: str) -> bool:
        """Record activated region."""
        self.activated_regions.append(region_id)
        self._focused_region_id = region_id
        return True

    def focused_region_id(self) -> str | None:
        """Return the last activated region ID."""
        return self._focused_region_id


@dataclass
class _Ports:
    """Bundle of group selection controller port test doubles."""

    selector: _SelectorPort
    actions: _ActionsPort
    tree_render: _TreeRenderPort
    mask_refresh: _MaskRefreshPort
    analysis_focus: _AnalysisFocus


def _make_ports() -> _Ports:
    """Create a fresh bundle of port test doubles."""
    return _Ports(
        selector=_SelectorPort(),
        actions=_ActionsPort(),
        tree_render=_TreeRenderPort(),
        mask_refresh=_MaskRefreshPort(),
        analysis_focus=_AnalysisFocus(),
    )


def _line(
    line_id: str, *, center_z: float = 1.0, model_ids: list[str] | None = None
) -> AbsorptionLine:
    """Create a minimal absorption line."""
    return AbsorptionLine(
        line_id=line_id,
        species="H I",
        rest_wavelength=1215.67,
        center_z=center_z,
        window_kms=150.0,
        region_id="region-1",
        multiplet_label="Ly alpha",
        transition_name="Ly alpha",
        oscillator_strength=0.1,
        gamma_value=1e8,
        model_ids=model_ids if model_ids is not None else [],
    )


def _project() -> SpectroscopyProject:
    """Create a project with one selectable absorption region."""
    project = SpectroscopyProject()
    line = _line("line-1")
    region = AbsorptionRegion(
        region_id="region-1", line_ids=[line.line_id], analysis_range=(3500.0, 3600.0)
    )
    project.absorption_lines[line.line_id] = line
    project.absorption_regions[region.region_id] = region
    project.mark_region_needs_optimization(region.region_id)
    return project


def _controller(ports: _Ports) -> OptimizeGroupSelectionController:
    """Create a group selection controller with production analysis rules."""
    return OptimizeGroupSelectionController(
        selector=ports.selector,
        actions=ports.actions,
        tree_render=ports.tree_render,
        mask_refresh=ports.mask_refresh,
        analysis_focus=ports.analysis_focus,
        usecase=OptimizeGroupAnalysisUseCase(),
    )


def test_refresh_group_choices_builds_choices_without_auto_selecting() -> None:
    """Populating the selector must display but never silently activate a region.

    A previous auto-select branch attempted this here, guarded by
    `current_group_selector_index() < 0`. Against real Qt that guard is
    always false (`QComboBox.addItem` sets currentIndex to 0 immediately on
    the first insert), so the branch never fired and was removed. Canonical
    focus write-back happens only through explicit post-context-switch
    reconciliation (`reconcile_focus_with_selector`).
    """
    ports = _make_ports()
    controller = _controller(ports)
    project = _project()

    controller.refresh_group_choices(project)

    assert ports.selector.enabled is True
    assert ports.selector.current_index == 0
    assert ports.selector.choices[0][1] == "region-1"
    assert ports.tree_render.rendered_regions == []
    assert ports.analysis_focus.activated_regions == []
    assert ports.mask_refresh.mask_refreshes == 0
    assert ports.mask_refresh.group_changes == []
    assert ports.actions.export_state == (False, True)


def test_reconcile_focus_with_selector_promotes_display_when_canonical_unset() -> None:
    """With no canonical focus, adopt whatever region the selector displays."""
    ports = _make_ports()
    controller = _controller(ports)
    project = _project()
    controller.refresh_group_choices(project)
    assert ports.analysis_focus.focused_region_id() is None

    controller.reconcile_focus_with_selector(project)

    assert ports.analysis_focus.focused_region_id() == "region-1"
    assert ports.analysis_focus.activated_regions == ["region-1"]


def test_reconcile_focus_with_selector_projects_canonical_into_selector() -> None:
    """A persisted canonical focus must win over whatever the selector defaulted to."""
    ports = _make_ports()
    controller = _controller(ports)
    project = _project()
    second_line = _line("line-2")
    second_line.region_id = "region-2"
    second_region = AbsorptionRegion(region_id="region-2", line_ids=[second_line.line_id])
    project.absorption_lines[second_line.line_id] = second_line
    project.absorption_regions[second_region.region_id] = second_region
    ports.selector.choices = [("Region 1", "region-1"), ("Region 2", "region-2")]
    ports.selector.current_index = 0
    ports.analysis_focus.focus_region("region-2")
    ports.analysis_focus.activated_regions.clear()

    controller.reconcile_focus_with_selector(project)

    assert ports.selector.current_index == 1
    assert ports.tree_render.rendered_regions == ["region-2"]
    assert ports.analysis_focus.activated_regions == []


def test_reconcile_focus_with_selector_is_a_no_op_without_project() -> None:
    """Reconciliation must not touch canonical focus when no project is active."""
    ports = _make_ports()
    controller = _controller(ports)

    controller.reconcile_focus_with_selector(None)

    assert ports.analysis_focus.activated_regions == []


def test_reconcile_focus_with_selector_is_a_no_op_when_selector_is_empty() -> None:
    """Reconciliation must not fabricate a focus when the selector has nothing to show."""
    ports = _make_ports()
    controller = _controller(ports)
    project = _project()
    del project.absorption_regions["region-1"]
    controller.refresh_group_choices(project)

    controller.reconcile_focus_with_selector(project)

    assert ports.analysis_focus.activated_regions == []
    assert ports.analysis_focus.focused_region_id() is None


def test_projected_group_focus_does_not_write_back_to_analysis_navigation() -> None:
    """Legacy active-group projection should render without reactivating the region."""
    ports = _make_ports()
    controller = _controller(ports)
    project = _project()
    second_line = _line("line-2")
    second_line.region_id = "region-2"
    second_region = AbsorptionRegion(region_id="region-2", line_ids=[second_line.line_id])
    project.absorption_lines[second_line.line_id] = second_line
    project.absorption_regions[second_region.region_id] = second_region
    ports.selector.choices = [("Region 1", "region-1"), ("Region 2", "region-2")]
    ports.selector.current_index = 0

    controller.select_group_id(project, "region-2")

    assert ports.selector.current_index == 1
    assert ports.tree_render.rendered_regions == ["region-2"]
    assert ports.analysis_focus.activated_regions == []


def test_render_region_rebuilds_even_when_selector_index_is_unchanged() -> None:
    """Re-entering an unchanged region must still rebuild its tree from project state.

    This is the deleted-line scenario: `select_group_id` early-returns when the
    selector index has not moved, which is exactly what happens when Structure
    deletes a line and Detail is re-opened for the same region. `render_region`
    must rebuild unconditionally so the stale tree does not survive re-entry.
    """
    ports = _make_ports()
    controller = _controller(ports)
    project = _project()
    ports.selector.choices = [("Region 1", "region-1")]
    ports.selector.current_index = 0

    controller.render_region(project, "region-1")

    assert ports.selector.current_index == 0
    assert ports.tree_render.rendered_regions == ["region-1"]
    assert ports.analysis_focus.activated_regions == []


def test_render_region_with_no_project_is_a_no_op() -> None:
    """Rendering without a project must not touch the selector or tree."""
    ports = _make_ports()
    controller = _controller(ports)

    controller.render_region(None, "region-1")

    assert ports.tree_render.rendered_regions == []
    assert ports.selector.block_depth == 0


def test_record_successful_fit_enables_export_when_region_is_current() -> None:
    """Ready analysis should clear needs state and enable export for the current group."""
    ports = _make_ports()
    controller = _controller(ports)
    project = _project()
    controller.refresh_group_choices(project)
    summary = FitSummary(chi_squared=1.0)

    controller.record_successful_fit(project, "region-1", summary)

    assert project.is_region_needs_optimization("region-1") is False
    assert ports.actions.export_state == (True, False)
    assert ports.tree_render.style_refreshes >= 1
    assert controller.fit_summary(project, "region-1") == summary


def test_mark_region_needs_optimization_makes_evidence_stale() -> None:
    """Marking a region dirty should disable export and retain stored evidence."""
    ports = _make_ports()
    controller = _controller(ports)
    project = _project()
    controller.refresh_group_choices(project)
    summary = FitSummary(chi_squared=1.0)
    controller.record_successful_fit(project, "region-1", summary)

    controller.mark_region_needs_optimization(project, "region-1")

    assert project.is_region_needs_optimization("region-1") is True
    assert ports.actions.export_state == (False, True)
    assert controller.fit_summary(project, "region-1") == summary


def test_region_id_for_component_uses_component_group_before_line_lookup() -> None:
    """Component group id should be preferred when it points to an existing region."""
    ports = _make_ports()
    controller = _controller(ports)
    project = _project()
    component = AbsorberComponent(
        component_id="component-1",
        wavelength=1215.67,
        redshift=1.0,
        column_density=13.5,
        b_parameter=20.0,
        group_id="region-1",
    )

    assert controller.region_id_for_component(project, component) == "region-1"


def test_region_id_for_component_falls_back_to_line_lookup() -> None:
    """Line association should provide a region when component group id is unavailable."""
    ports = _make_ports()
    controller = _controller(ports)
    project = _project()
    component = AbsorberComponent(
        component_id="component-1",
        wavelength=1215.67,
        redshift=1.0,
        column_density=13.5,
        b_parameter=20.0,
    )
    project.absorption_lines["line-1"].model_ids.append(component.id)

    assert controller.region_id_for_component(project, component) == "region-1"
