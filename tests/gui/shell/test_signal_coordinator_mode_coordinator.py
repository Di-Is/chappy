"""Tests for ShellSignalConnector mode coordinator wiring."""

from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

from PySide6.QtWidgets import QWidget
import pytest
from pytestqt.qtbot import QtBot

from chappy.core.editing_mode import EditingMode
from chappy.gui.shell.signal_connector import (
    ShellSignalConnector,
    ShellSignalConnectorBindings,
    ShellSignalConnectorPorts,
)

if TYPE_CHECKING:
    from chappy.gui.modes.continuum.coordinator import ContinuumCoordinator
    from chappy.gui.modes.identify.coordinator import IdentifyModeCoordinator
    from chappy.gui.shell.absorber_coordinator import AbsorberCoordinator
    from chappy.gui.shell.main_window import MainWindow
    from chappy.gui.shell.mode_shell_coordinator import ModeShellCoordinator
    from chappy.gui.shell.view_stack import ViewStack


class _Signal:
    """Small signal test double."""

    def __init__(self) -> None:
        """Initialize callback storage."""
        self._callbacks: list[Callable[[EditingMode], None]] = []

    def connect(self, callback: Callable[[EditingMode], None]) -> None:
        """Register a callback.

        Args:
            callback: Callback to invoke on emission.
        """
        self._callbacks.append(callback)

    def emit(self, *args: EditingMode) -> None:
        """Emit values to callbacks.

        Args:
            args: Emitted positional arguments.
        """
        for callback in list(self._callbacks):
            callback(*args)


class _Coordinator:
    """Coordinator test double with status signal."""

    def __init__(self, _main_window: QWidget) -> None:
        """Initialize coordinator signal."""
        self.status_message = _Signal()


class _ContinuumCoordinator:
    """Continuum coordinator test double with status signal."""

    def __init__(self, _main_window: QWidget, _message_parent: QWidget) -> None:
        """Initialize coordinator signal."""
        self.status_message = _Signal()


class _IdentifyModeCoordinator:
    """Identify coordinator test double."""

    def __init__(self, _main_window: QWidget, **_kwargs: object) -> None:
        """Initialize coordinator signal."""
        self.status_message = _Signal()
        self.refreshed = False

    def refresh(self) -> None:
        """Record refresh calls."""
        self.refreshed = True

    def connect_status_message(self, callback: Callable[..., None]) -> None:
        """Connect status message callbacks."""
        self.status_message.connect(callback)

    def handle_cursor_left(self) -> None:
        """Accept non-identify mode changes."""


class _ModeShellCoordinator:
    """Mode coordinator test double supplied by the composition root."""

    def __init__(self) -> None:
        """Initialize mode changed signal."""
        self.mode_changed = _Signal()


class _SpectrumCoordinator:
    """Record absorber parameter routes forwarded to the spectrum coordinator."""

    def __init__(self) -> None:
        """Initialize route storage."""
        self.routes: list[tuple[str, str, float]] = []

    def update_absorber_param(self, absorber: str, parameter: str, value: float) -> None:
        """Record one parsed absorber parameter route."""
        self.routes.append((absorber, parameter, value))


class _MainWindow(QWidget):
    """Main window double satisfying continuum shell composition."""

    current_project = None
    view_stack = None
    continuum_editor = None
    mode_state_store = None
    continuum_history_recorder = None
    preset_store = None
    identify_velocity_runtime = object()


