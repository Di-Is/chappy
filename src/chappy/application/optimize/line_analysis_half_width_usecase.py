"""Use case for editing Optimize line analysis half-widths."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from chappy.application.optimize.models import (
    LineAnalysisHalfWidthAdjusted,
    LineAnalysisHalfWidthApplied,
    LineAnalysisHalfWidthEditOutcome,
    LineAnalysisHalfWidthEditRequest,
    LineAnalysisHalfWidthInvariantKind,
    LineAnalysisHalfWidthInvariantViolation,
    LineAnalysisHalfWidthLineChange,
    LineAnalysisHalfWidthNoChange,
    LineAnalysisHalfWidthNoChangeReason,
    LineAnalysisHalfWidthRejected,
    LineAnalysisHalfWidthRejectionReason,
    PreparedLineAnalysisHalfWidthChange,
)
from chappy.core.constants import LIGHT_SPEED_KMS
from chappy.core.velocity_ranges import (
    MAX_ANALYSIS_HALF_WIDTH_KMS,
    MIN_ANALYSIS_HALF_WIDTH_KMS,
    LineAnalysisHalfWidth,
)

if TYPE_CHECKING:
    from chappy.application.optimize.ports import (
        LineAnalysisHalfWidthReadPort,
        LineAnalysisHalfWidthTransactionPort,
    )


def component_velocity_relative_to_line(
    *, component_redshift: float, line_redshift: float
) -> float:
    """Return a component center velocity relative to one absorption line."""
    return LIGHT_SPEED_KMS * (component_redshift - line_redshift) / (1.0 + line_redshift)


class EditLineAnalysisHalfWidthUseCase:
    """Prepare and atomically commit one scientific half-width edit."""

    def __init__(
        self,
        *,
        reader: LineAnalysisHalfWidthReadPort,
        transaction: LineAnalysisHalfWidthTransactionPort,
    ) -> None:
        """Initialize the use case with read and commit boundaries."""
        self._reader = reader
        self._transaction = transaction

    def execute(
        self, request: LineAnalysisHalfWidthEditRequest
    ) -> LineAnalysisHalfWidthEditOutcome:
        """Validate, prepare, and commit one line analysis half-width edit."""
        requested = float(request.requested_half_width)
        if not math.isfinite(requested):
            return self._rejected(LineAnalysisHalfWidthRejectionReason.INVALID_NUMBER, requested)
        if not MIN_ANALYSIS_HALF_WIDTH_KMS <= requested <= MAX_ANALYSIS_HALF_WIDTH_KMS:
            return self._rejected(
                LineAnalysisHalfWidthRejectionReason.OUTSIDE_SUPPORTED_RANGE, requested
            )

        seed = self._reader.analysis_line(request.line_id)
        if seed is None or seed.region_id is None:
            return self._rejected(LineAnalysisHalfWidthRejectionReason.LINE_NOT_FOUND, requested)
        region = self._reader.analysis_region(seed.region_id)
        if region is None:
            return self._rejected(LineAnalysisHalfWidthRejectionReason.LINE_NOT_FOUND, requested)

        affected_ids = self._affected_line_ids(seed.line_id, seed.region_id)
        required, constraining_ids = self._required_half_width(affected_ids)
        if required > MAX_ANALYSIS_HALF_WIDTH_KMS:
            return self._rejected(
                LineAnalysisHalfWidthRejectionReason.COMPONENT_OUTSIDE_SUPPORTED_RANGE, requested
            )

        applied = LineAnalysisHalfWidth(max(requested, required))
        line_changes = tuple(self._line_change(line_id, applied) for line_id in affected_ids)
        after_region_range = self._region_range(
            region.line_ids, {change.line_id: change for change in line_changes}
        )
        unchanged = self._is_unchanged(line_changes, region.analysis_range, after_region_range)
        adjusted = requested < required
        if unchanged:
            reason = (
                LineAnalysisHalfWidthNoChangeReason.ALREADY_AT_REQUIRED_MINIMUM
                if adjusted
                else LineAnalysisHalfWidthNoChangeReason.ALREADY_EQUAL
            )
            return LineAnalysisHalfWidthNoChange(
                requested=requested,
                retained=applied,
                reason=reason,
                affected_line_ids=affected_ids,
                constraining_component_ids=constraining_ids,
                region_id=region.region_id,
            )

        change = PreparedLineAnalysisHalfWidthChange(
            seed_line_id=seed.line_id,
            region_id=region.region_id,
            line_changes=line_changes,
            region_line_ids=tuple(region.line_ids),
            before_region_analysis_range=region.analysis_range,
            after_region_analysis_range=after_region_range,
        )
        self._transaction.execute_line_analysis_half_width_change(change)
        if adjusted:
            return LineAnalysisHalfWidthAdjusted(
                requested=requested,
                applied_minimum=applied,
                affected_line_ids=affected_ids,
                constraining_component_ids=constraining_ids,
                region_id=region.region_id,
            )
        return LineAnalysisHalfWidthApplied(
            requested=requested,
            applied=applied,
            affected_line_ids=affected_ids,
            region_id=region.region_id,
        )

    def _affected_line_ids(self, seed_line_id: str, region_id: str) -> tuple[str, ...]:
        expanded = self._reader.expand_analysis_multiplet_line_ids(seed_line_id)
        stable_ids: list[str] = []
        seen: set[str] = set()
        for line_id in expanded or (seed_line_id,):
            if line_id in seen:
                continue
            line = self._reader.analysis_line(line_id)
            if line is not None and line.region_id == region_id:
                stable_ids.append(line_id)
                seen.add(line_id)
        if seed_line_id not in seen:
            stable_ids.insert(0, seed_line_id)
        return tuple(stable_ids)

    def _required_half_width(
        self, affected_line_ids: tuple[str, ...]
    ) -> tuple[float, tuple[str, ...]]:
        maximum = MIN_ANALYSIS_HALF_WIDTH_KMS
        constraining_ids: list[str] = []
        for line_id in affected_line_ids:
            line = self._reader.analysis_line(line_id)
            if line is None:
                continue
            for component_id in line.model_ids:
                component = self._reader.analysis_component(component_id)
                if component is None:
                    raise LineAnalysisHalfWidthInvariantViolation(
                        LineAnalysisHalfWidthInvariantKind.MISSING_COMPONENT, line_id, component_id
                    )
                redshift_parameter = component.parameters.get("redshift")
                if redshift_parameter is None:
                    raise LineAnalysisHalfWidthInvariantViolation(
                        LineAnalysisHalfWidthInvariantKind.MISSING_COMPONENT_REDSHIFT,
                        line_id,
                        component_id,
                    )
                redshift = float(redshift_parameter.value)
                if not math.isfinite(redshift):
                    raise LineAnalysisHalfWidthInvariantViolation(
                        LineAnalysisHalfWidthInvariantKind.NONFINITE_COMPONENT_REDSHIFT,
                        line_id,
                        component_id,
                    )
                velocity = abs(
                    component_velocity_relative_to_line(
                        component_redshift=redshift, line_redshift=line.center_z
                    )
                )
                if velocity > maximum and not math.isclose(velocity, maximum):
                    maximum = velocity
                    constraining_ids = [component_id]
                elif math.isclose(velocity, maximum) and component_id not in constraining_ids:
                    constraining_ids.append(component_id)
        return maximum, tuple(constraining_ids)

    def _line_change(
        self, line_id: str, applied: LineAnalysisHalfWidth
    ) -> LineAnalysisHalfWidthLineChange:
        line = self._reader.analysis_line(line_id)
        if line is None:
            msg = f"Affected absorption line disappeared while preparing edit: {line_id}"
            raise RuntimeError(msg)
        observed = line.observed_wavelength()
        delta = observed * applied.kms / LIGHT_SPEED_KMS
        return LineAnalysisHalfWidthLineChange(
            line_id=line_id,
            before_half_width=line.window_kms,
            after_half_width=applied,
            before_lambda_range=line.lambda_range,
            after_lambda_range=(observed - delta, observed + delta),
        )

    def _region_range(
        self, region_line_ids: list[str], changes: dict[str, LineAnalysisHalfWidthLineChange]
    ) -> tuple[float, float]:
        ranges: list[tuple[float, float]] = []
        for line_id in region_line_ids:
            change = changes.get(line_id)
            if change is not None:
                ranges.append(change.after_lambda_range)
                continue
            line = self._reader.analysis_line(line_id)
            if line is None:
                continue
            if line.lambda_range is not None:
                ranges.append(line.lambda_range)
                continue
            observed = line.observed_wavelength()
            delta = observed * line.window_kms / LIGHT_SPEED_KMS
            ranges.append((observed - delta, observed + delta))
        if not ranges:
            msg = "An Optimize analysis region must contain at least one absorption line."
            raise RuntimeError(msg)
        return (min(item[0] for item in ranges), max(item[1] for item in ranges))

    @staticmethod
    def _is_unchanged(
        changes: tuple[LineAnalysisHalfWidthLineChange, ...],
        before_region_range: tuple[float, float] | None,
        after_region_range: tuple[float, float],
    ) -> bool:
        lines_unchanged = all(
            math.isclose(change.before_half_width, change.after_half_width.kms)
            and change.before_lambda_range is not None
            and math.isclose(change.before_lambda_range[0], change.after_lambda_range[0])
            and math.isclose(change.before_lambda_range[1], change.after_lambda_range[1])
            for change in changes
        )
        region_unchanged = (
            before_region_range is not None
            and math.isclose(before_region_range[0], after_region_range[0])
            and math.isclose(before_region_range[1], after_region_range[1])
        )
        return lines_unchanged and region_unchanged

    @staticmethod
    def _rejected(
        reason: LineAnalysisHalfWidthRejectionReason, requested: float
    ) -> LineAnalysisHalfWidthRejected:
        return LineAnalysisHalfWidthRejected(
            reason=reason,
            requested=requested,
            supported_minimum=MIN_ANALYSIS_HALF_WIDTH_KMS,
            supported_maximum=MAX_ANALYSIS_HALF_WIDTH_KMS,
        )


__all__ = ["EditLineAnalysisHalfWidthUseCase", "component_velocity_relative_to_line"]
