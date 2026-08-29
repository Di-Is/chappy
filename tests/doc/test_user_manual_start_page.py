from __future__ import annotations

from pathlib import Path

import pytest


def _extract_first_table(text: str) -> list[str]:
    lines = text.splitlines()
    table: list[str] = []
    in_table = False
    for line in lines:
        if line.startswith("|"):
            table.append(line)
            in_table = True
            continue
        if in_table:
            break
    return table


@pytest.mark.skip(reason="生成物(dist/)のテストは環境依存のためスキップ")
def test_start_mode_table_has_single_data_row() -> None:
    doc_path = (
        Path(__file__).resolve().parents[2]
        / "docs"
        / "user_manual"
        / "dist"
        / "markdown_ja"
        / "screens"
        / "main_window"
        / "mode_start"
        / "MainWindow.md"
    )
    text = doc_path.read_text(encoding="utf-8")
    table_lines = _extract_first_table(text)
    assert not table_lines, "スタートモードではテーブルを生成しない想定です"

    assert "![annotated]" in text, "注釈付きスクリーンショットが欠落しています"
    assert "## 主な操作" in text, "主な操作セクションが欠落しています"
    operations_section = text.split("## 主な操作", maxsplit=1)[1]
    assert "- " in operations_section, "主な操作セクションに箇条書きの項目が必要です"
