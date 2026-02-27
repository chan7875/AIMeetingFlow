import asyncio
import logging
import shlex
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import AsyncIterator

from config.settings import settings

logger = logging.getLogger("claude_cli")
LOG_PREVIEW_LIMIT = 240
_SESSION_STATE_LOCK = threading.Lock()
_SESSION_EXEC_LOCK = asyncio.Lock()
_SESSION_STATE = {
    "id": "",
    "turns": 0,
    "last_used": 0.0,
}


def _shorten_for_log(text: str, limit: int = LOG_PREVIEW_LIMIT) -> str:
    value = str(text or "").strip().replace("\n", "\\n")
    if len(value) <= limit:
        return value
    return f"{value[:limit]}...(truncated)"


def _resolve_command() -> list[str]:
    command_text = (settings.claude_cli_command or "claude").strip()
    command = shlex.split(command_text) if command_text else ["claude"]
    if not command:
        return ["claude"]
    binary_name = Path(command[0]).name.lower()
    has_print_flag = any(token in {"-p", "--print"} for token in command[1:])
    claude_subcommands = {
        "agents",
        "auth",
        "doctor",
        "install",
        "mcp",
        "plugin",
        "setup-token",
        "update",
        "upgrade",
    }
    has_subcommand = len(command) > 1 and command[1] in claude_subcommands
    if binary_name == "claude" and not has_print_flag and not has_subcommand:
        command = [command[0], "-p", *command[1:]]
    return command


def _command_has_session_flags(command: list[str]) -> bool:
    for token in command[1:]:
        if token in {"--session-id", "-r", "--resume", "-c", "--continue", "--no-session-persistence"}:
            return True
        if token.startswith("--session-id=") or token.startswith("--resume="):
            return True
    return False


def _session_reuse_supported(command: list[str]) -> bool:
    if not settings.claude_cli_reuse_session:
        return False
    if not command:
        return False
    binary_name = Path(command[0]).name.lower()
    if binary_name != "claude":
        return False
    if _command_has_session_flags(command):
        return False
    return True


def _lease_session_id() -> tuple[str, bool]:
    now = time.monotonic()
    idle_limit = max(0, int(settings.claude_cli_session_idle_sec or 0))
    turn_limit = max(0, int(settings.claude_cli_session_max_turns or 0))
    with _SESSION_STATE_LOCK:
        current_id = str(_SESSION_STATE.get("id", "") or "")
        current_turns = int(_SESSION_STATE.get("turns", 0) or 0)
        last_used = float(_SESSION_STATE.get("last_used", 0.0) or 0.0)
        idle_expired = bool(current_id and idle_limit > 0 and last_used > 0 and (now - last_used) >= idle_limit)
        turn_expired = bool(current_id and turn_limit > 0 and current_turns >= turn_limit)
        created = False
        if not current_id or idle_expired or turn_expired:
            current_id = str(uuid.uuid4())
            _SESSION_STATE["id"] = current_id
            _SESSION_STATE["turns"] = 0
            _SESSION_STATE["last_used"] = now
            created = True
        return current_id, created


def _touch_session(session_id: str, success: bool) -> None:
    if not session_id:
        return
    now = time.monotonic()
    with _SESSION_STATE_LOCK:
        if str(_SESSION_STATE.get("id", "") or "") != session_id:
            return
        _SESSION_STATE["last_used"] = now
        if success:
            _SESSION_STATE["turns"] = int(_SESSION_STATE.get("turns", 0) or 0) + 1


def _reset_session(session_id: str) -> None:
    if not session_id:
        return
    with _SESSION_STATE_LOCK:
        if str(_SESSION_STATE.get("id", "") or "") != session_id:
            return
        _SESSION_STATE["id"] = ""
        _SESSION_STATE["turns"] = 0
        _SESSION_STATE["last_used"] = 0.0


def _maybe_reset_session_from_error(session_id: str, error_text: str) -> None:
    lowered = str(error_text or "").lower()
    if not lowered:
        return
    if "session" in lowered and ("not found" in lowered or "invalid" in lowered):
        logger.warning("Claude CLI session reset due to session-related error")
        _reset_session(session_id)


def _session_label(session_id: str) -> str:
    if not session_id:
        return "-"
    return session_id.split("-")[0]


