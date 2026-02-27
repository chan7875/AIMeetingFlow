import asyncio
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from web.config import (
    get_auto_watch_enabled,
    get_issue_folder,
    get_vault_path,
    set_auto_watch_enabled,
)

# Claude CLI가 Claude Code 내부에서 실행될 때 nested session 오류를 막기 위해
# CLAUDECODE 환경변수를 제거한 환경을 미리 준비해 둔다.
_CLEAN_ENV = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

router = APIRouter(prefix="/api/ai")

DEFAULT_PROMPT = """\
다음 마크다운 파일의 내용을 핵심 위주로 요약해 주세요.
현재 선택된 md 파일 상단에 아래의 내용을 추가를 해 줘.
 - account 는 md 파일이 포함된 상단의 폴더 이름이야.
 - Date : 는 md 파일 내의 날짜를 분석해서 입력해 줘, 포맷은 년-월-일 이고, 예시는 2026-02-02 야.
 - tags : [type 값, account 값] 을 입력해 줘.
주제, 핵심 내용, 액션 아이템을 구분하여 정리해 주세요.
아래에 제공된 Template_Issue.md 포맷에 맞춰서 마크다운으로 작성해 줘.
파일 저장은 시스템이 자동으로 처리하므로, 파일 쓰기는 하지 말고 내용만 출력해 줘.\
"""

AUTO_WATCH_EXTENSIONS = {".md", ".txt"}
AUTO_WATCH_EXCLUDED_DIR_NAMES = {".git", "__pycache__", "issues"}
AUTO_WATCH_POLL_SEC = 2.0
AUTO_WATCH_SETTLE_ATTEMPTS = 3
AUTO_WATCH_SETTLE_INTERVAL_SEC = 0.5

_AUTO_WATCH_STATE: dict[str, Any] = {
    "enabled": get_auto_watch_enabled(),
    "task": None,
    "known_files": set(),
    "vault_path": "",
    "processed_count": 0,
    "last_processed_file": "",
    "last_saved_path": "",
    "last_processed_at": "",
    "last_error": "",
    "last_error_at": "",
}
_AUTO_WATCH_LOCK = asyncio.Lock()


def _resolve_command(engine: str) -> list[str]:
    if engine == "codex":
        return ["codex", "exec"]
    return ["claude", "-p"]


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _safe_resolve_in_vault(vault: Path, relative_path: str) -> Path:
    resolved = (vault / relative_path).resolve()
    try:
        resolved.relative_to(vault)
    except ValueError as exc:
        raise PermissionError("경로 접근이 허용되지 않습니다.") from exc
    return resolved


def _scan_watch_candidates(vault: Path) -> set[str]:
    if not vault.exists() or not vault.is_dir():
        return set()

    excluded = {name.lower() for name in AUTO_WATCH_EXCLUDED_DIR_NAMES}
    issue_folder = get_issue_folder().strip().lower()
    if issue_folder:
        excluded.add(issue_folder)

    discovered: set[str] = set()
    for root, dirs, files in os.walk(vault):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d.lower() not in excluded]

        root_path = Path(root)
        for filename in files:
            if filename.startswith("."):
                continue
            if Path(filename).suffix.lower() not in AUTO_WATCH_EXTENSIONS:
                continue

            file_path = root_path / filename
            try:
                rel_path = file_path.relative_to(vault)
            except ValueError:
                continue

            if any(part.lower() in excluded for part in rel_path.parts[:-1]):
                continue

            discovered.add(str(rel_path))
    return discovered


