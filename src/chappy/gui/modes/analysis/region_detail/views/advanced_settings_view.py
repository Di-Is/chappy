"""Region Detail advanced settings card: convergence tuning for the active region."""

from __future__ import annotations

import math

from PySide6.QtCore import QSignalBlocker, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from chappy.core.optimizer_settings import (
    DEFAULT_AUTO_CONTINUE,
    DEFAULT_MAX_FUNCTION_EVALUATIONS,
    DEFAULT_TOLERANCE,
)
from chappy.gui.common.disclosure_header import DisclosureHeaderButton
from chappy.gui.common.side_panel_section import SidePanelSection
from chappy.gui.theme import Colors, apply_button_variant
from chappy.gui.visual_tokens import SidePanelMetrics

_TOLERANCE_CHOICES: tuple[tuple[str, float], ...] = (
    ("1e-6", 1e-6),
    ("1e-8", 1e-8),
    ("1e-10", 1e-10),
    ("1e-12", 1e-12),
)


class RegionDetailAdvancedSettingsView(QWidget):
    """Disclosure card exposing per-region optimizer convergence settings.

    Persisting the disclosure state and applying settings to the live
    optimizer stay with the panel; this view only owns the widgets and
    reports intent through typed signals.
    """

    expanded_toggled = Signal(bool)
    settings_changed = Signal()

    def __init__(self, *, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._frame = SidePanelSection(self, object_name="analysisDetailAdvancedCard")

        self._toggle = DisclosureHeaderButton(
            self._frame,
            object_name="advancedSettingsToggle",
            title_object_name="advancedSettingsTitleLabel",
        )
        self._toggle.setChecked(False)

        self._content = QWidget(self._frame)
        self._content.setObjectName("analysisDetailAdvancedContent")

        self._info_label = QLabel(self._content)
        self._info_label.setObjectName("analysisDetailAdvancedInfoLabel")
        self._info_label.setWordWrap(True)
        self._info_label.setStyleSheet(
            f"QLabel#analysisDetailAdvancedInfoLabel {{"
            f" color: {Colors.TEXT_SECONDARY}; font-style: italic; }}"
        )

        self._max_nfev_label = QLabel(self._content)
        self._max_nfev_spin = QSpinBox(self._content)
        self._max_nfev_spin.setObjectName("analysisDetailAdvancedMaxNfevSpin")
        self._max_nfev_spin.setRange(100, 100_000)
        self._max_nfev_spin.setSingleStep(100)
        self._max_nfev_spin.setValue(DEFAULT_MAX_FUNCTION_EVALUATIONS)

        self._tolerance_label = QLabel(self._content)
        self._tolerance_combo = QComboBox(self._content)
        self._tolerance_combo.setObjectName("analysisDetailAdvancedToleranceCombo")
        for label, value in _TOLERANCE_CHOICES:
            self._tolerance_combo.addItem(label, userData=value)
        self._tolerance_combo.setCurrentIndex(self._tolerance_index_for(DEFAULT_TOLERANCE))

        self._auto_continue_check = QCheckBox(self._content)
        self._auto_continue_check.setObjectName("analysisDetailAdvancedAutoContinueCheck")
        self._auto_continue_check.setChecked(DEFAULT_AUTO_CONTINUE)

        self._reset_button = QPushButton(self._content)
        self._reset_button.setObjectName("analysisDetailAdvancedResetButton")
        apply_button_variant(self._reset_button, "text")

        self._build_layout()

        self._toggle.toggled.connect(self._on_toggled)
        self._max_nfev_spin.valueChanged.connect(lambda _value: self.settings_changed.emit())
        self._tolerance_combo.currentIndexChanged.connect(
            lambda _index: self.settings_changed.emit()
        )
        self._auto_continue_check.toggled.connect(lambda _checked: self.settings_changed.emit())
        self._reset_button.clicked.connect(self._on_reset_clicked)

    def _build_layout(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._frame)

        advanced_layout = self._frame.body
        advanced_layout.addWidget(self._toggle)

        content_layout = QVBoxLayout(self._content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(SidePanelMetrics.SECTION_SPACING // 2)
        content_layout.addWidget(self._info_label)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.addRow(self._max_nfev_label, self._max_nfev_spin)
        form.addRow(self._tolerance_label, self._tolerance_combo)
        content_layout.addLayout(form)
        content_layout.addWidget(self._auto_continue_check)
        content_layout.addWidget(self._reset_button)

        advanced_layout.addWidget(self._content)

    def retranslate_ui(self) -> None:
        """Reapply translated text to all owned widgets."""
        self._toggle.set_title(self.tr("Advanced settings"))
        self._info_label.setText(self.tr("Applies to fits of this region."))
        self._max_nfev_label.setText(self.tr("Max evaluations per round"))
        self._tolerance_label.setText(self.tr("Convergence tolerance"))
        self._auto_continue_check.setText(self.tr("Continue automatically if not converged"))
        self._auto_continue_check.setToolTip(
            self.tr("Restart a stalled fit from its best point to reach convergence.")
        )
        self._reset_button.setText(self.tr("Reset to defaults"))

    def toggle_button(self) -> DisclosureHeaderButton:
        """Return the disclosure toggle (used by tests to inspect checked state)."""
        return self._toggle

    def content_widget(self) -> QWidget:
        """Return the collapsible content widget (used by tests to inspect visibility)."""
        return self._content

    def max_nfev_spin(self) -> QSpinBox:
        """Return the max-function-evaluations spin box."""
        return self._max_nfev_spin

    def tolerance_combo(self) -> QComboBox:
        """Return the convergence-tolerance combo box."""
        return self._tolerance_combo

    def reset_button(self) -> QPushButton:
        """Return the reset-to-defaults button."""
        return self._reset_button

    def auto_continue_check(self) -> QCheckBox:
        """Return the auto-continue checkbox."""
        return self._auto_continue_check

    def set_expanded(self, expanded: bool) -> None:
        """Apply an expanded state without emitting ``expanded_toggled`` (used to restore)."""
        with QSignalBlocker(self._toggle):
            self._toggle.setChecked(expanded)
        self._apply_expanded(expanded)

    def show_settings(
        self, max_function_evaluations: int, tolerance: float, auto_continue: bool
    ) -> None:
        """Display given optimizer settings without emitting ``settings_changed``."""
        with (
            QSignalBlocker(self._max_nfev_spin),
            QSignalBlocker(self._tolerance_combo),
            QSignalBlocker(self._auto_continue_check),
        ):
            self._max_nfev_spin.setValue(max_function_evaluations)
            self._tolerance_combo.setCurrentIndex(self._tolerance_index_for(tolerance))
            self._auto_continue_check.setChecked(auto_continue)

    def current_settings(self) -> tuple[int, float, bool]:
        """Return the currently displayed optimizer settings."""
        max_function_evaluations = self._max_nfev_spin.value()
        tolerance = float(self._tolerance_combo.currentData())
        auto_continue = self._auto_continue_check.isChecked()
        return max_function_evaluations, tolerance, auto_continue

    def _apply_expanded(self, expanded: bool) -> None:
        self._content.setVisible(expanded)
        self._toggle.set_chevron_expanded(expanded)

    def _on_toggled(self, expanded: bool) -> None:
        self._apply_expanded(expanded)
        self.expanded_toggled.emit(expanded)

    def _on_reset_clicked(self) -> None:
        self.show_settings(
            DEFAULT_MAX_FUNCTION_EVALUATIONS, DEFAULT_TOLERANCE, DEFAULT_AUTO_CONTINUE
        )
        self.settings_changed.emit()

    @staticmethod
    def _tolerance_index_for(tolerance: float) -> int:
        for index, (_label, value) in enumerate(_TOLERANCE_CHOICES):
            if math.isclose(value, tolerance, rel_tol=1e-9):
                return index
        return 1
