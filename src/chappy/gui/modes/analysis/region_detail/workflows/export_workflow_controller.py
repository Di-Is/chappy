"""Controller for optimize export workflow orchestration."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Protocol

from PySide6.QtCore import QCoreApplication

from chappy.core.absorption.models import AbsorptionRegion
from chappy.core.analysis import AnalysisReadiness, FitSummary
from chappy.core.cosmology import CosmologyParameters
from chappy.core.spectroscopy_project import SpectroscopyProject

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

    from chappy.application.optimize.models import (
        OptimizationExportDocument,
        OptimizationExportRequest,
    )
    from chappy.gui.modes.analysis.region_detail.adapters.export_dialog_adapter import (
        OptimizeExportDialogAdapter,
    )

type OptimizeExportRequestBuilder = Callable[
    [SpectroscopyProject, AbsorptionRegion, CosmologyParameters, FitSummary],
    "OptimizationExportRequest",
]


class OptimizeExportWorkflowPort(Protocol):
    """Panel operations required by optimize export workflow."""

    def current_export_region_id(self) -> str | None:
        """Return the current Analysis region ID to export."""
        ...

    def export_project(self) -> SpectroscopyProject | None:
        """Return the active project."""
        ...

    def analysis_readiness(self, group_id: str) -> AnalysisReadiness:
        """Re-evaluate current project readiness for a group."""
        ...

    def export_fit_summary(self, group_id: str) -> FitSummary | None:
        """Return fit summary for a group."""
        ...

    def load_export_cosmology(self) -> CosmologyParameters:
        """Return cosmology parameters used by export."""
        ...

    def emit_export_success(self, message: str) -> None:
        """Emit successful export feedback."""
        ...

    def project_file_path(self) -> str | None:
        """Return the file path hint for the active project, if any."""
        ...


class OptimizeExportUseCasePort(Protocol):
    """Export document builder required by the workflow."""

    def build_document(self, request: OptimizationExportRequest) -> OptimizationExportDocument:
        """Build an export document."""
        ...


class OptimizeExportDocumentPort(Protocol):
    """Export document fields required for CSV writing."""

    filename_stem: str
    header: Iterable[str]
    rows: Iterable[Iterable[str]]


class OptimizeCsvWriterPort(Protocol):
    """CSV writer required by the workflow."""

    def write(
        self,
        path: Path,
        header: Iterable[str],
        rows: Iterable[Iterable[str]],
        *,
        encoding: str = "utf-8",
    ) -> None:
        """Write CSV rows."""
        ...


class OptimizeExportWorkflowController:
    """Coordinate optimize export document creation and CSV writing."""

    def __init__(
        self,
        *,
        port: OptimizeExportWorkflowPort,
        dialog_adapter: OptimizeExportDialogAdapter,
        export_usecase: OptimizeExportUseCasePort,
        csv_exporter: OptimizeCsvWriterPort,
        request_builder: OptimizeExportRequestBuilder,
    ) -> None:
        """Initialize the controller.

        Args:
            port: Panel port supplying export state and feedback.
            dialog_adapter: Dialog adapter for path selection and errors.
            export_usecase: Export document builder.
            csv_exporter: CSV writer.
            request_builder: Builder for detached export request DTOs.
        """
        self._port = port
        self._dialog_adapter = dialog_adapter
        self._export_usecase = export_usecase
        self._csv_exporter = csv_exporter
        self._request_builder = request_builder

    def export_current_region(self) -> None:
        """Export the current Analysis region when possible."""
        region_id = self._port.current_export_region_id()
        project = self._port.export_project()
        if not region_id or project is None:
            return

        region = project.absorption_regions.get(region_id)
        if not isinstance(region, AbsorptionRegion):
            return

        if self._port.analysis_readiness(region_id) is not AnalysisReadiness.LATEST:
            return
        summary = self._port.export_fit_summary(region_id)
        if summary is None:
            return

        document = self._export_usecase.build_document(
            self._request_builder(project, region, self._port.load_export_cosmology(), summary)
        )

        try:
            result = self._dialog_adapter.prompt_export_path(
                f"{document.filename_stem}.csv", self._port.project_file_path()
            )
            if result is None:
                return

            path, encoding = result
            self._csv_exporter.write(path, document.header, document.rows, encoding=encoding)
            template = QCoreApplication.translate("RegionDetailPanel", "Exported CSV to {path}")
            self._port.emit_export_success(template.format(path=str(path)))
        except OSError as error:  # pragma: no cover - filesystem dependent
            self._dialog_adapter.show_export_error(error)
