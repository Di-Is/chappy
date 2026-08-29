"""Fail-fast tests for low-level plotting renderer operations."""

from __future__ import annotations

import numpy as np
import pytest

from chappy.plotting.renderers.matplotlib_renderer import MatplotlibRenderer


def test_update_curve_rejects_unknown_curve() -> None:
    """Updating an unknown curve should expose the caller contract violation."""
    renderer = MatplotlibRenderer()
    renderer.create_plot_widget()

    with pytest.raises(KeyError, match="missing"):
        renderer.update_curve("missing", np.array([1.0]), np.array([1.0]))


def test_remove_curve_rejects_unknown_curve() -> None:
    """Removing an unknown curve should expose the caller contract violation."""
    renderer = MatplotlibRenderer()
    renderer.create_plot_widget()

    with pytest.raises(KeyError, match="missing"):
        renderer.remove_curve("missing")
