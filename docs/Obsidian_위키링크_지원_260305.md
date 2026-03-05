# Obsidian 위키링크(`[[...]]`) 지원 (2026-03-05)

## 변경 배경
- 기존 뷰어는 일반 마크다운 링크만 처리하고 Obsidian 위키링크는 텍스트로 남았습니다.
- 볼트 문서 간 탐색이 끊겨 Obsidian 사용자 경험이 저하되었습니다.

## 적용 내용
- `web/static/app.js`
  - `transformWikiLinks()` 추가
    - `[[대상]]`, `[[대상|표시명]]`을 내부 링크(`wikilink:`)로 변환
  - `resolveWikiLinkTarget()` 추가
    - 트리 데이터 기준으로 대상 파일 경로 해석
  - `bindWikiLinks()` 추가
    - 렌더된 링크 클릭 시 `openFile()`로 파일 로드
  - `parseMarkdownSafe()`에 위키링크 전처리 연결
  - 뷰어/AI 결과 렌더 후 위키링크 바인딩 실행
- `web/static/style.css`
  - 위키링크 표시용 스타일(`data-wikilink`) 추가

## 기대 효과
- `[[문서명]]` 형태 링크를 클릭해 즉시 연관 문서로 이동할 수 있습니다.
- Obsidian 볼트 탐색 경험이 웹 뷰어에서도 자연스럽게 유지됩니다.

## 테스트
- 실행 명령: `.venv/bin/python -m pytest -q`
- 결과: `71 passed`
