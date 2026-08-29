"""Qt-independent project and observation file classification helpers."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

logger = logging.getLogger(__name__)

FITS_EXTENSIONS = {".fits", ".fit"}
PROJECT_EXTENSIONS = {".h5", ".hdf5"}
EXPECTED_FITS_PAIR_COUNT = 2


class AmbiguousFITSFileSelectionError(ValueError):
    """Raised when flux/error files cannot be inferred safely."""


@dataclass(frozen=True, slots=True)
class DroppedFileClassification:
    """Categorized local paths from a drag-and-drop payload."""

    fits_files: tuple[str, ...]
    project_files: tuple[str, ...]
    unsupported_files: tuple[str, ...]

    @property
    def has_mixed_supported_types(self) -> bool:
        """Return whether both FITS and project files were dropped."""
        return bool(self.fits_files and self.project_files)


class ObservationFileClassifier:
    """Classify observation data files and infer flux/error file pairs."""

    def classify_paths(self, paths: Sequence[str]) -> DroppedFileClassification:
        """Classify local file paths by supported project import type.

        Args:
            paths: Local file paths to classify.

        Returns:
            File classification grouped by FITS, project, and unsupported paths.
        """
        fits_files: list[str] = []
        project_files: list[str] = []
        unsupported_files: list[str] = []

        for path in paths:
            suffix = Path(path).suffix.lower()
            if suffix in FITS_EXTENSIONS:
                fits_files.append(path)
            elif suffix in PROJECT_EXTENSIONS:
                project_files.append(path)
            else:
                unsupported_files.append(path)

        return DroppedFileClassification(
            fits_files=tuple(fits_files),
            project_files=tuple(project_files),
            unsupported_files=tuple(unsupported_files),
        )

    def error_file_patterns(self) -> set[str]:
        """Return patterns used to identify error files."""
        return {
            "_err",
            "_error",
            ".err",
            ".error",
            "_sigma",
            ".sigma",
            "_unc",
            ".unc",
            "_uncertainty",
            ".uncertainty",
            "_noise",
            ".noise",
            "e.fits",
            "e.fit",
        }

    def classify_fits_files(self, fits_files: Sequence[str]) -> tuple[list[str], list[str]]:
        """Classify FITS files into flux and error candidates.

        Args:
            fits_files: FITS paths to classify.

        Returns:
            Pair of flux candidates and error candidates.
        """
        flux_candidates: list[str] = []
        error_candidates: list[str] = []
        error_patterns = self.error_file_patterns()

        for file_path in fits_files:
            path_obj = Path(file_path)
            file_stem = path_obj.stem.lower()
            file_name = path_obj.name.lower()

            is_error_file = any(
                pattern in file_stem or file_name.endswith(pattern) for pattern in error_patterns
            )

            if is_error_file:
                error_candidates.append(file_path)
            else:
                flux_candidates.append(file_path)

        return flux_candidates, error_candidates

    def find_matching_flux_error_pair(
        self, flux_candidates: Sequence[str], error_candidates: Sequence[str]
    ) -> tuple[str, str] | None:
        """Find the best matching flux/error file pair.

        Args:
            flux_candidates: FITS files that look like flux files.
            error_candidates: FITS files that look like error files.

        Returns:
            Matching flux/error pair when one can be inferred.
        """
        for flux_file in flux_candidates:
            flux_stem = Path(flux_file).stem

            for error_file in error_candidates:
                error_stem = Path(error_file).stem
                error_base = self._strip_error_suffix(error_stem)

                if error_base == flux_stem:
                    logger.info("Identified flux-error pair: %s <-> %s", flux_file, error_file)
                    return flux_file, error_file

                if len(error_base) > 0 and error_base[-1] == "e" and len(flux_stem) > 0:
                    flux_base = flux_stem
                    if flux_base.endswith("f"):
                        flux_base = flux_base[:-1]
                        error_base = error_base[:-1]

                    if flux_base == error_base:
                        logger.info("Identified flux-error pair: %s <-> %s", flux_file, error_file)
                        return flux_file, error_file

        return None

    def identify_flux_and_error_files(
        self, fits_files: Sequence[str], error_file_finder: Callable[[str], str | None]
    ) -> tuple[str, str | None]:
        """Identify flux and error files from FITS paths.

        Args:
            fits_files: FITS file paths.
            error_file_finder: Callback for finding a neighboring error file.

        Returns:
            Flux file path and optional error file path.
        """
        if len(fits_files) == 1:
            flux_file = fits_files[0]
            return flux_file, error_file_finder(flux_file)

        flux_candidates, error_candidates = self.classify_fits_files(fits_files)
        if flux_candidates and error_candidates:
            match = self.find_matching_flux_error_pair(flux_candidates, error_candidates)
            if match is not None:
                return match

        if flux_candidates:
            msg = "Ambiguous FITS files: multiple flux candidates without a clear error pair."
            raise AmbiguousFITSFileSelectionError(msg)

        msg = "Ambiguous FITS files: no clear flux candidate identified."
        raise AmbiguousFITSFileSelectionError(msg)

    @staticmethod
    def _strip_error_suffix(error_stem: str) -> str:
        """Remove a known error suffix from a FITS stem."""
        for pattern in ["_err", "_error", "_sigma", "_unc", "_uncertainty", "_noise"]:
            if error_stem.endswith(pattern):
                return error_stem[: -len(pattern)]
        return error_stem