def _build_context(vault: Path, file_path: str) -> str:
    """파일 경로로부터 account, 템플릿, 기존 이슈 목록을 조합해 컨텍스트 문자열을 반환한다."""
    parts: list[str] = []
    path_parts = Path(file_path).parts

    # account = 볼트 루트 바로 아래 폴더명 (파일이 루트에 있으면 "루트")
    account = path_parts[0] if len(path_parts) > 1 else ""
    parts.append(
        f"[파일 정보]\n"
        f"- 파일 경로: {file_path}\n"
        f"- Account(상위 폴더): {account or '(볼트 루트)'}"
    )

    # Template_Issue.md 내용 주입
    template_path = vault / "_Templates" / "Template_Issue.md"
    if template_path.exists():
        tmpl = template_path.read_text(encoding="utf-8", errors="replace")
        parts.append(f"[Template_Issue.md 내용 — 이 포맷에 맞춰 작성]\n{tmpl}")

    # account 하위 Issues 폴더의 기존 파일 목록 (번호 채번 참고용)
    if account:
        issues_dir = vault / account / "Issues"
        if issues_dir.exists():
            issue_files = sorted(f.name for f in issues_dir.glob("*.md"))
            if issue_files:
                file_list = "\n".join(f"- {f}" for f in issue_files)
                parts.append(
                    f"[{account}/Issues/ 폴더의 기존 파일 목록 — 이름 규칙 참고]\n{file_list}"
                )
            else:
                parts.append(f"[{account}/Issues/ 폴더]: 비어 있음 (첫 번째 이슈로 -001 사용)")

    return "\n\n".join(parts)


def _build_input(content: str, prompt: str, context: str = "") -> str:
    parts = [prompt.strip()]
    if context:
        parts.append(context)
    parts.append(f"[파일 내용]\n{content.strip()}")
    return "\n\n".join(parts) + "\n"


def _extract_issue_index(stem: str) -> int | None:
    patterns = [
        r"^[^_]+_(\d+)_",   # 새 규칙: folder_001_title
        r"^[^-]+-(\d+)_",   # 기존 규칙: CODE-001_title
    ]
    for pattern in patterns:
        match = re.match(pattern, stem)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                return None
    return None


def _extract_title_from_ai_output(ai_output: str, fallback: str) -> str:
    text = (ai_output or "").strip()
    if not text:
        return fallback

    lines = text.splitlines()

    # YAML frontmatter의 title: 값을 우선 사용
    if lines and lines[0].strip() == "---":
        for line in lines[1:120]:
            if line.strip() == "---":
                break
            match = re.match(r"^\s*title\s*:\s*(.+?)\s*$", line, flags=re.IGNORECASE)
            if match:
                value = match.group(1).strip().strip("\"'")
                if value:
                    return value

    # 첫 번째 Markdown heading 사용
    for line in lines:
        heading = line.strip()
        if heading.startswith("#"):
            value = heading.lstrip("#").strip()
            if value:
                return value

    return fallback


def _sanitize_filename_token(value: str, fallback: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        raw = fallback

    cleaned = re.sub(r"[\\/:*?\"<>|]+", "", raw)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = cleaned.replace(" ", "_")
    cleaned = re.sub(r"_+", "_", cleaned).strip("._")
    if not cleaned:
        cleaned = fallback
    return cleaned[:80]


def _save_ai_output(vault: Path, source_path: str, source_abs: Path, ai_output: str) -> dict[str, str]:
    path_parts = Path(source_path).parts
    account = path_parts[0] if len(path_parts) > 1 else ""
    if account:
        issue_dir = vault / account / "Issues"
    else:
        issue_dir = vault / get_issue_folder()
    issue_dir.mkdir(parents=True, exist_ok=True)

    existing = sorted(f.stem for f in issue_dir.glob("*.md"))
    next_num = 1
    for stem in existing:
        index = _extract_issue_index(stem)
        if index is not None:
            next_num = max(next_num, index + 1)

    folder_token = _sanitize_filename_token(account or issue_dir.name or "issue", "issue")
    title_raw = _extract_title_from_ai_output(ai_output, source_abs.stem)
    title_token = _sanitize_filename_token(title_raw, source_abs.stem or "untitled")

    out_name = f"{folder_token}_{next_num:03d}_{title_token}.md"
    out_path = issue_dir / out_name
    out_path.write_text(ai_output, encoding="utf-8")
    return {"saved_path": str(out_path.relative_to(vault)), "name": out_name}


async def _run_subprocess_once(command: list[str], full_input: str, timeout_sec: int, cwd: str | None = None) -> str:
    try:
        proc = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=_CLEAN_ENV,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"`{command[0]}` 명령어를 찾을 수 없습니다.") from exc

    try:
        stdout_data, stderr_data = await asyncio.wait_for(
            proc.communicate(input=full_input.encode("utf-8")),
            timeout=timeout_sec,
        )
    except asyncio.TimeoutError as exc:
        proc.kill()
        await proc.wait()
        raise RuntimeError(f"실행 시간 초과({timeout_sec}초)") from exc

    ai_output = stdout_data.decode("utf-8", errors="replace").strip()
    stderr_text = stderr_data.decode("utf-8", errors="replace").strip()

    if proc.returncode != 0:
        detail = stderr_text or f"실행 실패 (returncode={proc.returncode})"
        raise RuntimeError(detail)
    if not ai_output:
        detail = f"AI가 빈 결과를 반환했습니다.{chr(10) + stderr_text if stderr_text else ''}"
        raise RuntimeError(detail)
    return ai_output


