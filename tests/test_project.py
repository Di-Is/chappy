"""Tests for project management functionality."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from chappy.application.project_io_usecase import ProjectIOUseCase
from chappy.core.components.absorber import AbsorberComponent
from chappy.core.components.continuum import ContinuumComponent
from chappy.core.spectroscopy_project import SpectroscopyProject
from chappy.core.resolution import RESOLUTION_CONSTRAINTS
from chappy.infrastructure.project_io_factory import create_default_project_io_usecase
from tests.helpers.simple_fits_builder import write_primary_image


P2_PROJECT_REQUIRE_API_REASON = "P2-PROJECT-REQUIRE-API pending"


def _seed_absorption_line(project: SpectroscopyProject) -> str:
    """Create and return one absorption line identifier for contract tests."""
    line = project.add_absorption_line(
        species="C IV",
        rest_wavelength=1548.195,
        center_z=0.5,
        window_kms=150.0,
        multiplet_label="",
        transition_name="C IV 1548",
        oscillator_strength=0.19,
        gamma_value=2.65e8,
        lambda_range=(1500.0, 1600.0),
    )
    return line.line_id


def _seed_region(project: SpectroscopyProject, *, line_id: str) -> str:
    """Create and return a temporary region containing the provided line."""
    region = project.create_region_with_lines([line_id])
    return region.region_id


@pytest.fixture
def project_io() -> ProjectIOUseCase:
    """Create the default project I/O use case."""
    return create_default_project_io_usecase()


@pytest.fixture
def sample_fits_file(tmp_path: Path) -> str:
    """Create a sample FITS file for testing."""
    fits_path = tmp_path / "sample.fits"
    wavelength = np.linspace(4000, 5000, 1000)
    rng = np.random.default_rng(42)
    flux = np.ones_like(wavelength) + 0.1 * rng.standard_normal(len(wavelength))

    write_primary_image(
        fits_path,
        flux,
        crval1=4000.0,
        cdelt1=1.0,
        crpix1=1,
        extra_cards=[
            ("OBJECT", "Test Star"),
            ("OBSERVER", "Test Observer"),
            ("EXPTIME", 3600.0),
            ("INSTRUME", "Test Spectrograph"),
        ],
    )

    return str(fits_path)


@pytest.fixture
def sample_error_fits_file(tmp_path: Path) -> str:
    """Create a sample FITS file with error data for testing."""
    fits_path = tmp_path / "sample_error.fits"
    rng = np.random.default_rng(42)
    error = np.ones(1000) * 0.05
    for idx in [100, 200, 300, 400, 500]:
        error[idx] = 10.0
    error += 0.01 * rng.standard_normal(len(error))

    write_primary_image(
        fits_path,
        error,
        crval1=4000.0,
        cdelt1=1.0,
        crpix1=1,
        extra_cards=[
            ("OBJECT", "Test Star Error"),
            ("OBSERVER", "Test Observer"),
            ("EXPTIME", 3600.0),
            ("INSTRUME", "Test Spectrograph"),
        ],
    )

    return str(fits_path)


class TestDProject:
    """Test suite for SpectroscopyProject class."""

    def test_basic_initialization(self) -> None:
        """Test basic project initialization."""
        project = SpectroscopyProject(name="Test Project")

        assert project.name == "Test Project"
        assert project.spectrum_filename is None
        assert len(project.model.components) == 0
        assert project.metadata["version"] == "2.0"
        assert project.metadata["created_by"] == "chappy"

    def test_from_fits_creation(self, project_io: ProjectIOUseCase, sample_fits_file: str) -> None:
        """Test project creation from FITS file."""
        project = project_io.create_from_fits(sample_fits_file, name="FITS Test")

        assert project.name == "FITS Test"
        assert project.spectrum_filename == sample_fits_file
        assert project.model.observed_spectrum is not None
        assert project.model.observed_spectrum.n_pixels == 1000

        assert "object_name" in project.metadata
        assert project.metadata["object_name"] == "Test Star"
        assert "observer" in project.metadata
        assert project.metadata["observer"] == "Test Observer"

    def test_from_fits_auto_name(
        self, project_io: ProjectIOUseCase, sample_fits_file: str
    ) -> None:
        """Test automatic name generation from FITS filename."""
        project = project_io.create_from_fits(sample_fits_file)

        expected_name = Path(sample_fits_file).stem
        assert project.name == expected_name

    def test_initialize_continuum(
        self, project_io: ProjectIOUseCase, sample_fits_file: str
    ) -> None:
        """Test explicit history-free continuum project initialization."""
        project = project_io.create_from_fits(sample_fits_file)

        initial_components = len(project.model.components)
        initialized = project.initialize_continuum(name="Linear")

        assert len(project.model.components) == initial_components + 1

        continuums = [
            c
            for c in project.model.components
            if isinstance(c, ContinuumComponent) and c.name == "Linear"
        ]
        assert len(continuums) == 1
        continuum = continuums[0]
        assert initialized is continuum
        assert continuum.name == "Linear"

        project.initialize_continuum()

        assert len(project.model.components) == initial_components + 2
        continuum_names = [
            c.name for c in project.model.components if isinstance(c, ContinuumComponent)
        ]
        assert "Continuum 3" in continuum_names

    def test_remove_unknown_absorber_component_fails_fast(self) -> None:
        """Removing an unknown absorber component is an invariant violation."""
        project = SpectroscopyProject(name="Test Project")
        component = AbsorberComponent(name="Detached")

        with pytest.raises(ValueError, match="Absorber component not found"):
            project.remove_absorber_component(component)

    def test_remove_unknown_absorber_component_by_id_fails_fast(self) -> None:
        """Removing an unknown absorber component ID is an invariant violation."""
        project = SpectroscopyProject(name="Test Project")

        with pytest.raises(ValueError, match="Absorber component not found"):
            project.remove_absorber_component_by_id("missing-component")

    def test_mutating_unknown_absorption_line_fails_fast(self) -> None:
        """Core line mutation APIs fail fast for unknown line IDs."""
        project = SpectroscopyProject(name="Test Project")

        with pytest.raises(ValueError, match="Absorption line not found"):
            project.assign_line_to_region("missing-line", None)

        with pytest.raises(ValueError, match="Absorption line not found"):
            project.remove_absorption_line("missing-line")

    def test_mutating_unknown_absorption_region_fails_fast(self) -> None:
        """Core region mutation APIs fail fast for unknown region IDs."""
        project = SpectroscopyProject(name="Test Project")

        with pytest.raises(ValueError, match="Absorption region not found"):
            project.update_region_analysis_range("missing-region")

        with pytest.raises(ValueError, match="Absorption region not found"):
            project.remove_absorption_region("missing-region")

    def test_move_unknown_absorption_lines_fails_fast(self) -> None:
        """Moving a non-empty unknown line selection is an invariant violation."""
        project = SpectroscopyProject(name="Test Project")

        with pytest.raises(ValueError, match="Absorption lines not found"):
            project.move_absorption_lines(["missing-line"], target_region_id=None)

    def test_merge_unknown_absorption_regions_fails_fast(self) -> None:
        """Merging unknown regions is an invariant violation."""
        project = SpectroscopyProject(name="Test Project")

        with pytest.raises(ValueError, match="Absorption regions not found"):
            project.merge_absorption_regions(["missing-a", "missing-b"])

    def test_project_with_error_file(
        self, project_io: ProjectIOUseCase, sample_fits_file: str, sample_error_fits_file: str
    ) -> None:
        """Test loading project with associated error file."""
        project = project_io.create_from_fits(sample_fits_file, error_path=sample_error_fits_file)

        assert project.model.observed_spectrum is not None
        assert project.model.observed_spectrum.error is not None
        assert (
            project.model.observed_spectrum.error.shape
            == project.model.observed_spectrum.flux.shape
        )


class TestDProjectContractLookupSemantics:
    """Contract tests for future SpectroscopyProject lookup APIs."""

    @pytest.mark.xfail(
        condition=not hasattr(SpectroscopyProject, "find_absorber_component"),
        reason=P2_PROJECT_REQUIRE_API_REASON,
        strict=True,
    )
    def test_find_absorber_component_missing_returns_none(self) -> None:
        """Missing absorber-component lookup must return None."""
        project = SpectroscopyProject(name="Test Project")

        assert project.find_absorber_component("missing-component") is None

    @pytest.mark.xfail(
        condition=not hasattr(SpectroscopyProject, "require_absorber_component"),
        reason=P2_PROJECT_REQUIRE_API_REASON,
        strict=True,
    )
    def test_require_absorber_component_missing_or_present(self) -> None:
        """Missing absorber-component lookup must raise; present lookup must return the component."""
        project = SpectroscopyProject(name="Test Project")
        component = AbsorberComponent(
            name="H I", wavelength=1215.67, oscillator_strength=0.4164, gamma=6.265e8
        )
        project.model.add_component(component)
        absorber = project.model.components[0]

        assert project.require_absorber_component(absorber.id) is absorber
        assert project.find_absorber_component(absorber.id) is absorber

        with pytest.raises(ValueError):
            project.require_absorber_component("missing-component")

    @pytest.mark.xfail(
        condition=not hasattr(SpectroscopyProject, "find_absorption_line"),
        reason=P2_PROJECT_REQUIRE_API_REASON,
        strict=True,
    )
    def test_find_absorption_line_missing_returns_none(self) -> None:
        """Missing line lookup must return None."""
        project = SpectroscopyProject(name="Test Project")
        line_id = _seed_absorption_line(project)
        assert project.find_absorption_line(line_id) is not None

        assert project.find_absorption_line("missing-line") is None

    @pytest.mark.xfail(
        condition=not hasattr(SpectroscopyProject, "require_absorption_line"),
        reason=P2_PROJECT_REQUIRE_API_REASON,
        strict=True,
    )
    def test_require_absorption_line_missing_or_present(self) -> None:
        """Missing line lookup must raise; present lookup must return the line."""
        project = SpectroscopyProject(name="Test Project")
        line_id = _seed_absorption_line(project)
        line = project.find_absorption_line(line_id)

        assert line is not None
        assert project.require_absorption_line(line_id) is line
        assert project.find_absorption_line(line_id) is line

        with pytest.raises(ValueError):
            project.require_absorption_line("missing-line")

    @pytest.mark.xfail(
        condition=not hasattr(SpectroscopyProject, "find_absorption_region"),
        reason=P2_PROJECT_REQUIRE_API_REASON,
        strict=True,
    )
    def test_find_absorption_region_missing_returns_none(self) -> None:
        """Missing region lookup must return None."""
        project = SpectroscopyProject(name="Test Project")
        line_id = _seed_absorption_line(project)
        region_id = _seed_region(project, line_id=line_id)
        assert project.find_absorption_region(region_id) is not None

        assert project.find_absorption_region("missing-region") is None

    @pytest.mark.xfail(
        condition=not hasattr(SpectroscopyProject, "require_absorption_region"),
        reason=P2_PROJECT_REQUIRE_API_REASON,
        strict=True,
    )
    def test_require_absorption_region_missing_or_present(self) -> None:
        """Missing region lookup must raise; present lookup must return the region."""
        project = SpectroscopyProject(name="Test Project")
        line_id = _seed_absorption_line(project)
        region_id = _seed_region(project, line_id=line_id)
        region = project.find_absorption_region(region_id)

        assert region is not None
        assert project.require_absorption_region(region_id) is region

        with pytest.raises(ValueError):
            project.require_absorption_region("missing-region")

    @pytest.mark.xfail(
        condition=not hasattr(SpectroscopyProject, "find_lines_for_region"),
        reason=P2_PROJECT_REQUIRE_API_REASON,
        strict=True,
    )
    def test_find_lines_for_region_missing_returns_none(self) -> None:
        """Missing region lines lookup must return None."""
        project = SpectroscopyProject(name="Test Project")
        line_id = _seed_absorption_line(project)
        region_id = _seed_region(project, line_id=line_id)
        assert project.find_lines_for_region(region_id) is not None

        assert project.find_lines_for_region("missing-region") is None

    def test_require_lines_for_region_missing_or_present(self) -> None:
        """Missing region must raise via require_absorption_region; present lookup returns lines."""
        project = SpectroscopyProject(name="Test Project")
        line_id = _seed_absorption_line(project)
        region_id = _seed_region(project, line_id=line_id)
        region_lines = project.find_lines_for_region(region_id)
        assert region_lines is not None

        assert project.find_lines_for_region(region_id) == region_lines

        with pytest.raises(ValueError):
            project.require_absorption_region("missing-region")

    def test_mutating_missing_ids_fail_fast(self) -> None:
        """Mutation APIs must fail fast when required state entries are missing."""
        project = SpectroscopyProject(name="Test Project")

        with pytest.raises(ValueError, match="Absorption line not found"):
            project.assign_line_to_region("missing-line", None)

        with pytest.raises(ValueError, match="Absorption region not found"):
            project.update_region_analysis_range("missing-region")

        with pytest.raises(ValueError, match="Absorption lines not found"):
            project.move_absorption_lines(["missing-line"], target_region_id=None)

        with pytest.raises(ValueError, match="Absorption regions not found"):
            project.merge_absorption_regions(["missing-a", "missing-b"])

        with pytest.raises(ValueError, match="Absorption lines not found"):
            project.remove_absorption_lines_with_multiplet(["missing-line"])
