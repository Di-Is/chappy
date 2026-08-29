"""Wavelength window builder for spectrum model and residual rendering."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, SupportsFloat, SupportsIndex

import numpy as np

from chappy.core.constants import LIGHT_SPEED_KMS

if TYPE_CHECKING:
    from collections.abc import Mapping

    from numpy.typing import NDArray

    from chappy.core.absorption.models import AbsorptionLine, AbsorptionRegion


class ModelWindowBuilder:
    """Build wavelength windows and slice arrays for selected absorption regions."""

    def region_wavelength_windows(
        self, lines_by_id: Mapping[str, AbsorptionLine], region: AbsorptionRegion | None
    ) -> list[tuple[float, float]]:
        """Return merged wavelength windows for a selected absorption region."""
        if region is None:
            return []

        line_windows: list[tuple[float, float]] = []
        for line_id in region.line_ids:
            line = lines_by_id.get(line_id)
            bounds = self.line_wavelength_bounds(line)
            if bounds is not None:
                line_windows.append(bounds)

        analysis_range = region.analysis_range
        if not line_windows:
            if analysis_range is not None and self.is_valid_range(
                analysis_range[0], analysis_range[1]
            ):
                return [(float(analysis_range[0]), float(analysis_range[1]))]
            return []

        merged_windows = self.merge_wavelength_windows(line_windows)
        if analysis_range is not None and self.is_valid_range(
            analysis_range[0], analysis_range[1]
        ):
            lower = float(analysis_range[0])
            upper = float(analysis_range[1])
            clipped: list[tuple[float, float]] = []
            for start, end in merged_windows:
                window_start = max(start, lower)
                window_end = min(end, upper)
                if window_start < window_end:
                    clipped.append((window_start, window_end))
            return clipped

        return merged_windows

    @staticmethod
    def merge_wavelength_windows(windows: list[tuple[float, float]]) -> list[tuple[float, float]]:
        """Merge overlapping wavelength windows while preserving gaps."""
        if not windows:
            return []

        sorted_windows = sorted(windows, key=lambda span: span[0])
        merged: list[tuple[float, float]] = [sorted_windows[0]]

        for start, end in sorted_windows[1:]:
            prev_start, prev_end = merged[-1]
            if start <= prev_end:
                merged[-1] = (prev_start, max(prev_end, end))
            else:
                merged.append((start, end))

        return merged

    @staticmethod
    def slice_data_to_windows(
        wavelength: NDArray[np.float64],
        values: NDArray[np.float64],
        windows: list[tuple[float, float]],
    ) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
        """Extract data inside windows and insert NaN separators between gaps."""
        if wavelength.size == 0 or values.size == 0 or len(wavelength) != len(values):
            return np.zeros(0, dtype=np.float64), np.zeros(0, dtype=np.float64)

        segments: list[tuple[NDArray[np.float64], NDArray[np.float64]]] = []
        for start, end in windows:
            mask = (wavelength >= start) & (wavelength <= end)
            if not np.any(mask):
                continue
            segments.append((wavelength[mask], values[mask]))

        if not segments:
            return np.zeros(0, dtype=np.float64), np.zeros(0, dtype=np.float64)

        total_points = sum(segment[0].size for segment in segments)
        if len(segments) > 1:
            total_points += len(segments) - 1

        window_wavelength: NDArray[np.float64] = np.empty(total_points, dtype=np.float64)
        window_values: NDArray[np.float64] = np.empty(total_points, dtype=np.float64)

        insert_index = 0
        for idx, (segment_wave, segment_values) in enumerate(segments):
            count = segment_wave.size
            window_wavelength[insert_index : insert_index + count] = segment_wave
            window_values[insert_index : insert_index + count] = segment_values
            insert_index += count

            if idx < len(segments) - 1:
                window_wavelength[insert_index] = np.nan
                window_values[insert_index] = np.nan
                insert_index += 1

        return window_wavelength, window_values

    @classmethod
    def line_wavelength_bounds(cls, line: AbsorptionLine | None) -> tuple[float, float] | None:
        """Compute wavelength bounds for a line using its configured window."""
        if line is None:
            return None

        lambda_range = line.lambda_range
        if lambda_range is not None and cls.is_valid_range(lambda_range[0], lambda_range[1]):
            return float(lambda_range[0]), float(lambda_range[1])

        observed_value = line.observed_wavelength()
        window_kms = line.window_kms
        if (
            not math.isfinite(observed_value)
            or observed_value <= 0.0
            or not math.isfinite(window_kms)
            or window_kms <= 0.0
        ):
            return None

        delta = observed_value * window_kms / LIGHT_SPEED_KMS
        start = observed_value - delta
        end = observed_value + delta
        if not cls.is_valid_range(start, end):
            return None
        return start, end

    @staticmethod
    def is_valid_range(
        start: SupportsFloat | SupportsIndex | None, end: SupportsFloat | SupportsIndex | None
    ) -> bool:
        """Validate that start and end define a finite increasing interval."""
        if start is None or end is None:
            return False
        start_f = float(start)
        end_f = float(end)
        return math.isfinite(start_f) and math.isfinite(end_f) and start_f < end_f
