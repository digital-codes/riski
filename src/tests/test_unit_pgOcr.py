"""Unit tests for src.pgOcr – remote.ocr is mocked, no network."""

import pytest

from src import pgOcr


@pytest.fixture()
def mock_ocr(monkeypatch):
    calls = []

    def _ocr(document, model=None):
        calls.append(document)
        return {"pages": [{"markdown": "# Seite 1"}, {"markdown": "Seite 2"}]}

    monkeypatch.setattr(pgOcr.remote, "ocr", _ocr)
    return calls


class TestOcrPdfToMarkdown:
    def test_joins_pages(self, mock_ocr):
        md = pgOcr.ocr_pdf_to_markdown("whatever.pdf")
        assert md == "# Seite 1\n\nSeite 2"

    def test_empty_pages(self, monkeypatch):
        monkeypatch.setattr(pgOcr.remote, "ocr", lambda d: {"pages": []})
        assert pgOcr.ocr_pdf_to_markdown("x.pdf") == ""


class TestFindMissing:
    def test_skips_existing_md(self, tmp_path):
        pdf_dir = tmp_path / "pdf"
        md_dir = tmp_path / "md"
        pdf_dir.mkdir()
        md_dir.mkdir()
        (pdf_dir / "0001.pdf").write_bytes(b"%PDF")
        (pdf_dir / "0002.pdf").write_bytes(b"%PDF")
        (md_dir / "0001.md").write_text("x")
        missing = pgOcr.find_missing(pdf_dir, md_dir)
        assert [p.name for p in missing] == ["0002.pdf"]

    def test_sorted_and_empty(self, tmp_path):
        pdf_dir = tmp_path / "pdf"
        pdf_dir.mkdir()
        assert pgOcr.find_missing(pdf_dir, tmp_path / "md") == []
        for name in ("b.pdf", "a.pdf"):
            (pdf_dir / name).write_bytes(b"%PDF")
        assert [p.name for p in pgOcr.find_missing(pdf_dir, tmp_path / "md")] == ["a.pdf", "b.pdf"]


class TestRun:
    def test_writes_markdown(self, tmp_path, mock_ocr):
        pdf_dir = tmp_path / "pdf"
        md_dir = tmp_path / "md"
        pdf_dir.mkdir()
        (pdf_dir / "0001.pdf").write_bytes(b"%PDF")
        stats = pgOcr.run(pdf_dir, md_dir)
        assert stats == {"missing": 1, "ocr_ok": 1, "ocr_failed": 0, "empty": 0}
        assert (md_dir / "0001.md").read_text() == "# Seite 1\n\nSeite 2"

    def test_resumable_skips_existing(self, tmp_path, mock_ocr):
        pdf_dir = tmp_path / "pdf"
        md_dir = tmp_path / "md"
        pdf_dir.mkdir()
        md_dir.mkdir()
        (pdf_dir / "0001.pdf").write_bytes(b"%PDF")
        (md_dir / "0001.md").write_text("old")
        stats = pgOcr.run(pdf_dir, md_dir)
        assert stats["missing"] == 0
        assert (md_dir / "0001.md").read_text() == "old"
        assert mock_ocr == []

    def test_failure_continues(self, tmp_path, monkeypatch):
        pdf_dir = tmp_path / "pdf"
        md_dir = tmp_path / "md"
        pdf_dir.mkdir()
        (pdf_dir / "0001.pdf").write_bytes(b"%PDF")
        (pdf_dir / "0002.pdf").write_bytes(b"%PDF")

        def boom(document, model=None):
            raise RuntimeError("api down")

        monkeypatch.setattr(pgOcr.remote, "ocr", boom)
        stats = pgOcr.run(pdf_dir, md_dir)
        assert stats["ocr_failed"] == 2
        assert stats["ocr_ok"] == 0
        assert list(md_dir.glob("*.md")) == []

    def test_limit(self, tmp_path, mock_ocr):
        pdf_dir = tmp_path / "pdf"
        md_dir = tmp_path / "md"
        pdf_dir.mkdir()
        for n in ("a", "b", "c"):
            (pdf_dir / f"{n}.pdf").write_bytes(b"%PDF")
        stats = pgOcr.run(pdf_dir, md_dir, limit=2)
        assert stats["missing"] == 2
        assert stats["ocr_ok"] == 2

    def test_out_dir_writes_elsewhere(self, tmp_path, mock_ocr):
        pdf_dir = tmp_path / "pdf"
        md_dir = tmp_path / "md"   # canonical, read-only in production
        out_dir = tmp_path / "out"
        pdf_dir.mkdir()
        md_dir.mkdir()
        (pdf_dir / "0001.pdf").write_bytes(b"%PDF")
        stats = pgOcr.run(pdf_dir, md_dir, out_dir=out_dir)
        assert stats["ocr_ok"] == 1
        assert (out_dir / "0001.md").read_text() == "# Seite 1\n\nSeite 2"
        assert not (md_dir / "0001.md").exists()

    def test_empty_result_not_written(self, tmp_path, monkeypatch):
        pdf_dir = tmp_path / "pdf"
        md_dir = tmp_path / "md"
        pdf_dir.mkdir()
        (pdf_dir / "0001.pdf").write_bytes(b"%PDF")
        monkeypatch.setattr(pgOcr.remote, "ocr", lambda d: {"pages": [{"markdown": ""}]})
        stats = pgOcr.run(pdf_dir, md_dir)
        assert stats["empty"] == 1
        assert not (md_dir / "0001.md").exists()
