# Auto-watch 오류 상태 UI 표시 (2026-03-05)

## 변경 배경
- 백엔드 상태(`last_error`)는 수집되지만, 헤더 버튼에서 즉시 식별하기 어려웠습니다.
- 사용자가 자동 분석 실패를 놓치기 쉬워 문제 인지가 늦어질 수 있었습니다.

## 적용 내용
- `web/static/app.js`
  - `renderAutoWatchButton()`에서 `status.last_error` 기반 `hasError` 계산 추가
  - 오류가 있으면 버튼에 `toggle-error` 클래스 적용
  - 버튼 라벨을 `오류 ON/OFF`로 표시
  - 툴팁에 최근 오류 내용을 계속 노출
- `web/static/style.css`
  - `.header-btn.toggle-error` 스타일 추가 (노란색 경고 톤)

## 기대 효과
- 자동 분석 오류 발생 시 헤더에서 즉시 식별 가능합니다.
- 툴팁으로 최근 오류 내용을 바로 확인할 수 있어 대응 시간이 단축됩니다.

## 테스트
- 실행 명령: `.venv/bin/python -m pytest -q`
- 결과: `54 passed`
