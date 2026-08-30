"""Panel-level coverage for canonical Analysis focus / selector reconciliation.

Unit 8(a) of the Region Detail decomposition made the region selector a pure
display projection: it never writes back to canonical Analysis focus except
through `RegionDetailPanel.reconcile_focus_with_selector`, called by the shell
once a project context change has fully settled. These tests exercise that
method directly against a real `RegionDetailPanel`, proving the completion
criteria from the target-architecture doc: project open without persisted
focus, project open with persisted focus (restored focus wins), project
switch, and focused-region deletion.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from PySide6.QtWidgets import QTreeWidget

from chappy.core.absorption.models import AbsorptionLine, AbsorptionRegion
from chappy.core.change_set import ChangeSet
from chappy.core.events import RegionTopologyChanged
from chappy.core.spectroscopy_project import SpectroscopyProject
from chappy.gui.modes.analysis.region_detail.editor import OptimizeEditor
from chappy.gui.modes.analysis.region_detail.panel import RegionDetailPanel
from tests.gui.widgets.optimize_panel_helpers import (
    AnalysisFocusRecorder,
    NoOpModelAdditionUseCase,
    build_region_detail_usecases,
)

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot

    from chappy.gui.modes.common.analysis_navigation import AnalysisRegionFocusPort


@pytest.fixture
def analysis_focus() -> AnalysisFocusRecorder:
    """Create a fresh canonical Analysis focus recorder."""
    return AnalysisFocusRecorder()


@pytest.fixture
def panel(qtbot: QtBot, analysis_focus: AnalysisRegionFocusPort) -> RegionDetailPanel:
    """Create a Region Detail panel wired to a real, inspectable focus recorder."""
    editor = OptimizeEditor()
    parameter_mutation_usecase, tie_set_edit_usecase = build_region_detail_usecases()
    widget = RegionDetailPanel(
        optimize_editor=editor,
        analysis_focus=analysis_focus,
        mode_state=object(),
        model_addition_usecase=NoOpModelAdditionUseCase(),
        parameter_mutation_usecase=parameter_mutation_usecase,
        tie_set_edit_usecase=tie_set_edit_usecase,
        velocity_plot_active_provider=lambda: False,
        project_file_path_provider=lambda: None,
    )
    qtbot.addWidget(editor)
    qtbot.addWidget(widget)
    return widget


def _region(region_id: str, line_id: str) -> tuple[AbsorptionRegion, AbsorptionLine]:
    line = AbsorptionLine(
        line_id=line_id,
        species="H I",
        rest_wavelength=1215.67,
        center_z=1.0,
        window_kms=150.0,
        region_id=region_id,
        multiplet_label="Ly alpha",
        transition_name="Ly alpha",
        oscillator_strength=0.1,
        gamma_value=1e8,
    )
    region = AbsorptionRegion(
        region_id=region_id, line_ids=[line_id], analysis_range=(3500.0, 3600.0)
    )
    return region, line


def _one_region_project(
    region_id: str = "region-1", line_id: str = "line-1"
) -> SpectroscopyProject:
    project = SpectroscopyProject()
    region, line = _region(region_id, line_id)
    project.absorption_lines[line_id] = line
    project.absorption_regions[region_id] = region
    return project


def _two_region_project() -> SpectroscopyProject:
    project = _one_region_project("region-1", "line-1")
    region, line = _region("region-2", "line-2")
    project.absorption_lines["line-2"] = line
    project.absorption_regions["region-2"] = region
    return project


def test_project_open_without_persisted_focus_promotes_selector_default(
    panel: RegionDetailPanel, analysis_focus: AnalysisFocusRecorder
) -> None:
    """Opening a project with no restored focus adopts the selector's default region."""
    project = _one_region_project()

    panel.set_project(project)
    assert analysis_focus.focused_region_id() is None

    panel.reconcile_focus_with_selector()

    assert analysis_focus.focused_region_id() == "region-1"


def test_project_open_with_persisted_focus_keeps_restored_focus(
    panel: RegionDetailPanel, analysis_focus: AnalysisFocusRecorder
) -> None:
    """A persisted focus restored before reconciliation must win over the selector default."""
    project = _two_region_project()
    analysis_focus.focus_region("region-2")
    analysis_focus.region_ids.clear()

    panel.set_project(project)
    panel.reconcile_focus_with_selector()

    assert analysis_focus.focused_region_id() == "region-2"
    assert analysis_focus.region_ids == []
    assert panel.current_region_id() == "region-2"


