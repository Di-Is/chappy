"""Use case for applying optimizer fit results."""

from __future__ import annotations

import math

from chappy.application.history.ports import LineOptimizationStateSnapshot
from chappy.application.optimize.models import (
    ComponentParameterSnapshot,
    FitResultApplication,
    FitResultPayload,
    FitResultRawPayload,
    FitResultRawValue,
    FitResultStatusKind,
    LineOptimizationInputSnapshot,
    OptimizeHistorySnapshot,
)
from chappy.core.analysis import FitSummary
from chappy.core.components.optimize import FitOutcome


class FitResultPayloadParser:
    """Normalize legacy optimizer payload mappings into typed payloads."""

    def parse(self, payload: FitResultRawPayload) -> FitResultPayload:
        """Parse a legacy optimizer result payload.

        Args:
            payload: Legacy optimizer payload.

        Returns:
            Normalized fit result payload.
        """
        message = payload.get("message")
        outcome = payload.get("outcome")
        return FitResultPayload(
            success=_parse_success(payload),
            message=message if isinstance(message, str) and message else None,
            outcome=outcome if isinstance(outcome, str) and outcome else None,
            chi_squared=_optional_finite_float(payload, "chi_squared"),
            reduced_chi_squared=_optional_finite_float(payload, "reduced_chi_squared"),
            n_parameters=_optional_int(payload, "n_parameters"),
            n_function_evaluations=_optional_int(payload, "n_function_evaluations"),
        )

    def parse_statistics(self, payload: FitResultRawPayload) -> FitSummary:
        """Parse legacy fit statistics into a typed summary.

        Args:
            payload: Legacy statistics payload from optimize component.

        Returns:
            Fit summary populated with known statistic fields.
        """
        return FitSummary(
            chi_squared=_optional_finite_float(payload, "chi_squared"),
            reduced_chi_squared=_optional_finite_float(payload, "reduced_chi_squared"),
            degrees_of_freedom=_optional_finite_float(payload, "degrees_of_freedom"),
            n_parameters=_optional_int(payload, "n_parameters"),
            n_function_evaluations=_optional_int(payload, "n_function_evaluations"),
        )


class ApplyFitResultUseCase:
    """Build UI-independent fit result application decisions."""

    def apply(
        self, payload: FitResultPayload, fit_statistics: FitSummary | None = None
    ) -> FitResultApplication:
        """Apply a normalized fit result payload.

        Args:
            payload: Normalized optimizer result payload.
            fit_statistics: Optional detailed statistics from the fitted model.

        Returns:
            Fit result application decision.
        """
        status_kind = _status_kind(payload)
        summary = _build_summary(payload, fit_statistics) if payload.success else None
        return FitResultApplication(
            status_kind=status_kind,
            status_value=payload.chi_squared,
            reduced_status_value=payload.reduced_chi_squared,
            raw_message=payload.message,
            summary=summary,
            analysis_ready=payload.success,
            outcome=payload.outcome,
        )


class CaptureOptimizeHistorySnapshotUseCase:
    """Capture typed optimize history state from application snapshots."""

    def capture(
        self,
        *,
        components: tuple[ComponentParameterSnapshot, ...],
        component_ids: frozenset[str],
        lines: tuple[LineOptimizationInputSnapshot, ...],
        region_id: str | None,
    ) -> OptimizeHistorySnapshot:
        """Capture component parameters and line optimization flags.

        Args:
            components: Component parameter snapshots available in the model.
            component_ids: Target component IDs to include.
            lines: Line optimization snapshots available in the project.
            region_id: Region whose line optimization flags should be captured.

        Returns:
            Typed optimize history snapshot.
        """
        component_states = tuple(
            component for component in components if component.component_id in component_ids
        )
        line_states = (
            tuple(
                LineOptimizationStateSnapshot(
                    line_id=line.line_id, needs_optimization=line.needs_optimization
                )
                for line in lines
                if line.region_id == region_id
            )
            if region_id is not None
            else ()
        )
        return OptimizeHistorySnapshot(
            component_states=component_states, line_optimization_states=line_states
        )


