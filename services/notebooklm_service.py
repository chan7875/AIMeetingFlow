import asyncio
import json
import logging
import os
import re
from pathlib import Path
from typing import Final

logger = logging.getLogger("notebooklm")

DATA_DIR = Path(__file__).parent.parent / "data"
NOTEBOOK_MAP_FILE = DATA_DIR / "nlm_notebooks.json"

# nlm CLI가 Claude Code 내부에서 실행될 때 nested session 오류를 막기 위해
# CLAUDECODE 환경변수를 제거한 환경을 준비한다.
_CLEAN_ENV = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

_notebook_map_lock = asyncio.Lock()
SLIDE_DECK_READY_TIMEOUT_SEC = 900
SLIDE_DECK_STATUS_POLL_SEC = 5
NLM_STDOUT_TAIL_LIMIT: Final[int] = 2000
SLIDE_CREATE_RETRY_COUNT: Final[int] = 3
SLIDE_CREATE_RETRY_BASE_SEC: Final[float] = 8.0
SLIDE_CREATE_RETRY_MARKERS: Final[tuple[str, ...]] = (
    "notebooklm rejected slide deck creation",
    "try again later",
    "try again",
)
SOURCE_ADD_RETRY_COUNT: Final[int] = 3
SOURCE_ADD_RETRY_BASE_SEC: Final[float] = 6.0
SOURCE_ADD_RETRY_MARKERS: Final[tuple[str, ...]] = (
    "uploading",
    "waiting for processing",
    "processing",
    "returncode=130",
    "could not add file source",
    "could not add text source",
    "failed to add file source",
    "failed to add text source",
)
SLIDE_CREATE_WAIT_READY_ON_FAILURE_SEC: Final[int] = 20

_slide_pipeline_lock = asyncio.Lock()


async def _refresh_notebook(account: str) -> str:
    """기존 매핑을 초기화하고 새 노트북을 강제 생성한다."""
    async with _notebook_map_lock:
        mapping = _load_notebook_map()
        if account in mapping:
            mapping.pop(account, None)
            _save_notebook_map(mapping)
    return await ensure_notebook(account, force_create=True)


def _is_retryable_slide_create_error(text: str) -> bool:
    lowered = (text or "").strip().lower()
    return any(marker in lowered for marker in SLIDE_CREATE_RETRY_MARKERS)


def _is_retryable_source_add_error(text: str) -> bool:
    lowered = (text or "").strip().lower()
    return any(marker in lowered for marker in SOURCE_ADD_RETRY_MARKERS)


def _set_slide_stage(exc: Exception, stage: str) -> Exception:
    setattr(exc, "slide_stage", stage)
    return exc


def _extract_slide_artifact_id(text: str) -> str:
    match = re.search(r"Artifact ID:\s*([a-zA-Z0-9_-]+)", text)
    if match:
        return match.group(1)
    return ""


def _normalize_status(value: str) -> str:
    return (value or "").strip().lower()


def _is_ready_status(status: str) -> bool:
    normalized = _normalize_status(status)
    return normalized in {"ready", "done", "completed", "success"}


def _is_failed_status(status: str) -> bool:
    normalized = _normalize_status(status)
    return normalized in {"failed", "error", "canceled", "cancelled"}


