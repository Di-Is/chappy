import pytest

from chappy.core.masking import MaskDefinition, MaskMode
from chappy.core.spectrum_model import SpectrumModel


def test_mask_definition_range_properties() -> None:
    mask = MaskDefinition.from_range(5100.0, 5200.0, label="Telluric")

    assert mask.mode is MaskMode.RANGE
    assert pytest.approx(mask.wavelength_min) == 5100.0
    assert pytest.approx(mask.wavelength_max) == 5200.0
    assert pytest.approx(mask.center or 0.0) == 5150.0
    assert pytest.approx(mask.full_width) == 100.0
    assert mask.as_tuple() == (5100.0, 5200.0)


def test_spectrum_model_mask_ranges_group_filtering() -> None:
    model = SpectrumModel()

    group_mask = MaskDefinition.from_range(
        1020.0, 1030.0, label="Group", identifier="m-group"
    ).with_group_id("grp-1")
    other_group_mask = MaskDefinition.from_range(
        1000.0, 1010.0, label="Other Group", identifier="m-other"
    ).with_group_id("grp-2")
    disabled_mask = MaskDefinition(
        identifier="m-disabled",
        label="Disabled",
        mode=MaskMode.RANGE,
        start_wavelength=1040.0,
        end_wavelength=1050.0,
        enabled=False,
        group_id="grp-1",
    )

    model.mask_definitions = [other_group_mask, group_mask, disabled_mask]

    assert model.mask_ranges() == [(1000.0, 1010.0), (1020.0, 1030.0)]
    assert model.mask_ranges_for_group("grp-1") == [(1020.0, 1030.0)]
    assert model.mask_ranges_for_group("grp-2") == [(1000.0, 1010.0)]
    assert model.mask_ranges_for_group("grp-unknown") == []
