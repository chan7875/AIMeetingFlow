from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from web.config import get_nlm_enabled, get_vault_path, set_nlm_enabled

router = APIRouter(prefix="/api/slides")


class GenerateBody(BaseModel):
    account: str
    issue_content: str
    issue_title: str
    issue_md_name: str = ""


class EnableBody(BaseModel):
    enabled: bool


@router.post("/generate")
async def generate_slides(body: GenerateBody):
    """수동으로 슬라이드를 생성한다."""
    from services.notebooklm_service import generate_slides_for_issue

    if not body.account or not body.issue_content:
        raise HTTPException(status_code=400, detail="account와 issue_content는 필수입니다.")

    vault = get_vault_path()
    try:
        result = await generate_slides_for_issue(
            account=body.account,
            issue_content=body.issue_content,
            issue_title=body.issue_title or "untitled",
            vault=vault,
            issue_md_name=body.issue_md_name,
        )
        return result
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/notebooks")
async def get_notebooks():
    """account→notebook_id 매핑을 조회한다."""
    from services.notebooklm_service import get_notebook_map

    return get_notebook_map()


@router.get("/status")
async def get_slide_status():
    """auto-watch의 슬라이드 생성 상태를 조회한다."""
    from web.routers.ai import _AUTO_WATCH_LOCK, _AUTO_WATCH_STATE

    async with _AUTO_WATCH_LOCK:
        return {
            "nlm_enabled": get_nlm_enabled(),
            "last_slide_path": str(_AUTO_WATCH_STATE.get("last_slide_path", "")),
            "last_slide_error": str(_AUTO_WATCH_STATE.get("last_slide_error", "")),
            "last_slide_error_stage": str(_AUTO_WATCH_STATE.get("last_slide_error_stage", "")),
            "last_slide_error_type": str(_AUTO_WATCH_STATE.get("last_slide_error_type", "")),
            "last_slide_error_trace": str(_AUTO_WATCH_STATE.get("last_slide_error_trace", "")),
            "last_slide_at": str(_AUTO_WATCH_STATE.get("last_slide_at", "")),
            "slides_generated_count": int(_AUTO_WATCH_STATE.get("slides_generated_count", 0)),
        }


@router.post("/enable")
async def toggle_nlm(body: EnableBody):
    """NLM 슬라이드 생성 기능을 활성화/비활성화한다."""
    enabled = set_nlm_enabled(body.enabled)
    return {"nlm_enabled": enabled}
