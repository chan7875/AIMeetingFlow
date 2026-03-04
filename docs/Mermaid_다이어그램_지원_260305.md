# Mermaid 다이어그램 지원 개발 내역

> 개발일: 2026-03-05

---

## 개요

마크다운 파일 내에 Mermaid 코드 블록(` ```mermaid `)이 있으면 자동으로 다이어그램으로 렌더링하는 기능을 추가했습니다.

## 변경 사항

| 파일 | 변경 내용 |
|------|----------|
| `web/static/index.html` | Mermaid.js v10 CDN 스크립트 추가 |
| `web/static/style.css` | `.mermaid-diagram` 스타일 추가 |
| `web/static/app.js` | `renderMermaidBlocks()` 함수 추가, Mermaid 초기화 및 테마 연동, 파일 열기 시 자동 렌더링 |

## 지원 다이어그램 유형

- Flowchart (흐름도)
- Sequence Diagram (시퀀스 다이어그램)
- Class Diagram (클래스 다이어그램)
- State Diagram (상태 다이어그램)
- Gantt Chart (간트 차트)
- Pie Chart (파이 차트)
- 그 외 Mermaid v10 지원 모든 다이어그램

## 주요 기능

1. **자동 렌더링**: ` ```mermaid ` 코드 블록을 SVG 다이어그램으로 자동 변환
2. **테마 연동**: 다크/라이트 테마에 맞게 다이어그램 색상 자동 전환
3. **안전한 렌더링**: 렌더링 실패 시 원본 코드 블록 유지
4. **반응형**: 다이어그램 SVG가 컨테이너 너비에 맞게 조정
