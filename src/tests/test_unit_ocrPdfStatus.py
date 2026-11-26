"""Unit tests for the OCR pre-retry PDF validity check
(update-orchestration; pdfinfo preferred, `file` fallback,
missing-command handling)."""

from pathlib import Path

import pytest

from src.update.pgOcr import pdf_status

pytestmark = pytest.mark.unit


def test_pdfinfo_unavailable_falls_back_to_file(monkeypatch, tmp_path):
    monkeypatch.setattr("subprocess.run", _res_with("empty"))
    monkeypatch.setattr("shutil.which", lambda name: None if name == "pdfinfo"
                        else "/usr/bin/file")
    pdf = tmp_path / "empty.pdf"
    pdf.write_bytes(b"")
    assert pdf_status(pdf) == "invalid"


def test_pdfinfo_reports_invalid(monkeypatch, tmp_path):
    pdf = tmp_path / "broken.pdf"
    pdf.write_bytes(b"%PDF-corrupt")
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/pdfinfo"
                        if name == "pdfinfo" else "/usr/bin/file")
    monkeypatch.setattr("subprocess.run",
                        lambda *a, **k: _res(1, "", "Invalid PDF structure"))
    assert pdf_status(pdf) == "invalid"
    monkeypatch.setattr("subprocess.run",
                        lambda *a, **k: _res(0, "Pages:          12\n", ""))
    assert pdf_status(pdf) == "ok"
    monkeypatch.setattr("subprocess.run",
                        lambda *a, **k: _res(0, "Pages:          0\n", ""))
    assert pdf_status(pdf) == "invalid"
    # missing Pages line (unexpected output) → unknown
    monkeypatch.setattr("subprocess.run",
                        lambda *a, **k: _res(0, "Producer:       skia\n", ""))
    assert pdf_status(pdf) == "unknown"


def test_missing_commands_yield_unknown(monkeypatch, tmp_path):
    monkeypatch.setattr("shutil.which", lambda name: None)
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    assert pdf_status(pdf) == "unknown"


def test_file_detects_empty_and_non_pdf(monkeypatch, tmp_path):
    monkeypatch.setattr("shutil.which", lambda name: None if name == "pdfinfo"
                        else "/usr/bin/file")
    cases = {
        "empty": "empty",
        "html junk": "HTML document, ASCII text",
        "plain data": "data",
    }
    for name, out in cases.items():
        monkeypatch.setattr("subprocess.run", _res_with(out))
        assert pdf_status(tmp_path / f"{name}.pdf") == "invalid", name


def _res_with(out):
    return lambda *a, **k: _res(0, out, "")


class _Res:
    def __init__(self, returncode, stdout, stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _res(rc, out, err=""):
    return _Res(rc, out, err)
