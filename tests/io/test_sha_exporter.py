from __future__ import annotations

from pathlib import Path

from chappy.infrastructure.csv_exporter import write_csv


class TestWriteCsv:
    """Tests for write_csv encoding options."""

    def test_write_csv_utf8_no_bom(self, tmp_path: Path) -> None:
        """UTF-8 encoding should not include BOM."""
        csv_path = tmp_path / "test.csv"
        header = ["wavelength[Å]", "flux"]
        rows = [["1548.2", "0.5"]]

        write_csv(csv_path, header, rows, encoding="utf-8")

        raw_bytes = csv_path.read_bytes()
        # UTF-8 BOM is 0xEF 0xBB 0xBF
        assert not raw_bytes.startswith(b"\xef\xbb\xbf")
        # Content should still be valid UTF-8
        content = csv_path.read_text(encoding="utf-8")
        assert "wavelength[Å]" in content

    def test_write_csv_utf8_sig_includes_bom(self, tmp_path: Path) -> None:
        """UTF-8-sig encoding should include BOM for Excel compatibility."""
        csv_path = tmp_path / "test.csv"
        header = ["wavelength[Å]", "flux"]
        rows = [["1548.2", "0.5"]]

        write_csv(csv_path, header, rows, encoding="utf-8-sig")

        raw_bytes = csv_path.read_bytes()
        # UTF-8 BOM should be present
        assert raw_bytes.startswith(b"\xef\xbb\xbf")
        # Content should be readable with utf-8-sig
        content = csv_path.read_text(encoding="utf-8-sig")
        assert "wavelength[Å]" in content

    def test_write_csv_default_encoding_is_utf8(self, tmp_path: Path) -> None:
        """Default encoding should be UTF-8 without BOM."""
        csv_path = tmp_path / "test.csv"
        header = ["col"]
        rows = [["value"]]

        write_csv(csv_path, header, rows)  # No encoding specified

        raw_bytes = csv_path.read_bytes()
        assert not raw_bytes.startswith(b"\xef\xbb\xbf")
