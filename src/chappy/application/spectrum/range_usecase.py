"""Use cases for spectrum range navigation."""

from __future__ import annotations

import math

from chappy.application.spectrum.models import (
    CenterOnWavelengthNavigationIntent,
    PanNavigationIntent,
    RangeNavigationRequest,
    RangeNavigationResult,
    SelectRangeNavigationIntent,
    SpectrumRangeSource,
    ZoomFactorNavigationIntent,
    ZoomRectNavigationIntent,
)

MIN_WAVELENGTH_DISPLAY_SPAN: float = 10.0


class RangeNavigationUseCase:
    """Calculate validated spectrum ranges from navigation intents."""

    def calculate(self, request: RangeNavigationRequest) -> RangeNavigationResult:
        """Calculate a validated wavelength range for one navigation intent.

        Args:
            request: Range navigation request with current range, data bounds, and intent.

        Returns:
            Navigation result containing validated wavelength and optional flux range.
        """
        _validate_request(request)
        proposed_range = self._calculate_new_range(request)
        validated_range = self._validate_range(proposed_range, request)
        return RangeNavigationResult(
            wavelength_range=validated_range,
            flux_range=_flux_range_from_intent(request.intent),
            source=_source_from_intent(request.intent),
        )

    def _calculate_new_range(self, request: RangeNavigationRequest) -> tuple[float, float]:
        """Calculate a proposed wavelength range before final validation.

        Args:
            request: Range navigation request.

        Returns:
            Proposed wavelength range.
        """
        min_wave, max_wave = request.current_range
        current_span = max_wave - min_wave
        center = (min_wave + max_wave) / 2.0
        intent = request.intent

        if isinstance(intent, PanNavigationIntent):
            return calculate_pan_range(
                (float(min_wave), float(max_wave)),
                float(intent.fraction),
                bounds=request.data_bounds,
            )

        if isinstance(intent, ZoomFactorNavigationIntent):
            if (
                intent.cursor_relative_position is not None
                and intent.center_wavelength is not None
            ):
                cursor = intent.center_wavelength
                relative_position = intent.cursor_relative_position
                new_span = current_span / intent.factor
                new_min = cursor - relative_position * new_span
                new_max = cursor + (1.0 - relative_position) * new_span
                return new_min, new_max

            if intent.center_wavelength is not None:
                center = intent.center_wavelength
            new_half_span = current_span / (2.0 * intent.factor)
            return center - new_half_span, center + new_half_span

        if isinstance(intent, ZoomRectNavigationIntent):
            return intent.min_wavelength, intent.max_wavelength

        if isinstance(intent, SelectRangeNavigationIntent):
            return intent.start_wavelength, intent.end_wavelength

        if isinstance(intent, CenterOnWavelengthNavigationIntent):
            new_min = intent.wavelength - current_span / 2.0
            new_max = intent.wavelength + current_span / 2.0
            if request.data_bounds is None:
                return new_min, new_max

            data_min, data_max = request.data_bounds
            if new_max > data_max:
                new_max = data_max
                new_min = max(data_min, new_max - current_span)
            elif new_min < data_min:
                new_min = data_min
                new_max = min(data_max, new_min + current_span)
            return new_min, new_max

        return request.current_range

    def _validate_range(
        self, range_tuple: tuple[float, float], request: RangeNavigationRequest
    ) -> tuple[float, float]:
        """Validate and clip a wavelength range.

        Args:
            range_tuple: Proposed wavelength range.
            request: Original navigation request.

        Returns:
            Validated wavelength range.
        """
        min_wave, max_wave = range_tuple

        if min_wave >= max_wave:
            min_wave, max_wave = max_wave, min_wave

        bounds = request.data_bounds
        if bounds is not None:
            data_min, data_max = bounds
            min_wave = max(min_wave, data_min)
            max_wave = min(max_wave, data_max)

        anchor_wavelength: float | None = None
        anchor_relative: float | None = None
        intent = request.intent

        if isinstance(intent, ZoomFactorNavigationIntent):
            if intent.center_wavelength is not None:
                anchor_wavelength = float(intent.center_wavelength)
                if intent.cursor_relative_position is not None:
                    anchor_relative = float(intent.cursor_relative_position)
                else:
                    anchor_relative = 0.5
            else:
                existing_min, existing_max = request.current_range
                anchor_wavelength = float((existing_min + existing_max) / 2.0)
                anchor_relative = 0.5

        return enforce_min_wavelength_span(
            float(min_wave),
            float(max_wave),
            bounds=bounds,
            anchor_wavelength=anchor_wavelength,
            anchor_relative_position=anchor_relative,
        )


