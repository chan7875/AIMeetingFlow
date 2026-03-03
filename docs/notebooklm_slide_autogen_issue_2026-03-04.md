# NotebookLM 슬라이드 자동 생성 현황 (2026-03-04)

## 현재 상태
- `GET /api/slides/status`에서 `nlm_enabled=true`로 설정은 정상입니다.
- 자동 생성 파이프라인은 다음 단계별로 동작합니다.
  - `source add`(소스 추가)
  - `create slides`(슬라이드 생성)
  - `artifact 상태 대기`
  - `download`

## 최근 확인된 실패 패턴
- 대부분의 실패는 **`소스 파일 추가` 단계**에서 발생합니다.
  - `Uploading ... waiting for processing...`
  - `Adding text and waiting for processing...`
  - `Error: Failed to add text source.`
- 일부는 이전에 `NotebookLM rejected slide deck creation` 메시지로 `slides create` 단계에서 `try again later` 재시도 후에도 실패.

## 적용된 코드 조치
- `services/notebooklm_service.py`
  - `add_source_file` 재시도 강화
    - `--file` 실패 시 `--text` 방식으로 전환해 재시도
    - 실패 판별 패턴 확대 (`uploading`, `waiting for processing`, `processing`, `Failed to add ...` 등)
  - `create_slides`에서 실패 응답 후에도 신규 슬라이드 아티팩트 존재 여부를 폴백 체크
    - `studio status` 기반으로 신규 `slide_deck` 아티팩트 감지 시 다운로드 경로로 진행
  - 슬라이드 생성 파이프라인 전 구간을 lock으로 직렬화해 동시 충돌 최소화
  - 슬라이드 다운로드 결과를 `.pptx`로 정규화하고, 필요 시 바탕색 보정 수행
- `web/routers/ai.py`
  - `/api/ai/summarize`에서 요약 저장 후 NLM 슬라이드 생성 자동 트리거 연결
  - 슬라이드 실패/성공 이력(에러 단계/타입/트레이스) 추적 상태 추가
- `web/routers/slides.py`
  - `/api/slides/status` 응답에 슬라이드 실패 단계/타입/트레이스 필드 추가
- `add_source_file` 연속 실패 시 노트북 재생성 후 1회 재시도 경로 추가

## 향후 우선순위
1. `source add` 일시 실패 지속 시: 재시도 횟수/대기시간 상향, 소스 정규화/분할 업로드 검토
2. 실패 시 `last_slide_error_stage`, `last_slide_error_type`, `last_slide_error_trace`로 즉시 진단 가능

