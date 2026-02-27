# 파일 자동감시 + Codex 자동분석 기능 개발내역

## 1. 개요

Vault 폴더 내 신규 파일 생성 시 자동으로 파일을 감지하고, `Codex CLI`로 분석한 뒤 이슈 문서를 저장하는 기능을 추가했다.  
동시에 웹 상단 헤더에서 기능을 즉시 켜고/끄는 `ON/OFF 토글 버튼`을 제공하도록 구현했다.

## 2. 구현 범위

- 백엔드 자동 감시 루프 추가
- 자동 감시 상태 조회/변경 API 추가
- 신규 파일 감지 시 `codex exec` 자동 실행 및 결과 저장
- 상단 헤더 `자동 분석 ON/OFF` 버튼 추가
- 프론트 상태 동기화 및 주기적 폴링 반영

## 3. 백엔드 변경 사항

### 3.1 자동 감시 상태 관리

- `web/routers/ai.py`
  - 메모리 상태(`enabled`, `running`, `processed_count`, `last_error` 등) 관리
  - 비동기 잠금(`asyncio.Lock`) 기반 상태 보호
  - 폴링 루프 기반 신규 파일 감지 (`AUTO_WATCH_POLL_SEC=2.0`)

### 3.2 파일 감지 및 분석/저장

- 감시 확장자: `.md`, `.txt`
- 제외 경로:
  - `.git`
  - `__pycache__`
  - `issue`, `Issues` (자동 저장 파일 재감지 방지)
- 신규 파일 감지 후 파일 크기 안정화 체크를 거친 뒤 `codex exec` 실행
- 기존 요약 저장 로직을 공통 함수로 정리하여 자동 감시/수동 저장에서 재사용

### 3.3 API 추가

- `GET /api/ai/auto-watch`
  - 자동 감시 상태 조회
- `POST /api/ai/auto-watch`
  - 자동 감시 ON/OFF 전환

### 3.4 앱 라이프사이클 연동

- `web/main.py`
  - FastAPI lifespan에서 서버 시작 시 감시 루프 시작
  - 서버 종료 시 감시 루프 안전 종료

### 3.5 설정 영속화

- `web/config.py`
  - `auto_watch_enabled` 설정 조회/저장 함수 추가
  - 환경변수 `AUTO_WATCH_ENABLED` 기본값 지원

## 4. 프론트엔드 변경 사항

- `web/static/index.html`
  - 헤더 버튼 추가: `🛰 자동 분석 ON/OFF`
- `web/static/app.js`
  - 상태 조회: `/api/ai/auto-watch`
  - 상태 전환: `toggleAutoWatch()`
  - 주기적 폴링으로 처리 건수 변화 감지 시 트리 자동 새로고침
- `web/static/style.css`
  - 토글 ON 상태 시 강조 스타일(`toggle-on`) 추가

## 5. 동작 흐름

1. 사용자가 헤더에서 자동 분석 기능을 ON
2. 서버 감시 루프가 Vault를 주기적으로 스캔
3. 신규 파일 생성 감지
4. 파일 안정화 확인 후 `codex exec` 실행
5. 분석 결과를 이슈 파일로 저장
6. 프론트가 상태를 폴링하여 변경사항 반영

## 6. 확인 항목

- Python 컴파일 점검(`python3 -m compileall web`) 통과
- 프론트 JS 문법 점검 통과
- 자동 감시 상태 API 응답 확인 (`GET/POST /api/ai/auto-watch`)

## 7. 참고

- 초기 기준 파일 집합은 감시 시작 시점에 스냅샷으로 저장된다.
- 자동 감시 ON 이후 새로 생성된 파일만 자동 분석 대상이 된다.
- `issue/Issues` 경로는 재귀 분석 루프 방지를 위해 감시 대상에서 제외된다.
