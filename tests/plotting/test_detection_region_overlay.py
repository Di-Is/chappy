"""Unit tests for detection region overlays."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from chappy.plotting.overlays.detection_regions import DetectionRegionOverlay


@dataclass
class _RegionArtist:
    edgecolor: str | None = None

    def set_edgecolor(self, color: str) -> None:
        self.edgecolor = color


@dataclass
class _RegionRenderer:
    regions: list[tuple[str, float, float, float]] = field(default_factory=list)
    cleared_prefixes: list[str] = field(default_factory=list)

    def add_region(
        self, name: str, x_min: float, x_max: float, style=None, label: str | None = None
    ) -> _RegionArtist:
        del label
        fill_alpha = style.fill_alpha if style is not None else 0.0
        self.regions.append((name, x_min, x_max, fill_alpha))
        return _RegionArtist()

    def remove_regions_with_prefix(self, prefix: str) -> None:
        self.cleared_prefixes.append(prefix)


@dataclass
class _Canvas:
    draw_idle_calls: int = 0

    def draw_idle(self) -> None:
        self.draw_idle_calls += 1


def test_detection_region_overlay_renders_valid_regions() -> None:
    """Valid payloads should render regions and request one redraw."""
    renderer = _RegionRenderer()
    canvas = _Canvas()
    overlay = DetectionRegionOverlay(renderer=renderer, canvas=canvas, prefix="detect_")

    overlay.set_regions(
        [
            {"lambda_start": 1000.0, "lambda_end": 1010.0},
            {"lambda_start": 1020.0, "lambda_end": 1030.0, "alpha": 0.3},
        ]
    )

    assert renderer.cleared_prefixes == ["detect_"]
    assert renderer.regions == [
        ("detect_1", 1000.0, 1010.0, 0.18),
        ("detect_2", 1020.0, 1030.0, 0.3),
    ]
    assert canvas.draw_idle_calls == 1


@pytest.mark.parametrize(
    "payload, match",
    [
        ([{"lambda_start": 1000.0}], "requires both"),
        ([{"lambda_start": 1000.0, "lambda_end": 990.0}], "lambda_start < lambda_end"),
        ([{"lambda_start": 1000.0, "lambda_end": 1010.0, "alpha": 2.0}], "between 0.0 and 1.0"),
    ],
)
def test_detection_region_overlay_rejects_invalid_payload(
    payload: list[dict[str, object]], match: str
) -> None:
    """Invalid detection payloads should fail before drawing."""
    overlay = DetectionRegionOverlay(
        renderer=_RegionRenderer(), canvas=_Canvas(), prefix="detect_"
    )

    with pytest.raises(ValueError, match=match):
        overlay.set_regions(payload)
