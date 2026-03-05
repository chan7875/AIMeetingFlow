# Git Push 파일 선택 기능 (2026-03-05)

## 변경 배경
- 기존 Push는 `git add -A`를 사용해 의도하지 않은 민감 파일까지 스테이징될 수 있었습니다.
- 사용자에게 Push 대상 파일 제어권이 필요했습니다.

## 적용 내용
- `web/routers/git.py`
  - `GET /api/git/changes` 추가: `git status --short` 기반 변경 파일 목록 반환
  - `_parse_changed_files()` 추가: rename/untracked 포함 파싱
  - `POST /api/git/push` 요청 바디에 `files` 필드 추가
  - 선택 파일만 `git add -- <files...>` 수행
  - 파일 미선택 시 `400` 반환
- `web/static/index.html`
  - Git Push 모달에 파일 체크박스 리스트(`git-files-list`) 추가
  - 실행 버튼 ID(`git-push-run-btn`) 추가
- `web/static/app.js`
  - `loadGitPushFiles()`로 변경 파일 목록 조회/렌더
  - 체크박스 선택 수 기반 실행 버튼 활성/비활성
  - `runGitPush()`에서 선택 파일 목록을 서버로 전송
- `web/static/style.css`
  - Git 파일 리스트 UI 스타일 추가

## 기대 효과
- 사용자가 Push할 파일을 명시적으로 선택할 수 있어 오커밋 위험이 줄어듭니다.
- Git Push 작업의 안전성과 예측 가능성이 향상됩니다.

## 테스트
- 실행 명령: `.venv/bin/python -m pytest -q`
- 결과: `63 passed`
