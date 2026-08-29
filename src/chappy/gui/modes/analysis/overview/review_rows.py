"""Build Analysis Overview rows from authoritative project facts."""

from __future__ import annotations

from typing import TYPE_CHECKING

from chappy.application.analysis_artifacts import DeriveAnalysisReadinessUseCase
from chappy.core.absorption.models import UNASSIGNED_REGION_ID
from chappy.core.absorption_display import format_region_display
from chappy.presentation.analysis import (
    AnalysisReviewFacts,
    AnalysisReviewPresenter,
    AnalysisReviewRow,
    AnalysisReviewSummary,
)

if TYPE_CHECKING:
    from chappy.core.spectroscopy_project import SpectroscopyProject


class AnalysisOverviewRowsBuilder:
    """Project the current project aggregate into typed presentation rows."""

    def __init__(self) -> None:
        self._readiness = DeriveAnalysisReadinessUseCase()
        self._presenter = AnalysisReviewPresenter()

    def build(
        self, project: SpectroscopyProject | None
    ) -> tuple[tuple[AnalysisReviewRow, ...], AnalysisReviewSummary]:
        """Return rows in wavelength order and their typed summary."""
        rows: list[AnalysisReviewRow] = []
        if project is not None:
            for region_id, region in project.absorption_regions.items():
                if region_id == UNASSIGNED_REGION_ID:
                    continue
                line_ids = tuple(region.line_ids)
                missing_line_ids = tuple(
                    line_id for line_id in line_ids if line_id not in project.absorption_lines
                )
                lines = tuple(
                    project.absorption_lines[line_id]
                    for line_id in line_ids
                    if line_id in project.absorption_lines
                )
                label = (
                    format_region_display(lines, region.analysis_range).display_name
                    if lines
                    else region_id[:8]
                )
                facts = AnalysisReviewFacts(
                    region_id=region_id,
                    region_label=label,
                    readiness=self._readiness.execute(project, region_id),
                    analysis_state=project.region_analysis_state(region_id),
                    requires_reanalysis=project.region_requires_reanalysis(region_id),
                    line_ids=line_ids,
                    missing_line_ids=missing_line_ids,
                )
                rows.append(self._presenter.build_row(facts))
        materialized = tuple(rows)
        return materialized, self._presenter.build_summary(materialized)


__all__ = ["AnalysisOverviewRowsBuilder"]
