"""Tests for typed SpectrumModel change sets."""

from __future__ import annotations

import logging

import numpy as np
import pytest

from chappy.core.change_set import ChangeSet
from chappy.core.components.absorber import AbsorberComponent
from chappy.core.components.tie_set import ParameterTieSet
from chappy.core.events import ComponentAdded, ComponentRemoved, MasksChanged, ModelUpdated
from chappy.core.masking import MaskDefinition, MaskMode
from chappy.core.resolution import ResolutionState
from chappy.core.spectrum import Spectrum
from chappy.core.spectrum_model import SpectrumModel


def _observed_spectrum() -> Spectrum:
    """Create an observed spectrum for model change tests."""
    wavelength = np.linspace(5000.0, 5100.0, 20, dtype=np.float64)
    flux = np.ones_like(wavelength, dtype=np.float64)
    return Spectrum(wavelength=wavelength, flux=flux, error=None, header={})


def test_add_and_remove_component_return_typed_events() -> None:
    """Component add/remove operations should return typed model events."""
    model = SpectrumModel()
    model.set_observed_spectrum(_observed_spectrum())
    component = AbsorberComponent(component_id="absorber-1")

    add_changes = model.add_component(component)
    remove_changes = model.remove_component(component)

    assert add_changes.filter(ComponentAdded)[0].component_id == "absorber-1"
    assert add_changes.contains(ModelUpdated)
    assert remove_changes.filter(ComponentRemoved)[0].component_id == "absorber-1"
    assert remove_changes.contains(ModelUpdated)


def test_mask_operations_dispatch_masks_changed_event() -> None:
    """Mask updates should dispatch masks-changed events."""
    model = SpectrumModel()
    dispatched = []
    model.events.subscribe(dispatched.append)

    model.add_mask_definition(
        MaskDefinition(
            identifier="mask-1",
            label="Mask 1",
            mode=MaskMode.RANGE,
            start_wavelength=5001.0,
            end_wavelength=5002.0,
            group_id="group-1",
        )
    )

    assert any(change_set.contains(MasksChanged) for change_set in dispatched)


def test_rebuild_tie_sets_propagates_component_attach_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reloaded tie set attachment failures should not be hidden."""
    model = SpectrumModel()
    component_a = AbsorberComponent(component_id="component-a")
    component_b = AbsorberComponent(component_id="component-b")
    model.components.extend([component_a, component_b])

    def fail_add_component(self: ParameterTieSet, component: AbsorberComponent) -> object:
        del self, component
        raise RuntimeError("broken multiplet attachment")

    monkeypatch.setattr(ParameterTieSet, "add_component", fail_add_component)

    with pytest.raises(RuntimeError, match="broken multiplet attachment"):
        model.rebuild_tie_sets(
            (
                {
                    "tie_id": "mgii",
                    "name": "Mg II",
                    "component_ids": ("component-a", "component-b"),
                    "shared_parameters": {},
                },
            )
        )


def test_transaction_snapshot_restores_exact_derived_arrays_and_validity() -> None:
    """A failed storage transaction can restore derived model caches exactly."""
    model = SpectrumModel()
    model.set_observed_spectrum(_observed_spectrum())
    component = AbsorberComponent(component_id="absorber-1", redshift=2.25, column_density=15.0)
    model.add_component(component)
    model.invalidate_model()
    before = model.snapshot_derived_state_for_transaction()

    component.parameters["column_density"].set_value(18.0)
    model.rebuild_model_storage()
    assert model.is_model_valid

    model.restore_derived_state_for_transaction(before)

    restored = model.snapshot_derived_state_for_transaction()
    assert restored.model_valid is before.model_valid
    assert restored.model_flux is not None
    assert before.model_flux is not None
    np.testing.assert_array_equal(restored.model_flux, before.model_flux)
    assert restored.residuals is not None
    assert before.residuals is not None
    np.testing.assert_array_equal(restored.residuals, before.residuals)
    assert restored.raw_model_flux is not None
    assert before.raw_model_flux is not None
    np.testing.assert_array_equal(restored.raw_model_flux, before.raw_model_flux)


def test_publish_storage_changes_isolates_listener_failure_and_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Committed model changes must reach later listeners after one observer fails."""
    model = SpectrumModel()
    received: list[ChangeSet] = []
    changes = ChangeSet.of(ModelUpdated())

    def fail_listener(_changes: ChangeSet) -> None:
        raise RuntimeError("observer failed")

    model.events.subscribe(fail_listener)
    model.events.subscribe(received.append)

    with caplog.at_level(logging.ERROR, logger="chappy.core.event_dispatcher"):
        model.publish_storage_changes(changes)

    assert received == [changes]
    assert "Domain listener failed during isolated post-commit dispatch" in caplog.text


