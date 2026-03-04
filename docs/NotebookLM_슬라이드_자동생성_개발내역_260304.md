# NotebookLM 슬라이드 자동 생성 기능 개발내역

## 1. 개요

Vault 폴더에 새 파일이 감지되어 이슈가 생성된 후, 자동으로 NotebookLM에 소스를 업로드하고 슬라이드(PPTX)를 생성/다운로드하는 파이프라인을 추가했다.
`notebooklm-mcp-cli` 패키지의 `nlm` CLI를 subprocess로 호출하는 방식으로, 기존 codex/claude CLI 패턴과 동일하게 구현했다.

## 2. 구현 범위

- `nlm` CLI 래퍼 서비스 신규 생성
- NLM 활성화 설정 관리 (config)
- auto-watch 파이프라인에 슬라이드 생성 훅 추가 (fire-and-forget)
- 슬라이드 관련 REST API 엔드포인트 추가
- account별 notebook 재사용 매핑 관리

## 3. 사전 준비 (수동)

```bash
uv tool install notebooklm-mcp-cli
nlm login          # 브라우저 Google 인증
nlm login --check  # 인증 확인
```

## 4. 변경 파일 요약

| 파일 | 작업 | 설명 |
|------|------|------|
| `web/config.py` | 수정 | NLM 활성화 설정 추가 |
| `services/notebooklm_service.py` | 신규 | nlm CLI 래퍼 서비스 |
| `web/routers/ai.py` | 수정 | 슬라이드 생성 훅 추가 |
| `web/routers/slides.py` | 신규 | 슬라이드 API 엔드포인트 |
| `web/main.py` | 수정 | slides 라우터 등록 |

## 5. 백엔드 변경 사항

### 5.1 설정 관리 (`web/config.py`)

기존 `get_auto_watch_enabled()` 패턴과 동일하게 추가:

- `DEFAULT_NLM_ENABLED`: 환경변수 `NLM_ENABLED` (기본값: `false`)
- `get_nlm_enabled() -> bool`: 현재 NLM 활성화 상태 조회
- `set_nlm_enabled(enabled: bool) -> bool`: NLM 활성화 상태 변경 및 `viewer_config.json` 저장

### 5.2 NotebookLM 서비스 (`services/notebooklm_service.py`)

핵심 함수:

| 함수 | 설명 |
|------|------|
| `_run_nlm(args, timeout_sec)` | `nlm` CLI subprocess 실행 (기본 타임아웃 120초) |
| `_load_notebook_map()` / `_save_notebook_map()` | `data/nlm_notebooks.json`에 account→notebook_id 매핑 관리 |
| `ensure_notebook(account)` | 매핑에 있으면 재사용, 없으면 `nlm notebook create` 후 저장 |
| `add_source_file(notebook_id, file_path)` | `nlm source add`로 소스 파일 추가 |
| `create_slides(notebook_id)` | `nlm slides create`로 슬라이드 생성 (타임아웃 180초) |
| `download_slides(notebook_id, output_dir, filename)` | `nlm download slide-deck`으로 PPTX 다운로드 |
| `generate_slides_for_issue(account, issue_content, issue_title, vault)` | 위 함수들을 조합한 전체 파이프라인 |
| `get_notebook_map()` | 현재 매핑 조회 |

동시성 보호:
- `asyncio.Lock()`으로 `nlm_notebooks.json` 접근 보호
- 같은 account에 대해 2개 파일이 동시 감지되더라도 race condition 방지

### 5.3 auto-watch 슬라이드 훅 (`web/routers/ai.py`)

상태 필드 추가:

| 필드 | 설명 |
|------|------|
| `last_slide_path` | 마지막 생성된 슬라이드 경로 |
| `last_slide_error` | 마지막 슬라이드 생성 에러 |
| `last_slide_at` | 마지막 슬라이드 생성 시각 |
| `slides_generated_count` | 총 슬라이드 생성 횟수 |

주요 변경:
- `_trigger_slide_generation()`: 에러를 격리하여 state에 기록하는 비동기 함수
- `_handle_auto_watch_file()` 끝에서 `get_nlm_enabled()` 확인 후 `asyncio.create_task()`로 fire-and-forget 실행
- 이슈 생성 완료 후 저장된 이슈 파일의 내용을 읽어 슬라이드 생성에 전달

### 5.4 슬라이드 API (`web/routers/slides.py`)

| 엔드포인트 | 메서드 | 설명 |
|------------|--------|------|
| `/api/slides/generate` | POST | 수동 슬라이드 생성 (account, issue_content, issue_title 필요) |
| `/api/slides/notebooks` | GET | account→notebook_id 매핑 조회 |
| `/api/slides/status` | GET | 슬라이드 생성 상태 조회 (last_slide_path, error, count 등) |
| `/api/slides/enable` | POST | NLM 슬라이드 생성 기능 ON/OFF 전환 |

### 5.5 라우터 등록 (`web/main.py`)

- `slides_router` import 및 `app.include_router()` 추가

## 6. 데이터 흐름

```
새 파일 감지 → summarize_file_to_issue() → Issues/ 저장
                                              ↓ (nlm_enabled일 때)
                                    asyncio.create_task (비동기, fire-and-forget)
                                              ↓
                                    ensure_notebook(account)
                                              ↓
                                    add_source_file(notebook_id, issue.md)
                                              ↓
                                    create_slides(notebook_id)
                                              ↓
                                    download_slides → {account}/Slides/*.pptx
```

## 7. 데이터 저장

| 파일 | 위치 | 내용 |
|------|------|------|
| `data/nlm_notebooks.json` | 프로젝트 루트 | account→notebook_id 매핑 |
| `data/viewer_config.json` | 프로젝트 루트 | `nlm_enabled` 설정값 포함 |
| `{account}/Slides/*.pptx` | Vault 내 | 생성된 슬라이드 파일 |

## 8. 에러 처리

- 슬라이드 생성 실패는 이슈 생성에 영향 없음 (fire-and-forget 패턴)
- 모든 에러는 `_AUTO_WATCH_STATE["last_slide_error"]`에 기록되어 `/api/slides/status`로 확인 가능
- `nlm` 미설치 시 `RuntimeError` → state에 기록, 다음 파일에서 재시도
- 인증 만료 시 `nlm login` 재실행 필요
- 임시 소스 파일은 `finally` 블록에서 항상 정리

## 9. 검증 방법

1. `nlm login --check`로 인증 확인
2. 서버 시작 후 `POST /api/slides/enable {"enabled": true}`
3. vault의 account 폴더에 새 `.md` 파일 추가
4. `GET /api/ai/auto-watch`로 이슈 생성 및 슬라이드 상태 확인
5. `GET /api/slides/status`로 슬라이드 생성 상태 확인
6. `{account}/Slides/` 폴더에 PPTX 파일 생성 확인
