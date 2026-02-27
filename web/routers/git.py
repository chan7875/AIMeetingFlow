import asyncio

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from web.config import get_vault_path

router = APIRouter(prefix="/api/git")


def _sse(data: str, event: str = "message") -> str:
    lines = data.replace("\r\n", "\n").split("\n")
    payload = "\n".join(f"data: {line}" for line in lines)
    return f"event: {event}\n{payload}\n\n"


async def _run_git_stream(args: list[str]):
    """Run a git command in the vault directory and stream output as SSE."""
    vault = get_vault_path()
    if not vault.exists():
        yield _sse(f"오류: 볼트 경로를 찾을 수 없습니다: {vault}", event="error")
        return

    command = ["git"] + args
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=str(vault),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,  # merge stderr into stdout
        )
    except FileNotFoundError:
        yield _sse("오류: git 명령어를 찾을 수 없습니다.", event="error")
        return

    async def _pump():
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            yield line.decode("utf-8", errors="replace")

    try:
        async with asyncio.timeout(120):
            async for line in _pump():
                yield _sse(line, event="chunk")
            await process.wait()
    except TimeoutError:
        process.kill()
        await process.wait()
        yield _sse("오류: git 명령 실행 시간 초과(120초)", event="error")
        return

    if process.returncode == 0:
        yield _sse("완료", event="done")
    else:
        yield _sse(f"오류: git 명령 실패 (returncode={process.returncode})", event="error")


@router.get("/status")
async def git_status():
    vault = get_vault_path()
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "status", "--short",
            cwd=str(vault),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        if proc.returncode != 0:
            return {"is_git_repo": False, "message": stderr.decode().strip()}
        return {
            "is_git_repo": True,
            "status": stdout.decode("utf-8", errors="replace").strip(),
        }
    except FileNotFoundError:
        return {"is_git_repo": False, "message": "git이 설치되어 있지 않습니다."}
    except Exception as e:
        return {"is_git_repo": False, "message": str(e)}


@router.post("/pull")
async def git_pull():
    async def generator():
        async for chunk in _run_git_stream(["pull", "origin"]):
            yield chunk

    return StreamingResponse(generator(), media_type="text/event-stream")


class PushBody(BaseModel):
    message: str = "웹 뷰어에서 업데이트"


@router.post("/push")
async def git_push(body: PushBody):
    commit_msg = f"auto: {body.message}"

    async def generator():
        # git add -A
        async for chunk in _run_git_stream(["add", "-A"]):
            yield chunk
        # git commit
        async for chunk in _run_git_stream(["commit", "-m", commit_msg]):
            yield chunk
        # git push
        async for chunk in _run_git_stream(["push", "origin"]):
            yield chunk

    return StreamingResponse(generator(), media_type="text/event-stream")
