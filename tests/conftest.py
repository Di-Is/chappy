"""Global pytest fixtures."""

from __future__ import annotations

from collections.abc import Iterator
import os
import sys

import pytest

from chappy.gui.application_font import configure_offscreen_font_environment

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

configure_offscreen_font_environment()


@pytest.fixture(autouse=True)
def _auto_accept_qmessage_box(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Automatically accept ``QMessageBox`` dialogs during tests.

    Args:
        request: Pytest fixture request for checking if qapp is in use.
        monkeypatch: Pytest monkeypatch helper that injects the auto-accept
            behaviour.

    This fixture prevents modal dialogs from blocking the test run by
    scheduling a synthetic click on the affirmative button as soon as the
    message box enters its local event loop.
    """
    # Only patch if qapp fixture is being used by this test
    if "qapp" not in request.fixturenames and "qtbot" not in request.fixturenames:
        return

    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QAbstractButton, QMessageBox

    original_exec = QMessageBox.exec

    def _auto_exec(message_box: QMessageBox) -> int:
        """Invoke the original exec after scheduling an automatic response.

        Args:
            message_box: Dialog instance awaiting user interaction.

        Returns:
            Exit code returned by the original ``QMessageBox.exec`` call.
        """

        def _trigger_acceptance() -> None:
            """Simulate pressing the affirmative button on the dialog."""

            yes_button = message_box.button(QMessageBox.StandardButton.Yes)
            target_button: QAbstractButton | None = yes_button or message_box.defaultButton()
            if target_button is None:
                buttons = message_box.buttons()
                target_button = buttons[0] if buttons else None
            if target_button is not None:
                target_button.click()

        QTimer.singleShot(0, _trigger_acceptance)
        return original_exec(message_box)

    monkeypatch.setattr(QMessageBox, "exec", _auto_exec)


@pytest.fixture(autouse=True)
def _close_matplotlib_figures() -> Iterator[None]:
    """Close Matplotlib figures between tests to avoid pending Qt draw events."""
    yield
    if "matplotlib.pyplot" not in sys.modules:
        return

    import matplotlib.pyplot as plt

    plt.close("all")
    if "PySide6.QtWidgets" in sys.modules:
        from PySide6.QtWidgets import QApplication

        application = QApplication.instance()
        if application is not None:
            application.processEvents()
