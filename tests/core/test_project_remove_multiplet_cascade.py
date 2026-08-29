"""Tests for SpectroscopyProject.remove_absorption_lines_with_multiplet method."""

from __future__ import annotations

import pytest

from chappy.core.absorption.models import AbsorptionLine, AbsorptionRegion
from chappy.core.spectroscopy_project import SpectroscopyProject


def _make_line(
    line_id: str,
    *,
    center_z: float = 1.0,
    rest_wavelength: float = 1215.67,
    species: str = "H I",
    region_id: str | None = None,
    multiplet_ids: list[str] | None = None,
) -> AbsorptionLine:
    """Create a minimal AbsorptionLine for testing."""
    return AbsorptionLine(
        line_id=line_id,
        species=species,
        rest_wavelength=rest_wavelength,
        center_z=center_z,
        window_kms=150.0,
        multiplet_label="",
        transition_name=f"{species} {rest_wavelength:.1f}",
        oscillator_strength=0.1,
        gamma_value=1e8,
        region_id=region_id,
        multiplet_ids=multiplet_ids if multiplet_ids is not None else [],
    )


def _make_region(region_id: str, line_ids: list[str]) -> AbsorptionRegion:
    """Create a minimal AbsorptionRegion for testing."""
    return AbsorptionRegion(region_id=region_id, line_ids=line_ids)


class TestRemoveAbsorptionLinesWithMultiplet:
    """Tests for remove_absorption_lines_with_multiplet method."""

    def test_remove_single_line_without_multiplet(self) -> None:
        """Single line without multiplet should be removed alone."""
        project = SpectroscopyProject()

        line = _make_line("line1", region_id="region_1", multiplet_ids=[])
        region = _make_region("region_1", ["line1"])

        project.absorption_lines["line1"] = line
        project.absorption_regions["region_1"] = region

        removed = project.remove_absorption_lines_with_multiplet(["line1"])

        assert removed == 1
        assert "line1" not in project.absorption_lines

    def test_remove_doublet_from_primary_id(self) -> None:
        """Removing primary ID should cascade to related multiplet lines."""
        project = SpectroscopyProject()

        line1 = _make_line(
            "mg2_2796",
            center_z=1.5,
            rest_wavelength=2796.35,
            species="Mg II",
            region_id="region_1",
            multiplet_ids=["mg2_2803"],
        )
        line2 = _make_line(
            "mg2_2803",
            center_z=1.5,
            rest_wavelength=2803.53,
            species="Mg II",
            region_id="region_1",
            multiplet_ids=["mg2_2796"],
        )
        region = _make_region("region_1", ["mg2_2796", "mg2_2803"])

        project.absorption_lines["mg2_2796"] = line1
        project.absorption_lines["mg2_2803"] = line2
        project.absorption_regions["region_1"] = region

        # Remove only primary ID, should cascade to secondary
        removed = project.remove_absorption_lines_with_multiplet(["mg2_2796"])

        assert removed == 2
        assert "mg2_2796" not in project.absorption_lines
        assert "mg2_2803" not in project.absorption_lines

    def test_remove_doublet_from_secondary_id(self) -> None:
        """Removing secondary ID should also cascade to primary."""
        project = SpectroscopyProject()

        line1 = _make_line(
            "mg2_2796",
            center_z=1.5,
            rest_wavelength=2796.35,
            species="Mg II",
            region_id="region_1",
            multiplet_ids=["mg2_2803"],
        )
        line2 = _make_line(
            "mg2_2803",
            center_z=1.5,
            rest_wavelength=2803.53,
            species="Mg II",
            region_id="region_1",
            multiplet_ids=["mg2_2796"],
        )
        region = _make_region("region_1", ["mg2_2796", "mg2_2803"])

        project.absorption_lines["mg2_2796"] = line1
        project.absorption_lines["mg2_2803"] = line2
        project.absorption_regions["region_1"] = region

        # Remove secondary ID, should cascade to primary
        removed = project.remove_absorption_lines_with_multiplet(["mg2_2803"])

        assert removed == 2
        assert "mg2_2796" not in project.absorption_lines
        assert "mg2_2803" not in project.absorption_lines

    def test_remove_triplet(self) -> None:
        """Removing any line in triplet should cascade to all."""
        project = SpectroscopyProject()

        line1 = _make_line("line_a", multiplet_ids=["line_b", "line_c"], region_id="r1")
        line2 = _make_line("line_b", multiplet_ids=["line_a", "line_c"], region_id="r1")
        line3 = _make_line("line_c", multiplet_ids=["line_a", "line_b"], region_id="r1")
        region = _make_region("r1", ["line_a", "line_b", "line_c"])

        project.absorption_lines["line_a"] = line1
        project.absorption_lines["line_b"] = line2
        project.absorption_lines["line_c"] = line3
        project.absorption_regions["r1"] = region

        removed = project.remove_absorption_lines_with_multiplet(["line_b"])

        assert removed == 3
        assert "line_a" not in project.absorption_lines
        assert "line_b" not in project.absorption_lines
        assert "line_c" not in project.absorption_lines

    def test_remove_asymmetric_multiplet(self) -> None:
        """Asymmetric references should still cascade (Risk-7)."""
        project = SpectroscopyProject()

        # line1 references line2, but line2 does NOT reference line1
        line1 = _make_line("line1", region_id="r1", multiplet_ids=["line2"])
        line2 = _make_line(
            "line2",
            region_id="r1",
            multiplet_ids=[],  # No back-reference
        )
        region = _make_region("r1", ["line1", "line2"])

        project.absorption_lines["line1"] = line1
        project.absorption_lines["line2"] = line2
        project.absorption_regions["r1"] = region

        # Remove line1, should cascade to line2 via forward reference
        removed = project.remove_absorption_lines_with_multiplet(["line1"])

        assert removed == 2
        assert "line1" not in project.absorption_lines
        assert "line2" not in project.absorption_lines

    def test_remove_nonexistent_line_fails_fast(self) -> None:
        """Removing a non-empty unknown line selection fails fast."""
        project = SpectroscopyProject()

        with pytest.raises(ValueError, match="Absorption lines not found"):
            project.remove_absorption_lines_with_multiplet(["nonexistent"])

    def test_remove_empty_list(self) -> None:
        """Empty list should return 0."""
        project = SpectroscopyProject()

        removed = project.remove_absorption_lines_with_multiplet([])

        assert removed == 0

    def test_remove_multiple_independent_lines(self) -> None:
        """Multiple independent lines should all be removed."""
        project = SpectroscopyProject()

        line1 = _make_line("line1", region_id="r1", multiplet_ids=[])
        line2 = _make_line("line2", region_id="r1", multiplet_ids=[])
        region = _make_region("r1", ["line1", "line2"])

        project.absorption_lines["line1"] = line1
        project.absorption_lines["line2"] = line2
        project.absorption_regions["r1"] = region

        removed = project.remove_absorption_lines_with_multiplet(["line1", "line2"])

        assert removed == 2
        assert "line1" not in project.absorption_lines
        assert "line2" not in project.absorption_lines
