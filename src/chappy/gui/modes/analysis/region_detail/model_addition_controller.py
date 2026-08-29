"""Controller for optimize model-addition entrypoints."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Protocol

from PySide6.QtCore import QPoint

from chappy.application.analysis_artifacts import (
    GlobalAnalysisMutationUseCase,
    run_postcommit_actions_isolated,
)
from chappy.application.optimize import (
    AbsorberModelTopologyUseCase,
    ModelAdditionRequest,
    component_topology_change_set,
    model_addition_wavelength_range,
)
from chappy.core.constants import LIGHT_SPEED_KMS
from chappy.gui.theme import create_styled_menu

if TYPE_CHECKING:
    from contextlib import AbstractContextManager

    from PySide6.QtWidgets import QWidget

    from chappy.core.absorption.models import AbsorptionLine
    from chappy.core.components.absorber import AbsorberComponent
    from chappy.core.components.tie_set import ParameterTieSet
    from chappy.core.spectroscopy_project import SpectroscopyProject

logger = logging.getLogger(__name__)


class OptimizeModelAdditionPort(Protocol):
    """Panel operations required by model-addition entrypoints."""

    def selected_model_addition_line(self) -> AbsorptionLine | None:
        """Return the currently selected absorption line."""
        ...

    def model_addition_project(self) -> SpectroscopyProject | None:
        """Return the active project."""
        ...

    def line_wavelength_range_for_model_addition(
        self, line: AbsorptionLine
    ) -> tuple[float, float] | None:
        """Return the observed wavelength range accepted for a line."""
        ...

    def record_model_addition(
        self, components: dict[str, AbsorberComponent], tie_sets: tuple[ParameterTieSet, ...]
    ) -> None:
        """Record model components added by the workflow."""
        ...

    def finalise_model_addition(
        self, components: dict[str, AbsorberComponent], *, focus_line: AbsorptionLine
    ) -> None:
        """Refresh UI state after adding model components."""
        ...

    def model_addition_history_atomic_recording(self) -> AbstractContextManager[None]:
        """Return the required atomic history scope."""
        ...


class ModelAdditionResultPort(Protocol):
    """Application result required by the optimize model-addition controller."""

    @property
    def components_by_line_id(self) -> dict[str, AbsorberComponent]:
        """Return created components keyed by absorption line identifier."""
        ...

    @property
    def tie_sets(self) -> tuple[ParameterTieSet, ...]:
        """Return materialized parameter tie sets created by the use case."""
        ...


class OptimizeModelAdditionUseCasePort(Protocol):
    """Application use case operations required by the optimize GUI controller."""

    def add_components(
        self, project: SpectroscopyProject, line: AbsorptionLine, request: ModelAdditionRequest
    ) -> ModelAdditionResultPort:
        """Create model components for the selected line."""
        ...


class OptimizeModelAdditionController:
    """Coordinate model-addition entrypoints for optimize mode."""

    def __init__(
        self,
        port: OptimizeModelAdditionPort,
        usecase: OptimizeModelAdditionUseCasePort,
        *,
        topology: AbsorberModelTopologyUseCase | None = None,
        mutations: GlobalAnalysisMutationUseCase | None = None,
    ) -> None:
        """Initialize the controller.

        Args:
            port: Panel port used to perform mutation and UI finalization.
            usecase: Application use case.
            topology: Exact absorber topology snapshot use case.
            mutations: Global scientific mutation transaction.
        """
        self._port = port
        self._usecase = usecase
        self._topology = topology or AbsorberModelTopologyUseCase()
        self._mutations = mutations or GlobalAnalysisMutationUseCase()

    def add_to_selected_line(self) -> None:
        """Add default model components to the selected line."""
        line = self._port.selected_model_addition_line()
        if line is None:
            return
        self.add_to_line(line)

    def add_to_line(self, line: AbsorptionLine) -> None:
        """Add default model components to an explicit absorption line."""
        components = self._add_models_for_line(
            line,
            ModelAdditionRequest(
                redshift=line.center_z, column_density=13.0, b_parameter=10.0, covering_factor=1.0
            ),
        )
        if components:
            self._finalise_model_addition(components, focus_line=line)

    def add_at_wavelength(self, wavelength: float) -> None:
        """Add model components at an observed wavelength."""
        line = self._port.selected_model_addition_line()
        if line is None:
            return

        bounds = self._port.line_wavelength_range_for_model_addition(line)
        if bounds is None:
            logger.info(
                "Rejecting model addition at %.4f Å: no bounds for line %s",
                wavelength,
                line.line_id,
            )
            return

        low, high = bounds
        if not (low <= wavelength <= high):
            logger.info(
                "Rejected model addition at %.4f Å outside selected line %s range",
                wavelength,
                line.line_id,
            )
            return

        initial_z = (wavelength / line.rest_wavelength) - 1.0
        components = self._add_models_for_line(
            line,
            ModelAdditionRequest(
                redshift=initial_z, column_density=13.0, b_parameter=10.0, covering_factor=1.0
            ),
        )
        logger.info(
            "Added %d model component(s) for line %s via shift-click at %.4f Å",
            len(components),
            line.line_id,
            wavelength,
        )
        if components:
            self._finalise_model_addition(components, focus_line=line)

    def add_from_velocity(
        self, velocity: float, line: AbsorptionLine, rest_wavelength: float, center_z: float
    ) -> None:
        """Add model components from a velocity-space position."""
        wavelength = rest_wavelength * (1.0 + center_z) * (1.0 + velocity / LIGHT_SPEED_KMS)
        initial_z = (wavelength / line.rest_wavelength) - 1.0

        components = self._add_models_for_line(
            line,
            ModelAdditionRequest(
                redshift=initial_z, column_density=13.0, b_parameter=10.0, covering_factor=1.0
            ),
        )
        logger.info(
            "Added %d model component(s) for line %s from velocity plot at v=%.1f km/s (λ=%.4f Å)",
            len(components),
            line.line_id,
            velocity,
            wavelength,
        )
        if components:
            self._finalise_model_addition(components, focus_line=line)

    def add_from_velocity_line_id(
        self, velocity: float, line_id: str, rest_wavelength: float, center_z: float
    ) -> None:
        """Add model components from a velocity-space line identifier."""
        project = self._port.model_addition_project()
        if project is None:
            return

        line = project.absorption_lines.get(line_id)
        if line is None:
            logger.warning(
                "Cannot add component via Shift+click: line %s not found in project", line_id
            )
            return

        self.add_from_velocity(velocity, line, rest_wavelength, center_z)

    def show_velocity_context_menu(
        self,
        parent: QWidget,
        *,
        add_label: str,
        velocity: float,
        line_id: str,
        rest_wavelength: float,
        center_z: float,
        global_x: int,
        global_y: int,
    ) -> None:
        """Show the velocity model-addition context menu."""
        project = self._port.model_addition_project()
        if project is None:
            return

        line = project.absorption_lines.get(line_id)
        if line is None:
            logger.warning("Cannot add component: line %s not found in project", line_id)
            return

        menu = create_styled_menu(parent)
        add_action = menu.addAction(add_label)
        add_action.triggered.connect(
            lambda: self.add_from_velocity(velocity, line, rest_wavelength, center_z)
        )
        menu.exec(QPoint(global_x, global_y))

    def _add_models_for_line(
        self, line: AbsorptionLine, request: ModelAdditionRequest
    ) -> dict[str, AbsorberComponent]:
        """Create absorber components for the selected line and multiplet siblings."""
        project = self._port.model_addition_project()
        if project is None:
            msg = "Active project is required before adding optimize model components."
            raise RuntimeError(msg)

        topology_before = self._topology.capture(project)
        result: ModelAdditionResultPort | None = None

        def mutate() -> bool:
            nonlocal result
            result = self._usecase.add_components(project, line, request)
            return bool(result.components_by_line_id)

        def record_history() -> None:
            if result is None or not result.components_by_line_id:
                msg = "Cannot record an empty model addition."
                raise RuntimeError(msg)
            self._port.record_model_addition(result.components_by_line_id, result.tie_sets)

        impact = self._mutations.execute(
            project,
            mutate=mutate,
            rollback=lambda: self._topology.restore(project, topology_before),
            record_history=record_history,
            history_scope=self._port.model_addition_history_atomic_recording,
            postcommit_changes=lambda: component_topology_change_set(
                added_ids=(
                    tuple(component.id for component in result.components_by_line_id.values())
                    if result is not None
                    else ()
                )
            ),
        )
        if not impact.changed:
            return {}
        if result is None:
            msg = "Model addition returned no result."
            raise RuntimeError(msg)
        return result.components_by_line_id

    def _finalise_model_addition(
        self, components: dict[str, AbsorberComponent], *, focus_line: AbsorptionLine
    ) -> None:
        """Refresh the model-addition UI after the scientific commit."""
        run_postcommit_actions_isolated(
            lambda: self._port.finalise_model_addition(components, focus_line=focus_line)
        )


def model_addition_wavelength_range_for_line(
    line: AbsorptionLine | None,
) -> tuple[float, float] | None:
    """Return the accepted observed wavelength range for model addition."""
    if line is None:
        return None
    return model_addition_wavelength_range(line)
