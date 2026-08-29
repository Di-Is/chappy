"""Tests for spectrum input context."""

from __future__ import annotations

from chappy.gui.spectrum.interaction.input.spectrum_input_context import SpectrumInputContext


def test_context_stores_dragging_absorber() -> None:
    """Context should store mutable input adapter state."""
    context = SpectrumInputContext()

    context.dragging_absorber_id = "abs-1"

    assert context.dragging_absorber_id == "abs-1"
