"""Dialog minimum-size rendering tests under the faithful app environment."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from typing import cast

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from chappy.application.project_io_usecase import ProjectIOUseCase
from chappy.core.absorption.models import AbsorptionLine
from chappy.core.atomic_data import AtomicLine, AtomicLineData
from chappy.core.components.absorber import AbsorberComponent
from chappy.core.components.base import Parameter
from chappy.gui.dialogs.close_project_dialog import CloseProjectDialog
from chappy.gui.dialogs.cosmology_dialog import CosmologyDialog
from chappy.gui.dialogs.file_type_selection_dialog import FileTypeSelectionDialog
from chappy.gui.dialogs.line_selection_dialog import LineSelectionDialog
from chappy.gui.dialogs.observation_data_dialog import ObservationDataDialog
from chappy.gui.dialogs.parameter_adjustment_dialog import ParameterAdjustmentDialog
from chappy.gui.dialogs.resolution_dialog import ResolutionDialog
from chappy.gui.dialogs.welcome_dialog import WelcomeDialog
from chappy.gui.modes.identify.presets.preset_list_dialog import PresetListDialog
from chappy.gui.modes.identify.presets.preset_store import IdentifyPresetStore
from chappy.infrastructure.preset_store import PersistentPresetStore
from tests.gui.support.faithful_env import (
    assert_children_fit_at_minimum_size,
    faithful_application_environment,
)


@pytest.fixture
def isolated_settings(tmp_path: Path) -> Generator[QSettings, None, None]:
    """Provide isolated settings storage for each test."""

    settings_dir = tmp_path / "settings"
    settings_dir.mkdir()
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(settings_dir))
    settings = QSettings("TestOrg", "DialogMinimumSizeTests")
    settings.clear()
    yield settings
    settings.clear()


class _StubAtomicData:
    """Minimal atomic data provider for dialog tests."""

    def __init__(self, lines: list[AtomicLine]) -> None:
        self.lines = lines
        self._index = {line.line_id: line for line in lines}

    def get_line_by_id(self, line_id: str | None) -> AtomicLine | None:
        if line_id is None:
            return None
        return self._index.get(line_id)


class _FakeProjectIO:
    """Project I/O test double that serves FITS inspection metadata."""

    def get_fits_info(self, path: str) -> dict[str, object]:
        return {"primary_shape": [77], "n_extensions": 2}


def _make_line(identifier: str, species: str, wavelength: float, multiplet_id: str) -> AtomicLine:
    return AtomicLine(
        line_identifier=identifier,
        species=species,
        wavelength_angstrom=wavelength,
        oscillator_strength=0.1,
        gamma_value=1e8,
        multiplet_id=multiplet_id,
        comments="",
        element_symbol=species.split()[0],
        charge_state=None,
        transition_name=f"{species} {wavelength:.1f}",
        multiplet_label="",
    )


def _build_preset_list_dialog(tmp_path_factory: pytest.TempPathFactory) -> PresetListDialog:
    lines = [
        _make_line("line:civ1", "C IV", 1548.2, "civ"),
        _make_line("line:civ2", "C IV", 1550.8, "civ"),
        _make_line("line:mgii1", "Mg II", 2796.4, "mgii"),
        _make_line("line:mgii2", "Mg II", 2803.5, "mgii"),
    ]
    atomic_data = cast(AtomicLineData, _StubAtomicData(lines))
    store = PersistentPresetStore(
        atomic_data=atomic_data,
        storage_path=tmp_path_factory.mktemp("presets") / "presets.json",
        translate=lambda text: text,
    )
    preset = store.create_custom_preset("Custom", line_ids=[line.line_id for line in lines])
    preset_store = IdentifyPresetStore(store)
    dialog = PresetListDialog(None, preset_store, atomic_data=atomic_data)
    dialog._select_preset_in_list(preset.id)
    return dialog


def _build_line_selection_dialog() -> LineSelectionDialog:
    lines = [
        _make_line("line:hi", "H I", 1215.7, "hi"),
        _make_line("line:civ1", "C IV", 1548.2, "civ"),
        _make_line("line:civ2", "C IV", 1550.8, "civ"),
        _make_line("line:mgii1", "Mg II", 2796.4, "mgii"),
        _make_line("line:mgii2", "Mg II", 2803.5, "mgii"),
    ]
    return LineSelectionDialog(atomic_data=AtomicLineData(lines))


@pytest.mark.parametrize("language", ["ja", "en"])
def test_preset_list_dialog_fits_at_minimum_size(
    qtbot: QtBot, tmp_path_factory: pytest.TempPathFactory, language: str
) -> None:
    """No visible widget may overflow the preset dialog at its minimum size."""
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    with faithful_application_environment(app, language):
        dialog = _build_preset_list_dialog(tmp_path_factory)
        qtbot.addWidget(dialog)
        dialog.show()
        qtbot.waitExposed(dialog)
        assert_children_fit_at_minimum_size(dialog)
        dialog.close()


@pytest.mark.parametrize("language", ["ja", "en"])
def test_line_selection_dialog_fits_at_minimum_size(qtbot: QtBot, language: str) -> None:
    """Searchable filters fit under the real theme and translated labels."""
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    with faithful_application_environment(app, language):
        dialog = _build_line_selection_dialog()
        qtbot.addWidget(dialog)
        dialog.show()
        qtbot.waitExposed(dialog)
        assert_children_fit_at_minimum_size(dialog)
        assert not dialog._table.horizontalScrollBar().isVisible()
        dialog.close()


@pytest.mark.parametrize("language", ["ja", "en"])
def test_file_type_selection_dialog_fits_at_minimum_size(qtbot: QtBot, language: str) -> None:
    """No visible widget may overflow the file type dialog at its minimum size."""
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    with faithful_application_environment(app, language):
        dialog = FileTypeSelectionDialog(
            ["/tmp/spec_flux.fits", "/tmp/spec_error.fits"],
            project_io=cast(ProjectIOUseCase, _FakeProjectIO()),
        )
        qtbot.addWidget(dialog)
        dialog.show()
        qtbot.waitExposed(dialog)
        assert_children_fit_at_minimum_size(dialog)
        dialog.close()


def _build_sample_absorber_component() -> AbsorberComponent:
    component = AbsorberComponent(wavelength=1548.195, oscillator_strength=0.1908, gamma=2.65e8)
    component.parameters["redshift"] = Parameter(
        name="redshift", value=1.29, min_val=1.28, max_val=1.30, fixed=False
    )
    component.parameters["column_density"] = Parameter(
        name="column_density", value=13.5, min_val=10.0, max_val=22.0, fixed=False
    )
    component.parameters["b_parameter"] = Parameter(
        name="b_parameter", value=15.0, min_val=1.0, max_val=200.0, fixed=False
    )
    component.parameters["covering_factor"] = Parameter(
        name="covering_factor", value=1.0, min_val=0.0, max_val=1.0, fixed=True
    )
    return component


def _build_sample_absorption_line() -> AbsorptionLine:
    return AbsorptionLine(
        line_id="line_civ_1548",
        species="C IV",
        rest_wavelength=1548.195,
        center_z=1.29,
        window_kms=500.0,
        multiplet_label="C IV λ1548",
        transition_name="λ1548",
        oscillator_strength=0.1908,
        gamma_value=2.65e8,
    )


@pytest.mark.parametrize("language", ["ja", "en"])
def test_parameter_adjustment_dialog_fits_at_minimum_size(qtbot: QtBot, language: str) -> None:
    """No visible widget may overflow the parameter adjustment dialog at its minimum size."""
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    with faithful_application_environment(app, language):
        dialog = ParameterAdjustmentDialog()
        dialog.set_component(
            _build_sample_absorber_component(),
            line=_build_sample_absorption_line(),
            z_bounds=(1.28, 1.30),
            line_display_id=1,
            component_index=1,
        )
        qtbot.addWidget(dialog)
        dialog.show()
        qtbot.waitExposed(dialog)
        assert_children_fit_at_minimum_size(dialog)
        dialog.close()


@pytest.mark.parametrize("language", ["ja", "en"])
def test_close_project_dialog_fits_at_minimum_size(qtbot: QtBot, language: str) -> None:
    """No visible widget may overflow the close project dialog at its minimum size."""
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    with faithful_application_environment(app, language):
        dialog = CloseProjectDialog(None, project_name="Example Project")
        qtbot.addWidget(dialog)
        dialog.show()
        qtbot.waitExposed(dialog)
        assert_children_fit_at_minimum_size(dialog)
        dialog.close()


@pytest.mark.parametrize("language", ["ja", "en"])
def test_welcome_dialog_fits_at_minimum_size(qtbot: QtBot, language: str) -> None:
    """No visible widget may overflow the welcome dialog at its minimum size."""
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    with faithful_application_environment(app, language):
        dialog = WelcomeDialog(None, sample_available=True)
        qtbot.addWidget(dialog)
        dialog.show()
        qtbot.waitExposed(dialog)
        assert_children_fit_at_minimum_size(dialog)
        dialog.close()


@pytest.mark.parametrize("language", ["ja", "en"])
def test_resolution_dialog_fits_at_minimum_size(
    qtbot: QtBot, isolated_settings: QSettings, language: str
) -> None:
    """No visible widget may overflow the resolution dialog at its minimum size."""
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    with faithful_application_environment(app, language):
        dialog = ResolutionDialog(None, settings=isolated_settings)
        qtbot.addWidget(dialog)
        dialog.show()
        qtbot.waitExposed(dialog)
        assert_children_fit_at_minimum_size(dialog)
        dialog.close()


@pytest.mark.parametrize("language", ["ja", "en"])
def test_cosmology_dialog_fits_at_minimum_size(
    qtbot: QtBot, isolated_settings: QSettings, language: str
) -> None:
    """No visible widget may overflow the cosmology dialog at its minimum size."""
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    with faithful_application_environment(app, language):
        dialog = CosmologyDialog(None, settings=isolated_settings)
        qtbot.addWidget(dialog)
        dialog.show()
        qtbot.waitExposed(dialog)
        assert_children_fit_at_minimum_size(dialog)
        dialog.close()


@pytest.mark.parametrize("language", ["ja", "en"])
def test_observation_data_dialog_fits_at_minimum_size(qtbot: QtBot, language: str) -> None:
    """No visible widget may overflow the observation data dialog at its minimum size."""
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    with faithful_application_environment(app, language):
        dialog = ObservationDataDialog(None)
        qtbot.addWidget(dialog)
        dialog.show()
        qtbot.waitExposed(dialog)
        assert_children_fit_at_minimum_size(dialog)
        dialog.close()