def test_shell_signal_connector_uses_injected_mode_shell_coordinator(qtbot: QtBot) -> None:
    """Verify ShellSignalConnector connects the composition-root ModeShellCoordinator."""
    main_window = _MainWindow()
    qtbot.addWidget(main_window)
    coordinator = ShellSignalConnector(cast("MainWindow", main_window))
    emitted_modes: list[EditingMode] = []
    mode_shell_coordinator = _ModeShellCoordinator()
    absorber_coordinator = cast("AbsorberCoordinator", _Coordinator(main_window))
    continuum_coordinator = cast(
        "ContinuumCoordinator", _ContinuumCoordinator(main_window, main_window)
    )
    identify_coordinator = cast("IdentifyModeCoordinator", _IdentifyModeCoordinator(main_window))

    coordinator.set_ports(
        ShellSignalConnectorPorts(
            status_message=lambda _message: None, mode_changed=emitted_modes.append
        )
    )
    coordinator.set_coordinators(
        absorber_coordinator=absorber_coordinator,
        continuum_coordinator=continuum_coordinator,
        identify_coordinator=identify_coordinator,
        mode_shell_coordinator=cast("ModeShellCoordinator", mode_shell_coordinator),
    )
    mode_shell_coordinator.mode_changed.emit(EditingMode.IDENTIFY)

    assert coordinator.mode_shell_coordinator is mode_shell_coordinator
    assert emitted_modes == [EditingMode.IDENTIFY]
    assert isinstance(coordinator.identify_coordinator, _IdentifyModeCoordinator)
    assert coordinator.identify_coordinator.refreshed is True


def test_shell_signal_connector_requires_identify_coordinator_for_mode_signal(
    qtbot: QtBot,
) -> None:
    """Mode-change identify refresh wiring requires the identify coordinator."""
    main_window = _MainWindow()
    qtbot.addWidget(main_window)
    coordinator = ShellSignalConnector(cast("MainWindow", main_window))

    with pytest.raises(RuntimeError, match="Identify coordinator is required"):
        coordinator._handle_mode_changed_for_identify(EditingMode.IDENTIFY)


def test_shell_signal_connector_requires_identify_coordinator_when_connecting_mode_shell(
    qtbot: QtBot,
) -> None:
    """Connecting the mode shell must not skip the identify refresh target."""
    main_window = _MainWindow()
    qtbot.addWidget(main_window)
    coordinator = ShellSignalConnector(cast("MainWindow", main_window))
    coordinator.mode_shell_coordinator = cast("ModeShellCoordinator", _ModeShellCoordinator())

    with pytest.raises(RuntimeError, match="Identify coordinator is required"):
        coordinator._connect_mode_shell_coordinator_signals()


def test_absorber_parameter_route_is_split_before_spectrum_mutation(qtbot: QtBot) -> None:
    """Shell routing should preserve distinct absorber and parameter identities."""
    main_window = _MainWindow()
    qtbot.addWidget(main_window)
    connector = ShellSignalConnector(cast("MainWindow", main_window))
    spectrum_coordinator = _SpectrumCoordinator()
    view_stack = SimpleNamespace(spectrum_view=SimpleNamespace(coordinator=spectrum_coordinator))
    connector.bind_runtime_surfaces(
        ShellSignalConnectorBindings(
            absorber_editor=None,
            continuum_editor=None,
            optimize_editor=None,
            view_stack=cast("ViewStack", view_stack),
            identify_panel=None,
            optimize_panel=None,
        )
    )

    connector._forward_absorber_parameter_to_coordinator("H I.redshift", 2.1)

    assert spectrum_coordinator.routes == [("H I", "redshift", 2.1)]


def test_invalid_absorber_parameter_route_fails_fast(qtbot: QtBot) -> None:
    """A malformed editor route should not target an ambiguous parameter."""
    main_window = _MainWindow()
    qtbot.addWidget(main_window)
    connector = ShellSignalConnector(cast("MainWindow", main_window))
    view_stack = SimpleNamespace(spectrum_view=SimpleNamespace(coordinator=_SpectrumCoordinator()))
    connector.bind_runtime_surfaces(
        ShellSignalConnectorBindings(
            absorber_editor=None,
            continuum_editor=None,
            optimize_editor=None,
            view_stack=cast("ViewStack", view_stack),
            identify_panel=None,
            optimize_panel=None,
        )
    )

    with pytest.raises(ValueError, match="Invalid absorber parameter route"):
        connector._forward_absorber_parameter_to_coordinator("redshift", 2.1)