def _validate_request(request: RangeNavigationRequest) -> None:
    """Validate request-level invariants before navigation calculation.

    Args:
        request: Range navigation request.

    Raises:
        ValueError: If the request violates the range navigation contract.
    """
    _validate_ordered_pair(request.current_range, "current_range")
    if request.data_bounds is not None:
        _validate_ordered_pair(request.data_bounds, "data_bounds")
    _validate_intent(request.intent)


def _validate_ordered_pair(pair: tuple[float, float], label: str) -> None:
    """Validate that a numeric pair is finite and strictly ordered.

    Args:
        pair: Pair to validate.
        label: Diagnostic label.

    Raises:
        ValueError: If the pair is non-finite or not ordered.
    """
    lower, upper = pair
    if not math.isfinite(lower) or not math.isfinite(upper):
        msg = f"{label} values must be finite."
        raise ValueError(msg)
    if lower >= upper:
        msg = f"{label} must satisfy min < max."
        raise ValueError(msg)


def _validate_finite(value: float, label: str) -> None:
    """Validate that one navigation value is finite.

    Args:
        value: Value to validate.
        label: Diagnostic label.

    Raises:
        ValueError: If the value is not finite.
    """
    if not math.isfinite(value):
        msg = f"{label} must be finite."
        raise ValueError(msg)


def _validate_optional_finite(value: float | None, label: str) -> None:
    """Validate an optional finite navigation value.

    Args:
        value: Optional value to validate.
        label: Diagnostic label.

    Raises:
        ValueError: If a present value is not finite.
    """
    if value is None:
        return
    _validate_finite(value, label)


def _validate_intent(
    intent: (
        PanNavigationIntent
        | ZoomFactorNavigationIntent
        | ZoomRectNavigationIntent
        | SelectRangeNavigationIntent
        | CenterOnWavelengthNavigationIntent
    ),
) -> None:
    """Validate intent-specific request invariants.

    Args:
        intent: Navigation intent to validate.

    Raises:
        ValueError: If the intent violates the range navigation contract.
    """
    if isinstance(intent, PanNavigationIntent):
        _validate_finite(intent.fraction, "pan fraction")
        return

    if isinstance(intent, ZoomFactorNavigationIntent):
        _validate_finite(intent.factor, "zoom factor")
        if intent.factor <= 0.0:
            msg = "zoom factor must be positive."
            raise ValueError(msg)
        _validate_optional_finite(intent.center_wavelength, "zoom center_wavelength")
        _validate_optional_finite(intent.cursor_relative_position, "zoom cursor_relative_position")
        return

    if isinstance(intent, ZoomRectNavigationIntent):
        _validate_finite(intent.min_wavelength, "zoom rect min_wavelength")
        _validate_finite(intent.max_wavelength, "zoom rect max_wavelength")
        if math.isclose(intent.min_wavelength, intent.max_wavelength, rel_tol=0.0, abs_tol=0.0):
            msg = "zoom rect wavelength range must not be zero-width."
            raise ValueError(msg)
        _validate_optional_finite(intent.min_flux, "zoom rect min_flux")
        _validate_optional_finite(intent.max_flux, "zoom rect max_flux")
        return

    if isinstance(intent, SelectRangeNavigationIntent):
        _validate_finite(intent.start_wavelength, "select range start_wavelength")
        _validate_finite(intent.end_wavelength, "select range end_wavelength")
        if math.isclose(intent.start_wavelength, intent.end_wavelength, rel_tol=0.0, abs_tol=0.0):
            msg = "select range must not be zero-width."
            raise ValueError(msg)
        return

    if isinstance(intent, CenterOnWavelengthNavigationIntent):
        _validate_finite(intent.wavelength, "center wavelength")
        return


def calculate_pan_range(
    current_range: tuple[float, float],
    fraction: float,
    *,
    bounds: tuple[float, float] | None = None,
) -> tuple[float, float]:
    """Return a wavelength range adjusted by horizontal panning.

    Args:
        current_range: Current wavelength range.
        fraction: Fractional pan offset relative to the current span.
        bounds: Optional data wavelength bounds.

    Returns:
        New wavelength range.
    """
    min_wave, max_wave = current_range
    span = max_wave - min_wave
    if span <= 0.0:
        return float(min_wave), float(max_wave)

    delta = span * fraction
    proposed_min = float(min_wave + delta)
    proposed_max = float(max_wave + delta)

    if bounds is None:
        return proposed_min, proposed_max

    data_min, data_max = bounds
    if data_max <= data_min:
        return float(data_min), float(data_max)

    data_span = data_max - data_min
    if span >= data_span:
        return float(data_min), float(data_max)

    if proposed_min < data_min:
        proposed_min = data_min
        proposed_max = data_min + span
    elif proposed_max > data_max:
        proposed_max = data_max
        proposed_min = data_max - span

    adjusted_min = max(proposed_min, data_min)
    adjusted_max = min(proposed_max, data_max)
    return float(adjusted_min), float(adjusted_max)


