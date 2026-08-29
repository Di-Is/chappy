"""Resolution-state wiring tests for the identify detection workflow."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from chappy.application.identify import (
    DetectCandidateLinesRequest,
    DetectCandidateLinesResult,
    DetectCandidateLinesUseCase,
)
from chappy.application.project_mapper import create_project_from_spectrum
from chappy.core.components.continuum import ContinuumComponent
from chappy.core.identify_state import IdentifySessionState
from chappy.core.spectroscopy_project import SpectroscopyProject
from chappy.core.spectrum import Spectrum
from chappy.gui.modes.identify.workflows.detection_workflow import (
    IdentifyDetectionMessages,
    IdentifyDetectionWorkflow,
    IdentifyDetectionWorkflowPorts,
)
from chappy.infrastructure.fits_reader import FitsReader


class _CapturingDetectionUseCase(DetectCandidateLinesUseCase):
    """Capture requests while returning an empty successful result."""

    def __init__(self) -> None:
        self.requests: list[DetectCandidateLinesRequest] = []

    def detect(self, request: DetectCandidateLinesRequest) -> DetectCandidateLinesResult:
        self.requests.append(request)
        return DetectCandidateLinesResult(regions=())


def _project(*, resolution: float, enabled: bool) -> SpectroscopyProject:
    """Build the smallest project accepted by the detection workflow."""
    wavelength = np.linspace(1000.0, 1100.0, 120, dtype=float)
    spectrum = Spectrum(
        wavelength=wavelength, flux=np.ones_like(wavelength), error=np.full_like(wavelength, 0.05)
    )
    project = SpectroscopyProject()
    project.model.set_observed_spectrum(spectrum)
    continuum = ContinuumComponent()
    continuum.continuum_points = [(1000.0, 1.0), (1050.0, 1.0), (1100.0, 1.0)]
    project.model.add_component(continuum)
    project.set_resolution(resolution, enabled=enabled)
    return project


def _messages() -> IdentifyDetectionMessages:
    return IdentifyDetectionMessages(
        error_spectrum_required="error required",
        insufficient_data="insufficient data",
        no_continuum="continuum required",
        failed_template="failed: {reason}",
        unknown="unknown",
    )


def test_detection_uses_current_project_resolution_across_switches() -> None:
    """Every request takes resolution from the current project, never saved GUI settings."""
    first = _project(resolution=54_000.0, enabled=True)
    second = _project(resolution=36_000.0, enabled=False)
    current: list[SpectroscopyProject | None] = [first]
    usecase = _CapturingDetectionUseCase()
    workflow = IdentifyDetectionWorkflow(
        IdentifyDetectionWorkflowPorts(
            project_provider=lambda: current[0],
            session_provider=IdentifySessionState,
            sigma_threshold_provider=lambda: 50.0,
            status_callback=lambda _message: None,
            messages_provider=_messages,
        ),
        usecase,
    )

    assert workflow.compute_detection_regions() == []
    first_parameters = usecase.requests[-1].parameters
    assert first_parameters.resolution == 54_000.0
    assert first_parameters.resolution_enabled is True

    current[0] = second
    assert workflow.compute_detection_regions() == []
    second_parameters = usecase.requests[-1].parameters
    assert second_parameters.resolution == 36_000.0
    assert second_parameters.resolution_enabled is False

    current[0] = None
    request_count = len(usecase.requests)
    assert workflow.compute_detection_regions() == []
    assert len(usecase.requests) == request_count


def test_detection_parameters_without_project_disable_resolution() -> None:
    """The parameter builder represents a missing project without stale resolution."""
    workflow = IdentifyDetectionWorkflow(
        IdentifyDetectionWorkflowPorts(
            project_provider=lambda: None,
            session_provider=IdentifySessionState,
            sigma_threshold_provider=lambda: 50.0,
            status_callback=lambda _message: None,
            messages_provider=_messages,
        ),
        DetectCandidateLinesUseCase(),
    )

    parameters = workflow._build_detection_parameters(None)

    assert parameters.resolution is None
    assert parameters.resolution_enabled is False


def test_bundled_sample_detection_uses_project_resolution_at_tutorial_threshold() -> None:
    """The fresh tutorial sample exposes its known 4763 Å candidate at 50 σ."""
    repository_root = Path(__file__).parents[4]
    flux_spectrum = FitsReader.read_spectrum(
        str(repository_root / "sample_data" / "J033106-382404_f.fits")
    )
    error_spectrum = FitsReader.read_spectrum(
        str(repository_root / "sample_data" / "J033106-382404_e.fits")
    )
    project = create_project_from_spectrum(
        flux_spectrum, name="tutorial-sample", spectrum_filename="J033106-382404_f.fits"
    )
    observed_spectrum = project.model.observed_spectrum
    assert observed_spectrum is not None
    observed_spectrum.assign_error(error_spectrum.flux)
    project.set_resolution(54_000.0, enabled=True)
    threshold = [50.0]
    workflow = IdentifyDetectionWorkflow(
        IdentifyDetectionWorkflowPorts(
            project_provider=lambda: project,
            session_provider=IdentifySessionState,
            sigma_threshold_provider=lambda: threshold[0],
            status_callback=lambda _message: None,
            messages_provider=_messages,
        ),
        DetectCandidateLinesUseCase(),
    )

    regions_at_50 = workflow.compute_detection_regions()
    assert regions_at_50 is not None
    matching_at_50 = [
        region for region in regions_at_50 if region.lambda_start <= 4763.0 <= region.lambda_end
    ]
    assert len(matching_at_50) == 1
    assert matching_at_50[0].lambda_start == pytest.approx(4762.530529063918)
    assert matching_at_50[0].lambda_end == pytest.approx(4763.166012482901)

    threshold[0] = 100.0
    regions_at_100 = workflow.compute_detection_regions()
    assert regions_at_100 is not None
    assert not any(region.lambda_start <= 4763.0 <= region.lambda_end for region in regions_at_100)