async def summarize_file_to_issue(
    file_path: str,
    engine: str = "claude",
    prompt: str = DEFAULT_PROMPT,
    timeout_sec: int = 600,
) -> dict[str, str]:
    vault = get_vault_path()
    file_abs = _safe_resolve_in_vault(vault, file_path)

    if not file_abs.exists() or not file_abs.is_file():
        raise FileNotFoundError("파일을 찾을 수 없습니다.")

    content = file_abs.read_text(encoding="utf-8", errors="replace")
    command = _resolve_command(engine.lower())
    context = _build_context(vault, file_path)
    full_input = _build_input(content, prompt, context)
    ai_output = await _run_subprocess_once(command, full_input, timeout_sec, cwd=str(vault))
    return _save_ai_output(vault, file_path, file_abs, ai_output)


def _sse(data: str, event: str = "message") -> str:
    lines = data.replace("\r\n", "\n").split("\n")
    payload = "\n".join(f"data: {line}" for line in lines)
    return f"event: {event}\n{payload}\n\n"


async def _stream_subprocess(command: list[str], full_input: str, timeout_sec: int, cwd: str | None = None):
    """Yield SSE chunks from a subprocess stdout, draining stderr concurrently to prevent deadlock."""
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=_CLEAN_ENV,
        )
    except FileNotFoundError:
        yield _sse(f"오류: `{command[0]}` 명령어를 찾을 수 없습니다. 설치 및 PATH를 확인해 주세요.", event="error")
        return

    process.stdin.write(full_input.encode("utf-8"))
    await process.stdin.drain()
    process.stdin.close()

    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []
    queue: asyncio.Queue = asyncio.Queue()

    async def _pump(stream, channel: str):
        while True:
            line = await stream.readline()
            if not line:
                break
            await queue.put((channel, line.decode("utf-8", errors="replace")))
        await queue.put((channel, None))  # EOF sentinel

    tasks = [
        asyncio.create_task(_pump(process.stdout, "stdout")),
        asyncio.create_task(_pump(process.stderr, "stderr")),
    ]

    eof_count = 0
    try:
        async with asyncio.timeout(timeout_sec):
            while eof_count < 2:
                channel, text = await queue.get()
                if text is None:
                    eof_count += 1
                    continue
                if channel == "stdout":
                    stdout_chunks.append(text)
                    yield _sse(text, event="chunk")
                else:
                    stderr_chunks.append(text)
            await process.wait()
    except TimeoutError:
        process.kill()
        await process.wait()
        yield _sse(f"오류: 실행 시간 초과({timeout_sec}초)", event="error")
        return
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    if process.returncode != 0:
        stderr = "".join(stderr_chunks).strip()
        yield _sse(f"오류: 실행 실패 (returncode={process.returncode})\n{stderr}", event="error")
        return

    full_output = "".join(stdout_chunks).strip()
    if not full_output:
        stderr = "".join(stderr_chunks).strip()
        yield _sse(f"오류: AI가 빈 결과를 반환했습니다.{chr(10) + stderr if stderr else ''}", event="error")
        return

    yield _sse(full_output, event="done")


