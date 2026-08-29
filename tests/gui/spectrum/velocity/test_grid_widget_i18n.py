"""Tests for VelocityGridWidget Qt translation sources."""

from __future__ import annotations

import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from PySide6.QtWidgets import QLabel
from pytestqt.qtbot import QtBot

from chappy.gui.spectrum.velocity import VelocityGridWidget, VelocitySubplotWidget
from scripts.i18n_lupdate import run_lupdate


VELOCITY_VIEW_QT_SOURCES = {
    "No velocity data",
    "Region (auto)",
    "{label} (baseline)",
    "Velocity (km/s)",
    "Flux",
    "No lines in view",
    "No spectrum loaded",
    "No preset lines selected",
    "No samples in current window",
    "Velocity conversion failed",
    "Slot {index}",
    "{current} / {total}",
    "0 / 0",
}


def test_velocity_grid_widget_uses_qt_source_text(qtbot: QtBot) -> None:
    """Migrated grid and subplot labels should keep English Qt source text."""
    view = VelocityGridWidget()
    qtbot.addWidget(view)

    page_label = view.findChild(QLabel, "velocityPlotPageLabel")
    assert (page_label.text() if page_label is not None else "") == "0 / 0"

    subplot = _subplots(view)[0]
    assert subplot.render_state().title == "Slot 1"

    subplot.set_heading(None)
    assert subplot.render_state().title == "Region (auto)"

    subplot.set_heading("Mg II 2796", primary=True)
    assert subplot.render_state().title == "Mg II 2796 (baseline)"


def test_lupdate_extracts_velocity_grid_widget_sources(tmp_path: Path) -> None:
    """lupdate should extract the migrated VelocityGridWidget GUI sources."""
    if shutil.which("pyside6-lupdate") is None:
        pytest.skip("pyside6-lupdate is not available")

    ts_path = tmp_path / "velocity_view.ts"
    run_lupdate(source_dirs=[Path("src/chappy/gui/spectrum/velocity")], ts_output=ts_path)

    sources = _ts_sources(ts_path)
    assert VELOCITY_VIEW_QT_SOURCES <= sources
    assert not any("GUI__" in source for source in sources)


def _subplots(view: VelocityGridWidget) -> tuple[VelocitySubplotWidget, ...]:
    """Return the subplot children in grid order."""
    return tuple(view.findChildren(VelocitySubplotWidget))


def _ts_sources(ts_path: Path) -> set[str]:
    """Return source texts extracted into a Qt TS file."""
    tree = ET.parse(ts_path)
    return {source.text for source in tree.findall(".//source") if source.text is not None}