def test_project_switch_promotes_new_projects_own_region(
    panel: RegionDetailPanel, analysis_focus: AnalysisFocusRecorder
) -> None:
    """Switching projects while no focus is restored must adopt the new project's default.

    Canonical focus staleness across project switches is the navigation
    coordinator's responsibility (`AnalysisNavigationCoordinator.
    handle_project_context_changed`); this test only proves the panel-level
    half of reconciliation once that coordinator has already cleared or
    restored canonical focus for the new project.
    """
    first_project = _one_region_project("region-1", "line-1")
    panel.set_project(first_project)
    panel.reconcile_focus_with_selector()
    assert analysis_focus.focused_region_id() == "region-1"

    second_project = _one_region_project("region-9", "line-9")
    analysis_focus.clear_focus_if("region-1")  # simulate coordinator clearing stale focus
    panel.set_project(second_project)
    panel.reconcile_focus_with_selector()

    assert analysis_focus.focused_region_id() == "region-9"


def test_focused_region_deletion_leaves_focus_recovery_to_shell(
    panel: RegionDetailPanel, analysis_focus: AnalysisFocusRecorder
) -> None:
    """Detail refreshes its selector without owning canonical focus recovery."""
    project = _two_region_project()
    panel.set_project(project)
    panel.reconcile_focus_with_selector()
    assert analysis_focus.focused_region_id() == "region-1"

    del project.absorption_regions["region-1"]
    del project.absorption_lines["line-1"]
    project.model.publish_storage_changes(
        ChangeSet.of(RegionTopologyChanged(removed_region_ids=("region-1",)))
    )

    assert analysis_focus.focused_region_id() == "region-1"
    assert panel._group_selection_controller.current_group_id() == "region-2"  # noqa: SLF001
    assert analysis_focus.clear_focus_only_if_calls == []
    assert analysis_focus.clear_focus_if_calls == []


def test_non_focused_region_deletion_leaves_canonical_focus_untouched(
    panel: RegionDetailPanel, analysis_focus: AnalysisFocusRecorder
) -> None:
    """Deleting a region other than the focused one must not disturb canonical focus."""
    project = _two_region_project()
    panel.set_project(project)
    panel.reconcile_focus_with_selector()
    assert analysis_focus.focused_region_id() == "region-1"

    del project.absorption_regions["region-2"]
    del project.absorption_lines["line-2"]
    project.model.publish_storage_changes(
        ChangeSet.of(RegionTopologyChanged(removed_region_ids=("region-2",)))
    )

    assert analysis_focus.focused_region_id() == "region-1"
    assert analysis_focus.clear_focus_only_if_calls == []
    assert analysis_focus.clear_focus_if_calls == []


def _index_for_region(panel: RegionDetailPanel, region_id: str) -> int:
    header_view = panel._header_view  # noqa: SLF001
    for index in range(header_view.group_selector_count()):
        if header_view.group_id_at_selector_index(index) == region_id:
            return index
    msg = f"{region_id} is not a selector choice"
    raise AssertionError(msg)


def test_language_change_reprojects_selector_and_tree_onto_focused_region(
    panel: RegionDetailPanel, analysis_focus: AnalysisFocusRecorder
) -> None:
    """A language switch must not desync the selector/tree from canonical focus (P2).

    Rebuilding the group selector's choices on a language change used to
    leave Qt showing index 0 (the first region) while canonical focus stayed
    on whatever region was actually focused, and the tree was simply cleared.
    """
    project = _two_region_project()
    panel.set_project(project)
    panel.reconcile_focus_with_selector()
    assert analysis_focus.focused_region_id() == "region-1"

    # Focus a region other than the selector's default (first) choice, exactly
    # as a real user selection would.
    panel._on_group_combo_changed(_index_for_region(panel, "region-2"))  # noqa: SLF001
    assert analysis_focus.focused_region_id() == "region-2"

    panel._on_language_changed("en")  # noqa: SLF001

    assert analysis_focus.focused_region_id() == "region-2"
    assert panel._group_selection_controller.current_group_id() == "region-2"  # noqa: SLF001
    tree = panel.findChild(QTreeWidget, "analysisDetailParameterTree")
    assert tree is not None
    assert tree.topLevelItemCount() > 0


def test_language_change_with_no_canonical_focus_falls_back_to_reconciliation(
    panel: RegionDetailPanel, analysis_focus: AnalysisFocusRecorder
) -> None:
    """With no canonical focus yet, a language switch must still restore the invariant.

    The panel cannot render a tree for a region that hasn't been resolved yet,
    so it falls back to clearing the tree and promoting the selector's default
    to canonical focus via `reconcile_focus_with_selector`, exactly as before
    this fix.
    """
    project = _two_region_project()
    panel.set_project(project)
    assert analysis_focus.focused_region_id() is None

    panel._on_language_changed("en")  # noqa: SLF001

    assert analysis_focus.focused_region_id() == "region-1"