def _auto_watch_status_locked() -> dict[str, Any]:
    task = _AUTO_WATCH_STATE.get("task")
    return {
        "enabled": bool(_AUTO_WATCH_STATE["enabled"]),
        "running": bool(task and not task.done()),
        "poll_interval_sec": AUTO_WATCH_POLL_SEC,
        "processed_count": int(_AUTO_WATCH_STATE["processed_count"]),
        "last_processed_file": str(_AUTO_WATCH_STATE["last_processed_file"]),
        "last_saved_path": str(_AUTO_WATCH_STATE["last_saved_path"]),
        "last_processed_at": str(_AUTO_WATCH_STATE["last_processed_at"]),
        "last_error": str(_AUTO_WATCH_STATE["last_error"]),
        "last_error_at": str(_AUTO_WATCH_STATE["last_error_at"]),
    }


def _ensure_auto_watch_task_locked() -> None:
    task = _AUTO_WATCH_STATE.get("task")
    if task is None or task.done():
        _AUTO_WATCH_STATE["task"] = asyncio.create_task(_auto_watch_loop(), name="auto-watch-loop")


async def _set_auto_watch_error(message: str) -> None:
    async with _AUTO_WATCH_LOCK:
        _AUTO_WATCH_STATE["last_error"] = str(message)
        _AUTO_WATCH_STATE["last_error_at"] = _now_iso()


async def _wait_for_stable_file(file_abs: Path) -> bool:
    last_size = -1
    stable_count = 0
    attempts = AUTO_WATCH_SETTLE_ATTEMPTS * 3
    for _ in range(attempts):
        try:
            current_size = file_abs.stat().st_size
        except FileNotFoundError:
            return False
        if current_size == last_size:
            stable_count += 1
            if stable_count >= AUTO_WATCH_SETTLE_ATTEMPTS:
                return True
        else:
            stable_count = 0
            last_size = current_size
        await asyncio.sleep(AUTO_WATCH_SETTLE_INTERVAL_SEC)
    return file_abs.exists()


async def _handle_auto_watch_file(file_path: str) -> None:
    vault = get_vault_path()
    file_abs = _safe_resolve_in_vault(vault, file_path)
    if not file_abs.exists() or not file_abs.is_file():
        return

    if not await _wait_for_stable_file(file_abs):
        return

    saved = await summarize_file_to_issue(
        file_path=file_path,
        engine="codex",
        prompt=DEFAULT_PROMPT,
        timeout_sec=600,
    )
    async with _AUTO_WATCH_LOCK:
        _AUTO_WATCH_STATE["processed_count"] = int(_AUTO_WATCH_STATE["processed_count"]) + 1
        _AUTO_WATCH_STATE["last_processed_file"] = file_path
        _AUTO_WATCH_STATE["last_saved_path"] = saved.get("saved_path", "")
        _AUTO_WATCH_STATE["last_processed_at"] = _now_iso()
        _AUTO_WATCH_STATE["last_error"] = ""
        _AUTO_WATCH_STATE["last_error_at"] = ""


