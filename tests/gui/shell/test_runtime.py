"""Tests for the shell runtime skeleton."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

from chappy.core.editing_mode import EditingMode
from chappy.core.spectroscopy_project import SpectroscopyProject
from chappy.gui.shell.composition import create_shell_runtime
from chappy.gui.shell.dependencies import ShellDependencies
from chappy.gui.shell.runtime import ShellRuntime


@dataclass
class _SignalRecorder:
    calls: list[tuple[str, int]]

    def emit(self, message: str, timeout_ms: int) -> None:
        """Record a signal emission."""
        self.calls.append((message, timeout_ms))


class _FakeWindow:
    """Minimal main-window surface used by ShellRuntime tests."""

    def __init__(self) -> None:
        self.current_project: SpectroscopyProject | None = None
        self.status_message = _SignalRecorder([])
        self.calls: list[tuple[str, object | None]] = []
        self.dialog_commands = self
        self.continuum_mode_runtime = _FakeContinuumRuntime(self.calls)
        self.optimize_velocity_runtime = _FakeOptimizeVelocityRuntime(self.calls)

    def show(self) -> None:
        self.calls.append(("show", None))

    def close(self) -> bool:
        self.calls.append(("close", None))
        return True

    def open_observation_data(self) -> None:
        self.calls.append(("open_observation_data", None))

    def open_project(self) -> None:
        self.calls.append(("open_project", None))

    def save_project(self) -> None:
        self.calls.append(("save_project", None))

    def save_project_as(self) -> None:
        self.calls.append(("save_project_as", None))

    def close_project(self) -> None:
        self.calls.append(("close_project", None))

    def set_current_project(self, project: SpectroscopyProject | None) -> None:
        self.current_project = project
        self.calls.append(("set_current_project", project))

    def switch_mode(self, mode: EditingMode) -> None:
        self.calls.append(("switch_mode", mode))

    def open_user_manual(self) -> None:
        self.calls.append(("open_user_manual", None))

    def show_cosmology_dialog(self) -> None:
        self.calls.append(("show_cosmology_dialog", None))

    def show_resolution_dialog(self) -> None:
        self.calls.append(("show_resolution_dialog", None))

    def open_line_database_folder(self) -> None:
        self.calls.append(("open_line_database_folder", None))

    def show_language_dialog(self) -> None:
        self.calls.append(("show_language_dialog", None))

    def show_preset_list_dialog(self) -> None:
        self.calls.append(("show_preset_list_dialog", None))

    def zoom_in(self) -> None:
        self.calls.append(("zoom_in", None))

    def zoom_out(self) -> None:
        self.calls.append(("zoom_out", None))

    def reset_view(self) -> None:
        self.calls.append(("reset_view", None))

    def auto_adjust_flux(self) -> None:
        self.calls.append(("auto_adjust_flux", None))


class _FakeContinuumRuntime:
    """Record continuum runtime command requests."""

    def __init__(self, calls: list[tuple[str, object | None]]) -> None:
        """Initialize the runtime double."""
        self._calls = calls

    def add_continuum(self) -> None:
        """Record continuum additions."""
        self._calls.append(("add_continuum", None))


class _FakeOptimizeVelocityRuntime:
    """Record optimize velocity overlay toggles."""

    def __init__(self, calls: list[tuple[str, object | None]]) -> None:
        """Initialize the optimize runtime double."""
        self._calls = calls

    def toggle_velocity_overlay(self) -> None:
        """Record optimize velocity overlay toggles."""
        self._calls.append(("toggle_velocity_plot_optimize", None))

    def fit_model(self) -> None:
        """Record optimize fit requests."""
        self._calls.append(("fit_model", None))


class _FakeProjectIOUseCase:
    """Minimal project I/O use case used by runtime tests."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []
        self.project = SpectroscopyProject(name="loaded")

    def create_from_fits(self, path: str, *, error_path: str | None = None) -> SpectroscopyProject:
        self.calls.append((path, error_path))
        return self.project