async def _wait_for_slide_artifact_ready(notebook_id: str, artifact_id: str | None = None) -> str:
    deadline = asyncio.get_event_loop().time() + SLIDE_DECK_READY_TIMEOUT_SEC
    while True:
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            raise RuntimeError("slide deck 준비 대기 시간 초과")

        status_text = await _run_nlm(["studio", "status", notebook_id, "--json"], timeout_sec=30)
        try:
            items = json.loads(status_text)
            if not isinstance(items, list):
                items = []
        except Exception as exc:
            raise RuntimeError(f"studio status 출력 파싱 실패: {status_text[:1200]}") from exc

        candidates: list[dict[str, object]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            if item.get("type") != "slide_deck":
                continue
            if artifact_id and item.get("id") and item.get("id") != artifact_id:
                continue
            candidates.append(item)

        if not candidates:
            if artifact_id:
                logger.info("슬라이드 아티팩트 미출력: notebook=%s artifact=%s", notebook_id, artifact_id)
            else:
                logger.info("슬라이드 아티팩트 미출력: notebook=%s", notebook_id)
            await asyncio.sleep(SLIDE_DECK_STATUS_POLL_SEC)
            continue

        target = candidates[-1] if artifact_id is None else candidates[0]
        status = _normalize_status(str(target.get("status")))
        if _is_ready_status(status):
            logger.info(
                "slide deck 준비 완료: notebook=%s artifact=%s status=%s",
                notebook_id,
                target.get("id"),
                status,
            )
            value = target.get("id")
            return str(value) if value else ""
        if _is_failed_status(status):
            raise RuntimeError(f"슬라이드 생성 실패 상태: {status}")
        logger.info(
            "slide deck 미완료: notebook=%s artifact=%s status=%s",
            notebook_id,
            target.get("id"),
            status,
        )
        await asyncio.sleep(SLIDE_DECK_STATUS_POLL_SEC)


async def _list_slide_artifact_ids(notebook_id: str) -> set[str]:
    status_text = await _run_nlm(["studio", "status", notebook_id, "--json"], timeout_sec=30)
    try:
        items = json.loads(status_text)
        if not isinstance(items, list):
            return set()
    except Exception:
        return set()

    artifact_ids: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "slide_deck":
            continue
        value = item.get("id")
        if isinstance(value, str) and value:
            artifact_ids.add(value)
    return artifact_ids


async def _find_new_slide_artifact_id(
    notebook_id: str,
    before_ids: set[str],
) -> str:
    attempts = max(1, int(SLIDE_CREATE_WAIT_READY_ON_FAILURE_SEC / SLIDE_DECK_STATUS_POLL_SEC))
    for _ in range(attempts):
        await asyncio.sleep(SLIDE_DECK_STATUS_POLL_SEC)
        current_ids = await _list_slide_artifact_ids(notebook_id)
        diff = list(current_ids - before_ids)
        if diff:
            logger.info("슬라이드 생성 실패 응답 후 신규 아티팩트 감지: notebook=%s artifact=%s", notebook_id, diff[-1])
            return diff[-1]
    return ""


async def _run_nlm(args: list[str], timeout_sec: int = 120) -> str:
    """nlm CLI를 subprocess로 실행하고 stdout을 반환한다."""
    command = ["nlm", *args]
    logger.info("nlm CLI start: %s", " ".join(command))

    try:
        proc = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=_CLEAN_ENV,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "`nlm` 명령어를 찾을 수 없습니다. `uv tool install notebooklm-mcp-cli` 후 재시도하세요."
        ) from exc

    try:
        stdout_data, stderr_data = await asyncio.wait_for(
            proc.communicate(),
            timeout=timeout_sec,
        )
    except asyncio.TimeoutError as exc:
        proc.kill()
        await proc.wait()
        raise RuntimeError(f"nlm 실행 시간 초과({timeout_sec}초)") from exc

    stdout_text = stdout_data.decode("utf-8", errors="replace").strip()
    stderr_text = stderr_data.decode("utf-8", errors="replace").strip()

    if proc.returncode != 0:
        stdout_tail = stdout_text[:NLM_STDOUT_TAIL_LIMIT] if len(stdout_text) > NLM_STDOUT_TAIL_LIMIT else stdout_text
        if stderr_text:
            detail = f"{stderr_text}"
        elif stdout_tail:
            detail = f"STDOUT: {stdout_tail}"
        else:
            detail = f"nlm 실행 실패 (returncode={proc.returncode})"
        raise RuntimeError(detail)

    logger.info("nlm CLI done: returncode=%s stdout_len=%s", proc.returncode, len(stdout_text))
    return stdout_text


