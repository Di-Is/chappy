"""GUI dialogs for Chappy."""

from .close_project_dialog import CloseProjectDialog, prompt_close_project
from .cosmology_dialog import CosmologyDialog
from .language_settings_dialog import LanguageSettingsDialog
from .line_selection_dialog import LineSelectionDialog
from .observation_data_dialog import ObservationDataDialog
from .resolution_dialog import ResolutionDialog

__all__ = [
    "CloseProjectDialog",
    "CosmologyDialog",
    "LanguageSettingsDialog",
    "LineSelectionDialog",
    "ObservationDataDialog",
    "ResolutionDialog",
    "prompt_close_project",
]
