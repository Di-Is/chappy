"""Window bootstrapper settings recovery tests."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, cast

from PySide6.QtCore import QByteArray

import chappy.gui.shell.window_bootstrapper as window_bootstrapper
from chappy.gui.shell.window_bootstrapper import WindowBootstrapper

if TYPE_CHECKING:
    from chappy.gui.modes.analysis.region_detail.model_addition_controller import (
        OptimizeModelAdditionUseCasePort,
    )
    from chappy.gui.modes.analysis.region_detail.ui_facade import RegionDetailUi


class _FakeSettings:
    """Minimal QSettings replacement for window setting recovery tests."""

    def __init__(self) -> None:
        """Initialize stored values and removed keys."""
        self.values: dict[str, object] = {}
        self.removed_keys: list[str] = []

    def value(
        self, key: str, defaultValue: object | None = None, type: type | None = None
    ) -> object | None:
        """Return a stored value."""
        _ = type
        return self.values.get(key, defaultValue)

    def remove(self, key: str) -> None:
        """Record setting removal."""
        self.removed_keys.append(key)
        self.values.pop(key, None)

    def setValue(self, key: str, value: object) -> None:  # noqa: N802
        """Store one value."""
        self.values[key] = value


class _WindowProbe:
    """Main-window test double for settings restore behavior."""

    def __init__(self) -> None:
        """Initialize restore behavior."""
        self.geometry_result = True
        self.state_result = True
        self.stylesheets: list[str] = []

    def restoreGeometry(self, data: QByteArray) -> bool:  # noqa: N802
        """Restore geometry using the configured result."""
        _ = data
        return self.geometry_result

    def restoreState(self, data: QByteArray) -> bool:  # noqa: N802
        """Restore state using the configured result."""
        _ = data
        return self.state_result

    def setStyleSheet(self, stylesheet: str) -> None:  # noqa: N802
        """Record stylesheet application."""
        self.stylesheets.append(stylesheet)


class _FailingWindowProbe(_WindowProbe):
    """Main-window test double that raises from restoreState."""

    def restoreState(self, data: QByteArray) -> bool:  # noqa: N802
        """Raise to expose required window API failures."""
        _ = data
        msg = "restoreState failed"
        raise RuntimeError(msg)


def _noop_model_addition_usecase() -> "OptimizeModelAdditionUseCasePort":
    """Return a placeholder use case for bootstrapper tests that do not build docks."""
    return cast("OptimizeModelAdditionUseCasePort", object())


def _unused_region_detail_factory(**_: object) -> "RegionDetailUi":
    """Fail if called: these tests never reach dock construction."""
    msg = "region_detail_factory should not be invoked by settings-recovery tests"
    raise AssertionError(msg)


def test_restore_settings_clears_unrestorable_saved_window_state(monkeypatch, caplog) -> None:
    """Invalid persisted window settings are recoverable user state."""
    settings = _FakeSettings()
    settings.values["geometry"] = QByteArray(b"invalid-geometry")
    settings.values["windowState"] = QByteArray(b"invalid-state")
    settings.values[window_bootstrapper._WINDOW_LAYOUT_SCHEMA_KEY] = (
        window_bootstrapper._WINDOW_LAYOUT_SCHEMA_VERSION
    )
    monkeypatch.setattr(window_bootstrapper, "QSettings", lambda: settings)
    window = _WindowProbe()
    window.geometry_result = False
    window.state_result = False
    bootstrapper = WindowBootstrapper(
        cast("QMainWindow", window),
        optimize_model_addition_usecase=_noop_model_addition_usecase(),
        region_detail_factory=_unused_region_detail_factory,
    )

    with caplog.at_level(logging.WARNING, logger=window_bootstrapper.__name__):
        bootstrapper.restore_settings()

    assert settings.removed_keys == ["geometry", "windowState"]
    assert "Stored window geometry could not be restored" in caplog.text
    assert "Stored window state could not be restored" in caplog.text
    assert window.stylesheets


def test_restore_settings_propagates_window_api_failure(monkeypatch) -> None:
    """Required main-window API failures are not settings recovery."""
    settings = _FakeSettings()
    settings.values["windowState"] = QByteArray(b"state")
    settings.values[window_bootstrapper._WINDOW_LAYOUT_SCHEMA_KEY] = (
        window_bootstrapper._WINDOW_LAYOUT_SCHEMA_VERSION
    )
    monkeypatch.setattr(window_bootstrapper, "QSettings", lambda: settings)
    bootstrapper = WindowBootstrapper(
        cast("QMainWindow", _FailingWindowProbe()),
        optimize_model_addition_usecase=_noop_model_addition_usecase(),
        region_detail_factory=_unused_region_detail_factory,
    )

    try:
        bootstrapper.restore_settings()
    except RuntimeError as exc:
        assert str(exc) == "restoreState failed"
    else:
        raise AssertionError("restoreState failure should propagate")


def test_restore_settings_discards_legacy_dock_layout_before_restore(monkeypatch) -> None:
    """Old dock-based layout state is discarded by the bottom-pane schema cutover."""
    settings = _FakeSettings()
    settings.values["windowState"] = QByteArray(b"legacy-dock-names")
    settings.values["mainSplitterState"] = QByteArray(b"legacy-splitter")
    settings.values["analysisCenterSplitterState"] = QByteArray(b"legacy-center-splitter")
    monkeypatch.setattr(window_bootstrapper, "QSettings", lambda: settings)
    window = _WindowProbe()
    bootstrapper = WindowBootstrapper(
        cast("QMainWindow", window),
        optimize_model_addition_usecase=_noop_model_addition_usecase(),
        region_detail_factory=_unused_region_detail_factory,
    )

    bootstrapper.restore_settings()

    assert settings.removed_keys == [
        "windowState",
        "mainSplitterState",
        "analysisCenterSplitterState",
    ]
    assert settings.values[window_bootstrapper._WINDOW_LAYOUT_SCHEMA_KEY] == (
        window_bootstrapper._WINDOW_LAYOUT_SCHEMA_VERSION
    )


def test_layout_schema_version_covers_bottom_pane_cutover() -> None:
    """R2: the schema bump discards windowState that embeds analysisBottomDock."""
    assert window_bootstrapper._WINDOW_LAYOUT_SCHEMA_VERSION == 3
