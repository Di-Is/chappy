"""Tests for Qt domain event adapters."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtTest import QSignalSpy

from chappy.core.components.absorber import AbsorberComponent
from chappy.core.spectrum_model import SpectrumModel
from chappy.gui.adapters.model_event_adapter import SpectrumModelEventAdapter

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


def test_spectrum_model_adapter_emits_component_added(qtbot: QtBot) -> None:
    """Adapter should re-emit component add events as Qt signals."""
    model = SpectrumModel()
    adapter = SpectrumModelEventAdapter(model)
    spy = QSignalSpy(adapter.component_added)

    component = AbsorberComponent(component_id="absorber-1")
    model.add_component(component)
    qtbot.wait(0)

    assert spy.count() == 1
    assert spy.at(0)[0] is component
    adapter.close()
