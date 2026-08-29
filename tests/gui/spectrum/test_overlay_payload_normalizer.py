"""Tests for SpectrumOverlayPayloadNormalizer (Qt-independent)."""

from __future__ import annotations

import pytest

from chappy.gui.spectrum.overlay_payload_normalizer import SpectrumOverlayPayloadNormalizer

Normalizer = SpectrumOverlayPayloadNormalizer


def test_identify_preview_none_returns_none() -> None:
    """A ``None`` payload normalizes to ``None``."""
    assert Normalizer.normalize_identify_preview(None) is None


def test_identify_preview_non_mapping_returns_none() -> None:
    """A non-mapping payload is an internal contract violation."""
    with pytest.raises(TypeError, match="mapping"):
        Normalizer.normalize_identify_preview([1, 2, 3])  # type: ignore[arg-type]


def test_identify_preview_entry_missing_bounds_fails_fast() -> None:
    """Entries missing lambda_min/lambda_max fail fast."""
    payload = {"entries": ({"lambda_min": 1000.0},)}

    with pytest.raises(KeyError, match="lambda_max"):
        Normalizer.normalize_identify_preview(payload)


def test_identify_preview_entry_normalizes_bounds() -> None:
    """Entries with explicit bounds are preserved."""
    payload = {"entries": ({"lambda_min": 1200.0, "lambda_max": 1210.0, "color": "#fff"},)}

    result = Normalizer.normalize_identify_preview(payload)
    assert result is not None
    entries = result["entries"]
    assert len(entries) == 1
    assert entries[0]["lambda_min"] == 1200.0
    assert entries[0]["lambda_max"] == 1210.0
    assert entries[0]["color"] == "#fff"


def test_identify_preview_invalid_bounds_fails_fast() -> None:
    """Malformed identify preview bounds fail fast."""
    with pytest.raises(ValueError, match="lambda_min"):
        Normalizer.normalize_identify_preview(
            {"entries": ({"lambda_min": "bad", "lambda_max": 1210.0},)}
        )

    with pytest.raises(TypeError, match="lambda_min"):
        Normalizer.normalize_identify_preview(
            {"entries": ({"lambda_min": True, "lambda_max": 1210.0},)}
        )

    with pytest.raises(ValueError, match="increasing"):
        Normalizer.normalize_identify_preview(
            {"entries": ({"lambda_min": 1210.0, "lambda_max": 1200.0},)}
        )


def test_identify_preview_empty_entries_yields_empty_payload() -> None:
    """No valid entries yields a payload without an ``entries`` key."""
    result = Normalizer.normalize_identify_preview({"entries": ()})

    assert result == {}


def test_identify_preview_preserves_nonempty_hint_text() -> None:
    """Typed transient guidance survives normalization for overlay rendering."""
    result = Normalizer.normalize_identify_preview(
        {"entries": ({"lambda_min": 1200.0, "lambda_max": 1210.0},), "hint_text": "Shift hint"}
    )

    assert result is not None
    assert result["hint_text"] == "Shift hint"


def test_identify_preview_normalizes_optional_fields() -> None:
    """Optional numeric fields are converted while bool fields stay typed."""
    payload = {
        "entries": (
            {
                "lambda_min": "1200.0",
                "lambda_max": "1210.0",
                "is_primary": True,
                "line_width": "1.5",
            },
        )
    }

    result = Normalizer.normalize_identify_preview(payload)

    assert result is not None
    entry = result["entries"][0]
    assert entry["lambda_min"] == 1200.0
    assert entry["is_primary"] is True
    assert entry["line_width"] == 1.5


def test_identify_preview_ignores_non_bool_primary_flag() -> None:
    """String bool values are not accepted for internal preview flags."""
    payload = {"entries": ({"lambda_min": 1200.0, "lambda_max": 1210.0, "is_primary": "true"},)}

    result = Normalizer.normalize_identify_preview(payload)

    assert result is not None
    assert "is_primary" not in result["entries"][0]


def test_absorption_regions_none_or_empty() -> None:
    """Empty or ``None`` region input yields an empty list."""
    assert Normalizer.normalize_absorption_regions(None) == []
    assert Normalizer.normalize_absorption_regions([]) == []


def test_absorption_region_missing_bounds_fails_fast() -> None:
    """Regions missing lambda_start/lambda_end fail fast."""
    regions = [{"lambda_start": 1000.0}]

    with pytest.raises(KeyError, match="lambda_end"):
        Normalizer.normalize_absorption_regions(regions)


def test_absorption_region_normalizes_bounds() -> None:
    """Regions with explicit bounds are preserved."""
    regions = [{"lambda_start": 1200.0, "lambda_end": 1250.0, "id": "r1"}]

    result = Normalizer.normalize_absorption_regions(regions)
    assert len(result) == 1
    assert result[0]["id"] == "r1"
    assert result[0]["lambda_start"] == 1200.0
    assert result[0]["lambda_end"] == 1250.0


def test_absorption_region_invalid_bounds_fails_fast() -> None:
    """Malformed absorption region bounds fail fast."""
    with pytest.raises(ValueError, match="lambda_start"):
        Normalizer.normalize_absorption_regions([{"lambda_start": "bad", "lambda_end": 1250.0}])

    with pytest.raises(TypeError, match="lambda_start"):
        Normalizer.normalize_absorption_regions([{"lambda_start": True, "lambda_end": 1250.0}])

    with pytest.raises(ValueError, match="increasing"):
        Normalizer.normalize_absorption_regions([{"lambda_start": 1250.0, "lambda_end": 1200.0}])


def test_absorption_region_label_y_and_box_alpha_clamped() -> None:
    """label_y and label_box_alpha are clamped to the [0, 1] range."""
    regions = [
        {"lambda_start": 1200.0, "lambda_end": 1250.0, "label_y": 1.5, "label_box_alpha": -0.2}
    ]

    result = Normalizer.normalize_absorption_regions(regions)

    assert result[0]["label_y"] == 1.0
    assert result[0]["label_box_alpha"] == 0.0


def test_absorption_region_label_weight_fallback() -> None:
    """label_weight is used as a fallback for label_font_weight."""
    regions = [{"lambda_start": 1200.0, "lambda_end": 1250.0, "label_weight": "bold"}]

    result = Normalizer.normalize_absorption_regions(regions)

    assert result[0]["label_font_weight"] == "bold"


def test_absorption_region_requires_typed_zorder_and_label_visibility() -> None:
    """Internal int and bool flags are accepted without string coercion."""
    regions = [
        {"lambda_start": 1200.0, "lambda_end": 1250.0, "zorder": -6, "label_visible": True},
        {"lambda_start": 1300.0, "lambda_end": 1350.0, "zorder": "-6", "label_visible": "true"},
    ]

    result = Normalizer.normalize_absorption_regions(regions)

    assert result[0]["zorder"] == -6
    assert result[0]["label_visible"] is True
    assert "zorder" not in result[1]
    assert "label_visible" not in result[1]


def test_absorption_region_font_weight_takes_priority() -> None:
    """An explicit label_font_weight is preferred over label_weight."""
    regions = [
        {
            "lambda_start": 1200.0,
            "lambda_end": 1250.0,
            "label_font_weight": "normal",
            "label_weight": "bold",
        }
    ]

    result = Normalizer.normalize_absorption_regions(regions)

    assert result[0]["label_font_weight"] == "normal"
