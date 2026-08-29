"""Tests for optimizer fit result application use case."""

from __future__ import annotations

import pytest

from chappy.application.optimize import (
    ApplyFitResultUseCase,
    CaptureOptimizeHistorySnapshotUseCase,
    ComponentParameterSnapshot,
    FitResultPayloadParser,
    FitResultStatusKind,
    LineOptimizationInputSnapshot,
    ParameterStateSnapshot,
)


def test_success_with_chi_squared_builds_chi2_status_and_summary() -> None:
    """Successful payload should produce chi-squared status and export summary."""
    parser = FitResultPayloadParser()
    payload = parser.parse(
        {
            "success": True,
            "chi_squared": "12.5",
            "reduced_chi_squared": 1.25,
            "n_parameters": 3,
            "n_function_evaluations": 20,
        }
    )

    result = ApplyFitResultUseCase().apply(payload)

    assert result.status_kind is FitResultStatusKind.CHI2
    assert result.status_value == 12.5
    assert result.reduced_status_value == 1.25
    assert result.analysis_ready is True
    assert result.summary is not None
    assert result.summary.chi_squared == 12.5
    assert result.summary.n_parameters == 3
    assert result.summary.n_function_evaluations == 20


def test_success_without_chi_squared_uses_complete_status() -> None:
    """Successful payload without chi-squared should still be ready."""
    payload = FitResultPayloadParser().parse({"success": True})

    result = ApplyFitResultUseCase().apply(payload)

    assert result.status_kind is FitResultStatusKind.COMPLETE
    assert result.status_value is None
    assert result.summary is not None
    assert result.summary.chi_squared is None


def test_failure_with_message_uses_custom_status() -> None:
    """Failed payload with raw optimizer message should keep that message."""
    payload = FitResultPayloadParser().parse({"success": False, "message": "solver failed"})

    result = ApplyFitResultUseCase().apply(payload)

    assert result.status_kind is FitResultStatusKind.CUSTOM
    assert result.raw_message == "solver failed"
    assert result.analysis_ready is False
    assert result.summary is None


def test_malformed_fit_result_payload_fails_fast() -> None:
    """Malformed optimizer payload values are internal contract violations."""
    parser = FitResultPayloadParser()

    with pytest.raises(ValueError, match="chi_squared"):
        parser.parse({"success": True, "chi_squared": "not-a-number"})

    with pytest.raises(ValueError, match="reduced_chi_squared"):
        parser.parse({"success": True, "reduced_chi_squared": float("inf")})

    with pytest.raises(TypeError, match="n_parameters"):
        parser.parse({"success": True, "n_parameters": 2.5})

    with pytest.raises(TypeError, match="success"):
        parser.parse({"success": "yes"})


def test_statistics_override_payload_summary_values() -> None:
    """Detailed fit statistics should override payload values in export summary."""
    parser = FitResultPayloadParser()
    payload = parser.parse(
        {"success": True, "chi_squared": 10.0, "reduced_chi_squared": 2.0, "n_parameters": 2}
    )
    statistics = parser.parse_statistics(
        {
            "chi_squared": 9.5,
            "reduced_chi_squared": 1.9,
            "degrees_of_freedom": 5,
            "n_parameters": 4.0,
            "n_function_evaluations": 30.0,
        }
    )

    result = ApplyFitResultUseCase().apply(payload, statistics)

    assert result.summary is not None
    assert result.summary.chi_squared == 9.5
    assert result.summary.reduced_chi_squared == 1.9
    assert result.summary.degrees_of_freedom == 5.0
    assert result.summary.n_parameters == 4
    assert result.summary.n_function_evaluations == 30


def test_capture_optimize_history_snapshot_filters_components_and_region_lines() -> None:
    """History snapshot capture should keep only target components and region lines."""
    target = ComponentParameterSnapshot(
        component_id="target",
        parameters=(ParameterStateSnapshot(name="redshift", value=2.0, fixed=True, error=0.01),),
    )
    other = ComponentParameterSnapshot(component_id="other", parameters=())
    matching_line = LineOptimizationInputSnapshot(
        line_id="line-1", region_id="region-1", needs_optimization=True
    )
    other_line = LineOptimizationInputSnapshot(
        line_id="line-2", region_id="region-2", needs_optimization=True
    )

    snapshot = CaptureOptimizeHistorySnapshotUseCase().capture(
        components=(target, other),
        component_ids=frozenset({"target"}),
        lines=(matching_line, other_line),
        region_id="region-1",
    )

    assert len(snapshot.component_states) == 1
    component = snapshot.component_states[0]
    assert component.component_id == "target"
    redshift_state = next(param for param in component.parameters if param.name == "redshift")
    assert redshift_state.value == 2.0
    assert redshift_state.fixed is True
    assert redshift_state.error == 0.01
    assert snapshot.line_optimization_states[0].line_id == "line-1"
    assert snapshot.line_optimization_states[0].needs_optimization is True
