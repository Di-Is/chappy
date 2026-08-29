"""Regression tests for observer-free spectrum project attachment."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from matplotlib.lines import Line2D

from chappy.application.project_mapper import project_to_document
from chappy.core.components.absorber import AbsorberComponent
from chappy.core.spectroscopy_project import SpectroscopyProject
from chappy.core.spectrum import Spectrum
from chappy.gui.spectrum.spectrum_data_bridge import SpectrumDataBridge

if TYPE_CHECKING:
    import pytest
    from pytestqt.qtbot import QtBot

    from chappy.core.change_set import ChangeSet


def _project() -> SpectroscopyProject:
    """Return a project with one calculated absorber model."""
    project = SpectroscopyProject(name="Attach Test")
    wavelength = np.linspace(1200.0, 1230.0, 121)
    flux = np.linspace(0.9, 1.1, wavelength.size)
    project.model.set_observed_spectrum(Spectrum(wavelength=wavelength, flux=flux))
    project.model.add_component(
        AbsorberComponent(
            component_id="absorber-1",
            wavelength=1215.67,
            column_density=13.0,
            b_parameter=15.0,
            redshift=0.0,
        )
    )
    return project


def _serialized_science(project: SpectroscopyProject) -> object:
    """Return persisted scientific fields that project attachment must preserve."""
    document = project_to_document(project)
    return (
        document.components,
        document.masks,
        document.fit_wavelength_range,
        document.tie_sets,
        document.absorption_regions,
        document.absorption_lines,
        document.analysis_states,
        document.identify_state,
        document.settings,
    )


def test_set_project_keeps_valid_derived_state_without_rebuild(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Attaching a valid model only subscribes the bridge and emits project change."""
    project = _project()
    assert project.model.is_model_valid is True
    derived_before = project.model.snapshot_derived_state_for_transaction()
    modified_before = project.modified
    revisions_before = project.region_analysis_states()
    science_before = _serialized_science(project)
    model_events: list[ChangeSet] = []
    project.model.events.subscribe(model_events.append)

    def fail_rebuild() -> ChangeSet:
        raise AssertionError("a valid model must not be rebuilt during attachment")

    monkeypatch.setattr(project.model, "rebuild_model_storage", fail_rebuild)
    bridge = SpectrumDataBridge()
    data_updates = 0

    def capture_data_update() -> None:
        nonlocal data_updates
        data_updates += 1

    bridge.data_updated.connect(capture_data_update)
    bridge.set_project(project)

    derived_after = project.model.snapshot_derived_state_for_transaction()
    assert derived_after.model_valid is True
    np.testing.assert_array_equal(derived_after.model_flux, derived_before.model_flux)
    np.testing.assert_array_equal(derived_after.residuals, derived_before.residuals)
    np.testing.assert_array_equal(derived_after.raw_model_flux, derived_before.raw_model_flux)
    assert project.modified == modified_before
    assert project.region_analysis_states() == revisions_before
    assert _serialized_science(project) == science_before
    assert model_events == []
    assert data_updates == 0


def test_set_project_ensures_invalid_derived_state_without_observer_events() -> None:
    """Attaching an invalid model calculates its cache without changing persisted science."""
    project = _project()
    component = project.require_absorber_component("absorber-1")
    component.parameters["column_density"].set_value(14.0)
    project.model.invalidate_model()
    assert project.model.is_model_valid is False
    modified_before = project.modified
    revisions_before = project.region_analysis_states()
    science_before = _serialized_science(project)
    model_events: list[ChangeSet] = []
    project.model.events.subscribe(model_events.append)
    bridge = SpectrumDataBridge()
    data_updates = 0

    def capture_data_update() -> None:
        nonlocal data_updates
        data_updates += 1

    bridge.data_updated.connect(capture_data_update)
    bridge.set_project(project)

    assert project.model.is_model_valid is True
    assert project.modified == modified_before
    assert project.region_analysis_states() == revisions_before
    assert _serialized_science(project) == science_before
    assert model_events == []
    assert data_updates == 0


def test_display_derived_recalculation_does_not_mark_science_modified() -> None:
    """A display refresh may rebuild runtime cache without dirtying the project."""
    project = _project()
    project.model.invalidate_model()
    modified_before = project.modified
    revisions_before = project.region_analysis_states()
    science_before = _serialized_science(project)

    project.model.update_model()

    assert project.model.is_model_valid is True
    assert project.modified == modified_before
    assert project.region_analysis_states() == revisions_before
    assert _serialized_science(project) == science_before


def test_spectrum_view_renders_project_without_model_notifications(qtbot: QtBot) -> None:
    """Project attachment explicitly renders observed data while remaining observer-free."""
    from chappy.gui.spectrum.spectrum_plot import create_default_spectrum_plot_host_factory
    from chappy.gui.spectrum.spectrum_view import SpectrumView

    project = _project()
    observed = project.model.observed_spectrum
    assert observed is not None
    view = SpectrumView(plot_host_factory=create_default_spectrum_plot_host_factory())
    qtbot.addWidget(view)
    data_updates = 0

    def capture_data_update() -> None:
        nonlocal data_updates
        data_updates += 1

    view.data_bridge.data_updated.connect(capture_data_update)

    view.set_project(project)

    plot_widget = view.plot_host.plot_widget
    assert plot_widget is not None
    artist = plot_widget.renderer.plot_items.get("observed")
    assert isinstance(artist, Line2D)
    np.testing.assert_array_equal(artist.get_xdata(), observed.wavelength)
    np.testing.assert_array_equal(artist.get_ydata(), observed.flux)
    assert artist.get_visible()
    assert data_updates == 0