def _load_notebook_map() -> dict[str, str]:
    """data/nlm_notebooks.json에서 account→notebook_id 매핑을 로드한다."""
    if NOTEBOOK_MAP_FILE.exists():
        try:
            return json.loads(NOTEBOOK_MAP_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_notebook_map(mapping: dict[str, str]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    NOTEBOOK_MAP_FILE.write_text(
        json.dumps(mapping, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


async def _find_notebook_by_account(account: str) -> str:
    """NotebookLM 서버 목록에서 account 이름과 일치하는 노트북 ID를 조회한다."""
    try:
        output = await _run_nlm(["notebook", "list", "--json"], timeout_sec=60)
        items = json.loads(output)
        if not isinstance(items, list):
            return ""
    except Exception as exc:
        logger.warning("notebook list 조회 실패 (무시): %s", exc)
        return ""

    for item in items:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or item.get("name") or "").strip()
        if title.lower() == account.strip().lower():
            notebook_id = str(item.get("id") or "").strip()
            if notebook_id:
                logger.info("서버 목록에서 기존 노트북 발견: account=%s id=%s", account, notebook_id)
                return notebook_id
    return ""


async def ensure_notebook(account: str, force_create: bool = False) -> str:
    """account에 대응하는 notebook_id를 반환한다.

    탐색 순서:
      1. 로컬 캐시(nlm_notebooks.json) 확인
      2. NLM 서버 notebook list 조회 — account 이름과 동일한 노트북 재사용
      3. 위 둘 다 없으면 신규 생성

    force_create=True 이면 1·2 단계를 건너뛰고 항상 새 노트북을 생성한다.
    (_refresh_notebook 에서 고장난 노트북을 교체할 때 사용)
    """
    if not force_create:
        # 1. 로컬 캐시 확인
        async with _notebook_map_lock:
            mapping = _load_notebook_map()
            existing_id = mapping.get(account)
            if existing_id:
                logger.info("notebook 재사용 (로컬 캐시): account=%s id=%s", account, existing_id)
                return existing_id

        # 2. NLM 서버 목록 조회 (락 없이 I/O 수행)
        found_id = await _find_notebook_by_account(account)
        if found_id:
            async with _notebook_map_lock:
                mapping = _load_notebook_map()
                # race condition 방지: 다른 태스크가 먼저 등록했을 수 있음
                if not mapping.get(account):
                    mapping[account] = found_id
                    _save_notebook_map(mapping)
            logger.info("notebook 재사용 (서버 조회): account=%s id=%s", account, found_id)
            return found_id

    # 3. 신규 생성
    async with _notebook_map_lock:
        mapping = _load_notebook_map()
        if not force_create:
            # 락 진입 직전 다른 태스크가 이미 생성했을 경우 재사용
            existing_id = mapping.get(account)
            if existing_id:
                logger.info("notebook 재사용 (race 재확인): account=%s id=%s", account, existing_id)
                return existing_id

        try:
            output = await _run_nlm(["notebook", "create", account])
        except Exception as exc:
            raise _set_slide_stage(exc, "notebook 생성") from exc

        notebook_id = _extract_notebook_id(output)
        if not notebook_id:
            raise RuntimeError(f"notebook ID를 추출할 수 없습니다: {output}")

        mapping[account] = notebook_id
        _save_notebook_map(mapping)
        logger.info("notebook 신규 생성: account=%s id=%s", account, notebook_id)
        return notebook_id


def _extract_notebook_id(output: str) -> str:
    """nlm notebook create 출력에서 notebook ID를 추출한다.

    실제 출력 예시:
        ✓ Created notebook: test_slide_check
          ID: d8de88b9-0678-430e-b63c-48a372bf4c4f
    """
    # "ID: <uuid>" 패턴 (가장 우선)
    id_match = re.search(r"ID:\s*([a-fA-F0-9-]+)", output)
    if id_match:
        return id_match.group(1)

    # URL 형태에서 ID 추출: https://notebooklm.google.com/notebook/<id>
    url_match = re.search(r"notebook/([a-zA-Z0-9_-]+)", output)
    if url_match:
        return url_match.group(1)

    # 마지막 줄이 ID일 수 있음
    lines = [line.strip() for line in output.strip().splitlines() if line.strip()]
    if lines:
        last = lines[-1]
        if re.match(r"^[a-zA-Z0-9_-]+$", last):
            return last

    return ""


async def _cleanup_sources(notebook_id: str) -> None:
    """notebook의 기존 소스를 모두 삭제하여 누적을 방지한다."""
    try:
        output = await _run_nlm(["source", "list", notebook_id, "--json"], timeout_sec=30)
        items = json.loads(output)
        if not isinstance(items, list) or not items:
            return
        source_ids = [
            item["id"] for item in items
            if isinstance(item, dict) and item.get("id")
        ]
        if not source_ids:
            return
        await _run_nlm(["source", "delete", *source_ids, "--confirm"], timeout_sec=60)
        logger.info("기존 소스 %d개 삭제 완료: notebook=%s", len(source_ids), notebook_id)
    except Exception as exc:
        logger.warning("소스 정리 실패 (무시): notebook=%s err=%s", notebook_id, exc)


async def add_source_file(notebook_id: str, file_path: str) -> str:
    """notebook에 소스 파일을 추가한다."""
    source_text = Path(file_path).read_text(encoding="utf-8", errors="replace")
    last_error: Exception | None = None
    for attempt in range(1, SOURCE_ADD_RETRY_COUNT + 1):
        use_text = False
        cmd = "file"
        if attempt > 1:
            use_text = True
            cmd = "text"
        try:
            if use_text:
                logger.info("source add 재시도 중 텍스트 방식 사용: notebook=%s attempt=%d", notebook_id, attempt)
                return await _run_nlm(
                    ["source", "add", notebook_id, "--text", source_text, "--wait"],
                    timeout_sec=300,
                )
            return await _run_nlm(
                ["source", "add", notebook_id, "--file", file_path, "--wait"],
                timeout_sec=300,
            )
        except RuntimeError as exc:
            last_error = exc
            if attempt >= SOURCE_ADD_RETRY_COUNT or not _is_retryable_source_add_error(str(exc)):
                raise
            wait_sec = int(SOURCE_ADD_RETRY_BASE_SEC * attempt)
            logger.warning(
                "source add 실패, %s초 후 재시도 (%d/%d) [method=%s]: notebook=%s err=%s",
                wait_sec,
                attempt,
                SOURCE_ADD_RETRY_COUNT,
                cmd,
                notebook_id,
                str(exc),
            )
            await asyncio.sleep(wait_sec)

    raise last_error or RuntimeError("source add 실패")


async def create_slides(notebook_id: str) -> str:
    """notebook에서 슬라이드를 생성하고 artifact id를 반환한다."""
    last_error: Exception | None = None
    before_ids = await _list_slide_artifact_ids(notebook_id)
    for attempt in range(1, SLIDE_CREATE_RETRY_COUNT + 1):
        try:
            output = await _run_nlm(
                ["slides", "create", notebook_id, "--confirm", "--language", "ko"],
                timeout_sec=180,
            )
            artifact_id = _extract_slide_artifact_id(output)
            if artifact_id:
                logger.info("슬라이드 생성 시작: notebook=%s artifact=%s", notebook_id, artifact_id)
            else:
                logger.info("슬라이드 생성 출력에서 artifact id를 추출하지 못함: %s", output)
            return artifact_id
        except RuntimeError as exc:
            last_error = exc
            if attempt < SLIDE_CREATE_RETRY_COUNT and _is_retryable_slide_create_error(str(exc)):
                wait_sec = int(SLIDE_CREATE_RETRY_BASE_SEC * attempt)
                logger.warning(
                    "슬라이드 생성 일시 거부, %s초 후 재시도 (%d/%d): notebook=%s",
                    wait_sec,
                    attempt,
                    SLIDE_CREATE_RETRY_COUNT,
                    notebook_id,
                )
                await asyncio.sleep(wait_sec)
                continue
            new_artifact_id = await _find_new_slide_artifact_id(notebook_id, before_ids)
            if new_artifact_id:
                logger.warning("슬라이드 생성 예외 후에도 신규 아티팩트를 사용: notebook=%s artifact=%s", notebook_id, new_artifact_id)
                return new_artifact_id
            raise

    if last_error is None:
        raise RuntimeError("슬라이드 생성에 실패했습니다.")
    raise last_error


def _set_white_background(pptx_path: str) -> None:
    """다운로드된 PPTX의 모든 슬라이드 바탕색을 흰색으로 설정한다."""
    try:
        from pptx import Presentation
        from pptx.util import Pt
        from pptx.dml.color import RGBColor
        from pptx.enum.dml import MSO_THEME_COLOR

        prs = Presentation(pptx_path)
        for slide in prs.slides:
            bg = slide.background
            fill = bg.fill
            fill.solid()
            fill.fore_color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        prs.save(pptx_path)
        logger.info("슬라이드 바탕색을 흰색으로 설정 완료: %s", pptx_path)
    except ImportError:
        logger.warning("python-pptx가 설치되지 않아 바탕색 변경을 건너뜁니다.")
    except Exception as exc:
        logger.warning("바탕색 변경 실패 (무시): %s", exc)


async def download_slides(
    notebook_id: str,
    output_dir: str,
    filename: str,
    artifact_id: str | None = None,
) -> str:
    """생성된 슬라이드를 PPTX로 다운로드한다."""
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    output_path = out_path / filename
    if output_path.suffix.lower() != ".pptx":
        output_path = output_path.with_suffix(".pptx")
    output_file = str(output_path)
    before_files = {p.name: p.stat().st_mtime_ns for p in out_path.iterdir() if p.is_file()}
    args = ["download", "slide-deck", notebook_id, "--format", "pptx", "--output", output_file]
    if artifact_id:
        args.extend(["--id", artifact_id])
    await _run_nlm(
        args,
        timeout_sec=120,
    )

    downloaded = out_path / output_path.name
    if not downloaded.exists():
        candidates = sorted(
            (
                p
                for p in out_path.iterdir()
                if p.is_file() and p.name not in before_files
                and p.stem.startswith(output_path.stem)
            ),
            key=lambda p: p.stat().st_mtime_ns,
            reverse=True,
        )
        if not candidates:
            candidates = sorted(
                (
                    p
                    for p in out_path.iterdir()
                    if p.is_file() and p.stem.startswith(output_path.stem)
                ),
                key=lambda p: p.stat().st_mtime_ns,
                reverse=True,
            )
        if candidates:
            downloaded = candidates[0]
        else:
            raise RuntimeError(f"다운로드 결과 파일을 찾지 못했습니다: {output_file}")

    if downloaded.suffix.lower() != ".pptx":
        new_downloaded = downloaded.with_suffix(".pptx")
        if new_downloaded != downloaded:
            if new_downloaded.exists():
                logger.warning("pptx 대상 경로가 이미 존재해 덮어씌우지 않습니다: %s", new_downloaded)
            else:
                downloaded = downloaded.rename(new_downloaded)

    logger.info("슬라이드 다운로드 완료: %s", downloaded)

    # 바탕색을 흰색으로 설정
    _set_white_background(str(downloaded))

    return str(downloaded)


async def generate_slides_for_issue(
    account: str,
    issue_content: str,
    issue_title: str,
    vault: Path,
    issue_md_name: str = "",
) -> dict[str, str]:
    """이슈 내용으로부터 슬라이드를 생성하는 전체 파이프라인.

    issue_md_name이 주어지면 PPTX 파일명을 해당 md 파일명(확장자 제외)과 동일하게 저장한다.
    """
    # 1. 임시 파일로 이슈 내용 저장 (nlm source add는 파일 경로를 요구)
    temp_dir = vault / account / "Slides"
    temp_dir.mkdir(parents=True, exist_ok=True)

    # 이전 실행에서 남은 _source_*.md 잔여 파일 정리
    for leftover in temp_dir.glob("_source_*.md"):
        try:
            leftover.unlink()
        except OSError:
            pass

    # 이슈 내용을 임시 md 파일로 저장 (1개만 생성)
    safe_title = re.sub(r"[^a-zA-Z0-9._-]+", "_", issue_title).strip("._-")
    if not safe_title:
        safe_title = "issue"
    safe_title = safe_title[:60]
    if not safe_title:
        safe_title = "issue"
    source_file = temp_dir / f"_source_{safe_title}.md"
    source_file.write_text(issue_content, encoding="utf-8")

    try:
        # 2~5. 파이프라인 전체를 직렬화해서 notebook 동시 작업 충돌을 방지
        async with _slide_pipeline_lock:
            # 2. notebook 확보 (재사용 또는 생성)
            try:
                notebook_id = await ensure_notebook(account)
            except Exception as exc:
                raise _set_slide_stage(exc, "notebook 확보") from exc

            # 2.5. 기존 소스 정리 (누적 방지)
            await _cleanup_sources(notebook_id)

            # 3. 소스 파일 추가
            try:
                await add_source_file(notebook_id, str(source_file))
            except Exception as exc:
                logger.warning(
                    "소스 파일 추가 실패로 노트북 재생성 후 1회 재시도: account=%s notebook=%s",
                    account,
                    notebook_id,
                )
                try:
                    notebook_id = await _refresh_notebook(account)
                    await add_source_file(notebook_id, str(source_file))
                except Exception as fallback_exc:
                    logger.warning(
                        "재생성 노트북으로도 source add 실패: account=%s err=%s",
                        account,
                        str(fallback_exc),
                    )
                    raise _set_slide_stage(fallback_exc, "소스 파일 추가") from fallback_exc
                logger.info("노트북 재생성 후 source add 성공: account=%s", account)

            # 4. 슬라이드 생성
            try:
                artifact_id = await create_slides(notebook_id)
                if not artifact_id:
                    artifact_id = None
            except Exception as exc:
                raise _set_slide_stage(exc, "슬라이드 생성") from exc

            try:
                ready_id = await _wait_for_slide_artifact_ready(notebook_id, artifact_id)
                if ready_id:
                    artifact_id = ready_id
            except Exception as exc:
                raise _set_slide_stage(exc, "슬라이드 상태 대기") from exc

            # 5. 슬라이드 다운로드 — issue md 파일명과 동일하게 저장
            if issue_md_name:
                pptx_stem = Path(issue_md_name).stem
            else:
                pptx_stem = safe_title
            pptx_filename = f"{pptx_stem}.pptx"
            try:
                output_path = await download_slides(
                    notebook_id,
                    str(temp_dir),
                    pptx_filename,
                    artifact_id=artifact_id,
                )
            except Exception as exc:
                raise _set_slide_stage(exc, "슬라이드 다운로드") from exc

        rel_path = Path(output_path).relative_to(vault)
        return {
            "notebook_id": notebook_id,
            "slide_path": str(rel_path),
            "account": account,
        }
    finally:
        # 임시 소스 파일 정리
        if source_file.exists():
            source_file.unlink()


def get_notebook_map() -> dict[str, str]:
    """현재 account→notebook_id 매핑을 반환한다."""
    return _load_notebook_map()
