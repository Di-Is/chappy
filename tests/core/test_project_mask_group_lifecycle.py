"""Tests for mask lifecycle tied to absorption region operations."""

from __future__ import annotations

import numpy as np
import pytest

from chappy.core.masking import MaskDefinition
from chappy.core.spectroscopy_project import SpectroscopyProject
from chappy.core.spectrum import Spectrum


@pytest.fixture
def project_with_spectrum() -> SpectroscopyProject:
    """Create a project with a minimal observed spectrum."""
    project = SpectroscopyProject(name="Test Project")
    wavelength = np.linspace(1000.0, 2000.0, 100, dtype=float)
    flux = np.ones(100, dtype=float)
    error = np.full(100, 0.05, dtype=float)
    project.model.set_observed_spectrum(Spectrum(wavelength=wavelength, flux=flux, error=error))
    return project


def _add_test_line(project: SpectroscopyProject, *, center_z: float = 0.5) -> str:
    """Add a minimal absorption line and return its identifier.

    Args:
        project: Target project.
        center_z: Line redshift.

    Returns:
        Created absorption line identifier.
    """
    line = project.add_absorption_line(
        species="C IV",
        rest_wavelength=1548.195,
        center_z=center_z,
        window_kms=150.0,
        multiplet_label="",
        transition_name="C IV 1548",
        oscillator_strength=0.19,
        gamma_value=2.65e8,
        lambda_range=(1500.0, 1600.0),
    )
    return line.line_id


class TestProjectMaskGroupLifecycle:
    """Tests for group deletion/merge propagating to masks."""

    def test_region_deletion_removes_group_masks(
        self, project_with_spectrum: SpectroscopyProject
    ) -> None:
        """Deleting a region removes masks belonging to that group."""
        project = project_with_spectrum

        line_id = _add_test_line(project)
        region = project.create_region_with_lines([line_id])

        kept_mask = project.model.add_mask_definition(
            MaskDefinition.from_range(1200.0, 1210.0).with_group_id("other-group")
        )
        deleted_mask = project.model.add_mask_definition(
            MaskDefinition.from_range(1505.0, 1510.0).with_group_id(region.region_id)
        )

        project.remove_absorption_region(region.region_id, delete_models=False)

        assert project.model.find_mask(deleted_mask.identifier) is None
        assert project.model.find_mask(kept_mask.identifier) is not None

    def test_region_merge_moves_group_masks(
        self, project_with_spectrum: SpectroscopyProject
    ) -> None:
        """Merging regions moves masks into the surviving region."""
        project = project_with_spectrum

        primary_line_id = _add_test_line(project, center_z=0.5)
        secondary_line_id = _add_test_line(project, center_z=0.6)

        primary_region = project.create_region_with_lines([primary_line_id])
        secondary_region = project.create_region_with_lines([secondary_line_id])

        secondary_mask = project.model.add_mask_definition(
            MaskDefinition.from_range(1515.0, 1520.0).with_group_id(secondary_region.region_id)
        )

        merged = project.merge_absorption_regions(
            [primary_region.region_id, secondary_region.region_id]
        )
        assert merged is not None
        assert secondary_region.region_id not in project.absorption_regions

        updated_mask = project.model.find_mask(secondary_mask.identifier)
        assert updated_mask is not None
        assert updated_mask.group_id == primary_region.region_id

    def test_line_move_deletes_empty_region_masks(
        self, project_with_spectrum: SpectroscopyProject
    ) -> None:
        """Moving the last line out of a region deletes masks for the emptied region."""
        project = project_with_spectrum

        line_id = _add_test_line(project)
        region = project.create_region_with_lines([line_id])

        mask = project.model.add_mask_definition(
            MaskDefinition.from_range(1501.0, 1503.0).with_group_id(region.region_id)
        )

        destination_id = project.move_absorption_lines([line_id], target_region_id=None)
        assert destination_id is not None

        assert region.region_id not in project.absorption_regions
        assert project.model.find_mask(mask.identifier) is None
