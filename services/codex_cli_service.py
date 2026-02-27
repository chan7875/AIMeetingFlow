import asyncio
import logging
import shlex
import subprocess
import time
from pathlib import Path
from typing import AsyncIterator

from config.settings import settings

logger = logging.getLogger("codex_cli")
LOG_PREVIEW_LIMIT = 240


def _shorten_for_log(text: str, limit: int = LOG_PREVIEW_LIMIT) -> str:
    value = str(text or "").strip().replace("\n", "\\n")
    if len(value) <= limit:
        return value
    return f"{value[:limit]}...(truncated)"


def _resolve_command() -> list[str]:
    command_text = (settings.codex_cli_command or "codex").strip()
    command = shlex.split(command_text) if command_text else ["codex"]
    if not command:
        return ["codex"]
    binary_name = Path(command[0]).name.lower()
    codex_subcommands = {
        "exec",
        "review",
        "login",
        "logout",
        "mcp",
        "mcp-server",
        "app-server",
        "app",
        "completion",
        "sandbox",
        "debug",
        "apply",
        "a",
        "resume",
        "fork",
        "cloud",
        "features",
        "help",
    }
    has_subcommand = len(command) > 1 and command[1] in codex_subcommands
    if binary_name == "codex" and not has_subcommand:
        command = [command[0], "exec", *command[1:]]
    return command


def _build_full_input(transcript: str, prompt: str) -> str:
    return f"{(prompt or '').strip()}\n\n[전사 텍스트]\n{(transcript or '').strip()}\n"


def run_codex(transcript: str, prompt: str, timeout_sec: int = 600) -> str:
    """
    transcript: 입력 본문 텍스트
    prompt: Codex CLI에 전달할 지시문
    return: codex CLI가 stdout으로 출력한 결과 텍스트
    """
    text = (transcript or "").strip()
    instruction = (prompt or "").strip()
    if not text:
        raise ValueError("본문 텍스트가 비어 있습니다.")

    command = _resolve_command()
    full_input = _build_full_input(text, instruction)
    timeout_value = max(1, int(timeout_sec or 1))
    command_text = " ".join(command)
    started_at = time.monotonic()
    logger.info(
        "Codex CLI start: command=%s timeout=%ss transcript_chars=%s prompt_chars=%s",
        command_text,
        timeout_value,
        len(text),
        len(instruction),
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
        logger.error("Codex CLI executable not found: command=%s", command_text)
        raise RuntimeError("codex CLI를 찾을 수 없습니다. 설치 및 PATH 설정을 확인해 주세요.") from exc
    except subprocess.TimeoutExpired as exc:
        elapsed = time.monotonic() - started_at
        logger.error("Codex CLI timeout: duration=%.2fs timeout=%ss", elapsed, timeout_value)
        raise RuntimeError(f"codex 실행 시간 초과({timeout_value}초)") from exc

    if proc.returncode != 0:
        stderr_text = (proc.stderr or "").strip()
        elapsed = time.monotonic() - started_at
        logger.error(
            "Codex CLI failed: returncode=%s duration=%.2fs stderr_preview=%s",
            proc.returncode,
            elapsed,
            _shorten_for_log(stderr_text),
        )
        raise RuntimeError(f"codex 실패(returncode={proc.returncode}): {stderr_text}")

    output = (proc.stdout or "").strip()
    if not output:
        elapsed = time.monotonic() - started_at
        logger.error("Codex CLI empty output: duration=%.2fs", elapsed)
        raise RuntimeError("codex CLI가 빈 결과를 반환했습니다.")
    elapsed = time.monotonic() - started_at
    logger.info(
        "Codex CLI done: duration=%.2fs output_preview=%s",
        elapsed,
        _shorten_for_log(output),
    )
    return output


async def generate_with_codex_cli(transcript: str, prompt: str, timeout_sec: int | None = None) -> str:
    timeout_value = int(timeout_sec if timeout_sec is not None else settings.codex_cli_timeout_sec)
    return await asyncio.to_thread(run_codex, transcript, prompt, timeout_value)


async def stream_codex_cli(
    transcript: str,
    prompt: str,
    timeout_sec: int | None = None,
) -> AsyncIterator[dict]:
    text = (transcript or "").strip()
    instruction = (prompt or "").strip()
    if not text:
        raise ValueError("본문 텍스트가 비어 있습니다.")

    timeout_value = int(timeout_sec if timeout_sec is not None else settings.codex_cli_timeout_sec)
    timeout_value = max(1, timeout_value)
    command = _resolve_command()
    full_input = _build_full_input(text, instruction)
    command_text = " ".join(command)
    started_at = time.monotonic()
    logger.info(
        "Codex CLI stream start: command=%s timeout=%ss transcript_chars=%s prompt_chars=%s",
        command_text,
        timeout_value,
        len(text),
        len(instruction),
    )

    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        logger.error("Codex CLI stream executable not found: command=%s", command_text)
        raise RuntimeError("codex CLI를 찾을 수 없습니다. 설치 및 PATH 설정을 확인해 주세요.") from exc

    if process.stdin is None or process.stdout is None or process.stderr is None:
        raise RuntimeError("codex CLI 입출력 파이프를 열 수 없습니다.")

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
                        logger.info("Codex CLI stream stdout partial: %s", _shorten_for_log(row))
                        logged_stdout_preview = True
                else:
                    row = str(event.get("text", ""))
                    stderr_chunks.append(row)
                    if not logged_stderr_preview:
                        logger.warning("Codex CLI stream stderr partial: %s", _shorten_for_log(row))
                        logged_stderr_preview = True
                yield event
            returncode = await process.wait()
    except TimeoutError as exc:
        process.kill()
        await process.wait()
        elapsed = time.monotonic() - started_at
        logger.error("Codex CLI stream timeout: duration=%.2fs timeout=%ss", elapsed, timeout_value)
        raise RuntimeError(f"codex 실행 시간 초과({timeout_value}초)") from exc
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    if returncode != 0:
        stderr_text = "".join(stderr_chunks).strip()
        elapsed = time.monotonic() - started_at
        logger.error(
            "Codex CLI stream failed: returncode=%s duration=%.2fs stderr_preview=%s",
            returncode,
            elapsed,
            _shorten_for_log(stderr_text),
        )
        raise RuntimeError(f"codex 실패(returncode={returncode}): {stderr_text}")

    output = "".join(stdout_chunks).strip()
    if not output:
        elapsed = time.monotonic() - started_at
        logger.error("Codex CLI stream empty output: duration=%.2fs", elapsed)
        raise RuntimeError("codex CLI가 빈 결과를 반환했습니다.")
    elapsed = time.monotonic() - started_at
    logger.info(
        "Codex CLI stream done: duration=%.2fs output_preview=%s",
        elapsed,
        _shorten_for_log(output),
    )
    yield {"type": "done", "result": output}


def save_markdown(out_path: Path, md: str):
    out_path.write_text(md, encoding="utf-8")
