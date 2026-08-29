"""Tests for project I/O application use case boundaries."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pytest

from chappy.application.project_io_usecase import ProjectIOUseCase
from chappy.core.spectroscopy_project import SpectroscopyProject
from chappy.core.spectrum import Spectrum

if TYPE_CHECKING:
    from chappy.application.project_document import ProjectDocument


class _FakeSpectrumReader:
    """Spectrum reader test double for inspection delegation."""

    def __init__(self) -> None:
        self.validated_paths: list[str] = []
        self.info_paths: list[str] = []

    def read_spectrum(self, path: str) -> Spectrum:
        """Fail if a test unexpectedly requests a full spectrum read."""
        _ = path
        raise AssertionError("read_spectrum should not be called")

    def validate_spectrum(self, path: str) -> tuple[bool, list[str]]:
        """Record validation and return a deterministic result."""
        self.validated_paths.append(path)
        return False, ["missing wavelength"]

    def get_spectrum_info(self, path: str) -> dict[str, object]:
        """Record metadata inspection and return deterministic metadata."""
        self.info_paths.append(path)
        return {"primary_shape": [123]}


class _FakeProjectRepository:
    """Project repository test double unused by inspection tests."""

    def load(self, path: str) -> ProjectDocument:
        """Fail if a test unexpectedly loads a project."""
        _ = path
        raise AssertionError("load should not be called")

    def save(self, document: ProjectDocument, path: str) -> None:
        """Fail if a test unexpectedly saves a project."""
        _ = document, path
        raise AssertionError("save should not be called")


class _ErrorSpectrumReader:
    """Spectrum reader double returning a configured error spectrum."""

    def __init__(self, spectrum: Spectrum) -> None:
        self.spectrum = spectrum

    def read_spectrum(self, path: str) -> Spectrum:
        """Return the configured spectrum."""
        _ = path
        return self.spectrum

    def validate_spectrum(self, path: str) -> tuple[bool, list[str]]:
        """Return a deterministic validation result."""
        _ = path
        return True, []

    def get_spectrum_info(self, path: str) -> dict[str, object]:
        """Return deterministic metadata."""
        _ = path
        return {}


class _FailingErrorSpectrumReader(_ErrorSpectrumReader):
    """Spectrum reader double that raises while reading the error file."""

    def __init__(self, exc: Exception) -> None:
        """Initialize the configured read failure."""
        super().__init__(Spectrum(wavelength=np.array([1000.0]), flux=np.array([0.1])))
        self._exc = exc

    def read_spectrum(self, path: str) -> Spectrum:
        """Raise the configured exception."""
        _ = path
        raise self._exc


def _project_with_observed_spectrum() -> SpectroscopyProject:
    """Create a project with a simple observed spectrum."""
    project = SpectroscopyProject(name="merge-error-test")
    project.model.set_observed_spectrum(
        Spectrum(wavelength=np.array([1000.0, 1001.0, 1002.0]), flux=np.array([1.0, 0.9, 0.8]))
    )
    return project


def test_fits_inspection_delegates_to_spectrum_reader() -> None:
    """Verify ProjectIOUseCase routes FITS inspection through the reader port."""
    reader = _FakeSpectrumReader()
    usecase = ProjectIOUseCase(spectrum_reader=reader, project_repository=_FakeProjectRepository())

    is_valid, issues = usecase.validate_fits_spectrum("flux.fits")
    fits_info = usecase.get_fits_info("flux.fits")

    assert is_valid is False
    assert issues == ["missing wavelength"]
    assert fits_info == {"primary_shape": [123]}
    assert reader.validated_paths == ["flux.fits"]
    assert reader.info_paths == ["flux.fits"]


def test_merge_error_data_rejects_wavelength_mismatch(tmp_path: "Path") -> None:
    """Error spectra with mismatched wavelengths should not be merged."""
    error_file = tmp_path / "error.fits"
    error_file.write_bytes(b"placeholder")
    project = _project_with_observed_spectrum()
    reader = _ErrorSpectrumReader(
        Spectrum(wavelength=np.array([1000.0, 1001.5, 1002.0]), flux=np.array([0.1, 0.2, 0.3]))
    )
    usecase = ProjectIOUseCase(spectrum_reader=reader, project_repository=_FakeProjectRepository())

    with pytest.raises(ValueError, match="differs from main spectrum"):
        usecase.merge_error_data(project, str(error_file))

    assert project.model.observed_spectrum is not None
    assert project.model.observed_spectrum.error is None


def test_merge_error_data_accepts_wavelength_within_tolerance(tmp_path: "Path") -> None:
    """Small wavelength differences inside tolerance can still be merged."""
    error_file = tmp_path / "error.fits"
    error_file.write_bytes(b"placeholder")
    project = _project_with_observed_spectrum()
    reader = _ErrorSpectrumReader(
        Spectrum(wavelength=np.array([1000.0, 1001.005, 1002.0]), flux=np.array([0.1, 0.2, 0.3]))
    )
    usecase = ProjectIOUseCase(spectrum_reader=reader, project_repository=_FakeProjectRepository())

    usecase.merge_error_data(project, str(error_file))

    assert project.model.observed_spectrum is not None
    np.testing.assert_allclose(project.model.observed_spectrum.error, [0.1, 0.2, 0.3])


def test_merge_error_data_converts_external_read_error(tmp_path: "Path") -> None:
    """External error-file read diagnostics remain user-facing I/O errors."""
    error_file = tmp_path / "error.fits"
    error_file.write_bytes(b"placeholder")
    project = _project_with_observed_spectrum()
    usecase = ProjectIOUseCase(
        spectrum_reader=_FailingErrorSpectrumReader(ValueError("malformed FITS")),
        project_repository=_FakeProjectRepository(),
    )

    with pytest.raises(OSError, match="malformed FITS"):
        usecase.merge_error_data(project, str(error_file))


def test_merge_error_data_internal_reader_failure_propagates(tmp_path: "Path") -> None:
    """Internal reader failures should not be converted to user I/O errors."""
    error_file = tmp_path / "error.fits"
    error_file.write_bytes(b"placeholder")
    project = _project_with_observed_spectrum()
    usecase = ProjectIOUseCase(
        spectrum_reader=_FailingErrorSpectrumReader(RuntimeError("reader bug")),
        project_repository=_FakeProjectRepository(),
    )

    with pytest.raises(RuntimeError, match="reader bug"):
        usecase.merge_error_data(project, str(error_file))
