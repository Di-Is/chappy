"""Tests for the shared display half-width across velocity grid pages."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from PySide6.QtWidgets import QPushButton

from chappy.gui.spectrum.velocity import VelocityGridWidget, VelocitySubplotWidget
from chappy.presentation.velocity import (
    VelocityDisplayHalfWidth,
    VelocitySliceInfo,
    VelocitySpectrumData,
    VelocityViewData,
)

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


def test_display_half_width_is_shared_by_all_subplots_and_pages(qtbot: QtBot) -> None:
    """Paging must never restore a line's individual analysis half-width as X limits."""
    grid = VelocityGridWidget()
    qtbot.addWidget(grid)
    grid.set_mode("optimize")
    grid.set_display_half_width(VelocityDisplayHalfWidth(300.0))
    rest_wavelength = 1215.67
    observed = VelocitySpectrumData(
        wavelength=np.linspace(1214.0, 1217.0, 500), flux=np.ones(500), error=np.full(500, 0.05)
    )
    slices = tuple(
        VelocitySliceInfo(
            rest_wavelength=rest_wavelength,
            label=f"Line {index}",
            tie_group_key="",
            center_z=0.0,
            analysis_half_width_kms=100.0 + (index * 50.0),
        )
        for index in range(7)
    )
    grid.apply_view_data(VelocityViewData(observed=observed, model=None, slices=slices))

    rendered = tuple(
        subplot.render_state()
        for subplot in grid.findChildren(VelocitySubplotWidget)
        if not subplot.render_state().placeholder_visible
    )
    assert len(rendered) == 6
    assert {state.display_velocity_range for state in rendered} == {(-300.0, 300.0)}

    next_button = grid.findChild(QPushButton, "velocityPlotNextPage")
    assert next_button is not None
    next_button.click()

    rendered_page_two = tuple(
        subplot.render_state()
        for subplot in grid.findChildren(VelocitySubplotWidget)
        if not subplot.render_state().placeholder_visible
    )
    assert len(rendered_page_two) == 1
    assert rendered_page_two[0].display_velocity_range == (-300.0, 300.0)
    assert grid.display_half_width == VelocityDisplayHalfWidth(300.0)


def test_identify_analysis_range_out_of_view_is_visible_and_accessible(qtbot: QtBot) -> None:
    """Identify should show a non-color warning when candidate bounds exceed the view."""
    grid = VelocityGridWidget()
    qtbot.addWidget(grid)
    grid.set_mode("identify")
    grid.set_display_half_width(VelocityDisplayHalfWidth(200.0))
    observed = VelocitySpectrumData(
        wavelength=np.linspace(1214.0, 1217.0, 500), flux=np.ones(500), error=np.full(500, 0.05)
    )
    grid.apply_view_data(
        VelocityViewData(
            observed=observed,
            model=None,
            slices=(
                VelocitySliceInfo(
                    rest_wavelength=1215.67,
                    label="Lyα",
                    tie_group_key="",
                    center_z=0.0,
                    analysis_half_width_kms=350.0,
                ),
            ),
        )
    )

    rendered_subplots = [
        subplot
        for subplot in grid.findChildren(VelocitySubplotWidget)
        if not subplot.render_state().placeholder_visible
    ]
    assert len(rendered_subplots) == 1
    subplot = rendered_subplots[0]
    state = subplot.render_state()
    assert state.analysis_out_of_view_text == ("↔ Analysis range extends beyond view (±350 km/s)")
    assert "Fit view to analysis ranges" in subplot.accessibleDescription()
