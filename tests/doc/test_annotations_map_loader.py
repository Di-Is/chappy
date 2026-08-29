import textwrap

import pytest
from PySide6.QtWidgets import QMainWindow, QWidget

from chappy_user_manual_generator import annotations as doc_annotations
from chappy_user_manual_generator.annotations import DocAnnotationError


class _DummyWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.view_stack = QWidget(self)
        self.view_stack.setObjectName("viewManager")
        self._view_stack = QWidget(self.view_stack)
        self._view_stack.setObjectName("innerStack")
        self.view_stack._view_stack = self._view_stack

        extra = QWidget(self)
        extra.setObjectName("extraNode")


def test_apply_doc_annotations_with_yaml(tmp_path, monkeypatch, qtbot) -> None:
    yaml_path = tmp_path / "annotations.yaml"
    yaml_path.write_text(
        textwrap.dedent(
            """
            - target: window.view_stack
              props:
                doc.include: true
                doc.labelKey:
                  text: Mode Bar
                doc.descByScopeKey:
                  start:
                    text: Spectrum area shown while starting up.
            - target: window
              props:
                doc.windowTitleKey:
                  text: chappy User Manual
            - target: window.view_stack._view_stack
              props:
                doc.include: false
            - target: objectName:extraNode
              props:
                doc.include: false
        """
        ).strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(doc_annotations, "ANNOTATIONS_PATH", yaml_path)

    window = _DummyWindow()
    qtbot.addWidget(window)

    doc_annotations.apply_doc_annotations(window)

    assert window.view_stack.property("doc.include") is True
    assert window.view_stack.property("doc.labelKey") == "Mode Bar"
    assert window.view_stack.property("doc.descByScopeKey") == {
        "start": "Spectrum area shown while starting up."
    }
    assert window.property("doc.windowTitleKey") == "chappy User Manual"

    extra = window.findChild(QWidget, "extraNode")
    assert extra is not None
    assert extra.property("doc.include") is False
    assert window._view_stack.property("doc.include") is False


def test_apply_doc_annotations_with_invalid_text(tmp_path, monkeypatch, qtbot) -> None:
    yaml_path = tmp_path / "annotations.yaml"
    yaml_path.write_text(
        textwrap.dedent(
            """
            - target: window.view_stack
              props:
                doc.labelKey:
                  text:
                    - 1
                    - 2
            """
        ).strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(doc_annotations, "ANNOTATIONS_PATH", yaml_path)

    window = _DummyWindow()
    qtbot.addWidget(window)

    with pytest.raises(DocAnnotationError):
        doc_annotations.apply_doc_annotations(window)
