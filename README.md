# AIMeetingFlow

AI 기반 콘텐츠 생성 및 다중 플랫폼 자동 배포 시스템입니다.
YouTube, Threads, 네이버 블로그, LinkedIn에 콘텐츠를 자동으로 생성·최적화·게시하며,
Obsidian 마크다운 볼트를 위한 웹 뷰어와 AI 어시스턴트 기능도 포함합니다.

---

## 주요 기능

- **AI 콘텐츠 생성**: OpenAI GPT-4o, Claude CLI, Codex CLI를 활용한 콘텐츠 자동 생성
- **다중 플랫폼 배포**: YouTube, Threads(450자 분할), 네이버 블로그(Playwright), LinkedIn 자동 게시
- **Obsidian 웹 뷰어**: 마크다운 파일 탐색 및 렌더링, 실시간 AI 분석
- **Git 연동**: 웹 UI에서 git pull/push/commit 직접 실행
- **자동 감시(Auto-watch)**: 새 파일 감지 시 Codex 자동 처리
- **알림**: 이메일, Slack 알림 지원

---

## 프로젝트 구조

```
AIMeetingFlow/
├── services/                    # 비즈니스 로직
│   ├── chatgpt_service.py       # OpenAI GPT-4o 콘텐츠 생성
│   ├── claude_cli_service.py    # Claude CLI 세션 관리 및 스트리밍
│   └── codex_cli_service.py     # Codex CLI 통합
├── web/                         # FastAPI 웹 애플리케이션
│   ├── main.py                  # 서버 진입점 (포트 8101)
│   ├── config.py                # 설정 관리 (볼트 경로 등)
│   ├── run.sh                   # 서버 실행 스크립트
│   ├── requirements.txt         # Python 의존성
│   ├── routers/
│   │   ├── files.py             # 파일/폴더 API
│   │   ├── ai.py                # AI 실행 및 스트리밍 API
│   │   └── git.py               # Git 명령 API
│   └── static/
│       ├── index.html           # 단일 페이지 앱
│       ├── app.js               # 프론트엔드 로직
│       └── style.css            # 스타일시트
├── docs/
│   └── 옵시디언_마크다운_뷰어_기획서.md
├── data/                        # 토큰, 설정 JSON (gitignore)
└── CLAUDE.md                    # Claude Code 프로젝트 가이드
```

---

## 빠른 시작

### 1. 의존성 설치

```bash
pip install -r web/requirements.txt
```

추가 의존성 (플랫폼별 기능):

```bash
pip install httpx playwright apscheduler boto3 openai yt-dlp
playwright install chromium
```

### 2. 환경 변수 설정

```bash
# 필수
export OBSIDIAN_VAULT_PATH="/path/to/your/obsidian/vault"

# 선택
export PORT=8101
export AUTO_WATCH_ENABLED=false
```

### 3. 서버 실행

```bash
# 방법 1: 스크립트로 실행 (볼트 경로 인자 지원)
./web/run.sh ~/path/to/vault

# 방법 2: Python 모듈로 실행
python3 -m web.main
```

서버 실행 후 브라우저에서 `http://localhost:8101` 접속

---

## API 엔드포인트

### 파일 관리 (`/api/`)

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/api/config` | 볼트 경로 및 설정 조회 |
| POST | `/api/config` | 볼트 경로 업데이트 |
| GET | `/api/tree` | 디렉토리 트리 조회 |
| GET | `/api/file` | 파일 내용 조회 (`?path=...`) |
| POST | `/api/upload` | 파일 업로드 (최대 50MB) |

### AI 통합 (`/api/ai/`)

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/api/ai/status` | 현재 선택 및 auto-watch 상태 |
| POST | `/api/ai/execute` | Claude/Codex 실행 |
| GET | `/api/ai/stream` | AI 응답 SSE 스트리밍 |
| POST | `/api/ai/save-issue` | AI 결과 저장 |
| GET/POST | `/api/ai/auto-watch` | Auto-watch 설정 조회/변경 |

### Git 연동 (`/api/git/`)

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/api/git/status` | git status 조회 |
| GET | `/api/git/stream/{command}` | git 명령 스트리밍 (pull/push/commit) |

---

## 서비스 상세

### chatgpt_service.py

OpenAI GPT-4o를 사용한 콘텐츠 생성:

- `generate_youtube_content()` — YouTube SRT 자막 → 챕터, 썸네일, 쇼츠, 태그 JSON 생성
- `generate_news_content()` — 텍스트/뉴스 → 영상 메타데이터 JSON 생성
- `generate_threads_post()` — 450자 Threads 포스트 생성

### claude_cli_service.py

Claude CLI 세션 관리:

- 세션 재사용 (idle timeout, max turns 설정 가능)
- 스트리밍 출력 지원
- `stream_claude_cli()` — 비동기 스트리밍 이터레이터

### codex_cli_service.py

Codex CLI 통합 (Claude와 동일한 인터페이스):

- `stream_codex_cli()` — 비동기 스트리밍 이터레이터

---

## 플랫폼별 설정

| 플랫폼 | 인증 방식 | 특이사항 |
|--------|-----------|----------|
| YouTube | OAuth2 (`data/youtube_token.json`) | yt-dlp 다운로드, ffmpeg 프레임 추출 |
| Threads | Meta Graph API | 450자 제한, 문단 단위 분할 |
| 네이버 블로그 | Playwright 브라우저 자동화 | Chrome CDP URL 필요, 글자별 타이핑 |
| LinkedIn | OAuth2 (`data/linkedin_token.json`) | 쿨다운: 1~72시간 설정 가능 |

---

## 필수 설정값 (config.settings)

```python
# AI
openai_api_key

# YouTube / Google
google_client_id
google_client_secret

# LinkedIn
linkedin_oauth_credentials

# 네이버 블로그
naver_id
naver_password
naver_blog_name
chrome_cdp_url

# AWS S3
s3_bucket_name
s3_region
aws_access_key
aws_secret_key

# Airtable
airtable_base_id
airtable_table_name
airtable_api_key

# 이메일 알림
smtp_host
smtp_port
smtp_user
smtp_password
smtp_from
notify_email_to

# Slack (선택)
slack_webhook_url
```

---

## 콘텐츠 워크플로우

```
입력 (YouTube URL or 텍스트)
    ↓
AI 생성 (ChatGPT / Claude / Codex)
    ↓
품질 점수 검사 (0~100)
    ↓
템플릿 적용 (선택)
    ↓
APScheduler 예약
    ↓
다중 플랫폼 비동기 배포
    ↓
이메일 / Slack / 브라우저 알림
```

---

## 기술 스택

- **Backend**: Python 3.10+, FastAPI, Uvicorn
- **Async**: `async/await`, `httpx`, `apscheduler`
- **AI**: OpenAI GPT-4o, Claude CLI, Codex CLI
- **Browser Automation**: Playwright
- **Cloud**: AWS S3, Airtable
- **Frontend**: Vanilla JS, marked.js, highlight.js
- **Video**: yt-dlp, ffmpeg

---

## 라이선스

MIT License
