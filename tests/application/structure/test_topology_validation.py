"""Corruption matrix for baseline-aware structure topology validation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pytest

from chappy.application.structure import (
    StructureTopologyValidationError,
    StructureTopologyValidator,
    StructureTopologyViolation,
    StructureTopologyViolationKind,
)
from chappy.core.absorption.models import UNASSIGNED_REGION_ID, AbsorptionLine, AbsorptionRegion
from chappy.core.components.absorber import AbsorberComponent
from chappy.core.masking import MaskDefinition
from chappy.core.spectrum_model import SpectrumModel


@dataclass(slots=True)
class _Project:
    """Minimal project facts consumed by the reusable validator."""

    absorption_regions: dict[str, AbsorptionRegion]
    absorption_lines: dict[str, AbsorptionLine]
    model: SpectrumModel


@dataclass(frozen=True, slots=True)
class _CorruptionCase:
    """One exact postcondition corruption and its expected violations."""

    name: str
    corrupt: Callable[[_Project], None]
    expected: frozenset[StructureTopologyViolation]


def _line(line_id: str) -> AbsorptionLine:
    """Build one line assigned to the common valid region."""
    return AbsorptionLine(
        line_id=line_id,
        species="C IV",
        rest_wavelength=1548.2,
        center_z=2.0,
        window_kms=200.0,
        multiplet_label="C IV",
        transition_name="1548",
        oscillator_strength=0.19,
        gamma_value=2.64e8,
        region_id="region",
    )


def _project() -> _Project:
    """Build a clean topology with line, model, mask, and region references."""
    model = SpectrumModel()
    model.add_component_storage(AbsorberComponent(component_id="component-1", group_id="region"))
    mask = MaskDefinition.from_range(100.0, 110.0, identifier="mask-1").with_group_id("region")
    model.restore_mask_definitions_for_transaction((mask,), model_was_valid=False)
    lines = {line_id: _line(line_id) for line_id in ("line-1", "line-2", "line-3")}
    return _Project(
        absorption_regions={"region": AbsorptionRegion(region_id="region", line_ids=list(lines))},
        absorption_lines=lines,
        model=model,
    )


def _set_multiplets(project: _Project, links: dict[str, tuple[str, ...]]) -> None:
    """Replace selected multiplet links for one matrix row."""
    for line_id, related_ids in links.items():
        project.absorption_lines[line_id].multiplet_ids[:] = related_ids


def _replace_mask_group(project: _Project, group_id: str | None) -> None:
    """Replace the current mask group without invoking unrelated validation."""
    mask = project.model.mask_definitions[0].with_group_id(group_id)
    project.model.restore_mask_definitions_for_transaction((mask,), model_was_valid=False)


_CORRUPTION_CASES = (
    _CorruptionCase(
        "missing-multiplet",
        lambda project: project.absorption_lines["line-1"].multiplet_ids.append("missing"),
        frozenset(
            {
                StructureTopologyViolation(
                    StructureTopologyViolationKind.MISSING_MULTIPLET_REFERENCE, "line-1", "missing"
                )
            }
        ),
    ),
    _CorruptionCase(
        "self-multiplet",
        lambda project: project.absorption_lines["line-1"].multiplet_ids.append("line-1"),
        frozenset(
            {
                StructureTopologyViolation(
                    StructureTopologyViolationKind.SELF_MULTIPLET_REFERENCE, "line-1", "line-1"
                )
            }
        ),
    ),
    _CorruptionCase(
        "duplicate-multiplet",
        lambda project: _set_multiplets(
            project, {"line-1": ("line-2", "line-2"), "line-2": ("line-1",)}
        ),
        frozenset(
            {
                StructureTopologyViolation(
                    StructureTopologyViolationKind.DUPLICATE_MULTIPLET_REFERENCE,
                    "line-1",
                    "line-2",
                    2,
                )
            }
        ),
    ),
    _CorruptionCase(
        "asymmetric-multiplet",
        lambda project: _set_multiplets(project, {"line-1": ("line-2",)}),
        frozenset(
            {
                StructureTopologyViolation(
                    StructureTopologyViolationKind.ASYMMETRIC_MULTIPLET_REFERENCE,
                    "line-1",
                    "line-2",
                )
            }
        ),
    ),
    _CorruptionCase(
        "incomplete-multiplet-closure",
        lambda project: _set_multiplets(
            project, {"line-1": ("line-2",), "line-2": ("line-1", "line-3"), "line-3": ("line-2",)}
        ),
        frozenset(
            {
                StructureTopologyViolation(
                    StructureTopologyViolationKind.INCOMPLETE_MULTIPLET_CLOSURE, "line-1", "line-3"
                ),
                StructureTopologyViolation(
                    StructureTopologyViolationKind.INCOMPLETE_MULTIPLET_CLOSURE, "line-3", "line-1"
                ),
            }
        ),
    ),
    _CorruptionCase(
        "missing-line-model",
        lambda project: project.absorption_lines["line-1"].model_ids.append("missing"),
        frozenset(
            {
                StructureTopologyViolation(
                    StructureTopologyViolationKind.MISSING_LINE_MODEL_REFERENCE,
                    "line-1",
                    "missing",
                )
            }
        ),
    ),
    _CorruptionCase(
        "duplicate-line-model",
        lambda project: project.absorption_lines["line-1"].model_ids.extend(
            ("component-1", "component-1")
        ),
        frozenset(
            {
                StructureTopologyViolation(
                    StructureTopologyViolationKind.DUPLICATE_LINE_MODEL_REFERENCE,
                    "line-1",
                    "component-1",
                    2,
                )
            }
        ),
    ),
    _CorruptionCase(
        "missing-mask-region",
        lambda project: _replace_mask_group(project, "missing"),
        frozenset(
            {
                StructureTopologyViolation(
                    StructureTopologyViolationKind.MISSING_MASK_REGION_REFERENCE,
                    "mask-1",
                    "missing",
                )
            }
        ),
    ),
    _CorruptionCase(
        "missing-component-region",
        lambda project: project.model.components[0].set_group("missing"),
        frozenset(
            {
                StructureTopologyViolation(
                    StructureTopologyViolationKind.MISSING_COMPONENT_REGION_REFERENCE,
                    "component-1",
                    "missing",
                )
            }
        ),
    ),
)


@pytest.mark.parametrize("case", _CORRUPTION_CASES, ids=lambda case: case.name)
def test_corruption_matrix_rejects_exact_new_violations(case: _CorruptionCase) -> None:
    """Every required cross-reference defect is detected without extra categories."""
    project = _project()
    validator = StructureTopologyValidator()
    baseline = validator.capture(project)

    case.corrupt(project)

    validation = validator.capture(project)
    assert validation.violations == case.expected
    with pytest.raises(StructureTopologyValidationError) as raised:
        validator.require_no_regressions(project, baseline)
    assert raised.value.regressions == tuple(sorted(case.expected))


@pytest.mark.parametrize("case", _CORRUPTION_CASES, ids=lambda case: case.name)
def test_unchanged_legacy_corruption_is_allowed(case: _CorruptionCase) -> None:
    """An unrelated mutation is not blocked by an identical legacy defect."""
    project = _project()
    case.corrupt(project)
    validator = StructureTopologyValidator()
    baseline = validator.capture(project)

    project.absorption_regions["region"].display_color = "#ffffff"

    validator.require_no_regressions(project, baseline)


def test_duplicate_occurrences_distinguish_improvement_from_worsening() -> None:
    """Occurrence identities allow reduced duplication but reject one added duplicate."""
    project = _project()
    line = project.absorption_lines["line-1"]
    line.model_ids[:] = ("component-1", "component-1")
    validator = StructureTopologyValidator()
    baseline = validator.capture(project)

    line.model_ids.append("component-1")
    with pytest.raises(StructureTopologyValidationError) as raised:
        validator.require_no_regressions(project, baseline)
    assert raised.value.regressions == (
        StructureTopologyViolation(
            StructureTopologyViolationKind.DUPLICATE_LINE_MODEL_REFERENCE,
            "line-1",
            "component-1",
            3,
        ),
    )

    improved_baseline = validator.capture(project)
    line.model_ids.pop()
    validator.require_no_regressions(project, improved_baseline)


def test_none_and_unassigned_group_references_are_valid() -> None:
    """Global and unassigned group sentinels do not require stored regions."""
    project = _project()
    component = project.model.components[0]
    assert isinstance(component, AbsorberComponent)
    component.set_group(UNASSIGNED_REGION_ID)
    _replace_mask_group(project, None)

    validation = StructureTopologyValidator().capture(project)

    assert not validation.violations