def _build_command_with_session(base_command: list[str]) -> tuple[list[str], str]:
    command = list(base_command or [])
    if not _session_reuse_supported(command):
        return command, ""
    session_id, created = _lease_session_id()
    command.extend(["--session-id", session_id])
    logger.info(
        "Claude CLI session %s: session=%s max_turns=%s idle_limit=%ss",
        "created" if created else "reused",
        _session_label(session_id),
        max(0, int(settings.claude_cli_session_max_turns or 0)),
        max(0, int(settings.claude_cli_session_idle_sec or 0)),
    )
    return command, session_id


def _build_full_input(transcript: str, prompt: str) -> str:
    return f"{(prompt or '').strip()}\n\n[전사 텍스트]\n{(transcript or '').strip()}\n"


def run_claude(transcript: str, prompt: str, timeout_sec: int = 600) -> str:
    """
    transcript: 입력 본문 텍스트
    prompt: Claude CLI에 전달할 지시문
    return: claude CLI가 stdout으로 출력한 결과 텍스트
    """
    text = (transcript or "").strip()
    instruction = (prompt or "").strip()
    if not text:
        raise ValueError("본문 텍스트가 비어 있습니다.")

    command, session_id = _build_command_with_session(_resolve_command())
    full_input = _build_full_input(text, instruction)
    timeout_value = max(1, int(timeout_sec or 1))
    command_text = " ".join(command)
    started_at = time.monotonic()
    logger.info(
        "Claude CLI start: command=%s timeout=%ss transcript_chars=%s prompt_chars=%s session=%s",
        command_text,
        timeout_value,
        len(text),
        len(instruction),
        _session_label(session_id),
    )

    try:
        proc = subprocess.run(
            command,
            input=full_input,
            text=True,
            capture_output=True,
            timeout=timeout_value,
            check=False,
        )
    except FileNotFoundError as exc:
        _touch_session(session_id, success=False)
        logger.error("Claude CLI executable not found: command=%s", command_text)
        raise RuntimeError("claude CLI를 찾을 수 없습니다. 설치 및 PATH 설정을 확인해 주세요.") from exc
    except subprocess.TimeoutExpired as exc:
        _touch_session(session_id, success=False)
        elapsed = time.monotonic() - started_at
        logger.error("Claude CLI timeout: duration=%.2fs timeout=%ss", elapsed, timeout_value)
        raise RuntimeError(f"claude 실행 시간 초과({timeout_value}초)") from exc

    if proc.returncode != 0:
        stderr_text = (proc.stderr or "").strip()
        _touch_session(session_id, success=False)
        _maybe_reset_session_from_error(session_id, stderr_text)
        elapsed = time.monotonic() - started_at
        logger.error(
            "Claude CLI failed: returncode=%s duration=%.2fs stderr_preview=%s",
            proc.returncode,
            elapsed,
            _shorten_for_log(stderr_text),
        )
        raise RuntimeError(f"claude 실패(returncode={proc.returncode}): {stderr_text}")

    output = (proc.stdout or "").strip()
    if not output:
        _touch_session(session_id, success=False)
        elapsed = time.monotonic() - started_at
        logger.error("Claude CLI empty output: duration=%.2fs", elapsed)
        raise RuntimeError("claude CLI가 빈 결과를 반환했습니다.")
    _touch_session(session_id, success=True)
    elapsed = time.monotonic() - started_at
    logger.info(
        "Claude CLI done: duration=%.2fs output_preview=%s",
        elapsed,
        _shorten_for_log(output),
    )
    return output


async def generate_with_claude_cli(transcript: str, prompt: str, timeout_sec: int | None = None) -> str:
    timeout_value = int(timeout_sec if timeout_sec is not None else settings.claude_cli_timeout_sec)
    async with _SESSION_EXEC_LOCK:
        return await asyncio.to_thread(run_claude, transcript, prompt, timeout_value)


async def stream_claude_cli(
    transcript: str,
    prompt: str,
    timeout_sec: int | None = None,
) -> AsyncIterator[dict]:
    async with _SESSION_EXEC_LOCK:
        async for event in _stream_claude_cli_locked(transcript, prompt, timeout_sec):
            yield event