def _status_kind(payload: FitResultPayload) -> FitResultStatusKind:
    """Return status kind for a fit result payload.

    Args:
        payload: Normalized optimizer result payload.

    Returns:
        Status kind to apply in the presenter/widget layer.
    """
    if payload.success:
        if payload.chi_squared is not None:
            return FitResultStatusKind.CHI2
        return FitResultStatusKind.COMPLETE

    if payload.message:
        return FitResultStatusKind.CUSTOM
    return FitResultStatusKind.FAILED


def _build_summary(payload: FitResultPayload, fit_statistics: FitSummary | None) -> FitSummary:
    """Build export summary for a successful fit result.

    Args:
        payload: Normalized optimizer result payload.
        fit_statistics: Optional detailed fit statistics.

    Returns:
        Fit summary.
    """
    outcome = _parse_outcome(payload.outcome)
    if fit_statistics is None:
        return FitSummary(
            chi_squared=payload.chi_squared,
            reduced_chi_squared=payload.reduced_chi_squared,
            n_parameters=payload.n_parameters,
            n_function_evaluations=payload.n_function_evaluations,
            outcome=outcome,
        )

    return FitSummary(
        chi_squared=fit_statistics.chi_squared
        if fit_statistics.chi_squared is not None
        else payload.chi_squared,
        reduced_chi_squared=fit_statistics.reduced_chi_squared
        if fit_statistics.reduced_chi_squared is not None
        else payload.reduced_chi_squared,
        degrees_of_freedom=fit_statistics.degrees_of_freedom,
        n_parameters=fit_statistics.n_parameters
        if fit_statistics.n_parameters is not None
        else payload.n_parameters,
        n_function_evaluations=fit_statistics.n_function_evaluations
        if fit_statistics.n_function_evaluations is not None
        else payload.n_function_evaluations,
        outcome=outcome,
    )


def _parse_outcome(outcome: str | None) -> FitOutcome | None:
    """Convert the payload's raw outcome string into a typed `FitOutcome`."""
    if outcome is None:
        return None
    return FitOutcome(outcome)


def _parse_success(payload: FitResultRawPayload) -> bool:
    """Parse the optional success flag from a raw optimizer payload."""
    if "success" not in payload or payload["success"] is None:
        return False
    value = payload["success"]
    if isinstance(value, bool):
        return value
    msg = "Fit result payload field 'success' must be a bool."
    raise TypeError(msg)


def _optional_finite_float(payload: FitResultRawPayload, key: str) -> float | None:
    """Parse an optional finite float field from a raw optimizer payload."""
    if key not in payload or payload[key] is None:
        return None
    return _to_finite_float(payload[key], key)


def _optional_int(payload: FitResultRawPayload, key: str) -> int | None:
    """Parse an optional integer field from a raw optimizer payload."""
    if key not in payload or payload[key] is None:
        return None
    return _to_int(payload[key], key)


def _to_finite_float(value: FitResultRawValue, key: str) -> float:
    """Convert a value to a finite float when possible.

    Args:
        value: Value to convert.
        key: Payload field name for diagnostics.

    Returns:
        Finite float.

    Raises:
        ValueError: If the field is present but not a finite float.
        TypeError: If the field has an unsupported type.
    """
    if isinstance(value, bool):
        msg = f"Fit result payload field '{key}' must be a finite float."
        raise TypeError(msg)
    if isinstance(value, int | float):
        converted = float(value)
    elif isinstance(value, str):
        try:
            converted = float(value)
        except ValueError:
            msg = f"Fit result payload field '{key}' must be a finite float."
            raise ValueError(msg) from None
    else:
        msg = f"Fit result payload field '{key}' must be a finite float."
        raise TypeError(msg)

    if not math.isfinite(converted):
        msg = f"Fit result payload field '{key}' must be finite."
        raise ValueError(msg)
    return converted


def _to_int(value: FitResultRawValue, key: str) -> int:
    """Convert a value to int when representable.

    Args:
        value: Value to convert.
        key: Payload field name for diagnostics.

    Returns:
        Integer.

    Raises:
        ValueError: If the field is present but not an integer.
        TypeError: If the field has an unsupported type.
    """
    if isinstance(value, bool):
        msg = f"Fit result payload field '{key}' must be an integer."
        raise TypeError(msg)
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            msg = f"Fit result payload field '{key}' must be an integer."
            raise ValueError(msg) from None
    msg = f"Fit result payload field '{key}' must be an integer."
    raise TypeError(msg)