def test_regular_domain_dispatch_remains_fail_fast() -> None:
    """Ordinary in-transaction dispatch must retain its existing fail-fast behavior."""
    model = SpectrumModel()
    received: list[ChangeSet] = []
    changes = ChangeSet.of(ModelUpdated())

    def fail_listener(_changes: ChangeSet) -> None:
        raise RuntimeError("observer failed")

    model.events.subscribe(fail_listener)
    model.events.subscribe(received.append)

    with pytest.raises(RuntimeError, match="observer failed"):
        model.events.dispatch(changes)

    assert received == []


def _absorber_model() -> SpectrumModel:
    """Create a model with two enabled absorbers on a fine wavelength grid."""
    model = SpectrumModel()
    wavelength = np.linspace(5000.0, 5002.0, 400, dtype=np.float64)
    model.set_observed_spectrum(
        Spectrum(wavelength=wavelength, flux=np.ones_like(wavelength), error=None, header={})
    )
    model.add_component(
        AbsorberComponent(component_id="abs-1", wavelength=5000.5, column_density=13.5)
    )
    model.add_component(
        AbsorberComponent(component_id="abs-2", wavelength=5001.5, column_density=13.8)
    )
    model.update_model()
    return model


def test_component_transmissions_multiply_into_the_composite_model() -> None:
    """Without instrumental convolution the per-absorber curves rebuild the model."""
    model = _absorber_model()
    wavelength = np.linspace(5000.0, 5002.0, 400, dtype=np.float64)

    transmissions = model.component_transmissions_on(wavelength)

    assert [component_id for component_id, _ in transmissions] == ["abs-1", "abs-2"]
    assert model.model_spectrum is not None
    product = transmissions[0][1] * transmissions[1][1]
    np.testing.assert_allclose(product, model.model_spectrum.flux, rtol=1e-10)
    assert transmissions[0][1].min() < 0.9


def test_component_transmissions_stay_on_grid_under_instrumental_resolution() -> None:
    """Each curve is convolved on its own, so only shape and smearing are guaranteed."""
    model = _absorber_model()
    model.set_resolution_state(ResolutionState(value=20000.0, enabled=True))
    model.update_model()
    wavelength = np.linspace(5000.0, 5002.0, 400, dtype=np.float64)

    transmissions = model.component_transmissions_on(wavelength)

    assert len(transmissions) == 2
    for _, flux in transmissions:
        assert flux.shape == wavelength.shape
        assert np.isfinite(flux).all()


def test_component_transmissions_blank_masked_pixels() -> None:
    """Masked wavelengths are NaN in every component curve, as in the composite model."""
    model = _absorber_model()
    model.add_mask_definition(
        MaskDefinition(
            identifier="mask-1",
            label="Mask 1",
            mode=MaskMode.RANGE,
            start_wavelength=5000.4,
            end_wavelength=5000.6,
            group_id="group-1",
        )
    )
    wavelength = np.linspace(5000.0, 5002.0, 400, dtype=np.float64)
    masked = (wavelength >= 5000.4) & (wavelength <= 5000.6)

    transmissions = model.component_transmissions_on(wavelength)

    for _, flux in transmissions:
        np.testing.assert_array_equal(np.isnan(flux), masked)


def test_component_transmissions_skip_disabled_components() -> None:
    """A disabled absorber contributes no curve, matching the composite model."""
    model = _absorber_model()
    model.components[0].enabled = False

    transmissions = model.component_transmissions_on(
        np.linspace(5000.0, 5002.0, 400, dtype=np.float64)
    )

    assert [component_id for component_id, _ in transmissions] == ["abs-2"]
