import mimetypes
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from web.config import get_vault_path, set_vault_path, get_issue_folder

router = APIRouter(prefix="/api")

MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50MB
ALLOWED_EXTENSIONS = {".md", ".txt", ".png", ".jpg", ".jpeg", ".gif", ".pdf", ".svg", ".webp"}


def _safe_resolve(relative: str) -> Path:
    """Resolve a relative path within the vault and guard against path traversal."""
    vault = get_vault_path()
    candidate = (vault / relative).resolve()
    if not str(candidate).startswith(str(vault)):
        raise HTTPException(status_code=403, detail="경로 접근이 허용되지 않습니다.")
    return candidate


def _build_tree(path: Path, vault: Path) -> dict:
    rel = str(path.relative_to(vault))
    if rel == ".":
        rel = ""
    node: dict = {"name": path.name, "path": rel, "type": "directory" if path.is_dir() else "file"}
    if path.is_dir():
        children = []
        try:
            entries = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
            for entry in entries:
                if entry.name.startswith(".") or entry.name == "__pycache__":
                    continue
                if entry.is_dir():
                    children.append(_build_tree(entry, vault))
                elif entry.suffix.lower() in {".md", ".txt"}:
                    child_rel = str(entry.relative_to(vault))
                    children.append({"name": entry.name, "path": child_rel, "type": "file"})
        except PermissionError:
            pass
        node["children"] = children
    return node


# ── Config ──────────────────────────────────────────────────────────────────

class ConfigBody(BaseModel):
    vault_path: str


@router.get("/config")
def get_config():
    vault = get_vault_path()
    return {"vault_path": str(vault), "issue_folder": get_issue_folder()}


@router.post("/config")
def update_config(body: ConfigBody):
    p = Path(body.vault_path).expanduser()
    if not p.exists():
        raise HTTPException(status_code=400, detail=f"경로가 존재하지 않습니다: {body.vault_path}")
    if not p.is_dir():
        raise HTTPException(status_code=400, detail="폴더 경로를 입력해 주세요.")
    resolved = set_vault_path(body.vault_path)
    return {"vault_path": str(resolved)}


# ── Tree ─────────────────────────────────────────────────────────────────────

@router.get("/tree")
def get_tree():
    vault = get_vault_path()
    if not vault.exists():
        raise HTTPException(status_code=404, detail=f"볼트 경로를 찾을 수 없습니다: {vault}")
    return _build_tree(vault, vault)


# ── File Read ─────────────────────────────────────────────────────────────────

@router.get("/file")
def get_file(path: str = ""):
    if not path:
        raise HTTPException(status_code=400, detail="path 파라미터가 필요합니다.")
    target = _safe_resolve(path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")
    if not target.is_file():
        raise HTTPException(status_code=400, detail="파일이 아닙니다.")
    content = target.read_text(encoding="utf-8", errors="replace")
    return {"path": path, "name": target.name, "content": content}


# ── Upload ────────────────────────────────────────────────────────────────────

@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    dest_path: str = Form(default=""),
):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"허용되지 않는 파일 형식입니다: {suffix}")

    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="파일 크기가 50MB를 초과합니다.")

    dest_dir = _safe_resolve(dest_path) if dest_path else get_vault_path()
    if not dest_dir.is_dir():
        raise HTTPException(status_code=400, detail="저장 경로가 유효한 폴더가 아닙니다.")

    save_path = dest_dir / (file.filename or "upload")
    save_path.write_bytes(data)
    vault = get_vault_path()
    return {"saved_path": str(save_path.relative_to(vault)), "name": save_path.name}
