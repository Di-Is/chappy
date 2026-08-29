"""Shared dataclasses for documentation automation."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

from chappy.core.editing_mode import EditingMode
from chappy.gui.modes.common.analysis_navigation import AnalysisSurface

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

    from PySide6.QtWidgets import QApplication

    from chappy.gui.shell.main_window import MainWindow
    from chappy_user_manual_generator.panel_windows import AnalysisStructureDocWindow

    type ScenarioWindow = MainWindow | AnalysisStructureDocWindow


class PanelDestination(StrEnum):
    """Semantic panel prepared inside one top-level mode capture."""

    MODE = "mode"
    ANALYSIS_OVERVIEW = "analysis_overview"
    ANALYSIS_REGION_DETAIL = "analysis_region_detail"
    ANALYSIS_STRUCTURE = "analysis_structure"


@dataclass(frozen=True, slots=True)
class CaptureDestination:
    """Typed mode, Analysis surface, and panel destination for a capture."""

    mode: EditingMode
    panel: PanelDestination = PanelDestination.MODE
    analysis_surface: AnalysisSurface | None = None

    def __post_init__(self) -> None:
        """Reject contradictory mode, surface, and panel combinations."""
        analysis_panel = self.panel is not PanelDestination.MODE
        if analysis_panel and self.mode is not EditingMode.ANALYSIS:
            msg = "Only Analysis mode may use an Analysis panel destination."
            raise ValueError(msg)
        if analysis_panel is not (self.analysis_surface is not None):
            msg = "Analysis panel destinations require an Analysis surface."
            raise ValueError(msg)
        expected_surfaces = {
            PanelDestination.ANALYSIS_OVERVIEW: AnalysisSurface.OVERVIEW,
            PanelDestination.ANALYSIS_STRUCTURE: AnalysisSurface.OVERVIEW,
            PanelDestination.ANALYSIS_REGION_DETAIL: AnalysisSurface.REGION_DETAIL,
        }
        expected = expected_surfaces.get(self.panel)
        if expected is not None and self.analysis_surface is not expected:
            msg = f"{self.panel.value} requires the {expected.value} surface."
            raise ValueError(msg)

    @property
    def scope(self) -> str:
        """Return the annotation and output scope for this destination."""
        return self.mode.value if self.panel is PanelDestination.MODE else self.panel.value


class ScenarioCallable(Protocol):
    """Callable signature for operation flow scenarios."""

    def __call__(self, context: ScenarioContext) -> OperationFlow:
        """Generate an operation flow for the provided scenario context.

        Args:
            context: Scenario metadata and helpers used to build the flow.

        Returns:
            Fully populated operation flow definition.
        """
        ...


@dataclass(frozen=True)
class ScreenDocSpec:
    """Configuration for capturing screen documentation."""

    slug: str
    window_type: str = "main"
    fixtures: tuple[str, ...] = ()
    destinations: tuple[CaptureDestination, ...] = ()
    include_common: bool = True
    include_tabs: bool = True
    scopes: tuple[str, ...] = ()
    output_subdir: str | None = None
    destination_fixtures: Mapping[CaptureDestination, tuple[str, ...]] = field(
        default_factory=dict
    )


@dataclass(frozen=True)
class OperationStep:
    """One step in an operation flow."""

    order: int
    action: str
    expected: str


@dataclass(frozen=True)
class OperationSectionItem:
    """Bulleted item shown within a documentation section."""

    title: str
    description: str
    details: tuple[str, ...] = ()


@dataclass(frozen=True)
class OperationSectionBlock:
    """Arbitrary Markdown block placed inside a documentation section."""

    content: str


@dataclass(frozen=True)
class OperationSection:
    """Logical section within an operation flow."""

    heading: str
    description: str | None = None
    items: tuple[OperationSectionItem, ...] = ()
    blocks: tuple[OperationSectionBlock, ...] = ()


@dataclass(frozen=True)
class OperationFlow:
    """User-facing description of a task-oriented flow."""

    slug: str
    title: str
    summary: str
    steps: tuple[OperationStep, ...]
    sections: tuple[OperationSection, ...] = ()
    window_type: str = "main"
    fixtures: tuple[str, ...] = ()
    destination: CaptureDestination | None = None
    output_filename: str | None = None
    prerequisites: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    related_links: tuple[RelatedLink, ...] = ()


@dataclass(frozen=True)
class RelatedLink:
    """Link to supporting documentation for an operation flow."""

    label: str
    path: str


@dataclass(frozen=True)
class OperationScenarioSpec:
    """Manifest entry tying a scenario callable to metadata."""

    slug: str
    title: str
    summary: str
    scenario: ScenarioCallable
    window_type: str = "main"
    fixtures: tuple[str, ...] = ()
    destination: CaptureDestination | None = None
    output_dir: str = "operations"


@dataclass(frozen=True)
class DocManifest:
    """Profile definition grouping screen docs and operation flows."""

    version_label: str
    screens: Sequence[ScreenDocSpec] = field(default_factory=tuple)
    flows: Sequence[OperationScenarioSpec] = field(default_factory=tuple)
    menus: Sequence[MenuDocSpec] = field(default_factory=tuple)
    index: ManualIndexSpec | None = None


@dataclass(frozen=True)
class MenuDocSpec:
    """Configuration for documenting application menus."""

    slug: str
    window_type: str = "main"
    fixtures: tuple[str, ...] = ()
    menu_keys: tuple[str, ...] = ()
    output_subdir: str | None = None
    include_shortcuts: bool = True
    include_modes: bool = True
    include_status: bool = True
    action_modes: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    action_notes: Mapping[str, str] = field(default_factory=dict)
    menu_descriptions: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class IndexEntry:
    """Entry configuration within an index section."""

    title: str
    path: str | None = None
    description: str | None = None


@dataclass(frozen=True)
class IndexSection:
    """Logical grouping of index entries."""

    heading: str
    intro: str | None = None
    entries: tuple[IndexEntry, ...] = ()


@dataclass(frozen=True)
class ManualIndexSpec:
    """Specification for generating a manual landing page."""

    filename: str = "index.md"
    title: str | None = None
    overview: tuple[str, ...] = ()
    sections: tuple[IndexSection, ...] = ()
    footer: tuple[str, ...] = ()


class ScenarioContext:
    """Mutable context passed to scenario callables."""

    def __init__(  # noqa: PLR0913
        self,
        *,
        slug: str,
        title: str,
        summary: str,
        window: ScenarioWindow,
        app: QApplication,
        window_type: str = "main",
        fixtures: Sequence[str] | None = None,
        destination: CaptureDestination | None = None,
        output_filename: str | None = None,
    ) -> None:
        self.slug = slug
        self.title = title
        self.summary = summary
        self.window = window
        self.app = app
        self.window_type = window_type
        self.fixtures = tuple(fixtures or ())
        self.destination = destination
        self.output_filename = output_filename
        self._steps: list[OperationStep] = []
        self._prerequisites: list[str] = []
        self._notes: list[str] = []
        self._related_links: list[RelatedLink] = []
        self._sections: list[_MutableSection] = []

    def add_step(self, action: str, expected: str) -> None:
        """Append a documented step in order."""
        order = len(self._steps) + 1
        self._steps.append(OperationStep(order=order, action=action, expected=expected))

    def steps(self) -> Iterable[OperationStep]:
        """Return the accumulated steps."""
        return tuple(self._steps)

    def add_section(self, heading: str, description: str | None = None) -> SectionBuilder:
        """Start a new logical section for catalog-style documentation."""
        if not heading:
            msg = "Section heading must be a non-empty string."
            raise ValueError(msg)
        section = _MutableSection(heading=heading, description=description or "")
        self._sections.append(section)
        return SectionBuilder(section)

    def add_prerequisite(self, description: str) -> None:
        """Record a prerequisite condition for the workflow."""
        if description:
            self._prerequisites.append(description)

    def add_note(self, note: str) -> None:
        """Record supplementary guidance for the workflow."""
        if note:
            self._notes.append(note)

    def add_related_link(self, label: str, path: str) -> None:
        """Add a related documentation link."""
        if label and path:
            self._related_links.append(RelatedLink(label=label, path=path))

    def build_flow(self) -> OperationFlow:
        """Materialise the recorded steps as an OperationFlow."""
        return OperationFlow(
            slug=self.slug,
            title=self.title,
            summary=self.summary,
            steps=tuple(self._steps),
            sections=tuple(section.freeze() for section in self._sections),
            window_type=self.window_type,
            fixtures=self.fixtures,
            destination=self.destination,
            output_filename=self.output_filename,
            prerequisites=tuple(self._prerequisites),
            notes=tuple(self._notes),
            related_links=tuple(self._related_links),
        )


class _MutableSection:
    """Internal mutable representation of a section."""

    def __init__(self, *, heading: str, description: str) -> None:
        self.heading = heading
        self.description = description
        self.items: list[OperationSectionItem] = []
        self.blocks: list[OperationSectionBlock] = []

    def add_item(self, item: OperationSectionItem) -> None:
        self.items.append(item)

    def add_block(self, block: OperationSectionBlock) -> None:
        self.blocks.append(block)

    def freeze(self) -> OperationSection:
        description = self.description.strip() or None
        return OperationSection(
            heading=self.heading,
            description=description,
            items=tuple(self.items),
            blocks=tuple(self.blocks),
        )


class SectionBuilder:
    """Fluent helper for building documentation sections."""

    def __init__(self, section: _MutableSection) -> None:
        self._section = section

    def add_item(
        self, title: str, description: str, *, details: Iterable[str] | None = None
    ) -> SectionBuilder:
        """Append a bullet item to the section."""
        if not title or not description:
            msg = "Section items require both title and description."
            raise ValueError(msg)
        item = OperationSectionItem(
            title=title, description=description, details=tuple(details or ())
        )
        self._section.add_item(item)
        return self

    def add_block(self, content: str) -> SectionBuilder:
        """Append a raw Markdown block to the section."""
        if not content.strip():
            return self
        block = OperationSectionBlock(content=content.strip())
        self._section.add_block(block)
        return self
