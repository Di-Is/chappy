"""Static checks for the Qt i18n migration PoC."""

from __future__ import annotations

import ast
from dataclasses import dataclass


@dataclass(frozen=True)
class TrCallViolation:
    """Forbidden Qt translation call found in source code.

    Args:
        line: Source line number for the violation.
        reason: Human-readable violation reason.
    """

    line: int
    reason: str


class QtTranslationCallVisitor(ast.NodeVisitor):
    """Collect Qt translation calls that lupdate cannot safely extract."""

    def __init__(self) -> None:
        """Initialize the visitor."""
        self.violations: list[TrCallViolation] = []

    def visit_Call(self, node: ast.Call) -> None:
        """Record unsafe tr/translate call patterns.

        Args:
            node: Call expression node to inspect.
        """
        if self._is_self_tr_call(node):
            self._check_self_tr_call(node)
        if self._is_qcore_translate_call(node):
            self._check_qcore_translate_call(node)
        self.generic_visit(node)

    def _is_self_tr_call(self, node: ast.Call) -> bool:
        """Return whether a call targets ``self.tr``.

        Args:
            node: Call expression node to inspect.

        Returns:
            True when the call target is ``self.tr``.
        """
        if not isinstance(node.func, ast.Attribute):
            return False
        if node.func.attr != "tr":
            return False
        return isinstance(node.func.value, ast.Name) and node.func.value.id == "self"

    def _is_qcore_translate_call(self, node: ast.Call) -> bool:
        """Return whether a call targets ``QCoreApplication.translate``.

        Args:
            node: Call expression node to inspect.

        Returns:
            True when the call target is ``QCoreApplication.translate``.
        """
        if not isinstance(node.func, ast.Attribute):
            return False
        if node.func.attr != "translate":
            return False
        return isinstance(node.func.value, ast.Name) and node.func.value.id == "QCoreApplication"

    def _check_self_tr_call(self, node: ast.Call) -> None:
        """Record a violation when ``self.tr`` uses a dynamic source.

        Args:
            node: ``self.tr`` call expression node to inspect.
        """
        if not node.args:
            self.violations.append(TrCallViolation(node.lineno, "missing source text"))
            return
        source_arg = node.args[0]
        if isinstance(source_arg, ast.Constant) and isinstance(source_arg.value, str):
            return
        self.violations.append(TrCallViolation(node.lineno, "dynamic self.tr source"))

    def _check_qcore_translate_call(self, node: ast.Call) -> None:
        """Record violations for dynamic Qt translate context or source.

        Args:
            node: ``QCoreApplication.translate`` call expression node to inspect.
        """
        if len(node.args) < 2:
            self.violations.append(TrCallViolation(node.lineno, "missing context or source"))
            return

        context_arg = node.args[0]
        source_arg = node.args[1]
        if not isinstance(context_arg, ast.Constant) or not isinstance(context_arg.value, str):
            self.violations.append(TrCallViolation(node.lineno, "dynamic translate context"))
        if not isinstance(source_arg, ast.Constant) or not isinstance(source_arg.value, str):
            self.violations.append(TrCallViolation(node.lineno, "dynamic translate source"))


def collect_qt_translation_violations(source: str) -> list[TrCallViolation]:
    """Collect forbidden Qt translation patterns from Python source.

    Args:
        source: Python source code to inspect.

    Returns:
        Detected Qt translation call violations.
    """
    tree = ast.parse(source)
    visitor = QtTranslationCallVisitor()
    visitor.visit(tree)
    return visitor.violations


def test_static_literal_translation_calls_are_allowed() -> None:
    """Verify static Qt translation calls are accepted."""
    source = """
from PySide6.QtCore import QCoreApplication

class Example:
    def render(self) -> None:
        self.tr("Open")
        self.tr("Failed to load file: {path}").format(path="/tmp/a.fits")
        self.tr("%n selected item(s)", None, 3)
        QCoreApplication.translate("MainWindow", "Open")
"""

    violations = collect_qt_translation_violations(source)

    assert violations == []


def test_dynamic_translation_calls_are_flagged() -> None:
    """Verify dynamic Qt translation calls are rejected."""
    source = """
from PySide6.QtCore import QCoreApplication

class Example:
    def render(self, label: str, name: str, context: str) -> None:
        self.tr(label)
        self.tr(f"Open {name}")
        self.tr("Open " + name)
        QCoreApplication.translate(context, "Open")
        QCoreApplication.translate("MainWindow", label)
"""

    violations = collect_qt_translation_violations(source)
    reasons = [violation.reason for violation in violations]

    assert reasons == [
        "dynamic self.tr source",
        "dynamic self.tr source",
        "dynamic self.tr source",
        "dynamic translate context",
        "dynamic translate source",
    ]
