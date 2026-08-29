"""GUI adapter for optimize confirmation and message dialogs."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QMessageBox, QWidget


class OptimizeConfirmDialogAdapter:
    """Show optimize confirmation and informational message boxes."""

    def __init__(self, parent: QWidget) -> None:
        """Initialize the adapter.

        Args:
            parent: Parent widget for modal dialogs.
        """
        self._parent = parent

    def confirm_component_deletion(self, component_count: int) -> bool:
        """Return whether the user confirmed deleting the given component count.

        Args:
            component_count: Number of components targeted for deletion.

        Returns:
            Whether deletion is confirmed.
        """
        if not component_count:
            return False

        msg = QMessageBox(self._parent)
        msg.setWindowTitle(QCoreApplication.translate("RegionDetailPanel", "Confirm"))

        if component_count == 1:
            msg.setText(
                QCoreApplication.translate(
                    "RegionDetailPanel", "Do you want to delete this component?"
                )
            )
        else:
            template = QCoreApplication.translate(
                "RegionDetailPanel", "Delete {count} components?"
            )
            msg.setText(template.format(count=component_count))

        msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        msg.setDefaultButton(QMessageBox.StandardButton.No)

        return msg.exec() == QMessageBox.StandardButton.Yes

    def confirm_tie_set_redshift_divergence(
        self, max_delta_z: float, adopted_redshift: float
    ) -> bool:
        """Return whether the user confirmed sharing despite redshift divergence.

        Args:
            max_delta_z: Largest redshift difference among selected components.
            adopted_redshift: Redshift value that will be adopted for all components.

        Returns:
            Whether the divergence is confirmed.
        """
        msg = QMessageBox(self._parent)
        msg.setWindowTitle(QCoreApplication.translate("RegionDetailPanel", "Confirm"))
        template = QCoreApplication.translate(
            "RegionDetailPanel",
            "Selected components differ in z by up to {delta_z}. Sharing will align all"
            " components to z={adopted_z} (first component's value). Continue?",
        )
        msg.setText(
            template.format(delta_z=f"{max_delta_z:.6f}", adopted_z=f"{adopted_redshift:.5f}")
        )
        msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        msg.setDefaultButton(QMessageBox.StandardButton.No)
        return msg.exec() == QMessageBox.StandardButton.Yes

    def show_mask_velocity_disabled_message(self) -> None:
        """Notify the user that mask editing is unavailable in velocity mode."""
        QMessageBox.warning(
            self._parent,
            QCoreApplication.translate("RegionDetailPanel", "Error"),
            QCoreApplication.translate(
                "RegionDetailPanel", "Mask editing is disabled in velocity"
            ),
        )

    def show_mask_group_missing_message(self) -> None:
        """Notify the user that no maskable group is selected."""
        QMessageBox.information(
            self._parent,
            QCoreApplication.translate("RegionDetailPanel", "Masked Range"),
            QCoreApplication.translate(
                "RegionDetailPanel", "Cannot add a masked range because no regions exist."
            ),
        )
