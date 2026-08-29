"""Composition factory for default infrastructure adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from chappy.application.optimize import AddOptimizeModelComponentsUseCase
from chappy.infrastructure.atomic_lines import AtomicLineCsvRepository
from chappy.infrastructure.preset_store import PersistentPresetStore
from chappy.infrastructure.project_io_factory import create_default_project_io_usecase
from chappy.infrastructure.resources import RuntimeResourcePathResolver

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from chappy.application.ports import PresetStorePort, ResourcePathResolver
    from chappy.application.project_io_usecase import ProjectIOUseCase
    from chappy.core.atomic_data import AtomicLineData
    from chappy.core.presets import TranslateFunc


@dataclass(frozen=True)
class DefaultInfrastructureDependencies:
    """Default infrastructure objects built at the application boundary."""

    resource_resolver: ResourcePathResolver
    atomic_repository: AtomicLineData
    atomic_repository_provider: Callable[[], AtomicLineData]
    preset_store: PresetStorePort
    project_io_usecase: ProjectIOUseCase
    optimize_model_addition_usecase: AddOptimizeModelComponentsUseCase


def create_default_infrastructure_dependencies(
    *, translate_presets: TranslateFunc, preset_storage_path: str | Path | None = None
) -> DefaultInfrastructureDependencies:
    """Create default infrastructure-backed dependencies for GUI composition.

    Args:
        translate_presets: Initial translator used by the persistent preset store.
        preset_storage_path: Preset persistence file; defaults to the user preset file.

    Returns:
        Default dependency graph with concrete infrastructure adapters.
    """
    resource_resolver = RuntimeResourcePathResolver()
    atomic_loader = AtomicLineCsvRepository()
    atomic_repository = atomic_loader.load()

    def atomic_repository_provider() -> AtomicLineData:
        """Return the shared atomic line repository."""
        return atomic_repository

    preset_store = PersistentPresetStore(
        atomic_repository, storage_path=preset_storage_path, translate=translate_presets
    )
    optimize_model_addition_usecase = AddOptimizeModelComponentsUseCase(atomic_repository_provider)

    return DefaultInfrastructureDependencies(
        resource_resolver=resource_resolver,
        atomic_repository=atomic_repository,
        atomic_repository_provider=atomic_repository_provider,
        preset_store=preset_store,
        project_io_usecase=create_default_project_io_usecase(),
        optimize_model_addition_usecase=optimize_model_addition_usecase,
    )


__all__ = ["DefaultInfrastructureDependencies", "create_default_infrastructure_dependencies"]
