# 마크다운 XSS 방어 적용 (2026-03-05)

## 변경 배경
- 뷰어/AI 결과는 `marked.parse()` 결과를 `innerHTML`에 넣어 렌더링합니다.
- 볼트 파일에 악성 HTML/스크립트가 포함되면 브라우저에서 실행될 위험이 있어 방어가 필요했습니다.

## 적용 내용
- `web/static/index.html`에 `DOMPurify` CDN을 추가했습니다.
- `web/static/app.js`에 `parseMarkdownSafe()` 공통 함수를 추가했습니다.
  - `marked.parse()` 결과를 생성
  - `DOMPurify.sanitize()`로 정화
- 아래 렌더 경로를 모두 `parseMarkdownSafe()`로 통일했습니다.
  - 파일 뷰어 렌더 (`renderViewerMarkdown`)
  - AI 결과 렌더 (`renderAIResult`)

## 기대 효과
- 마크다운 내 악성 HTML/JS가 화면 렌더링 과정에서 제거됩니다.
- XSS 리스크를 줄이면서 기존 마크다운 렌더 흐름을 유지합니다.

## 테스트
- 실행 명령: `.venv/bin/python -m pytest -q`
- 결과: `46 passed`