async def _auto_watch_loop() -> None:
    while True:
        try:
            await asyncio.sleep(AUTO_WATCH_POLL_SEC)

            async with _AUTO_WATCH_LOCK:
                enabled = bool(_AUTO_WATCH_STATE["enabled"])
            if not enabled:
                continue

            vault = get_vault_path()
            if not vault.exists() or not vault.is_dir():
                await _set_auto_watch_error(f"볼트 경로를 찾을 수 없습니다: {vault}")
                continue

            current_files = _scan_watch_candidates(vault)
            vault_text = str(vault)

            async with _AUTO_WATCH_LOCK:
                known_files = set(_AUTO_WATCH_STATE["known_files"])
                tracked_vault = str(_AUTO_WATCH_STATE["vault_path"] or "")
                _AUTO_WATCH_STATE["vault_path"] = vault_text

            if tracked_vault != vault_text:
                async with _AUTO_WATCH_LOCK:
                    _AUTO_WATCH_STATE["known_files"] = current_files
                continue

            new_files = sorted(current_files - known_files)
            async with _AUTO_WATCH_LOCK:
                _AUTO_WATCH_STATE["known_files"] = current_files

            for rel_path in new_files:
                async with _AUTO_WATCH_LOCK:
                    if not _AUTO_WATCH_STATE["enabled"]:
                        break
                try:
                    await _handle_auto_watch_file(rel_path)
                except Exception as exc:  # noqa: BLE001 - watcher should not crash loop
                    await _set_auto_watch_error(f"{rel_path}: {exc}")
        except asyncio.CancelledError:
            break
        except Exception as exc:  # noqa: BLE001 - watcher should not crash loop
            await _set_auto_watch_error(str(exc))
            await asyncio.sleep(1.0)


async def start_auto_watch() -> None:
    async with _AUTO_WATCH_LOCK:
        _ensure_auto_watch_task_locked()
        enabled = bool(_AUTO_WATCH_STATE["enabled"])

    if enabled:
        vault = get_vault_path()
        snapshot = _scan_watch_candidates(vault)
        async with _AUTO_WATCH_LOCK:
            _AUTO_WATCH_STATE["vault_path"] = str(vault)
            _AUTO_WATCH_STATE["known_files"] = snapshot


async def stop_auto_watch() -> None:
    async with _AUTO_WATCH_LOCK:
        task = _AUTO_WATCH_STATE.get("task")
        _AUTO_WATCH_STATE["task"] = None
    if task and not task.done():
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


class RunBody(BaseModel):
    engine: str = "claude"  # "claude" | "codex"
    content: str
    prompt: str = DEFAULT_PROMPT
    timeout_sec: int = 600
    file_path: str = ""  # 컨텍스트 주입용 (optional)


class SummarizeBody(BaseModel):
    engine: str = "claude"
    file_path: str  # relative to vault
    prompt: str = DEFAULT_PROMPT
    timeout_sec: int = 600


class AutoWatchBody(BaseModel):
    enabled: bool


@router.post("/run")
async def run_ai(body: RunBody):
    """Stream AI output for given content + prompt."""
    vault = get_vault_path()
    engine = body.engine.lower()
    command = _resolve_command(engine)
    context = _build_context(vault, body.file_path) if body.file_path else ""
    full_input = _build_input(body.content, body.prompt, context)
    cwd = str(vault)

    async def generator():
        async for chunk in _stream_subprocess(command, full_input, body.timeout_sec, cwd=cwd):
            yield chunk

    return StreamingResponse(generator(), media_type="text/event-stream")


@router.post("/summarize")
async def summarize_and_save(body: SummarizeBody):
    """Run AI summarization on a vault file and save result to issue folder."""
    try:
        return await summarize_file_to_issue(
            file_path=body.file_path,
            engine=body.engine.lower(),
            prompt=body.prompt,
            timeout_sec=body.timeout_sec,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/auto-watch")
async def get_auto_watch_status():
    async with _AUTO_WATCH_LOCK:
        _ensure_auto_watch_task_locked()
        return _auto_watch_status_locked()


@router.post("/auto-watch")
async def set_auto_watch_status(body: AutoWatchBody):
    enabled = set_auto_watch_enabled(body.enabled)
    vault = get_vault_path()
    snapshot = _scan_watch_candidates(vault) if enabled else set()

    async with _AUTO_WATCH_LOCK:
        _AUTO_WATCH_STATE["enabled"] = enabled
        _AUTO_WATCH_STATE["vault_path"] = str(vault) if enabled else ""
        _AUTO_WATCH_STATE["known_files"] = snapshot
        if enabled:
            _AUTO_WATCH_STATE["last_error"] = ""
            _AUTO_WATCH_STATE["last_error_at"] = ""
        _ensure_auto_watch_task_locked()
        return _auto_watch_status_locked()
