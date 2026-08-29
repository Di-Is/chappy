"""Typed action identifiers for shell menus and toolbars."""

from __future__ import annotations

from enum import StrEnum


class ShellActionId(StrEnum):
    """Stable action vocabulary for shell command dispatch."""

    OPEN_OBSERVATION_DATA = "open_observation_data"
    OPEN_PROJECT = "open_project"
    SAVE_PROJECT = "save_project"
    SAVE_PROJECT_AS = "save_project_as"
    CLOSE_PROJECT = "close_project"
    QUIT = "quit"
    UNDO = "undo"
    REDO = "redo"
    COPY = "copy"
    PASTE = "paste"
    DELETE = "delete"
    ZOOM_IN = "zoom_in"
    ZOOM_OUT = "zoom_out"
    RESET_VIEW = "reset_view"
    AUTO_ADJUST_FLUX = "auto_adjust_flux"
    TOGGLE_VELOCITY_PLOT_IDENTIFY = "toggle_velocity_plot_identify"
    TOGGLE_VELOCITY_PLOT_ANALYSIS = "toggle_velocity_plot_analysis"
    TOGGLE_COMPONENT_PROFILES = "toggle_component_profiles"
    ZOOM_RECT = "zoom_rect"
    FIT_MODEL = "fit_model"
    IDENTIFY_MODE = "identify_mode"
    ANALYSIS_MODE = "analysis_mode"
    ANALYSIS_BACK = "analysis_back"
    CONTINUUM_MODE = "continuum_mode"
    OPEN_LINE_DATABASE_FOLDER = "open_line_database_folder"
    COSMOLOGY_SETTINGS = "cosmology_settings"
    RESOLUTION_SETTINGS = "resolution_settings"
    LANGUAGE_SETTINGS = "language_settings"
    PRESET_MANAGEMENT = "preset_management"
    HELP = "help"
    TUTORIAL = "tutorial"
    ABOUT = "about"
