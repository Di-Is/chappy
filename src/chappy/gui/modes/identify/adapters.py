"""Adapters for identify coordinator boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

    from chappy.core.atomic_data import AtomicLine, AtomicLineData
    from chappy.core.presets import Preset


@dataclass(frozen=True, slots=True)
class IdentifyPresetAdapterResult:
    """Resolved preset display data."""

    current_id: str | None
    options: tuple[tuple[str, str], ...]
    baseline_id: str | None
    line_items: tuple[AtomicLine, ...]


class IdentifyPresetAdapter:
    """Resolve preset option and baseline data."""

    def build_result(
        self, presets: Iterable[Preset], current_id: str | None, atomic_data: AtomicLineData
    ) -> IdentifyPresetAdapterResult:
        """Build preset data for the identify panel.

        Args:
            presets: Available presets.
            current_id: Current preset ID.
            atomic_data: Atomic line database.

        Returns:
            Resolved preset result.
        """
        preset_list = tuple(presets)
        options = tuple((preset.id, preset.name) for preset in preset_list)
        selected_id = current_id or (options[0][0] if options else None)
        preset = next((item for item in preset_list if item.id == selected_id), None)
        if preset is None:
            return IdentifyPresetAdapterResult(selected_id, options, None, ())

        preset.ensure_baseline(atomic_data)
        lines = tuple(
            line
            for line_id in preset.line_ids
            if (line := atomic_data.get_line_by_id(line_id)) is not None
        )
        return IdentifyPresetAdapterResult(selected_id, options, preset.baseline_id, lines)
