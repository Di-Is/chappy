"""Shell owner for project-scoped Analysis navigation and legacy mode entry."""

from __future__ import annotations

import math
from dataclasses import replace
from typing import TYPE_CHECKING
from weakref import WeakKeyDictionary

from PySide6.QtCore import QObject, Signal

from chappy.core.absorption.models import UNASSIGNED_REGION_ID
from chappy.core.editing_mode import EditingMode
from chappy.gui.modes.common.analysis_navigation import (
    AnalysisNavigationPersistenceIssue,
    AnalysisNavigationPersistenceOperation,
    AnalysisNavigationSettingsError,
    AnalysisNavigationSettingsPort,
    AnalysisNavigationState,
    AnalysisSurface,
    StructureSelectionIds,
    normalize_analysis_overview_column_state,
)
from chappy.gui.shell.project_context import ProjectContextChanged, ProjectContextChangeReason
from chappy.presentation.spectrum import SpectrumDisplayOptions

if TYPE_CHECKING:
    from collections.abc import Callable

    from chappy.core.analysis import AnalysisReadiness
    from chappy.core.spectroscopy_project import SpectroscopyProject
    from chappy.gui.modes.common.project_key import ProjectKey


class AnalysisEntryResolver:
    """Resolve one legacy top-level mode from a complete project context."""

    def resolve(self, event: ProjectContextChanged) -> EditingMode | None:
        """Return the mode to enter, or None when Save As keeps the current mode."""
        if event.reason is ProjectContextChangeReason.CLOSE:
            return EditingMode.START
        if event.reason is ProjectContextChangeReason.CREATE:
            return EditingMode.IDENTIFY
        if event.reason is ProjectContextChangeReason.SAVE_AS:
            return None
        return EditingMode.ANALYSIS


