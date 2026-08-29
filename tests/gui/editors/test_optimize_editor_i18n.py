"""Tests for OptimizeEditor Qt translation extraction."""

from __future__ import annotations

import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from scripts.i18n_lupdate import run_lupdate

OPTIMIZE_EDITOR_QT_SOURCES = {"Fit stopped by user"}


def test_lupdate_extracts_optimize_editor_sources(tmp_path: Path) -> None:
    """Verify lupdate extracts the OptimizeEditor's one remaining GUI source.

    OptimizeEditor is a headless fit backend with no widgets of its own; the
    only translatable string left is the one baked into the fit_completed
    signal payload emitted on user-initiated cancellation.
    """
    if shutil.which("pyside6-lupdate") is None:
        pytest.skip("pyside6-lupdate is not available")

    ts_path = tmp_path / "optimize_editor_ja.ts"
    run_lupdate(
        source_dirs=[Path("src/chappy/gui/modes/analysis/region_detail/editor.py")],
        ts_output=ts_path,
    )

    root = ET.parse(ts_path).getroot()
    sources = {
        source.text
        for source in root.findall("./context/message/source")
        if source.text is not None
    }
    assert OPTIMIZE_EDITOR_QT_SOURCES == sources
