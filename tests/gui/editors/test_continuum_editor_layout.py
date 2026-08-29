"""Visual-layout regression tests for the continuum side panel."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication, QFrame

from chappy.core.components.continuum import ContinuumComponent
from chappy.core.spectroscopy_project import SpectroscopyProject
from chappy.core.spectrum import Spectrum
from chappy.gui.modes.continuum.editor import ContinuumEditor
from chappy.gui.visual_tokens import SidePanelMetrics
from tests.gui.support.faithful_env import faithful_application_environment

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


def _project_with_continuum() -> SpectroscopyProject:
    project = SpectroscopyProject()
    wavelength = np.linspace(4000.0, 4100.0, 101)
    project.model.set_observed_spectrum(
        Spectrum(wavelength=wavelength, flux=np.ones_like(wavelength))
    )
    continuum = ContinuumComponent("Continuum")
    continuum.continuum_points = [
        (4000.0, 1.01),
        (4025.0, 0.99),
        (4050.0, 1.02),
        (4075.0, 1.00),
        (4100.0, 1.01),
    ]
    project.model.add_component(continuum)
    return project


def _show_editor(qtbot: QtBot, *, width: int) -> ContinuumEditor:
    project = _project_with_continuum()
    editor = ContinuumEditor(project=project)
    editor.set_project(project)
    qtbot.addWidget(editor)
    editor.resize(width, 760)
    editor.show()
    QApplication.processEvents()
    return editor


@pytest.mark.parametrize("language", ["ja", "en"])
@pytest.mark.parametrize("width", [320, 420])
def test_actions_align_and_control_points_fill_remaining_height(
    qtbot: QtBot, qapp: QApplication, language: str, width: int
) -> None:
    """Actions stay aligned and the table uses the available panel height."""
    with faithful_application_environment(qapp, language):
        editor = _show_editor(qtbot, width=width)
        actions_frame = editor.findChild(QFrame, "continuumActionsFrame")
        anchor_frame = editor.findChild(QFrame, "continuumAnchorFrame")
        auto_estimate = editor.guess_continuum_btn
        clear_points = editor.clear_all_btn
        percentile_label = editor._percentile_label
        percentile_spinbox = editor._percentile_spinbox
        table = editor.anchor_points_table

        assert actions_frame is not None
        assert anchor_frame is not None
        assert auto_estimate is not None
        assert clear_points is not None
        assert percentile_label is not None
        assert percentile_spinbox is not None
        assert table is not None

        assert percentile_label.geometry().right() < percentile_spinbox.geometry().left()
        assert auto_estimate.geometry().left() == clear_points.geometry().left()
        assert auto_estimate.geometry().right() == clear_points.geometry().right()
        assert auto_estimate.width() == clear_points.width()
        assert auto_estimate.property("variant") == "primary"
        assert clear_points.property("variant") == "secondary"

        bottom_margin = SidePanelMetrics.OUTER_MARGIN[3]
        assert anchor_frame.geometry().bottom() == editor.rect().bottom() - bottom_margin
        assert table.height() >= 300
        assert not table.horizontalScrollBar().isVisible()


def test_empty_control_points_state_uses_expanded_anchor_card(
    qtbot: QtBot, qapp: QApplication
) -> None:
    """The empty-state guidance occupies the same stable expanded surface."""
    with faithful_application_environment(qapp, "ja"):
        editor = ContinuumEditor()
        qtbot.addWidget(editor)
        editor.resize(320, 760)
        editor.show()
        QApplication.processEvents()

        anchor_frame = editor.findChild(QFrame, "continuumAnchorFrame")
        placeholder = editor._anchor_placeholder
        table = editor.anchor_points_table

        assert anchor_frame is not None
        assert placeholder is not None
        assert table is not None
        assert placeholder.isVisible()
        assert not table.isVisible()
        assert (
            anchor_frame.geometry().bottom()
            == editor.rect().bottom() - SidePanelMetrics.OUTER_MARGIN[3]
        )
