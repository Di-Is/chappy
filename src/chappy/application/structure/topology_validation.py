"""Baseline-aware postcondition validation for scientific structure topology."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from chappy.core.absorption.models import UNASSIGNED_REGION_ID
from chappy.core.components.absorber import AbsorberComponent

if TYPE_CHECKING:
    from .topology import StructureTopologyProjectPort


class StructureTopologyViolationKind(StrEnum):
    """Stable categories of structure topology corruption."""

    MISSING_MULTIPLET_REFERENCE = "missing_multiplet_reference"
    SELF_MULTIPLET_REFERENCE = "self_multiplet_reference"
    DUPLICATE_MULTIPLET_REFERENCE = "duplicate_multiplet_reference"
    ASYMMETRIC_MULTIPLET_REFERENCE = "asymmetric_multiplet_reference"
    INCOMPLETE_MULTIPLET_CLOSURE = "incomplete_multiplet_closure"
    MISSING_LINE_MODEL_REFERENCE = "missing_line_model_reference"
    DUPLICATE_LINE_MODEL_REFERENCE = "duplicate_line_model_reference"
    MISSING_MASK_REGION_REFERENCE = "missing_mask_region_reference"
    MISSING_COMPONENT_REGION_REFERENCE = "missing_component_region_reference"


@dataclass(frozen=True, order=True, slots=True)
class StructureTopologyViolation:
    """One stable, comparable topology violation identity."""

    kind: StructureTopologyViolationKind
    owner_id: str
    related_id: str = ""
    occurrence: int = 1


@dataclass(frozen=True, slots=True)
class StructureTopologyValidation:
    """Immutable set of topology violations at one transaction boundary."""

    violations: frozenset[StructureTopologyViolation]

    def regressions_from(
        self, baseline: StructureTopologyValidation
    ) -> tuple[StructureTopologyViolation, ...]:
        """Return newly introduced or worsened violations in stable order."""
        return tuple(sorted(self.violations - baseline.violations))


class StructureTopologyValidationError(ValueError):
    """Raised when a structure mutation introduces topology corruption."""

    def __init__(self, regressions: tuple[StructureTopologyViolation, ...]) -> None:
        self.regressions = regressions
        summary = ", ".join(
            f"{violation.kind.value}:{violation.owner_id}:{violation.related_id}"
            for violation in regressions
        )
        super().__init__(f"Structure mutation introduced topology violations: {summary}")


class StructureTopologyValidator:
    """Validate cross-object references without rejecting unchanged legacy defects."""

    def capture(self, project: StructureTopologyProjectPort) -> StructureTopologyValidation:
        """Capture every currently observable topology violation."""
        violations: set[StructureTopologyViolation] = set()
        lines = project.absorption_lines

        for line_id, line in lines.items():
            multiplet_ids = tuple(line.multiplet_ids)
            violations.update(
                _duplicate_violations(
                    StructureTopologyViolationKind.DUPLICATE_MULTIPLET_REFERENCE,
                    line_id,
                    multiplet_ids,
                )
            )
            for related_id in set(multiplet_ids):
                if related_id == line_id:
                    violations.add(
                        StructureTopologyViolation(
                            StructureTopologyViolationKind.SELF_MULTIPLET_REFERENCE,
                            line_id,
                            related_id,
                        )
                    )
                    continue
                related = lines.get(related_id)
                if related is None:
                    violations.add(
                        StructureTopologyViolation(
                            StructureTopologyViolationKind.MISSING_MULTIPLET_REFERENCE,
                            line_id,
                            related_id,
                        )
                    )
                elif line_id not in related.multiplet_ids:
                    violations.add(
                        StructureTopologyViolation(
                            StructureTopologyViolationKind.ASYMMETRIC_MULTIPLET_REFERENCE,
                            line_id,
                            related_id,
                        )
                    )

        violations.update(_multiplet_closure_violations(project))

        absorber_ids = {
            component.id
            for component in project.model.components
            if isinstance(component, AbsorberComponent)
        }
        for line_id, line in lines.items():
            model_ids = tuple(line.model_ids)
            violations.update(
                _duplicate_violations(
                    StructureTopologyViolationKind.DUPLICATE_LINE_MODEL_REFERENCE,
                    line_id,
                    model_ids,
                )
            )
            violations.update(
                StructureTopologyViolation(
                    StructureTopologyViolationKind.MISSING_LINE_MODEL_REFERENCE,
                    line_id,
                    component_id,
                )
                for component_id in set(model_ids) - absorber_ids
            )

        valid_region_ids = {*project.absorption_regions, UNASSIGNED_REGION_ID}
        violations.update(
            StructureTopologyViolation(
                StructureTopologyViolationKind.MISSING_MASK_REGION_REFERENCE,
                mask.identifier,
                mask.group_id,
            )
            for mask in project.model.mask_definitions
            if mask.group_id is not None and mask.group_id not in valid_region_ids
        )
        violations.update(
            StructureTopologyViolation(
                StructureTopologyViolationKind.MISSING_COMPONENT_REGION_REFERENCE,
                component.id,
                component.group_id,
            )
            for component in project.model.components
            if isinstance(component, AbsorberComponent)
            and component.group_id is not None
            and component.group_id not in valid_region_ids
        )
        return StructureTopologyValidation(frozenset(violations))

    def require_no_regressions(
        self, project: StructureTopologyProjectPort, baseline: StructureTopologyValidation
    ) -> None:
        """Reject violations that were absent from the transaction baseline."""
        regressions = self.capture(project).regressions_from(baseline)
        if regressions:
            raise StructureTopologyValidationError(regressions)


def _duplicate_violations(
    kind: StructureTopologyViolationKind, owner_id: str, values: tuple[str, ...]
) -> set[StructureTopologyViolation]:
    """Represent each excess occurrence so reduced legacy duplication is allowed."""
    counts: dict[str, int] = {}
    violations: set[StructureTopologyViolation] = set()
    for value in values:
        occurrence = counts.get(value, 0) + 1
        counts[value] = occurrence
        if occurrence > 1:
            violations.add(StructureTopologyViolation(kind, owner_id, value, occurrence))
    return violations


def _multiplet_closure_violations(
    project: StructureTopologyProjectPort,
) -> set[StructureTopologyViolation]:
    """Require each symmetric connected multiplet component to form a closed group."""
    lines = project.absorption_lines
    mutual_neighbors = {
        line_id: {
            related_id
            for related_id in line.multiplet_ids
            if related_id != line_id
            and related_id in lines
            and line_id in lines[related_id].multiplet_ids
        }
        for line_id, line in lines.items()
    }
    violations: set[StructureTopologyViolation] = set()
    pending = set(lines)
    while pending:
        first = min(pending)
        component: set[str] = set()
        frontier = [first]
        while frontier:
            line_id = frontier.pop()
            if line_id in component:
                continue
            component.add(line_id)
            frontier.extend(mutual_neighbors[line_id] - component)
        pending.difference_update(component)
        if len(component) < 3:
            continue
        for line_id in component:
            for related_id in component - {line_id} - mutual_neighbors[line_id]:
                violations.add(
                    StructureTopologyViolation(
                        StructureTopologyViolationKind.INCOMPLETE_MULTIPLET_CLOSURE,
                        line_id,
                        related_id,
                    )
                )
    return violations


__all__ = [
    "StructureTopologyValidation",
    "StructureTopologyValidationError",
    "StructureTopologyValidator",
    "StructureTopologyViolation",
    "StructureTopologyViolationKind",
]