def test_shell_runtime_delegates_to_wrapped_main_window() -> None:
    """ShellRuntime should expose shell commands without leaking call sites."""
    window = _FakeWindow()
    runtime = ShellRuntime(
        window,
        project_io_usecase=SimpleNamespace(),  # type: ignore[arg-type]
        dialog_commands=window,
    )

    project = SpectroscopyProject()
    runtime.show()
    assert runtime.close() is True
    runtime.show_status_message("ready", 1200)
    runtime.open_observation_data()
    runtime.open_project()
    runtime.save_project()
    runtime.save_project_as()
    runtime.close_project()
    runtime.set_current_project(project)
    runtime.switch_mode(EditingMode.IDENTIFY)
    runtime.add_continuum()
    runtime.fit_model()
    runtime.open_user_manual()
    runtime.show_cosmology_dialog()
    runtime.show_resolution_dialog()
    runtime.open_line_database_folder()
    runtime.show_language_dialog()
    runtime.show_preset_list_dialog()
    runtime.zoom_in()
    runtime.zoom_out()
    runtime.reset_view()
    runtime.auto_adjust_flux()
    runtime.toggle_velocity_plot_optimize()

    assert runtime.current_project is project
    assert window.status_message.calls == [("ready", 1200)]
    assert [name for name, _payload in window.calls] == [
        "show",
        "close",
        "open_observation_data",
        "open_project",
        "save_project",
        "save_project_as",
        "close_project",
        "set_current_project",
        "switch_mode",
        "add_continuum",
        "fit_model",
        "open_user_manual",
        "show_cosmology_dialog",
        "show_resolution_dialog",
        "open_line_database_folder",
        "show_language_dialog",
        "show_preset_list_dialog",
        "zoom_in",
        "zoom_out",
        "reset_view",
        "auto_adjust_flux",
        "toggle_velocity_plot_optimize",
    ]


def test_create_shell_runtime_builds_runtime_from_dependencies(monkeypatch) -> None:
    """Composition helper should return the runtime wrapper as the shell entrypoint."""
    created: list[ShellDependencies] = []
    fake_window = _FakeWindow()

    def _build_main_window(deps: ShellDependencies, *, shell_parts_factory: object) -> object:
        assert shell_parts_factory is not None
        created.append(deps)
        return fake_window

    monkeypatch.setattr("chappy.gui.shell.composition._create_main_window", _build_main_window)

    deps = ShellDependencies(
        project_io_usecase=SimpleNamespace(),
        atomic_data=SimpleNamespace(),
        preset_store=SimpleNamespace(),
        optimize_model_addition_usecase=SimpleNamespace(),
    )
    runtime = create_shell_runtime(deps)

    assert isinstance(runtime, ShellRuntime)
    assert created == [deps]
    runtime.show()
    assert fake_window.calls == [("show", None)]


def test_open_initial_file_defers_mode_selection_to_project_entry_resolver(tmp_path: Path) -> None:
    """Initial file loading should leave mode selection to project context handling."""
    file_path = tmp_path / "spectrum.fits"
    file_path.write_text("fits")
    window = _FakeWindow()
    project_io = _FakeProjectIOUseCase()
    runtime = ShellRuntime(
        window,
        project_io_usecase=project_io,  # type: ignore[arg-type]
        dialog_commands=window,
    )

    runtime.open_initial_file(file_path, error_file="err.fits")

    assert project_io.calls == [(str(file_path), "err.fits")]
    assert ("set_current_project", project_io.project) in window.calls
    assert all(call[0] != "switch_mode" for call in window.calls)


def test_open_initial_file_reports_missing_or_unknown_input(tmp_path: Path) -> None:
    """Initial file loading should surface the same shell status for invalid input."""
    window = _FakeWindow()
    runtime = ShellRuntime(
        window,
        project_io_usecase=_FakeProjectIOUseCase(),  # type: ignore[arg-type]
        dialog_commands=window,
    )
    unknown_path = tmp_path / "unknown.txt"
    unknown_path.write_text("text")

    runtime.open_initial_file(tmp_path / "missing.fits")
    runtime.open_initial_file(unknown_path)

    assert window.status_message.calls[0][0] == "File not found: missing.fits"
    assert window.status_message.calls[1][0] == "Unknown file type: .txt"
