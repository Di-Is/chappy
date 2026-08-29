"""Tests for the shared operation registry.

These pin the single-source-of-truth invariants described in
docs/adr/doc-translation-qt-unification.md (P4b): unique op ids, a working
lookup, and mode filtering.
"""

from __future__ import annotations

import pytest

from chappy.core.editing_mode import EditingMode
from chappy.gui.common.shared_operations import (
    SHARED_OPERATIONS,
    AnalysisOperationPanel,
    AnalysisOperationSurface,
    OperationScope,
    get_shared_operation,
    shared_operations_for_scope,
)


def test_op_ids_are_unique() -> None:
    """Every registered operation has a distinct op_id."""
    op_ids = [operation.op_id for operation in SHARED_OPERATIONS]

    assert len(op_ids) == len(set(op_ids))


def test_get_shared_operation_returns_registered_instance() -> None:
    """Looking up by op_id returns the exact registered instance."""
    for operation in SHARED_OPERATIONS:
        assert get_shared_operation(operation.op_id) is operation


def test_get_shared_operation_raises_for_unknown_id() -> None:
    """An unknown op_id raises KeyError instead of silently returning None."""
    with pytest.raises(KeyError):
        get_shared_operation("does-not-exist")


@pytest.mark.parametrize(
    ("mode", "surface", "panel"),
    [
        (None, AnalysisOperationSurface.OVERVIEW, None),
        (EditingMode.CONTINUUM, AnalysisOperationSurface.OVERVIEW, None),
        (EditingMode.ANALYSIS, None, AnalysisOperationPanel.STRUCTURE),
        (
            EditingMode.ANALYSIS,
            AnalysisOperationSurface.REGION_DETAIL,
            AnalysisOperationPanel.STRUCTURE,
        ),
        (EditingMode.ANALYSIS, AnalysisOperationSurface.OVERVIEW, AnalysisOperationPanel.DETAIL),
    ],
)
def test_operation_scope_rejects_invalid_destinations(
    mode: EditingMode | None,
    surface: AnalysisOperationSurface | None,
    panel: AnalysisOperationPanel | None,
) -> None:
    """Surface and panel metadata must describe one valid Analysis destination."""
    with pytest.raises(ValueError):
        OperationScope(mode=mode, analysis_surface=surface, analysis_panel=panel)


@pytest.mark.parametrize(
    "scope",
    [
        OperationScope.global_scope(),
        OperationScope(mode=EditingMode.IDENTIFY),
        OperationScope(mode=EditingMode.CONTINUUM),
        OperationScope(
            mode=EditingMode.ANALYSIS,
            analysis_surface=AnalysisOperationSurface.OVERVIEW,
            analysis_panel=AnalysisOperationPanel.SUMMARY,
        ),
        OperationScope(
            mode=EditingMode.ANALYSIS,
            analysis_surface=AnalysisOperationSurface.OVERVIEW,
            analysis_panel=AnalysisOperationPanel.STRUCTURE,
        ),
        OperationScope(
            mode=EditingMode.ANALYSIS,
            analysis_surface=AnalysisOperationSurface.REGION_DETAIL,
            analysis_panel=AnalysisOperationPanel.DETAIL,
        ),
    ],
)
def test_operation_scope_accepts_valid_destinations(scope: OperationScope) -> None:
    """Every supported global, mode, and Analysis destination is constructible."""
    assert isinstance(scope, OperationScope)


def test_shared_operations_for_scope_includes_global_and_exact_mode_scope() -> None:
    """A mode query includes global operations without leaking from other modes."""
    scope = OperationScope(mode=EditingMode.CONTINUUM)
    continuum_ops = shared_operations_for_scope(scope)

    assert continuum_ops
    assert {operation.op_id for operation in continuum_ops} == {
        "zoom_rect",
        "wheel_zoom_pan",
        "continuum_add_point",
        "continuum_move_point",
    }


def test_shared_operations_for_global_scope_selects_only_global_operations() -> None:
    """The global query does not duplicate or include destination-specific operations."""
    common_ops = shared_operations_for_scope(OperationScope.global_scope())

    assert common_ops
    assert all(operation.scope == OperationScope.global_scope() for operation in common_ops)


def test_analysis_scope_query_is_exact_across_surface_and_panel() -> None:
    """Structure and Detail operations cannot leak across Analysis panel boundaries."""
    structure_scope = OperationScope(
        mode=EditingMode.ANALYSIS,
        analysis_surface=AnalysisOperationSurface.OVERVIEW,
        analysis_panel=AnalysisOperationPanel.STRUCTURE,
    )
    detail_scope = OperationScope(
        mode=EditingMode.ANALYSIS,
        analysis_surface=AnalysisOperationSurface.REGION_DETAIL,
        analysis_panel=AnalysisOperationPanel.DETAIL,
    )

    structure_ids = {operation.op_id for operation in shared_operations_for_scope(structure_scope)}
    detail_ids = {operation.op_id for operation in shared_operations_for_scope(detail_scope)}

    assert "analysis_structure_merge" in structure_ids
    assert "analysis_fit" not in structure_ids
    assert "analysis_fit" in detail_ids
    assert "analysis_toggle_velocity" in detail_ids
    assert "analysis_structure_merge" not in detail_ids
