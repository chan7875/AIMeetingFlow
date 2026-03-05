# 헤더 서비스명 AI Meeting 변경 (2026-03-05)

## 변경 목적
- 웹 화면 좌측 상단 브랜드명을 기존 `Vault Viewer`에서 `AI Meeting`으로 통일해 서비스 식별성을 높입니다.

## 변경 내용
- 파일: `web/static/index.html`
- 변경 전: `📓 Vault Viewer`
- 변경 후: `AI Meeting`

## 영향 범위
- 화면 헤더의 제목 텍스트만 변경됩니다.
- API, 데이터, 라우팅, 백엔드 동작에는 영향이 없습니다.

## 검증
- `pytest` 전체 테스트 실행으로 회귀 여부를 확인합니다.
