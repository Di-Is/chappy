"""Tests for main window Qt translation sources."""

from __future__ import annotations

import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from scripts.i18n_lupdate import run_lupdate


SHELL_QT_SOURCES = {
    "&User Guide",
    "Reset plot ranges",
    "Auto-adjusted flux axis",
    "Switched to {name} view",
    "Fitting model...",
    "Fit completed: χ² = {value:.3f}",
    "Fit failed: {error}",
    "Analysis Region Detail editor not available",
    "Contextual help is under development.",
    "Could not open the user guide. Please verify that the manual has been generated.",
    "Applied resolution R={R}",
    "Language switched to {label}",
}


def _ts_sources(ts_path: Path) -> set[str]:
    """Return source texts extracted into a Qt TS file.

    Args:
        ts_path: Generated TS catalog path.

    Returns:
        Source texts found in the catalog.
    """
    root = ET.parse(ts_path).getroot()
    return {
        source.text
        for source in root.findall("./context/message/source")
        if source.text is not None
    }


def test_lupdate_extracts_shell_gui_sources(tmp_path: Path) -> None:
    """Verify lupdate extracts migrated shell source text.

    Args:
        tmp_path: Temporary directory for the generated TS file.
    """
    if shutil.which("pyside6-lupdate") is None:
        pytest.skip("pyside6-lupdate is not available")

    ts_path = tmp_path / "main_window.ts"
    run_lupdate(
        source_dirs=[
            Path("src/chappy/gui/shell/main_window.py"),
            Path("src/chappy/gui/shell/data_control_coordinator.py"),
            Path("src/chappy/gui/shell/dialog_workflow_coordinator.py"),
            Path("src/chappy/gui/modes/analysis/region_detail/runtime.py"),
        ],
        ts_output=ts_path,
    )

    sources = _ts_sources(ts_path)
    assert SHELL_QT_SOURCES <= sources
    assert not any("GUI__" in source for source in sources)
    assert not any("STATUS__" in source for source in sources)
    assert not any("TOOLTIP__" in source for source in sources)