async def _stream_claude_cli_locked(
    transcript: str,
    prompt: str,
    timeout_sec: int | None = None,
) -> AsyncIterator[dict]:
    text = (transcript or "").strip()
    instruction = (prompt or "").strip()
    if not text:
        raise ValueError("본문 텍스트가 비어 있습니다.")

    timeout_value = int(timeout_sec if timeout_sec is not None else settings.claude_cli_timeout_sec)
    timeout_value = max(1, timeout_value)
    command, session_id = _build_command_with_session(_resolve_command())
    full_input = _build_full_input(text, instruction)
    command_text = " ".join(command)
    started_at = time.monotonic()
    logger.info(
        "Claude CLI stream start: command=%s timeout=%ss transcript_chars=%s prompt_chars=%s session=%s",
        command_text,
        timeout_value,
        len(text),
        len(instruction),
        _session_label(session_id),
    )

    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        _touch_session(session_id, success=False)
        logger.error("Claude CLI stream executable not found: command=%s", command_text)
        raise RuntimeError("claude CLI를 찾을 수 없습니다. 설치 및 PATH 설정을 확인해 주세요.") from exc

    if process.stdin is None or process.stdout is None or process.stderr is None:
        _touch_session(session_id, success=False)
        raise RuntimeError("claude CLI 입출력 파이프를 열 수 없습니다.")

    process.stdin.write(full_input.encode("utf-8"))
    await process.stdin.drain()
    process.stdin.close()
    if hasattr(process.stdin, "wait_closed"):
        await process.stdin.wait_closed()

    queue: asyncio.Queue[dict] = asyncio.Queue()
    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []

    async def _pump(stream: asyncio.StreamReader, channel: str) -> None:
        while True:
            line = await stream.readline()
            if not line:
                break
            text_line = line.decode("utf-8", errors="replace")
            await queue.put({"type": "chunk", "channel": channel, "text": text_line})
        await queue.put({"type": "eof", "channel": channel})

    tasks = [
        asyncio.create_task(_pump(process.stdout, "stdout")),
        asyncio.create_task(_pump(process.stderr, "stderr")),
    ]

    eof_count = 0
    logged_stdout_preview = False
    logged_stderr_preview = False
    try:
        async with asyncio.timeout(timeout_value):
            while eof_count < 2:
                event = await queue.get()
                if event.get("type") == "eof":
                    eof_count += 1
                    continue
                if event.get("channel") == "stdout":
                    row = str(event.get("text", ""))
                    stdout_chunks.append(row)
                    if not logged_stdout_preview:
                        logger.info("Claude CLI stream stdout partial: %s", _shorten_for_log(row))
                        logged_stdout_preview = True
                else:
                    row = str(event.get("text", ""))
                    stderr_chunks.append(row)
                    if not logged_stderr_preview:
                        logger.warning("Claude CLI stream stderr partial: %s", _shorten_for_log(row))
                        logged_stderr_preview = True
                yield event
            returncode = await process.wait()
    except TimeoutError as exc:
        process.kill()
        await process.wait()
        _touch_session(session_id, success=False)
        elapsed = time.monotonic() - started_at
        logger.error("Claude CLI stream timeout: duration=%.2fs timeout=%ss", elapsed, timeout_value)
        raise RuntimeError(f"claude 실행 시간 초과({timeout_value}초)") from exc
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    if returncode != 0:
        stderr_text = "".join(stderr_chunks).strip()
        _touch_session(session_id, success=False)
        _maybe_reset_session_from_error(session_id, stderr_text)
        elapsed = time.monotonic() - started_at
        logger.error(
            "Claude CLI stream failed: returncode=%s duration=%.2fs stderr_preview=%s",
            returncode,
            elapsed,
            _shorten_for_log(stderr_text),
        )
        raise RuntimeError(f"claude 실패(returncode={returncode}): {stderr_text}")

    output = "".join(stdout_chunks).strip()
    if not output:
        _touch_session(session_id, success=False)
        elapsed = time.monotonic() - started_at
        logger.error("Claude CLI stream empty output: duration=%.2fs", elapsed)
        raise RuntimeError("claude CLI가 빈 결과를 반환했습니다.")
    _touch_session(session_id, success=True)
    elapsed = time.monotonic() - started_at
    logger.info(
        "Claude CLI stream done: duration=%.2fs output_preview=%s",
        elapsed,
        _shorten_for_log(output),
    )
    yield {"type": "done", "result": output}


def save_markdown(out_path: Path, md: str):
    out_path.write_text(md, encoding="utf-8")
