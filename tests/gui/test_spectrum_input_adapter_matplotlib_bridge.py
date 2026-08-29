"""Test SpectrumInputAdapter as event-handlers for matplotlib bridge."""

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent

from chappy.gui.protocols.intent_types import SelectAbsorberIntent
from chappy.gui.shell.spectrum_mode_policy import spectrum_interaction_mode_policy


@pytest.fixture
def spectrum_view(qtbot):
    """Create SpectrumView instance for testing."""
    from chappy.gui.spectrum.spectrum_plot import create_default_spectrum_plot_host_factory
    from chappy.gui.spectrum.spectrum_view import SpectrumView

    view = SpectrumView(plot_host_factory=create_default_spectrum_plot_host_factory())
    qtbot.addWidget(view)
    return view


def test_spectrum_input_adapter_has_required_methods(spectrum_view):
    """Test that spectrum_input_adapter has all required methods."""
    # Check that spectrum_input_adapter exists
    assert hasattr(spectrum_view, "spectrum_input_adapter")
    assert spectrum_view.spectrum_input_adapter is not None
    interactor = spectrum_view.spectrum_input_adapter

    # Check matplotlib bridge methods
    assert hasattr(interactor, "handle_mouse_press_event")
    assert hasattr(interactor, "handle_mouse_release_event")
    assert hasattr(interactor, "handle_mouse_move_event")
    assert hasattr(interactor, "handle_mouse_leave")
    assert hasattr(interactor, "process_mouse_event")

    # Check intent conversion entrypoints
    assert hasattr(interactor, "handle_mouse_click")
    assert hasattr(interactor, "handle_key_event")
    assert hasattr(interactor, "handle_wheel")

    # Check mode/state helpers
    assert hasattr(interactor, "set_rect_zoom_mode")
    assert hasattr(interactor, "set_selected_line_absorbers")


def test_plot_event_handler_generates_intent(spectrum_view):
    """Test that plot event handlers generate correct intents."""
    # Mock intent emission
    intents_received = []
    interactor = spectrum_view.spectrum_input_adapter
    interactor.sig_absorber_action.connect(lambda intent: intents_received.append(intent))

    handled = interactor.handle_mouse_click((5000.0, 0.8), "left")
    assert handled is False

    # Ensure no absorber intent emitted by default
    assert len(intents_received) == 0

    # Test keyboard navigation intent emission
    intents_received.clear()
    event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_N, Qt.KeyboardModifier.NoModifier)
    handled_key = interactor.handle_key_event(event)
    assert handled_key is True
    assert len(intents_received) == 1
    assert isinstance(intents_received[0], SelectAbsorberIntent)
    assert intents_received[0].direction == "next"


def test_mode_state_accessors(spectrum_view):
    """Test that mode state accessors work correctly."""
    interactor = spectrum_view.spectrum_input_adapter

    # Initially, modes should be False
    interactor.set_rect_zoom_mode(True)
    assert interactor.is_rect_zoom_mode_enabled() is True
    # Rect zoom disables other interaction modes
    interactor.set_rect_zoom_mode(False)
    assert interactor.is_rect_zoom_mode_enabled() is False
