"""Qt adapters for core domain events."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal

from chappy.core.components.base import ModelComponent
from chappy.core.events import (
    ComponentAdded,
    ComponentChanged,
    ComponentRemoved,
    MasksChanged,
    ModelUpdated,
    ModelUpdateProgress,
    RegionTopologyChanged,
)

if TYPE_CHECKING:
    from chappy.core.change_set import ChangeSet
    from chappy.core.spectrum_model import SpectrumModel


class SpectrumModelEventAdapter(QObject):
    """Expose ``SpectrumModel`` domain events as Qt signals."""

    model_changed = Signal()
    component_added = Signal(ModelComponent)
    component_removed = Signal(ModelComponent)
    masks_changed = Signal()
    region_topology_changed = Signal(RegionTopologyChanged)

    def __init__(self, model: SpectrumModel, parent: QObject | None = None) -> None:
        """Initialize an adapter for a spectrum model.

        Args:
            model: Spectrum model whose domain events should be adapted.
            parent: Optional Qt parent object.
        """
        super().__init__(parent)
        self._model = model
        self._component_cache: dict[str, ModelComponent] = {
            component.id: component for component in model.components
        }
        self._applying_region_topology_change = False
        self._model.events.subscribe(self.apply)

    @property
    def applying_region_topology_change(self) -> bool:
        """Return whether the current change set contains a topology event."""
        return self._applying_region_topology_change

    def close(self) -> None:
        """Detach this adapter from the model."""
        self._model.events.unsubscribe(self.apply)

    def apply(self, change_set: ChangeSet) -> None:
        """Emit Qt signals for a domain change set.

        Args:
            change_set: Domain changes emitted by the model.
        """
        self._applying_region_topology_change = change_set.contains(RegionTopologyChanged)
        try:
            for event in change_set:
                if isinstance(event, ComponentAdded):
                    component = self._model.get_component_by_id(event.component_id)
                    if component is None:
                        continue
                    self._component_cache[event.component_id] = component
                    self.component_added.emit(component)
                    continue

                if isinstance(event, ComponentRemoved):
                    component = self._component_cache.pop(event.component_id, None)
                    if component is not None:
                        self.component_removed.emit(component)
                    continue

                if isinstance(event, ComponentChanged):
                    component = self._model.get_component_by_id(event.component_id)
                    if component is None:
                        continue
                    self._component_cache[event.component_id] = component
                    continue

                if isinstance(event, MasksChanged):
                    self.masks_changed.emit()
                    continue

                if isinstance(event, RegionTopologyChanged):
                    self.region_topology_changed.emit(event)
                    continue

                if isinstance(event, ModelUpdateProgress):
                    continue

                if isinstance(event, ModelUpdated):
                    self.model_changed.emit()
        finally:
            self._applying_region_topology_change = False
