"""Tests for the parameter adjustment dialog Qt translation path."""

from __future__ import annotations

import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from scripts.i18n_lupdate import run_lupdate


def test_lupdate_extracts_parameter_adjustment_dialog_sources(tmp_path: Path) -> None:
    """Verify lupdate extracts migrated ParameterAdjustmentDialog sources."""
    if shutil.which("pyside6-lupdate") is None:
        pytest.skip("pyside6-lupdate is not available")

    ts_path = tmp_path / "chappy_ja.ts"
    run_lupdate(
        source_dirs=[Path("src/chappy/gui/dialogs/parameter_adjustment_dialog.py")],
        ts_output=ts_path,
    )

    root = ET.parse(ts_path).getroot()
    sources = {
        source.text
        for source in root.findall("./context/message/source")
        if source.text is not None
    }
    expected_sources = {
        "Adjust Absorber Parameters",
        "Line {id} · Component {index}",
        "logN (column density)",
        "b (Doppler parameter)",
        "z (redshift)",
        "Cf (covering factor)",
        "Lock",
        "Prevent the fitter from changing this parameter.",
        "Extended range",
        "Allow the Doppler parameter slider to use the full configured bounds.",
        "Changes are applied to the model immediately.",
        "No associated line",
        "Close",
    }
    assert expected_sources.issubset(sources)
    assert not any("DLG__" in source for source in sources)
    assert not any("GUI__" in source for source in sources)
