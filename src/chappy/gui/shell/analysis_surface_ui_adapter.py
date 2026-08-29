"""Shell adapter applying semantic Analysis policy to concrete GUI surfaces."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from chappy.core.editing_mode import EditingMode
from chappy.gui.modes.analysis.contracts import SpectrumProfile
from chappy.gui.modes.analysis.surface_policy import (
    AnalysisSemanticAction,
    AnalysisSurfaceUiPolicy,
)
from chappy.gui.shell.actions.ids import ShellActionId
from chappy.gui.shell.spectrum_mode_policy import spectrum_interaction_mode_policy
from chappy.gui.spectrum.policy import (
    SpectrumInputCapabilities,
    SpectrumPlotPolicy,
    SpectrumPolicy,
    SpectrumTransitionCleanup,
)
from chappy.presentation.spectrum import SpectrumPlotDisplayCommand

if TYPE_CHECKING:
    from collections.abc import Mapping
    from typing import Protocol

    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import QWidget

    from chappy.gui.modes.analysis.region_detail.ui_facade import RegionDetailUi
    from chappy.gui.modes.analysis.workspace import AnalysisWorkspace
    from chappy.gui.spectrum.spectrum_view import SpectrumView

    class _OverviewRefreshPort(Protocol):
        """Overview panel operation required to rebuild it on surface entry."""

        def refresh(self) -> None: ...


@dataclass(frozen=True, slots=True)
class AnalysisSurfaceUiPorts:
    """Concrete shell consumers updated by one Analysis policy commit."""

    workspace: AnalysisWorkspace
    spectrum_view: SpectrumView
    bottom_pane: QWidget
    data_control: QWidget
    actions: Mapping[ShellActionId, QAction]


class AnalysisSurfaceUiAdapter:
    """Translate Analysis semantics into spectrum, stacks, docks, and actions."""

    def __init__(self, ports: AnalysisSurfaceUiPorts) -> None:
        self._ports = ports
        self._current_policy: AnalysisSurfaceUiPolicy | None = None

    @property
    def current_policy(self) -> AnalysisSurfaceUiPolicy | None:
        """Return the last fully applied semantic policy."""
        return self._current_policy

    def apply(self, policy: AnalysisSurfaceUiPolicy) -> None:
        """Apply one complete policy, rolling concrete UI back on failure."""
        previous = self._current_policy
        try:
            self._ports.spectrum_view.apply_policy(self._spectrum_policy(policy.spectrum_profile))
            self._ports.workspace.apply_policy(policy)
            self._ports.bottom_pane.setVisible(True)
            self._ports.data_control.setVisible(policy.data_control_visible)
            self._apply_actions(policy)
        except Exception:
            if previous is not None:
                self._ports.spectrum_view.apply_policy(
                    self._spectrum_policy(previous.spectrum_profile)
                )
                self._ports.workspace.apply_policy(previous)
                self._ports.data_control.setVisible(previous.data_control_visible)
                self._apply_actions(previous)
            raise
        self._current_policy = policy

    @staticmethod
    def _spectrum_policy(profile: SpectrumProfile) -> SpectrumPolicy:
        return analysis_spectrum_policy(profile)

    def _apply_actions(self, policy: AnalysisSurfaceUiPolicy) -> None:
        mapping = {
            ShellActionId.FIT_MODEL: AnalysisSemanticAction.FIT,
            ShellActionId.TOGGLE_VELOCITY_PLOT_ANALYSIS: AnalysisSemanticAction.TOGGLE_VELOCITY,
            ShellActionId.ANALYSIS_BACK: AnalysisSemanticAction.RETURN_TO_OVERVIEW,
            ShellActionId.DELETE: AnalysisSemanticAction.STRUCTURE_DELETE,
        }
        for action_id, capability in mapping.items():
            action = self._ports.actions.get(action_id)
            if action is not None:
                allowed = policy.allows(capability)
                action.setEnabled(allowed)
                if action_id is ShellActionId.ANALYSIS_BACK:
                    action.setVisible(allowed)


class AnalysisSurfacePresentationAdapter:
    """Rebuild the destination Analysis surface from current project state."""

    def __init__(
        self, *, overview_panel: _OverviewRefreshPort, detail_panel: RegionDetailUi
    ) -> None:
        self._overview_panel = overview_panel
        self._detail_panel = detail_panel

    def refresh_overview(self) -> None:
        """Rebuild the Overview review table."""
        self._overview_panel.refresh()

    def refresh_region_detail(self, region_id: str) -> None:
        """Rebuild the Region Detail panel for one region."""
        self._detail_panel.render_focused_region(region_id)


def analysis_spectrum_policy(profile: SpectrumProfile) -> SpectrumPolicy:
    """Translate one semantic Analysis profile into the neutral spectrum contract."""
    if profile is SpectrumProfile.OVERVIEW:
        return spectrum_interaction_mode_policy(EditingMode.ANALYSIS)
    return SpectrumPolicy(
        input_capabilities=SpectrumInputCapabilities(
            identify_velocity_shortcut_enabled=False,
            detail_velocity_shortcut_enabled=True,
            identify_click_enabled=False,
            optimize_shift_click_enabled=True,
            absorber_drag_enabled=True,
        ),
        plot_policy=SpectrumPlotPolicy(
            display_command=SpectrumPlotDisplayCommand(
                use_normalized_observed=True, render_absorption_line_labels=False
            ),
            show_model_and_residual=True,
            show_mask_regions=True,
            show_absorption_line_markers=True,
        ),
        cursor_enabled=True,
        fit_model_enabled=True,
        start_overlay_active=False,
        transition_cleanup=SpectrumTransitionCleanup(),
    )


__all__ = [
    "AnalysisSurfacePresentationAdapter",
    "AnalysisSurfaceUiAdapter",
    "AnalysisSurfaceUiPorts",
    "analysis_spectrum_policy",
]
