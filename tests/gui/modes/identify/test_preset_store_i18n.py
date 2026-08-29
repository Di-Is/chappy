"""Tests for identify preset store Qt translation extraction."""

from __future__ import annotations

import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from scripts.i18n_lupdate import run_lupdate


def test_lupdate_extracts_builtin_preset_sources(tmp_path: Path) -> None:
    """Verify lupdate extracts built-in preset source text from the GUI boundary."""
    if shutil.which("pyside6-lupdate") is None:
        pytest.skip("pyside6-lupdate is not available")

    ts_path = tmp_path / "identify_preset_store_ja.ts"
    run_lupdate(
        source_dirs=[Path("src/chappy/gui/modes/identify/presets/preset_store.py")],
        ts_output=ts_path,
    )

    root = ET.parse(ts_path).getroot()
    sources = {
        source.text
        for source in root.findall("./context/message/source")
        if source.text is not None
    }
    assert {
        "Lyman Series",
        "Principal H I Lyman transitions for quick selection.",
        "Metal Lines",
        "Metal doublets.",
    }.issubset(sources)
    assert not any("GUI__" in source for source in sources)
