"""Backward-compatible exports for the shell signal connector."""

from chappy.gui.shell.signal_connector import ShellSignalConnector as SignalCoordinator
from chappy.gui.shell.signal_connector import ShellSignalConnectorBindings
from chappy.gui.shell.signal_connector import ShellSignalConnectorPorts as SignalCoordinatorPorts

__all__ = ["ShellSignalConnectorBindings", "SignalCoordinator", "SignalCoordinatorPorts"]
