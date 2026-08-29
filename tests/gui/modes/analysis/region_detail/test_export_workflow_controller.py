"""Tests for optimize export workflow controller."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING, cast

from chappy.core.absorption.models import AbsorptionRegion
from chappy.core.analysis import AnalysisReadiness, FitSummary
from chappy.core.cosmology import PLANCK_2018, CosmologyParameters
from chappy.gui.modes.analysis.region_detail.workflows.export_workflow_controller import (
    OptimizeExportDocumentPort,
    OptimizeExportWorkflowController,
)

if TYPE_CHECKING:
    from chappy.application.optimize.models import OptimizationExportRequest
    from chappy.core.spectroscopy_project import SpectroscopyProject
    from chappy.gui.modes.analysis.region_detail.adapters.export_dialog_adapter import (
        OptimizeExportDialogAdapter,
    )
    from chappy.infrastructure.csv_exporter import CsvExporter


class _Document:
    """Export document test double."""

    def __init__(
        self, *, filename_stem: str, header: Iterable[str], rows: Iterable[Iterable[str]]
    ) -> None:
        self.filename_stem = filename_stem
        self.header = header
        self.rows = rows

    filename_stem: str
    header: Iterable[str]
    rows: Iterable[Iterable[str]]


class _Port:
    """Panel-port test double."""

    def __init__(self) -> None:
        self.project = cast("SpectroscopyProject", _Project())
        self.success_messages: list[str] = []
        self.readiness = AnalysisReadiness.LATEST
        self.summary: FitSummary | None = FitSummary(chi_squared=1.2)

    def current_export_region_id(self) -> str | None:
        """Return the current test region."""
        return "region-1"

    def export_project(self) -> "SpectroscopyProject | None":
        """Return the test project."""
        return self.project

    def analysis_readiness(self, group_id: str) -> AnalysisReadiness:
        """Return current runtime readiness."""
        assert group_id == "region-1"
        return self.readiness

    def export_fit_summary(self, group_id: str) -> FitSummary | None:
        """Return fit summary for a group."""
        assert group_id == "region-1"
        return self.summary

    def load_export_cosmology(self) -> CosmologyParameters:
        """Return test cosmology."""
        return PLANCK_2018

    def emit_export_success(self, message: str) -> None:
        """Record successful export feedback."""
        self.success_messages.append(message)

    def project_file_path(self) -> str | None:
        """Return the test project file path hint."""
        return "/tmp/project.chappy"


class _Project:
    """Minimal project-like object accepted through test casts."""

    name = "Project"
    absorption_regions = {"region-1": AbsorptionRegion(region_id="region-1")}


class _ExportUseCase:
    """Export use case test double."""

    def __init__(self) -> None:
        self.requests: list[OptimizationExportRequest] = []

    def build_document(self, request: "OptimizationExportRequest") -> OptimizeExportDocumentPort:
        """Record the request and return a small document."""
        self.requests.append(request)
        return _Document(filename_stem="project-region", header=("col",), rows=(("value",),))


class _Dialog:
    """Dialog adapter test double."""

    def __init__(self, output_path: Path | None) -> None:
        self.output_path = output_path
        self.prompts: list[tuple[str, str | None]] = []
        self.errors: list[Exception] = []

    def prompt_export_path(
        self, default_filename: str, project_filename: str | None
    ) -> tuple[Path, str] | None:
        """Record prompt input and return the configured path."""
        self.prompts.append((default_filename, project_filename))
        if self.output_path is None:
            return None
        return self.output_path, "utf-8"

    def show_export_error(self, error: Exception) -> None:
        """Record export errors."""
        self.errors.append(error)


class _CsvExporter:
    """CSV writer test double."""

    def __init__(self) -> None:
        self.writes: list[tuple[Path, tuple[str, ...], tuple[tuple[str, ...], ...], str]] = []

    def write(
        self,
        path: Path,
        header: Iterable[str],
        rows: Iterable[Iterable[str]],
        *,
        encoding: str = "utf-8",
    ) -> None:
        """Record write requests."""
        self.writes.append((path, tuple(header), tuple(tuple(row) for row in rows), encoding))


class _Request:
    """Request DTO test double."""


def _request_builder(
    _project: "SpectroscopyProject",
    _region: AbsorptionRegion,
    _cosmology: CosmologyParameters,
    _fit_summary: FitSummary,
) -> "OptimizationExportRequest":
    """Return a detached request test double through the production type boundary."""
    return cast("OptimizationExportRequest", _Request())


def test_export_current_region_writes_document(tmp_path: Path) -> None:
    """Controller should build, prompt, write, and publish success feedback."""
    output_path = tmp_path / "result.csv"
    port = _Port()
    use_case = _ExportUseCase()
    dialog = _Dialog(output_path)
    writer = _CsvExporter()
    controller = OptimizeExportWorkflowController(
        port=port,
        dialog_adapter=cast("OptimizeExportDialogAdapter", dialog),
        export_usecase=use_case,
        csv_exporter=cast("CsvExporter", writer),
        request_builder=_request_builder,
    )

    controller.export_current_region()

    assert len(use_case.requests) == 1
    assert dialog.prompts == [("project-region.csv", "/tmp/project.chappy")]
    assert writer.writes == [(output_path, ("col",), (("value",),), "utf-8")]
    assert port.success_messages == [f"Exported CSV to {output_path}"]


def test_export_current_region_stops_when_dialog_is_cancelled(tmp_path: Path) -> None:
    """Controller should stop without writing when the dialog is cancelled."""
    port = _Port()
    writer = _CsvExporter()
    controller = OptimizeExportWorkflowController(
        port=port,
        dialog_adapter=cast("OptimizeExportDialogAdapter", _Dialog(None)),
        export_usecase=_ExportUseCase(),
        csv_exporter=cast("CsvExporter", writer),
        request_builder=_request_builder,
    )

    controller.export_current_region()

    assert writer.writes == []
    assert port.success_messages == []


def test_export_current_region_rejects_stale_runtime_state(tmp_path: Path) -> None:
    """An enabled button cannot bypass readiness re-evaluation at export time."""
    port = _Port()
    port.readiness = AnalysisReadiness.STALE
    use_case = _ExportUseCase()
    dialog = _Dialog(tmp_path / "stale.csv")
    writer = _CsvExporter()
    controller = OptimizeExportWorkflowController(
        port=port,
        dialog_adapter=cast("OptimizeExportDialogAdapter", dialog),
        export_usecase=use_case,
        csv_exporter=cast("CsvExporter", writer),
        request_builder=_request_builder,
    )

    controller.export_current_region()

    assert use_case.requests == []
    assert dialog.prompts == []
    assert writer.writes == []


def test_export_current_region_rejects_missing_summary(tmp_path: Path) -> None:
    """Latest readiness cannot fabricate a summary if project evidence is absent."""
    port = _Port()
    port.summary = None
    use_case = _ExportUseCase()
    dialog = _Dialog(tmp_path / "missing.csv")
    controller = OptimizeExportWorkflowController(
        port=port,
        dialog_adapter=cast("OptimizeExportDialogAdapter", dialog),
        export_usecase=use_case,
        csv_exporter=cast("CsvExporter", _CsvExporter()),
        request_builder=_request_builder,
    )

    controller.export_current_region()

    assert use_case.requests == []
    assert dialog.prompts == []
