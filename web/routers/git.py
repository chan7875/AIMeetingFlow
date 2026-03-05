import asyncio
from pathlib import Path

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


async def _run_git_stream_step(args: list[str], emit_done: bool = True):
    async for chunk in _run_git_stream(args):
        if not emit_done and chunk.startswith("event: done"):
            continue
        yield chunk


async def _run_git_capture(args: list[str]) -> tuple[int, str, str]:
    vault = get_vault_path()
    proc = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=str(vault),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
    return (
        proc.returncode,
        stdout.decode("utf-8", errors="replace"),
        stderr.decode("utf-8", errors="replace"),
    )


def _parse_changed_files(status_text: str) -> list[dict[str, str]]:
    files: list[dict[str, str]] = []
    for line in status_text.splitlines():
        raw = line.rstrip()
        if len(raw) < 3:
            continue
        status = raw[:2]
        path = raw[3:].strip()
        if "->" in path:
            path = path.split("->", 1)[1].strip()
        if path.startswith('"') and path.endswith('"') and len(path) >= 2:
            path = path[1:-1]
        if not path:
            continue
        files.append({"path": path, "status": status.strip() or "?"})
    return files


@router.get("/status")
async def git_status():
    try:
        code, stdout, stderr = await _run_git_capture(["status", "--short"])
        if code != 0:
            return {"is_git_repo": False, "message": stderr.strip()}
        return {
            "is_git_repo": True,
            "status": stdout.strip(),
        }
    except FileNotFoundError:
        return {"is_git_repo": False, "message": "git이 설치되어 있지 않습니다."}
    except Exception as e:
        return {"is_git_repo": False, "message": str(e)}


@router.get("/changes")
async def git_changes():
    try:
        code, stdout, stderr = await _run_git_capture(["status", "--short"])
        if code != 0:
            return {"is_git_repo": False, "message": stderr.strip(), "files": []}
        return {
            "is_git_repo": True,
            "files": _parse_changed_files(stdout),
        }
    except FileNotFoundError:
        return {"is_git_repo": False, "message": "git이 설치되어 있지 않습니다.", "files": []}
    except Exception as e:
        return {"is_git_repo": False, "message": str(e), "files": []}


@router.post("/pull")
async def git_pull():
    async def generator():
        async for chunk in _run_git_stream(["pull", "origin"]):
            yield chunk

    return StreamingResponse(generator(), media_type="text/event-stream")


class PushBody(BaseModel):
    message: str = "웹 뷰어에서 업데이트"
    files: list[str] = []


@router.post("/push")
async def git_push(body: PushBody):
    commit_msg = f"auto: {body.message}"
    selected_files = []
    for rel_path in body.files:
        normalized = str(rel_path or "").strip()
        if not normalized:
            continue
        if Path(normalized).is_absolute() or ".." in Path(normalized).parts:
            raise HTTPException(status_code=400, detail=f"허용되지 않는 경로: {rel_path}")
        selected_files.append(normalized)

    if not selected_files:
        raise HTTPException(status_code=400, detail="Push할 파일을 1개 이상 선택해 주세요.")

    async def generator():
        # git add selected files only
        async for chunk in _run_git_stream_step(["add", "--", *selected_files], emit_done=False):
            yield chunk
        # git commit
        async for chunk in _run_git_stream_step(["commit", "-m", commit_msg], emit_done=False):
            yield chunk
        # git push
        async for chunk in _run_git_stream_step(["push", "origin"]):
            yield chunk

    return StreamingResponse(generator(), media_type="text/event-stream")
