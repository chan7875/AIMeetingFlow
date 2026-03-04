# 웹 뷰어 UI/UX 개선 (2026-03-05)

## 기능 개요

Obsidian Vault 웹 뷰어(`web/`)에 사용성을 높이는 세 가지 기능을 추가하였습니다.

---

## 1. AI 실행 취소 버튼

### 주요 변경 내용

- AI 실행 중 **✕ 중단** 버튼이 나타나 즉시 스트리밍을 중단할 수 있습니다.
- `AbortController`를 활용해 fetch 요청 자체를 취소합니다.
- 취소 시 결과 영역에 "실행이 취소되었습니다." 안내 문구가 표시됩니다.
- 실행 완료 또는 취소 후 버튼은 자동으로 숨겨집니다.

### 사용법

1. 파일 선택 후 **▶ 실행** 클릭
2. 스트리밍 중 **✕ 중단** 클릭 → 즉시 중단

### 관련 파일

| 파일 | 변경 내용 |
|------|-----------|
| `web/static/app.js` | `state.abortController` 추가, `runAIStream()` 수정, `cancelAI()` 신규 |
| `web/static/index.html` | `#cancel-btn` 버튼 추가 |
| `web/static/style.css` | `.btn-cancel` 스타일 추가 |

---

## 2. Git 상태 배지

### 주요 변경 내용

- 헤더의 **Push** 버튼 옆에 미커밋 변경 파일 수를 빨간 배지로 표시합니다.
- 변경사항이 없으면 배지가 자동으로 숨겨집니다.
- 배지에 마우스를 올리면 `git status --short` 전체 내용이 툴팁으로 표시됩니다.
- 갱신 시점: 앱 로드 시, Pull/Push 완료 시, 30초 주기 자동 갱신.
- 기존 백엔드 `GET /api/git/status` API를 활용하므로 서버 변경 없음.

### 사용법

- 별도 조작 없이 Push 버튼 옆 배지를 통해 현재 변경 파일 수 확인 가능

### 관련 파일

| 파일 | 변경 내용 |
|------|-----------|
| `web/static/app.js` | `loadGitStatus()` 신규 추가, init·Pull·Push 완료 시 호출 |
| `web/static/index.html` | `#git-badge` span 추가 (Push 버튼 내부) |
| `web/static/style.css` | `.git-badge` 스타일 추가 |

---

## 3. 사이드바 파일 검색

### 주요 변경 내용

- 사이드바 파일 트리 위에 검색 입력창(🔍)이 추가되었습니다.
- 타이핑과 동시에 전체 트리를 재귀 탐색하여 파일명이 일치하는 항목만 표시합니다.
- 검색어를 지우면 원래 트리 구조로 즉시 복원됩니다.
- 자동 감시·수동 트리 새로고침 시 현재 검색어를 유지합니다.

### 사용법

1. 사이드바 상단 검색창에 파일명 입력 (대소문자 무관)
2. 일치하는 파일 목록이 즉시 표시됨
3. 파일 클릭하면 뷰어에서 열림

### 관련 파일

| 파일 | 변경 내용 |
|------|-----------|
| `web/static/app.js` | `filterTree()` 신규, `loadTree()` 내 검색어 유지 로직 추가 |
| `web/static/index.html` | `.sidebar-search` + `#sidebar-search-input` 추가 |
| `web/static/style.css` | `.sidebar-search` 스타일 추가 |
