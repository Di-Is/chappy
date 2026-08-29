"""Validated editor for the Identify future-candidate analysis half-width."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from PySide6.QtCore import QSignalBlocker, Signal
from PySide6.QtWidgets import QDoubleSpinBox, QSizePolicy, QWidget

from chappy.core.velocity_ranges import NewCandidateAnalysisHalfWidth

type NewCandidateHalfWidthRejectionReason = Literal["invalid_number", "outside_supported_range"]


@dataclass(frozen=True, slots=True)
class NewCandidateHalfWidthRejection:
    """Typed user-correctable rejection from the future-candidate editor."""

    reason: NewCandidateHalfWidthRejectionReason
    entered_text: str


class NewCandidateAnalysisHalfWidthSpinBox(QDoubleSpinBox):
    """Edit a validated half-width without Qt silently clamping business limits."""

    value_accepted = Signal(object)
    input_rejected = Signal(object)

    _REPRESENTATIVE_CONTENT = "±2000 km/s"
    _FRAME_AND_BUTTON_PADDING_PX = 40

    def __init__(self, parent: QWidget | None = None) -> None:
        """Configure a broad mechanical range and explicit domain validation."""
        super().__init__(parent)
        self.setObjectName("identifyNewCandidateAnalysisHalfWidthSpinBox")
        self.setDecimals(0)
        self.setSingleStep(10.0)
        self.setPrefix("±")
        self.setSuffix(" km/s")
        self.setKeyboardTracking(False)
        self.setRange(-1_000_000_000.0, 1_000_000_000.0)
        self.setWrapping(False)
        practical_width = (
            self.fontMetrics().horizontalAdvance(self._REPRESENTATIVE_CONTENT)
            + self._FRAME_AND_BUTTON_PADDING_PX
        )
        self.setFixedWidth(practical_width)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self._accepted_value = NewCandidateAnalysisHalfWidth(200.0)
        self._raw_text: str | None = None
        self.lineEdit().textEdited.connect(self._capture_raw_text)
        self.editingFinished.connect(self._commit_text)
        self.set_accepted_value(self._accepted_value)

    @property
    def accepted_value(self) -> NewCandidateAnalysisHalfWidth:
        """Return the last value accepted by the domain validator."""
        return self._accepted_value

    def set_accepted_value(self, value: NewCandidateAnalysisHalfWidth) -> None:
        """Render an already validated value without emitting user intent."""
        blocker = QSignalBlocker(self)
        self._accepted_value = value
        self.setValue(value.kms)
        self._raw_text = None
        del blocker

    def stepBy(self, steps: int) -> None:  # noqa: N802 - Qt virtual API
        """Route buttons and arrow keys through the same domain validator."""
        candidate = self._accepted_value.kms + (steps * self.singleStep())
        self._commit_candidate(candidate, entered_text=f"{candidate:g}")

    def _capture_raw_text(self, text: str) -> None:
        self._raw_text = text

    def _commit_text(self) -> None:
        entered_text = self._raw_text if self._raw_text is not None else self.cleanText()
        numeric_text = entered_text.strip()
        if numeric_text.startswith(self.prefix()):
            numeric_text = numeric_text[len(self.prefix()) :].strip()
        suffix = self.suffix().strip()
        if numeric_text.endswith(suffix):
            numeric_text = numeric_text[: -len(suffix)].strip()
        candidate, valid = self.locale().toDouble(numeric_text)
        if not valid:
            self._reject("invalid_number", entered_text)
            return
        self._commit_candidate(candidate, entered_text=entered_text)

    def _commit_candidate(self, candidate: float, *, entered_text: str) -> None:
        try:
            value = NewCandidateAnalysisHalfWidth(candidate)
        except ValueError:
            self._reject("outside_supported_range", entered_text)
            return
        self.set_accepted_value(value)
        self.value_accepted.emit(value)

    def _reject(self, reason: NewCandidateHalfWidthRejectionReason, entered_text: str) -> None:
        retained = self._accepted_value
        self.set_accepted_value(retained)
        self.input_rejected.emit(
            NewCandidateHalfWidthRejection(reason=reason, entered_text=entered_text)
        )


__all__ = [
    "NewCandidateAnalysisHalfWidthSpinBox",
    "NewCandidateHalfWidthRejection",
    "NewCandidateHalfWidthRejectionReason",
]
