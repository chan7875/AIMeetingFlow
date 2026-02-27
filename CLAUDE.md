# AIMeetingFlow - Claude Code Guide

## Project Overview

AI-powered content creation and multi-platform distribution system. Automates generating, optimizing, and publishing content (from YouTube videos, text, news) across YouTube, Threads, Naver Blog, and LinkedIn.

## Architecture

```
services/          # All business logic lives here
├── chatgpt_service.py            # OpenAI content generation
├── claude_cli_service.py         # Claude CLI integration
├── codex_cli_service.py          # Codex CLI integration

```

## Key Patterns

- **Async-first**: All services use `async/await`. Use `httpx` for HTTP, `playwright` for browser automation, `apscheduler` for scheduling.
- **Config**: All credentials/settings come from `config.settings` (centralized).
- **Data storage**: JSON files in `/data/` for tokens, notifications, templates, reminder logs.

## Platform-Specific Notes

| Platform | Auth | Notes |
|----------|------|-------|
| YouTube | OAuth2 (`/data/youtube_token.json`) | yt-dlp for downloads, ffmpeg for frame extraction |
| Threads | Meta Graph API (`https://graph.threads.net`) | 450-char limit, paragraph-aware splitting |
| Naver Blog | Playwright browser automation | Chrome CDP via `chrome_cdp_url`, char-by-char typing |
| LinkedIn | OAuth2 (`/data/linkedin_token.json`) | Cooldown: 1-72 hrs configurable |

## Required Config (config.settings)

```
openai_api_key
google_client_id / google_client_secret
linkedin OAuth credentials
naver_id / naver_password / naver_blog_name / chrome_cdp_url
s3_bucket_name / s3_region / aws_access_key / aws_secret_key
airtable_base_id / airtable_table_name / airtable_api_key
smtp_host / smtp_port / smtp_user / smtp_password / smtp_from / notify_email_to
slack_webhook_url (optional)
```

## Content Workflow

1. Input (YouTube URL or text) → ChatGPT/Claude/Codex generation
2. Quality score check (0-100)
3. Optional template application
4. Schedule via APScheduler
5. Async multi-platform distribution
6. Email/Slack/browser notifications + pre-schedule reminders

## Technology Stack

- **Python** (async throughout)
- `httpx`, `playwright`, `apscheduler`, `boto3`, `openai`, `yt-dlp`, `ffmpeg`

## Custom Skills

- `.claude/skills/doc-commit-push/` — Generates docs, updates README, commits/pushes in Korean
