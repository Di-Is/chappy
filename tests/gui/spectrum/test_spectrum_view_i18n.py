"""Tests for SpectrumView Qt translation extraction."""

from __future__ import annotations

import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from scripts.i18n_lupdate import run_lupdate


def test_lupdate_extracts_spectrum_view_velocity_sources(tmp_path: Path) -> None:
    """Verify lupdate extracts migrated SpectrumView velocity overlay sources."""
    if shutil.which("pyside6-lupdate") is None:
        pytest.skip("pyside6-lupdate is not available")

    ts_path = tmp_path / "spectrum_view_ja.ts"
    run_lupdate(
        source_dirs=[
            Path("src/chappy/gui/spectrum/spectrum_view.py"),
            Path("src/chappy/gui/spectrum/velocity/overlay_widget.py"),
        ],
        ts_output=ts_path,
    )

    root = ET.parse(ts_path).getroot()
    sources = {
        source.text
        for source in root.findall("./context/message/source")
        if source.text is not None
    }
    assert {
        "Velocity Plot",
        "Add selected lines to temporary list",
        "Back to Spectrum",
        "z = {value:.4f}",
    }.issubset(sources)
    assert not any("GUI__" in source for source in sources)
