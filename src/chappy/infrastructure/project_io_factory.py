"""Infrastructure composition for project I/O use cases."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING

from chappy.application.ports.project_io import ProjectRepository, SpectrumReader
from chappy.application.project_io_usecase import ProjectIOUseCase

if TYPE_CHECKING:
    from chappy.application.project_document import ProjectDocument
    from chappy.core.spectrum import Spectrum


def _create_spectrum_reader() -> SpectrumReader:
    """Import and validate the default spectrum adapter at first use."""
    adapter_type = getattr(
        import_module("chappy.infrastructure.fits_spectrum_reader"), "FitsSpectrumReader", None
    )
    if not isinstance(adapter_type, type):
        msg = "FITS spectrum adapter class is unavailable."
        raise TypeError(msg)
    adapter = adapter_type()
    if not isinstance(adapter, SpectrumReader):
        msg = "FITS spectrum adapter does not implement SpectrumReader."
        raise TypeError(msg)
    return adapter


def _create_project_repository() -> ProjectRepository:
    """Import and validate the default project repository at first use."""
    adapter_type = getattr(
        import_module("chappy.infrastructure.hdf5_project_repository"),
        "HDF5ProjectRepository",
        None,
    )
    if not isinstance(adapter_type, type):
        msg = "HDF5 project repository class is unavailable."
        raise TypeError(msg)
    adapter = adapter_type()
    if not isinstance(adapter, ProjectRepository):
        msg = "HDF5 project repository does not implement ProjectRepository."
        raise TypeError(msg)
    return adapter


class _LazyFitsSpectrumReader:
    """Load the FITS adapter only when external spectrum I/O is requested."""

    def __init__(self) -> None:
        self._delegate: SpectrumReader | None = None

    def _reader(self) -> SpectrumReader:
        if self._delegate is None:
            self._delegate = _create_spectrum_reader()
        return self._delegate

    def read_spectrum(self, path: str) -> Spectrum:
        """Read a spectrum through the lazily constructed adapter."""
        return self._reader().read_spectrum(path)

    def validate_spectrum(self, path: str) -> tuple[bool, list[str]]:
        """Validate one spectrum through the lazily constructed adapter."""
        return self._reader().validate_spectrum(path)

    def get_spectrum_info(self, path: str) -> dict[str, object]:
        """Read spectrum metadata through the lazily constructed adapter."""
        return self._reader().get_spectrum_info(path)


class _LazyHdf5ProjectRepository:
    """Load the HDF5 adapter only when project persistence is requested."""

    def __init__(self) -> None:
        self._delegate: ProjectRepository | None = None

    def _repository(self) -> ProjectRepository:
        if self._delegate is None:
            self._delegate = _create_project_repository()
        return self._delegate

    def load(self, path: str) -> ProjectDocument:
        """Load a project through the lazily constructed repository."""
        return self._repository().load(path)

    def save(self, document: ProjectDocument, path: str) -> None:
        """Save a project through the lazily constructed repository."""
        self._repository().save(document, path)


def create_default_project_io_usecase() -> ProjectIOUseCase:
    """Create a project I/O use case wired to default infrastructure adapters.

    Returns:
        Project I/O use case with FITS and HDF5 adapters.
    """
    return ProjectIOUseCase(
        spectrum_reader=_LazyFitsSpectrumReader(), project_repository=_LazyHdf5ProjectRepository()
    )
