"""Tests for SpectroscopyProject region line lookup methods."""

from __future__ import annotations

import pytest

from chappy.core.absorption.models import AbsorptionLine, AbsorptionRegion
from chappy.core.spectroscopy_project import SpectroscopyProject


def _make_line(
    line_id: str,
    *,
    rest_wavelength: float = 1215.67,
    species: str = "H I",
    center_z: float = 1.5,
    region_id: str | None = None,
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
        multiplet_ids=[],
        model_ids=[],
    )


def _make_region(region_id: str, line_ids: list[str]) -> AbsorptionRegion:
    """Create a minimal AbsorptionRegion for testing."""
    return AbsorptionRegion(region_id=region_id, line_ids=line_ids)


@pytest.fixture
def project_with_mg2_region() -> SpectroscopyProject:
    """Create a SpectroscopyProject with Mg II doublet region."""
    project = SpectroscopyProject()

    line_2796 = _make_line(
        "mg2_2796", rest_wavelength=2796.35, species="Mg II", region_id="region_1"
    )
    line_2803 = _make_line(
        "mg2_2803", rest_wavelength=2803.53, species="Mg II", region_id="region_1"
    )
    region = _make_region("region_1", ["mg2_2796", "mg2_2803"])

    project.absorption_lines["mg2_2796"] = line_2796
    project.absorption_lines["mg2_2803"] = line_2803
    project.absorption_regions[region.region_id] = region

    return project


@pytest.fixture
def project_with_orphan_line_id() -> SpectroscopyProject:
    """Create a SpectroscopyProject with a region referencing a non-existent line."""
    project = SpectroscopyProject()

    line_2796 = _make_line(
        "mg2_2796", rest_wavelength=2796.35, species="Mg II", region_id="region_1"
    )
    # Region references mg2_2803 but it doesn't exist
    region = _make_region("region_1", ["mg2_2796", "mg2_2803"])

    project.absorption_lines["mg2_2796"] = line_2796
    project.absorption_regions[region.region_id] = region

    return project


class TestFindLinesForRegion:
    """Tests for SpectroscopyProject.find_lines_for_region."""

    def test_returns_lines_for_valid_region(
        self, project_with_mg2_region: SpectroscopyProject
    ) -> None:
        """region_idに対応するラインのリストを返す."""
        lines = project_with_mg2_region.find_lines_for_region("region_1")

        assert lines is not None
        assert len(lines) == 2
        line_ids = [line.line_id for line in lines]
        assert "mg2_2796" in line_ids
        assert "mg2_2803" in line_ids

    def test_returns_empty_for_unknown_region(
        self, project_with_mg2_region: SpectroscopyProject
    ) -> None:
        """存在しないregion_idでは空リストを返す."""
        lines = project_with_mg2_region.find_lines_for_region("unknown_region")

        assert lines is None

    def test_skips_missing_lines(self, project_with_orphan_line_id: SpectroscopyProject) -> None:
        """line_idsに存在しないline_idがあればスキップする."""
        lines = project_with_orphan_line_id.find_lines_for_region("region_1")

        assert lines is not None
        assert len(lines) == 1
        assert lines[0].line_id == "mg2_2796"

    def test_returns_empty_for_empty_region(self) -> None:
        """空のline_idsを持つリージョンでは空リストを返す."""
        project = SpectroscopyProject()
        region = _make_region("empty_region", [])
        project.absorption_regions[region.region_id] = region

        lines = project.find_lines_for_region("empty_region")

        assert lines == []
