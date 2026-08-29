"""Pixel-level regression tests for the palette-first theme restructure.

Guards two bugs found while restructuring `chappy.gui.theme`
(see `docs/task/theme-restructure/plan.md`):

1. A `QDialog QWidget { background-color }` bracket rule (specificity 2)
   used to shadow single-type-selector input fills (e.g. `QDoubleSpinBox`,
   specificity 1) inside dialogs.
2. `QDialog QPushButton:default` used to outrank an explicit
   `QPushButton[variant=...]` rule because it combined two type selectors
   with the `:default` pseudo-class, giving it a higher type-selector count
   at equal attribute/pseudo-class count. That implicit `:default` accent
   rule has since been removed; `[variant=...]` is now the sole color
   source, and this is a regression guard against reintroducing it.

Both are asserted by sampling grabbed pixel colors at widget centers (to
avoid anti-aliased edges) under the real application theme.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDoubleSpinBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from chappy.gui.theme import Colors, _asset_url, apply_button_variant
from tests.gui.support.faithful_env import faithful_application_environment


def _center_pixel_color(widget: QWidget) -> QColor:
    image: QImage = widget.grab().toImage()
    ratio = image.devicePixelRatio()
    center = widget.rect().center()
    return image.pixelColor(int(center.x() * ratio), int(center.y() * ratio))


def test_dialog_spin_box_fills_with_background_input(qapp: QApplication) -> None:
    """A `QDoubleSpinBox` inside a `QDialog` must keep its own input fill color."""
    with faithful_application_environment(qapp, "en"):
        dialog = QDialog()
        layout = QVBoxLayout(dialog)
        spin_box = QDoubleSpinBox(dialog)
        layout.addWidget(spin_box)
        dialog.resize(200, 100)
        dialog.show()
        qapp.processEvents()

        assert _center_pixel_color(spin_box) == QColor(Colors.BACKGROUND_INPUT)

        dialog.close()


def test_primary_variant_button_fills_with_primary_color(qapp: QApplication) -> None:
    with faithful_application_environment(qapp, "en"):
        dialog = QDialog()
        layout = QVBoxLayout(dialog)
        button = QPushButton("", dialog)
        apply_button_variant(button, "primary")
        layout.addWidget(button)
        dialog.resize(200, 100)
        dialog.show()
        qapp.processEvents()

        assert _center_pixel_color(button) == QColor(Colors.PRIMARY)

        dialog.close()


def test_danger_variant_button_fills_with_error_color(qapp: QApplication) -> None:
    with faithful_application_environment(qapp, "en"):
        dialog = QDialog()
        layout = QVBoxLayout(dialog)
        button = QPushButton("", dialog)
        apply_button_variant(button, "danger")
        layout.addWidget(button)
        dialog.resize(200, 100)
        dialog.show()
        qapp.processEvents()

        assert _center_pixel_color(button) == QColor(Colors.ERROR)

        dialog.close()


def test_indicator_svg_assets_load_as_images(qapp: QApplication) -> None:
    """The ::indicator rules reference packaged SVGs by absolute path; a missing
    file or missing Qt SVG image plugin would silently drop the check mark.
    """
    for name in ("check.svg", "radio_dot.svg"):
        path = _asset_url(name)
        assert Path(path).is_file(), f"missing packaged asset: {path}"
        assert not QImage(path).isNull(), f"asset not loadable as image: {path}"


def test_checkbox_indicator_stands_out_from_dialog_background(qapp: QApplication) -> None:
    """Unchecked indicators must not blend into the dialog background: Fusion's
    palette-derived outline is darker than the dark theme's background, so the
    theme draws indicators explicitly (`QCheckBox::indicator` rules).
    """
    with faithful_application_environment(qapp, "en"):
        dialog = QDialog()
        layout = QVBoxLayout(dialog)
        unchecked = QCheckBox("", dialog)
        checked = QCheckBox("", dialog)
        checked.setChecked(True)
        layout.addWidget(unchecked)
        layout.addWidget(checked)
        dialog.resize(200, 120)
        dialog.show()
        qapp.processEvents()

        def indicator_color(box: QCheckBox) -> QColor:
            image: QImage = box.grab().toImage()
            ratio = image.devicePixelRatio()
            # Indicator is leftmost; sample its center (16px wide per theme).
            return image.pixelColor(int(8 * ratio), int(box.rect().center().y() * ratio))

        assert indicator_color(unchecked) == QColor(Colors.BACKGROUND_INPUT)
        checked_color = indicator_color(checked)
        assert checked_color in (QColor(Colors.PRIMARY), QColor("#FFFFFF"))

        dialog.close()


def test_panel_container_stylesheets_do_not_wipe_variant_fills(qapp: QApplication) -> None:
    """Widget-level container sheets outrank the application sheet, so an
    ancestor rule like `#panel QWidget { background: transparent }` silently
    erases `QPushButton[variant=...]` fills. Guard with a real container.
    """
    from chappy.gui.shell.data_control_panel import DataControlPanel

    with faithful_application_environment(qapp, "en"):
        panel = DataControlPanel()
        for button in panel.findChildren(QPushButton):
            button.setEnabled(True)
        panel.show()
        qapp.processEvents()

        image: QImage = panel.grab().toImage()
        ratio = image.devicePixelRatio()

        def fill_color(object_name: str) -> QColor:
            button = next(
                b for b in panel.findChildren(QPushButton) if b.objectName() == object_name
            )
            # Sample inside the top padding, clear of the label glyphs.
            center = button.mapTo(panel, button.rect().center())
            top = button.mapTo(panel, button.rect().topLeft())
            return image.pixelColor(int(center.x() * ratio), int((top.y() + 5) * ratio))

        assert fill_color("resetViewButton") == QColor(Colors.SECONDARY)
        assert fill_color("autoAdjustButton") == QColor(Colors.SECONDARY)

        panel.close()


def test_dialog_default_button_keeps_its_own_variant_color(qapp: QApplication) -> None:
    """A `:default` button with an explicit non-primary variant must not turn
    primary blue. `action_row_button_style()` used to paint `QDialog
    QPushButton:default` primary regardless of variant; that rule has been
    removed, and `[variant=...]` is now the only color source, but this stays
    as a regression guard.
    """
    with faithful_application_environment(qapp, "en"):
        dialog = QDialog()
        layout = QVBoxLayout(dialog)
        button = QPushButton("", dialog)
        apply_button_variant(button, "secondary")
        button.setDefault(True)
        layout.addWidget(button)
        dialog.resize(200, 100)
        dialog.show()
        qapp.processEvents()

        assert button.isDefault()
        assert _center_pixel_color(button) == QColor(Colors.SECONDARY)

        dialog.close()
