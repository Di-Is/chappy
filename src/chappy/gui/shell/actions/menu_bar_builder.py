"""Menu-bar construction for typed shell actions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QApplication, QMenu, QMenuBar

if TYPE_CHECKING:
    from collections.abc import Callable

    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import QMainWindow

    from chappy.gui.shell.actions.ids import ShellActionId
    from chappy.gui.shell.actions.registry import MenuDefinition


class MenuBarBuilder:
    """Build a menu bar from typed menu definitions and actions."""

    def __init__(
        self,
        *,
        main_window: QMainWindow,
        menus: tuple[MenuDefinition, ...],
        actions: dict[ShellActionId, QAction],
        translator: Callable[[str], str],
    ) -> None:
        """Store the menu-building dependencies."""
        self._main_window = main_window
        self._menus = menus
        self._actions = actions
        self._translate = translator

    def build(self) -> tuple[QMenuBar, dict[str, QMenu]]:
        """Create a configured menu bar and the created menus."""
        app = QApplication.instance()
        if isinstance(app, QApplication) and not app.screens():
            menubar = QMenuBar()
            menubar.setNativeMenuBar(False)
            menubar.setParent(self._main_window)
        else:
            menubar = QMenuBar(self._main_window)

        created_menus: dict[str, QMenu] = {}
        for menu_definition in self._menus:
            menu = menubar.addMenu(self._translate(menu_definition.source.title))
            created_menus[menu_definition.name] = menu
            for entry in menu_definition.entries:
                if entry is None:
                    menu.addSeparator()
                else:
                    menu.addAction(self._actions[entry])
        return menubar, created_menus