class AnalysisNavigationCoordinator(QObject):
    """Own Analysis IDs, persistence, project validation, and legacy projection."""

    persistence_error = Signal(object)  # AnalysisNavigationPersistenceIssue
    surface_changed = Signal(object)  # AnalysisSurface
    focused_region_changed = Signal(object)  # str | None
    display_options_changed = Signal(object)  # SpectrumDisplayOptions

    def __init__(
        self,
        *,
        settings: AnalysisNavigationSettingsPort,
        enter_mode: Callable[[EditingMode], None],
        parent: QObject | None = None,
    ) -> None:
        """Initialize navigation ownership with shell-provided adapters."""
        super().__init__(parent)
        self._settings = settings
        self._enter_mode = enter_mode
        self._entry_resolver = AnalysisEntryResolver()
        self._project: SpectroscopyProject | None = None
        self._project_key: ProjectKey | None = None
        self._state = AnalysisNavigationState()
        self._session_states: WeakKeyDictionary[SpectroscopyProject, AnalysisNavigationState] = (
            WeakKeyDictionary()
        )
        self._context_switching = False

    @property
    def state(self) -> AnalysisNavigationState:
        """Return the current immutable navigation state."""
        return self._state

    @property
    def project_key(self) -> ProjectKey | None:
        """Return the local UI key paired with the current navigation state."""
        return self._project_key

    def handle_project_context_changing(self) -> None:
        """Block panel-originated focus writes while project UI is refreshing."""
        self._context_switching = True

    def handle_project_context_changed(self, event: ProjectContextChanged) -> None:
        """Restore, validate, and project navigation after an atomic context change."""
        self._cache_session_state()
        try:
            if event.reason is ProjectContextChangeReason.SAVE_AS:
                state = self._state
                self._migrate_save_as(event, state)
            else:
                state = self._load_state(event.new_key, event.project)

            self._project = event.project
            self._project_key = event.new_key
            self._state = self._validated_state(state, event.project)
            self.display_options_changed.emit(self.display_options())
            target_mode = self._entry_resolver.resolve(event)
            if target_mode is not None:
                self._enter_mode(target_mode)
        finally:
            self._context_switching = False

    def set_surface(self, surface: AnalysisSurface) -> None:
        """Set and persist the current Analysis surface."""
        if surface is AnalysisSurface.REGION_DETAIL and not self._is_valid_focus(
            self._project, self._state.focused_region_id
        ):
            surface = AnalysisSurface.OVERVIEW
        if self._state.surface is surface:
            return
        self._state = self._state.with_surface(surface)
        self._persist_current_state()
        self.surface_changed.emit(surface)

    def focus_region(self, region_id: str) -> bool:
        """Focus a current-project region as the canonical Analysis selection."""
        if self._context_switching or self._project is None:
            return False
        if not self._is_valid_focus(self._project, region_id):
            return False
        if self._state.focused_region_id == region_id:
            return True
        self._state = self._state.with_focused_region(region_id)
        self._persist_current_state()
        self.focused_region_changed.emit(region_id)
        return True

    def focused_region_id(self) -> str | None:
        """Return the canonical Analysis Detail focused region ID, if any."""
        return self._state.focused_region_id

    def clear_focus_if(self, region_id: str) -> None:
        """Clear focus and return to Overview after the exact current region has been removed."""
        if self._state.focused_region_id != region_id:
            return
        surface_before = self._state.surface
        self._state = self._state.with_focused_region(None).with_surface(AnalysisSurface.OVERVIEW)
        self._persist_current_state()
        self.focused_region_changed.emit(None)
        if surface_before is not AnalysisSurface.OVERVIEW:
            self.surface_changed.emit(AnalysisSurface.OVERVIEW)

    def clear_focus_only_if(self, region_id: str) -> None:
        """Clear focus after a region removal without changing the current surface."""
        if self._state.focused_region_id != region_id:
            return
        self._state = self._state.with_focused_region(None)
        self._persist_current_state()
        self.focused_region_changed.emit(None)

    def select_overview_region(self, region_id: str | None) -> bool:
        """Update Overview row selection without changing Detail focus or surface."""
        if self._context_switching or self._project is None:
            return False
        if region_id is not None and not self._is_valid_focus(self._project, region_id):
            return False
        if (
            self._state.overview_selection == region_id
            and self._state.focused_region_id == region_id
        ):
            return True
        self._state = replace(
            self._state.with_focused_region(region_id), overview_selection=region_id
        )
        self._persist_current_state()
        self.focused_region_changed.emit(region_id)
        return True

    def update_overview_view(
        self,
        *,
        filter_text: str,
        filter_readiness: tuple[AnalysisReadiness, ...],
        sort_column_id: str | None,
        sort_ascending: bool,
        visible_column_ids: tuple[str, ...],
        column_order: tuple[str, ...],
        top_visible_region_id: str | None,
    ) -> None:
        """Update and persist Overview filter, columns, ordering, and scroll anchor."""
        if self._context_switching or self._project is None:
            return
        region_ids = self._project.absorption_regions
        valid_top_id = top_visible_region_id if top_visible_region_id in region_ids else None
        normalized_sort, normalized_visible, normalized_order = (
            normalize_analysis_overview_column_state(
                sort_column_id=sort_column_id,
                visible_column_ids=visible_column_ids,
                column_order=column_order,
            )
        )
        next_state = replace(
            self._state,
            filter_text=filter_text,
            filter_readiness=tuple(dict.fromkeys(filter_readiness)),
            sort_column_id=normalized_sort,
            sort_ascending=sort_ascending,
            visible_column_ids=normalized_visible,
            column_order=normalized_order,
            top_visible_region_id=valid_top_id,
        )
        if next_state == self._state:
            return
        self._state = next_state
        self._persist_current_state()

    def update_structure_selection(
        self, *, region_ids: tuple[str, ...], line_ids: tuple[str, ...]
    ) -> None:
        """Validate and retain session-only structure editor selection."""
        project = self._project
        if self._context_switching or project is None:
            return
        selection = StructureSelectionIds(
            region_ids=tuple(
                dict.fromkeys(
                    region_id
                    for region_id in region_ids
                    if region_id in project.absorption_regions
                )
            ),
            line_ids=tuple(
                dict.fromkeys(
                    line_id for line_id in line_ids if line_id in project.absorption_lines
                )
            ),
        )
        if selection == self._state.structure_selection:
            return
        self._state = replace(self._state, structure_selection=selection)
        self._cache_session_state()

    def update_spectrum_wavelength_range(
        self, wavelength_range: tuple[float, float] | None
    ) -> None:
        """Persist the current Analysis spectrum range for the project key."""
        if self._context_switching or self._project is None:
            return
        if wavelength_range is not None:
            minimum, maximum = wavelength_range
            if not math.isfinite(minimum) or not math.isfinite(maximum) or minimum >= maximum:
                msg = "Analysis spectrum wavelength range must be finite and increasing"
                raise ValueError(msg)
            wavelength_range = (float(minimum), float(maximum))
        if self._state.spectrum_wavelength_range == wavelength_range:
            return
        self._state = replace(self._state, spectrum_wavelength_range=wavelength_range)
        self._persist_current_state()

    def display_options(self) -> SpectrumDisplayOptions:
        """Return the current spectrum display options."""
        return SpectrumDisplayOptions(
            show_error_spectrum=self._state.show_error_spectrum,
            show_component_profiles=self._state.show_component_profiles,
        )

    def set_display_options(self, options: SpectrumDisplayOptions) -> None:
        """Set and persist the current spectrum display options."""
        if (
            self._state.show_error_spectrum == options.show_error_spectrum
            and self._state.show_component_profiles == options.show_component_profiles
        ):
            return
        self._state = replace(
            self._state,
            show_error_spectrum=options.show_error_spectrum,
            show_component_profiles=options.show_component_profiles,
        )
        self._persist_current_state()

    def _load_state(
        self, key: ProjectKey | None, project: SpectroscopyProject | None
    ) -> AnalysisNavigationState:
        if key is None:
            return AnalysisNavigationState()
        session_state = self._session_states.get(project) if project is not None else None
        if session_state is not None:
            return session_state
        if not key.persistent:
            return AnalysisNavigationState()
        try:
            snapshot = self._settings.load(key)
        except AnalysisNavigationSettingsError as error:
            self._report_persistence_error(AnalysisNavigationPersistenceOperation.LOAD, key, error)
            return AnalysisNavigationState()
        if snapshot is None:
            return AnalysisNavigationState()
        return AnalysisNavigationState.from_snapshot(snapshot)

    def _migrate_save_as(
        self, event: ProjectContextChanged, state: AnalysisNavigationState
    ) -> None:
        old_key = event.old_key
        new_key = event.new_key
        if new_key is None:
            return
        if not new_key.persistent:
            return
        snapshot = state.persistent_snapshot()
        try:
            if old_key is not None and old_key.persistent:
                self._settings.migrate(old_key, new_key, snapshot)
            else:
                self._settings.save(new_key, snapshot)
        except AnalysisNavigationSettingsError as error:
            self._report_persistence_error(
                AnalysisNavigationPersistenceOperation.MIGRATE, new_key, error
            )

    def _cache_session_state(self) -> None:
        if self._project is not None:
            self._session_states[self._project] = self._state

    def _persist_current_state(self) -> None:
        key = self._project_key
        project = self._project
        if key is None or project is None:
            return
        self._session_states[project] = self._state
        if key.persistent:
            try:
                self._settings.save(key, self._state.persistent_snapshot())
            except AnalysisNavigationSettingsError as error:
                self._report_persistence_error(
                    AnalysisNavigationPersistenceOperation.SAVE, key, error
                )

    def _validated_state(
        self, state: AnalysisNavigationState, project: SpectroscopyProject | None
    ) -> AnalysisNavigationState:
        if project is None:
            return AnalysisNavigationState()

        region_ids = frozenset(project.absorption_regions)
        line_ids = frozenset(project.absorption_lines)
        focused_region_id = (
            state.focused_region_id
            if self._is_valid_focus(project, state.focused_region_id)
            else None
        )
        surface = state.surface
        if surface is AnalysisSurface.REGION_DETAIL and focused_region_id is None:
            surface = AnalysisSurface.OVERVIEW
        top_visible_region_id = (
            state.top_visible_region_id if state.top_visible_region_id in region_ids else None
        )
        structure_selection = StructureSelectionIds(
            region_ids=tuple(
                region_id
                for region_id in state.structure_selection.region_ids
                if region_id in region_ids
            ),
            line_ids=tuple(
                line_id for line_id in state.structure_selection.line_ids if line_id in line_ids
            ),
        )
        return replace(
            state,
            surface=surface,
            focused_region_id=focused_region_id,
            overview_selection=focused_region_id,
            structure_selection=structure_selection,
            top_visible_region_id=top_visible_region_id,
        )

    @staticmethod
    def _is_valid_focus(project: SpectroscopyProject | None, region_id: str | None) -> bool:
        """Return whether a region can safely own the Analysis Detail surface."""
        return (
            project is not None
            and region_id is not None
            and region_id != UNASSIGNED_REGION_ID
            and project.is_region_analysis_capable(region_id)
        )

    def _report_persistence_error(
        self,
        operation: AnalysisNavigationPersistenceOperation,
        key: ProjectKey,
        error: AnalysisNavigationSettingsError,
    ) -> None:
        """Publish a non-fatal local persistence issue for shell status handling."""
        self.persistence_error.emit(
            AnalysisNavigationPersistenceIssue(
                operation=operation, project_key=key, message=str(error)
            )
        )


__all__ = ["AnalysisEntryResolver", "AnalysisNavigationCoordinator"]
