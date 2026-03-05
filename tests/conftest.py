import pytest
from unittest.mock import patch
from pathlib import Path
from fastapi.testclient import TestClient


@pytest.fixture
def tmp_vault(tmp_path):
    """Create a temporary vault with sample files."""
    (tmp_path / "Notes").mkdir()
    (tmp_path / "Notes" / "sub").mkdir()
    (tmp_path / "Notes" / "hello.md").write_text("# Hello\nWorld", encoding="utf-8")
    (tmp_path / "Notes" / "sub" / "deep.md").write_text("# Deep\nNested file", encoding="utf-8")
    (tmp_path / "Notes" / "diagram.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (tmp_path / "Notes" / "manual.pdf").write_bytes(b"%PDF-1.4\n%test\n")
    (tmp_path / "readme.txt").write_text("readme content", encoding="utf-8")
    return tmp_path


@pytest.fixture
def client(tmp_vault):
    """FastAPI test client with temporary vault."""
    with patch("web.config.get_vault_path", return_value=tmp_vault), \
         patch("web.routers.files.get_vault_path", return_value=tmp_vault):
        from web.main import app
        yield TestClient(app)
