# NotebookLM 슬라이드 생성 환경 문제 수정 및 Issue 저장 연동 (2026-03-05)

## 개요

서버 실행 환경에 따라 `nlm` CLI를 찾지 못하는 PATH 문제와,
Issue 저장(`/api/ai/save-result`) 시 슬라이드 자동 생성이 트리거되지 않던 문제를 수정했습니다.

## 수정 내용

### 1. `nlm` PATH 문제 수정 (`services/notebooklm_service.py`)

**문제**: 서버를 Claude Code 터미널 등 제한된 shell 환경에서 실행할 경우,
`uv tool install`로 설치된 `nlm`(`~/.local/bin/nlm`)이 subprocess 환경의 PATH에 포함되지 않아 실행 실패.

**수정**: `_CLEAN_ENV`를 모듈 레벨 dict에서 `_build_clean_env()` 함수로 변경.
`~/.local/bin`을 PATH 앞에 강제 추가.

```python
def _build_clean_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    extra = str(Path.home() / ".local" / "bin")
    current_path = env.get("PATH", "")
    path_parts = [p for p in current_path.split(os.pathsep) if p]
    if extra not in path_parts:
        path_parts.insert(0, extra)
    env["PATH"] = os.pathsep.join(path_parts)
    return env
```

### 2. 에러 메시지 개선 (`services/notebooklm_service.py`)

**수정**: `_run_nlm` 에러 시 stderr만 출력하던 것을 stderr + stdout 모두 포함.
문제 진단이 더 명확해짐.

### 3. 슬라이드 다운로드 progress bar 제거 (`services/notebooklm_service.py`)

**수정**: `nlm download slide-deck`에 `--no-progress` 플래그 추가.
progress bar 출력이 stdout에 섞여 파싱 오류를 일으킬 수 있는 문제 예방.

### 4. Issue 저장 시 슬라이드 자동 생성 연동 (`web/routers/ai.py`)

**문제**: `POST /api/ai/save-result`(AI 결과 저장)에는 슬라이드 생성 트리거가 없었음.
`/api/ai/summarize`에만 있어서 사용자가 AI 결과를 수동 저장할 때 슬라이드가 생성되지 않았음.

**수정**: `save_result` 엔드포인트에 슬라이드 생성 트리거 추가.
저장된 Issue md 파일을 NotebookLM 소스로 추가 후 슬라이드 생성 (백그라운드 비동기 실행).

```python
if get_nlm_enabled():
    saved_path = result.get("saved_path", "")
    if saved_path:
        # account 추출 → issue 내용 읽기 → 슬라이드 생성 태스크 생성
        asyncio.create_task(
            _trigger_slide_generation(account, issue_content, issue_title, issue_md_name),
            name=f"save-result-slide-gen-{account}",
        )
        result["slide_triggered"] = True
```

## 전체 슬라이드 생성 흐름

```
AI 결과 저장 (save-result)
    └─→ _save_ai_output() → Issue .md 파일 생성
    └─→ [NLM 활성화 시] _trigger_slide_generation() 비동기 실행
            └─→ ensure_notebook(account)       # account명 = 노트북 title 매칭
            └─→ _cleanup_sources(notebook_id)  # 기존 소스 삭제
            └─→ add_source_file(...)           # issue md 파일 소스 추가
            └─→ create_slides(notebook_id)     # 슬라이드 생성
            └─→ _wait_for_slide_artifact_ready # 완료 대기 (최대 900초)
            └─→ download_slides(...)           # .pptx 다운로드
```

## 관련 파일

- `services/notebooklm_service.py`
- `web/routers/ai.py`

## 슬라이드 생성 상태 확인

```bash
curl http://localhost:8101/api/slides/status
```
