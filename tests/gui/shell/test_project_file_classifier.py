"""Tests for project file classification helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from chappy.gui.shell.project_file_classifier import (
    AmbiguousFITSFileSelectionError,
    ObservationFileClassifier,
)


def test_classify_paths_separates_supported_project_and_fits_files(tmp_path: Path) -> None:
    """FITS, project, and unsupported paths are classified without Qt objects."""
    classifier = ObservationFileClassifier()
    flux = tmp_path / "spectrum.fits"
    project = tmp_path / "analysis.h5"
    notes = tmp_path / "notes.txt"

    classification = classifier.classify_paths([str(flux), str(project), str(notes)])

    assert classification.fits_files == (str(flux),)
    assert classification.project_files == (str(project),)
    assert classification.unsupported_files == (str(notes),)
    assert classification.has_mixed_supported_types is True


def test_identify_flux_error_pair_uses_error_suffix() -> None:
    """Automatic pair detection matches conventional error-file suffixes."""
    classifier = ObservationFileClassifier()
    flux_file, error_file = classifier.identify_flux_and_error_files(
        ["/data/qso.fits", "/data/qso_err.fits"], lambda _path: None
    )

    assert flux_file == "/data/qso.fits"
    assert error_file == "/data/qso_err.fits"


def test_ambiguous_multiple_flux_candidates_raise() -> None:
    """Multiple plausible flux files should not silently choose the first file."""
    classifier = ObservationFileClassifier()

    with pytest.raises(AmbiguousFITSFileSelectionError, match="multiple flux candidates"):
        classifier.identify_flux_and_error_files(
            ["/data/qso_a.fits", "/data/qso_b.fits"], lambda _path: None
        )
