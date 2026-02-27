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



## Technology Stack

- **Python** (async throughout)
- `httpx`, `playwright`, `apscheduler`, `boto3`, `openai`, `yt-dlp`, `ffmpeg`

## Custom Skills

- `.claude/skills/doc-commit-push/` — Generates docs, updates README, commits/pushes in Korean
