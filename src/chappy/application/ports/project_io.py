"""Project I/O port definitions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from chappy.application.project_document import ProjectDocument
    from chappy.core.spectrum import Spectrum


@runtime_checkable
class SpectrumReader(Protocol):
    """Port for reading observed spectra from external files."""

    def read_spectrum(self, path: str) -> Spectrum:
        """Read a spectrum from a file.

        Args:
            path: Source file path.

        Returns:
            Spectrum read from the file.
        """
        ...

    def validate_spectrum(self, path: str) -> tuple[bool, list[str]]:
        """Validate whether a file can be read as an observed spectrum.

        Args:
            path: Source file path.

        Returns:
            Pair of validity flag and validation issue messages.
        """
        ...

    def get_spectrum_info(self, path: str) -> dict[str, object]:
        """Return display-oriented metadata for a spectrum file.

        Args:
            path: Source file path.

        Returns:
            Spectrum metadata keyed by stable display field names.
        """
        ...


@runtime_checkable
class ProjectRepository(Protocol):
    """Port for persisting project documents."""

    def load(self, path: str) -> ProjectDocument:
        """Load a project document.

        Args:
            path: Project file path.

        Returns:
            Loaded project document.
        """
        ...

    def save(self, document: ProjectDocument, path: str) -> None:
        """Persist a project document.

        Args:
            document: Project document to persist.
            path: Destination file path.
        """
        ...
