from __future__ import annotations

import numpy as np
import pytest
from numpy.typing import NDArray

from chappy.core.change_set import ChangeSet
from chappy.core.components.absorber import AbsorberComponent
from chappy.core.components.continuum import ContinuumComponent
from chappy.core.components.base import ModelComponent
from chappy.core.spectrum import Spectrum
from chappy.core.spectrum_model import SpectrumModel


class CountingComponent(ModelComponent):  # type: ignore[misc]
    """Model component that counts calculate calls."""

    def __init__(self, name: str) -> None:
        """Initialize the component.

        Args:
            name: Component name.
        """
        super().__init__(name)
        self.n_calculations = 0

    def calculate(self, wavelength: NDArray[np.float64]) -> NDArray[np.float64]:
        """Return a unity contribution while counting calls.

        Args:
            wavelength: Wavelength array.

        Returns:
            Component contribution array.
        """
        self.n_calculations += 1
        return np.ones_like(wavelength, dtype=np.float64)


class FailingComponent(ModelComponent):  # type: ignore[misc]
    """Model component that fails during calculation."""

    def calculate(self, wavelength: NDArray[np.float64]) -> NDArray[np.float64]:
        """Raise an internal calculation failure."""
        _ = wavelength
        raise RuntimeError("component calculation failed")


class WrongShapeComponent(ModelComponent):  # type: ignore[misc]
    """Model component that returns an invalid contribution shape."""

    def calculate(self, wavelength: NDArray[np.float64]) -> NDArray[np.float64]:
        """Return a contribution with the wrong shape."""
        return np.ones(len(wavelength) + 1, dtype=np.float64)


class FailingContinuumExportComponent(ContinuumComponent):
    """Continuum component that fails while exporting for absorption."""

    def export_for_absorption(self, wavelength: NDArray[np.float64]) -> NDArray[np.float64] | None:
        """Raise for regression coverage of fail-fast behavior."""
        del wavelength
        raise RuntimeError("forced continuum export failure")


class FailingApplyContinuumAbsorberComponent(AbsorberComponent):
    """Absorber that fails while setting external continuum."""

    def set_external_continuum(
        self,
        continuum_name: str | None,
        wavelength: NDArray[np.float64] | None = None,
        continuum_flux: NDArray[np.float64] | None = None,
    ) -> ChangeSet:
        """Raise for regression coverage of fail-fast behavior."""
        del continuum_name
        del wavelength
        del continuum_flux
        raise RuntimeError("forced absorber apply failure")


def _build_observed_spectrum(n_points: int = 100) -> Spectrum:
    """Create an observed spectrum for model testing.

    Args:
        n_points: Number of data points.

    Returns:
        Spectrum instance.
    """
    wavelength = np.linspace(5000.0, 5100.0, n_points, dtype=np.float64)
    flux = np.ones_like(wavelength, dtype=np.float64)
    error = np.full_like(wavelength, 0.1, dtype=np.float64)
    return Spectrum(wavelength=wavelength, flux=flux, error=error, header={})


def test_add_component_does_not_recalculate_existing_components_when_model_valid() -> None:
    """Adding a component must not trigger recalculation for existing components."""
    model = SpectrumModel()
    model.set_observed_spectrum(_build_observed_spectrum())

    first = CountingComponent("first")
    model.add_component(first)
    first.n_calculations = 0

    second = CountingComponent("second")
    model.add_component(second)

    assert first.n_calculations == 0
    assert second.n_calculations == 1


def test_full_model_update_component_failure_propagates() -> None:
    """Full model updates should not hide component calculation failures."""
    model = SpectrumModel()
    model.set_observed_spectrum(_build_observed_spectrum())

    with pytest.raises(RuntimeError, match="component calculation failed"):
        model.add_component(FailingComponent("failing"))


def test_incremental_model_update_component_failure_propagates() -> None:
    """Incremental model updates should not fall back from component calculation failures."""
    model = SpectrumModel()
    model.set_observed_spectrum(_build_observed_spectrum())
    model.add_component(CountingComponent("first"))

    with pytest.raises(RuntimeError, match="component calculation failed"):
        model.add_component(FailingComponent("failing"))


def test_incremental_model_update_rejects_wrong_contribution_shape() -> None:
    """Invalid incremental contribution shape is an internal model failure."""
    model = SpectrumModel()
    model.set_observed_spectrum(_build_observed_spectrum())
    model.add_component(CountingComponent("first"))

    with pytest.raises(ValueError, match="contribution shape"):
        model.add_component(WrongShapeComponent("wrong-shape"))


def test_add_absorber_propagates_shared_continuum_export_failure() -> None:
    """Add absorber should propagate failures from shared continuum export."""
    model = SpectrumModel()
    model.set_observed_spectrum(_build_observed_spectrum())
    model.add_component(FailingContinuumExportComponent())

    with pytest.raises(RuntimeError, match="forced continuum export failure"):
        model.add_component(AbsorberComponent())


def test_add_absorber_propagates_shared_continuum_apply_failure() -> None:
    """Add absorber should propagate failures from absorber external-continuum apply."""
    model = SpectrumModel()
    model.set_observed_spectrum(_build_observed_spectrum())

    shared_continuum = ContinuumComponent("shared")
    shared_continuum.set_continuum_points(
        [(5000.0, 1.0), (5030.0, 1.0), (5070.0, 1.0), (5100.0, 1.0)]
    )
    model.add_component(shared_continuum)

    with pytest.raises(RuntimeError, match="forced absorber apply failure"):
        model.add_component(FailingApplyContinuumAbsorberComponent())


def test_apply_active_continuum_absence_keeps_change_set_empty() -> None:
    """No shared continuum should keep active continuum apply path empty."""
    model = SpectrumModel()
    model.set_observed_spectrum(_build_observed_spectrum())
    absorber = AbsorberComponent()

    assert not model._apply_active_continuum_to_absorber(absorber)


def test_apply_active_continuum_with_no_observed_spectrum_remains_valid_empty() -> None:
    """No observed spectrum keeps active continuum apply as valid empty behavior."""
    model = SpectrumModel()
    shared_continuum = ContinuumComponent("shared")
    shared_continuum.set_continuum_points(
        [(5000.0, 1.0), (5030.0, 1.0), (5070.0, 1.0), (5100.0, 1.0)]
    )
    model.add_component(shared_continuum)
    absorber = AbsorberComponent()

    assert not model._apply_active_continuum_to_absorber(absorber)
