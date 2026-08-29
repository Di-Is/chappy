"""Normalization of overlay payloads for the spectrum view.

Converts raw mapping payloads emitted by coordinators into the typed
representations consumed by the plot host. The logic is Qt-independent and
operates purely on mappings and primitive conversion.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

from chappy.core.conversion import coerce_float

if TYPE_CHECKING:
    from chappy.plotting.overlays import (
        AbsorptionLineRegion,
        IdentifyPreviewEntry,
        IdentifyPreviewPayload,
    )


class SpectrumOverlayPayloadNormalizer:
    """Normalize identify preview and absorption region overlay payloads."""

    @classmethod
    def normalize_identify_preview(
        cls, preview: Mapping[str, object] | IdentifyPreviewPayload | None
    ) -> IdentifyPreviewPayload | None:
        """Normalize identify preview payloads received from coordinators.

        Args:
            preview: Raw payload mapping emitted by the identify coordinator.

        Returns:
            Parsed payload consumable by the plot host, or ``None`` when invalid.
        """
        if preview is None:
            return None
        if not isinstance(preview, Mapping):
            msg = "Identify preview payload must be a mapping."
            raise TypeError(msg)

        entries_value = preview.get("entries", ())
        normalized_entries: list[IdentifyPreviewEntry] = []
        if isinstance(entries_value, Sequence):
            for entry in entries_value:
                if not isinstance(entry, Mapping):
                    msg = "Identify preview entries must be mappings."
                    raise TypeError(msg)
                normalized_entries.append(cls._normalize_identify_preview_entry(entry))
        else:
            msg = "Identify preview entries must be a sequence."
            raise TypeError(msg)

        normalized_payload: IdentifyPreviewPayload = {}
        if normalized_entries:
            normalized_payload["entries"] = tuple(normalized_entries)
        hint_text = preview.get("hint_text")
        if isinstance(hint_text, str) and hint_text:
            normalized_payload["hint_text"] = hint_text
        return normalized_payload

    @classmethod
    def _normalize_identify_preview_entry(
        cls, entry: Mapping[str, object]
    ) -> IdentifyPreviewEntry:
        """Convert a raw identify preview entry into the typed representation.

        Args:
            entry: Raw entry mapping.

        Returns:
            Typed preview entry.
        """
        lambda_min = cls._required_float(entry, "lambda_min")
        lambda_max = cls._required_float(entry, "lambda_max")
        cls._require_increasing_bounds(lambda_min, lambda_max, "identify preview bounds")

        normalized: IdentifyPreviewEntry = {"lambda_min": lambda_min, "lambda_max": lambda_max}

        center = coerce_float(entry.get("center"), default=None, require_finite=True)
        if center is not None:
            normalized["center"] = center

        color = entry.get("color")
        if isinstance(color, str) and color:
            normalized["color"] = color

        fill_alpha = coerce_float(entry.get("fill_alpha"), default=None, require_finite=True)
        if fill_alpha is not None:
            normalized["fill_alpha"] = fill_alpha

        line_alpha = coerce_float(entry.get("line_alpha"), default=None, require_finite=True)
        if line_alpha is not None:
            normalized["line_alpha"] = line_alpha

        line_width = coerce_float(entry.get("line_width"), default=None, require_finite=True)
        if line_width is not None:
            normalized["line_width"] = line_width

        line_style = entry.get("line_style")
        if isinstance(line_style, str) and line_style:
            normalized["line_style"] = line_style

        is_primary = entry.get("is_primary")
        if isinstance(is_primary, bool):
            normalized["is_primary"] = is_primary

        label = entry.get("label")
        if isinstance(label, str):
            normalized["label"] = label

        label_color = entry.get("label_color")
        if isinstance(label_color, str) and label_color:
            normalized["label_color"] = label_color

        label_font_size = coerce_float(
            entry.get("label_font_size"), default=None, require_finite=True
        )
        if label_font_size is not None:
            normalized["label_font_size"] = label_font_size

        label_font_weight = entry.get("label_font_weight")
        if isinstance(label_font_weight, str) and label_font_weight:
            normalized["label_font_weight"] = label_font_weight

        return normalized

    @classmethod
    def normalize_absorption_regions(
        cls, regions: Sequence[Mapping[str, object]] | Sequence[AbsorptionLineRegion] | None
    ) -> list[AbsorptionLineRegion]:
        """Normalize absorption line region payloads.

        Args:
            regions: Raw payloads describing spectrum regions.

        Returns:
            List of typed region payloads compatible with the plot host.
        """
        if not regions:
            return []

        normalized: list[AbsorptionLineRegion] = []
        for region in regions:
            if not isinstance(region, Mapping):
                msg = "Absorption region overlays must be mappings."
                raise TypeError(msg)
            normalized.append(cls._normalize_absorption_region_entry(region))
        return normalized

    @classmethod
    def _normalize_absorption_region_entry(
        cls, region: Mapping[str, object]
    ) -> AbsorptionLineRegion:
        """Convert a region payload into the AbsorptionLineRegion format.

        Args:
            region: Raw payload mapping.

        Returns:
            Typed region payload.
        """
        lambda_start = cls._required_float(region, "lambda_start")
        lambda_end = cls._required_float(region, "lambda_end")
        cls._require_increasing_bounds(lambda_start, lambda_end, "absorption region bounds")

        normalized: AbsorptionLineRegion = {"lambda_start": lambda_start, "lambda_end": lambda_end}

        region_id = region.get("id")
        if isinstance(region_id, str) and region_id:
            normalized["id"] = region_id

        color = region.get("color")
        if isinstance(color, str) and color:
            normalized["color"] = color

        edge_color = region.get("edge_color")
        if isinstance(edge_color, str) and edge_color:
            normalized["edge_color"] = edge_color

        alpha = coerce_float(region.get("alpha"), default=None, require_finite=True)
        if alpha is not None:
            normalized["alpha"] = alpha

        edge_alpha = coerce_float(region.get("edge_alpha"), default=None, require_finite=True)
        if edge_alpha is not None:
            normalized["edge_alpha"] = edge_alpha

        line_style = region.get("line_style")
        if isinstance(line_style, str) and line_style:
            normalized["line_style"] = line_style

        line_width = coerce_float(region.get("line_width"), default=None, require_finite=True)
        if line_width is not None:
            normalized["line_width"] = line_width

        zorder = region.get("zorder")
        if isinstance(zorder, int) and not isinstance(zorder, bool):
            normalized["zorder"] = zorder

        label = region.get("label")
        if isinstance(label, str):
            normalized["label"] = label

        lambda_center = coerce_float(
            region.get("lambda_center"), default=None, require_finite=True
        )
        if lambda_center is not None:
            normalized["lambda_center"] = lambda_center

        label_visible = region.get("label_visible")
        if isinstance(label_visible, bool):
            normalized["label_visible"] = label_visible

        label_color = region.get("label_color")
        if isinstance(label_color, str) and label_color:
            normalized["label_color"] = label_color

        label_font_size = coerce_float(
            region.get("label_font_size"), default=None, require_finite=True
        )
        if label_font_size is not None:
            normalized["label_font_size"] = label_font_size

        label_font_weight = region.get("label_font_weight")
        if isinstance(label_font_weight, str) and label_font_weight:
            normalized["label_font_weight"] = label_font_weight
        else:
            fallback_weight = region.get("label_weight")
            if isinstance(fallback_weight, str) and fallback_weight:
                normalized["label_font_weight"] = fallback_weight

        label_y = coerce_float(region.get("label_y"), default=None, require_finite=True)
        if label_y is not None:
            normalized["label_y"] = min(max(label_y, 0.0), 1.0)

        label_zorder = coerce_float(region.get("label_zorder"), default=None, require_finite=True)
        if label_zorder is not None:
            normalized["label_zorder"] = label_zorder

        label_box_alpha = coerce_float(
            region.get("label_box_alpha"), default=None, require_finite=True
        )
        if label_box_alpha is not None:
            normalized["label_box_alpha"] = min(max(label_box_alpha, 0.0), 1.0)

        label_box_color = region.get("label_box_color")
        if isinstance(label_box_color, str) and label_box_color:
            normalized["label_box_color"] = label_box_color

        label_box_pad = coerce_float(
            region.get("label_box_pad"), default=None, require_finite=True
        )
        if label_box_pad is not None:
            normalized["label_box_pad"] = label_box_pad

        category = region.get("category")
        if isinstance(category, str) and category:
            normalized["category"] = category

        status = region.get("status")
        if isinstance(status, str) and status:
            normalized["status"] = status

        sigma = coerce_float(region.get("sigma"), default=None, require_finite=True)
        if sigma is not None:
            normalized["sigma"] = sigma

        return normalized

    @staticmethod
    def _required_float(payload: Mapping[str, object], field: str) -> float:
        """Return a required finite float field from an internal overlay payload."""
        if field not in payload:
            msg = f"Overlay payload missing required field: {field}"
            raise KeyError(msg)
        value = payload[field]
        if isinstance(value, bool):
            msg = f"Overlay payload field '{field}' must be numeric."
            raise TypeError(msg)
        if not isinstance(value, int | float | str):
            msg = f"Overlay payload field '{field}' must be numeric."
            raise TypeError(msg)
        try:
            resolved = float(value)
        except (TypeError, ValueError):
            msg = f"Overlay payload field '{field}' must be numeric."
            raise ValueError(msg) from None
        if not math.isfinite(resolved):
            msg = f"Overlay payload field '{field}' must be finite."
            raise ValueError(msg)
        return resolved

    @staticmethod
    def _require_increasing_bounds(start: float, end: float, label: str) -> None:
        """Validate overlay bounds are increasing."""
        if start >= end:
            msg = f"{label} must be increasing."
            raise ValueError(msg)
