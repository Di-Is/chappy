"""Validated spin box for plot-local velocity display half-width input."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from PySide6.QtCore import QSignalBlocker, Signal
from PySide6.QtWidgets import QDoubleSpinBox, QSizePolicy, QWidget

from chappy.presentation.velocity import VelocityDisplayHalfWidth

type VelocityDisplayInputRejectionReason = Literal["invalid_number", "outside_supported_range"]


@dataclass(frozen=True, slots=True)
class VelocityDisplayInputRejection:
    """Typed user-correctable display-range input rejection."""

    reason: VelocityDisplayInputRejectionReason
    entered_text: str


class VelocityDisplayHalfWidthSpinBox(QDoubleSpinBox):
    """Spin box that rejects invalid endpoints instead of silently clamping."""

    value_accepted = Signal(object)
    input_rejected = Signal(object)

    _REPRESENTATIVE_CONTENT = "±5000.00 km/s"
    _FRAME_AND_BUTTON_PADDING_PX = 40

    def __init__(self, parent: QWidget | None = None) -> None:
        """Configure a mechanically broad editor with explicit business validation."""
        super().__init__(parent)
        self.setObjectName("velocityDisplayHalfWidthSpinBox")
        self.setDecimals(2)
        self.setSingleStep(25.0)
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

        self._accepted_value = VelocityDisplayHalfWidth(500.0)
        self._raw_text: str | None = None
        self.lineEdit().textEdited.connect(self._capture_raw_text)
        self.editingFinished.connect(self._commit_text)
        self.set_accepted_value(self._accepted_value)

    @property
    def accepted_value(self) -> VelocityDisplayHalfWidth:
        """Return the last value accepted by the business-range validator."""
        return self._accepted_value

    def set_accepted_value(self, value: VelocityDisplayHalfWidth) -> None:
        """Render an already validated value without emitting user intent."""
        blocker = QSignalBlocker(self)
        self._accepted_value = value
        self.setValue(value.value)
        self._raw_text = None
        del blocker

    def stepBy(self, steps: int) -> None:  # noqa: N802 - Qt virtual method
        """Route buttons, arrow keys, and wheel stepping through one validator."""
        candidate = self._accepted_value.value + (steps * self.singleStep())
        self._commit_candidate(candidate, entered_text=f"{candidate:g}")

    def _capture_raw_text(self, text: str) -> None:
        """Preserve the user's localized text before Qt normalizes the editor."""
        self._raw_text = text

    def _commit_text(self) -> None:
        """Parse and validate one completed keyboard edit."""
        entered_text = self._raw_text if self._raw_text is not None else self.cleanText()
        numeric_text = entered_text.strip()
        if numeric_text.startswith(self.prefix()):
            numeric_text = numeric_text[len(self.prefix()) :].strip()
        if numeric_text.endswith(self.suffix().strip()):
            numeric_text = numeric_text[: -len(self.suffix().strip())].strip()

        candidate, valid = self.locale().toDouble(numeric_text)
        if not valid:
            self._reject("invalid_number", entered_text)
            return
        self._commit_candidate(candidate, entered_text=entered_text)

    def _commit_candidate(self, candidate: float, *, entered_text: str) -> None:
        """Commit a candidate or restore the prior value with a typed reason."""
        try:
            value = VelocityDisplayHalfWidth(candidate)
        except ValueError:
            self._reject("outside_supported_range", entered_text)
            return

        self.set_accepted_value(value)
        self.value_accepted.emit(value)

    def _reject(self, reason: VelocityDisplayInputRejectionReason, entered_text: str) -> None:
        """Restore the previous accepted value and expose the correction reason."""
        retained = self._accepted_value
        self.set_accepted_value(retained)
        self.input_rejected.emit(
            VelocityDisplayInputRejection(reason=reason, entered_text=entered_text)
        )


__all__ = [
    "VelocityDisplayHalfWidthSpinBox",
    "VelocityDisplayInputRejection",
    "VelocityDisplayInputRejectionReason",
]
