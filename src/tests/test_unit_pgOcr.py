"""Unit tests for src.pgOcr – remote.ocr is mocked, no network."""

import importlib.util

import pytest

from src import pgOcr

# pypdf is an optional runtime dependency (OCR page-limit truncation);
# without it the PdfReader/PdfWriter-based tests cannot run, everything
# else here is mock-based and must still execute.
_PYPDF_MISSING = importlib.util.find_spec("pypdf") is None


@pytest.fixture()
def mock_ocr(monkeypatch):
    calls = []

    def _ocr(document, model=None, pages=None):
        calls.append((document, pages))
        return {"pages": [{"markdown": "# Seite 1"}, {"markdown": "Seite 2"}]}

    monkeypatch.setattr(pgOcr.remote, "ocr", _ocr)
    return calls


class TestOcrPdfToMarkdown:
    def test_joins_pages(self, mock_ocr):
        md = pgOcr.ocr_pdf_to_markdown("whatever.pdf")
        assert md == "# Seite 1\n\nSeite 2"
        assert mock_ocr[0][1] is None  # no page limit requested

    def test_empty_pages(self, monkeypatch):
        monkeypatch.setattr(pgOcr.remote, "ocr", lambda d, model=None, pages=None: {"pages": []})
        assert pgOcr.ocr_pdf_to_markdown("x.pdf") == ""


@pytest.mark.skipif(_PYPDF_MISSING, reason="pypdf not installed (optional OCR dependency)")
class TestPageLimit:
    def _make_pdf(self, path, n_pages):
        from pypdf import PdfWriter
        writer = PdfWriter()
        for _ in range(n_pages):
            writer.add_blank_page(width=100, height=100)
        with path.open("wb") as f:
            writer.write(f)

    def test_large_document_limited(self, tmp_path, monkeypatch):
        calls = []

        def _ocr(document, model=None, pages=None):
            calls.append(pages)
            return {"pages": [{"markdown": f"p{i}"} for i in range(12)]}

        monkeypatch.setattr(pgOcr.remote, "ocr", _ocr)
        pdf = tmp_path / "big.pdf"
        self._make_pdf(pdf, 20)
        md = pgOcr.ocr_pdf_to_markdown(pdf, max_pages=12)
        assert calls == ["0-11"]
        assert md.endswith("<!-- OCR truncated to the first 12 pages of 20 -->")

    def test_small_document_unlimited(self, tmp_path, monkeypatch):
        calls = []

        def _ocr(document, model=None, pages=None):
            calls.append(pages)
            return {"pages": [{"markdown": "p"}]}

        monkeypatch.setattr(pgOcr.remote, "ocr", _ocr)
        pdf = tmp_path / "small.pdf"
        self._make_pdf(pdf, 3)
        pgOcr.ocr_pdf_to_markdown(pdf, max_pages=12)
        assert calls == [None]

    def test_unknown_page_count_unlimited(self, tmp_path, monkeypatch):
        calls = []
        monkeypatch.setattr(pgOcr, "pdf_page_count", lambda p: None)

        def _ocr(document, model=None, pages=None):
            calls.append(pages)
            return {"pages": [{"markdown": "p"}]}

        monkeypatch.setattr(pgOcr.remote, "ocr", _ocr)
        assert pgOcr.ocr_pdf_to_markdown(tmp_path / "broken.pdf", max_pages=12) == "p"
        assert calls == [None]

    def test_max_pages_zero_disables_limit(self, tmp_path, monkeypatch):
        calls = []

        def _ocr(document, model=None, pages=None):
            calls.append(pages)
            return {"pages": [{"markdown": "p"}]}

        monkeypatch.setattr(pgOcr.remote, "ocr", _ocr)
        pdf = tmp_path / "big.pdf"
        self._make_pdf(pdf, 20)
        pgOcr.ocr_pdf_to_markdown(pdf, max_pages=None)
        assert calls == [None]


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

        def boom(document, model=None, pages=None):
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
        monkeypatch.setattr(
            pgOcr.remote, "ocr", lambda d, model=None, pages=None: {"pages": [{"markdown": ""}]}
        )
        stats = pgOcr.run(pdf_dir, md_dir)
        assert stats["empty"] == 1
        assert not (md_dir / "0001.md").exists()