def enforce_min_wavelength_span(
    min_wave: float,
    max_wave: float,
    *,
    bounds: tuple[float, float] | None = None,
    anchor_wavelength: float | None = None,
    anchor_relative_position: float | None = None,
) -> tuple[float, float]:
    """Return a wavelength window that respects the minimum display span.

    Args:
        min_wave: Proposed lower wavelength limit.
        max_wave: Proposed upper wavelength limit.
        bounds: Optional data bounds.
        anchor_wavelength: Optional wavelength to keep anchored when expanding.
        anchor_relative_position: Optional anchor relative position in the window.

    Returns:
        Adjusted wavelength range.
    """
    if max_wave < min_wave:
        min_wave, max_wave = max_wave, min_wave

    current_span = max_wave - min_wave
    target_span = MIN_WAVELENGTH_DISPLAY_SPAN

    if bounds is not None:
        data_min, data_max = bounds
        if data_max <= data_min:
            return float(data_min), float(data_max)
        target_span = min(target_span, data_max - data_min)

    if target_span <= 0:
        return float(min_wave), float(max_wave)

    if current_span >= target_span:
        return float(min_wave), float(max_wave)

    effective_anchor = None
    effective_anchor_relative = None
    if anchor_wavelength is not None:
        effective_anchor = float(anchor_wavelength)
        effective_anchor_relative = (
            float(anchor_relative_position) if anchor_relative_position is not None else 0.5
        )

    if effective_anchor is not None and effective_anchor_relative is not None:
        clamped_relative = min(max(effective_anchor_relative, 0.0), 1.0)
        if clamped_relative in (0.0, 1.0):
            epsilon = min(1e-6, 0.5)
            clamped_relative = epsilon if clamped_relative == 0.0 else 1.0 - epsilon

        new_min = effective_anchor - clamped_relative * target_span
        new_max = new_min + target_span
    else:
        center = (min_wave + max_wave) / 2.0
        half_span = target_span / 2.0
        new_min = center - half_span
        new_max = center + half_span

    if bounds is not None:
        data_min, data_max = bounds
        if data_max <= data_min:
            return float(data_min), float(data_max)

        shift = 0.0
        if new_min < data_min:
            shift = data_min - new_min
        elif new_max > data_max:
            shift = data_max - new_max

        if shift != 0.0:
            new_min += shift
            new_max += shift

        new_min = max(new_min, data_min)
        new_max = min(new_max, data_max)

        if not math.isclose(new_max - new_min, target_span, rel_tol=0.0, abs_tol=1e-9):
            if new_min <= data_min:
                new_max = min(data_min + target_span, data_max)
                new_min = new_max - target_span
            elif new_max >= data_max:
                new_min = max(data_max - target_span, data_min)
                new_max = new_min + target_span

    return float(new_min), float(new_max)


def _flux_range_from_intent(
    intent: (
        PanNavigationIntent
        | ZoomFactorNavigationIntent
        | ZoomRectNavigationIntent
        | SelectRangeNavigationIntent
        | CenterOnWavelengthNavigationIntent
    ),
) -> tuple[float, float] | None:
    """Return flux range encoded by a navigation intent.

    Args:
        intent: Navigation intent.

    Returns:
        Flux range when the intent carries one, otherwise None.
    """
    if (
        isinstance(intent, ZoomRectNavigationIntent)
        and intent.min_flux is not None
        and intent.max_flux is not None
    ):
        return intent.min_flux, intent.max_flux
    return None


def _source_from_intent(
    intent: (
        PanNavigationIntent
        | ZoomFactorNavigationIntent
        | ZoomRectNavigationIntent
        | SelectRangeNavigationIntent
        | CenterOnWavelengthNavigationIntent
    ),
) -> SpectrumRangeSource:
    """Return range update source for a navigation intent.

    Args:
        intent: Navigation intent.

    Returns:
        Source category used by the presenter for orchestration.
    """
    if isinstance(intent, ZoomRectNavigationIntent):
        return SpectrumRangeSource.RECT_ZOOM
    return SpectrumRangeSource.INTENT


__all__ = [
    "MIN_WAVELENGTH_DISPLAY_SPAN",
    "RangeNavigationUseCase",
    "calculate_pan_range",
    "enforce_min_wavelength_span",
]
