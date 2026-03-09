#!/usr/bin/env python3
"""AIMeetingFlow CLI — 터미널에서 프로젝트 기능을 실행하는 도구."""

import argparse
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from web.config import (
    get_vault_path,
    set_vault_path,
    get_issue_folder,
    set_issue_folder,
    get_auto_watch_enabled,
    set_auto_watch_enabled,
    get_nlm_enabled,
    set_nlm_enabled,
)


# ── 유틸리티 ──────────────────────────────────────────────────────────────────

def _print_json(data):
    """JSON 데이터를 보기 좋게 출력."""
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _resolve_in_vault(vault: Path, relative_path: str) -> Path:
    resolved = (vault / relative_path).resolve()
    if not str(resolved).startswith(str(vault)):
        print(f"오류: 경로 접근이 허용되지 않습니다: {relative_path}", file=sys.stderr)
        sys.exit(1)
    return resolved


# ── 설정 명령어 ───────────────────────────────────────────────────────────────

def cmd_config(args):
    """설정 조회 및 변경."""
    if args.action == "show":
        config = {
            "vault_path": str(get_vault_path()),
            "issue_folder": get_issue_folder(),
            "auto_watch_enabled": get_auto_watch_enabled(),
            "nlm_enabled": get_nlm_enabled(),
        }
        _print_json(config)
    elif args.action == "set":
        if not args.key or not args.value:
            print("오류: --key와 --value가 필요합니다.", file=sys.stderr)
            sys.exit(1)
        key = args.key
        value = args.value
        if key == "vault_path":
            p = Path(value).expanduser()
            if not p.exists() or not p.is_dir():
                print(f"오류: 경로가 존재하지 않거나 폴더가 아닙니다: {value}", file=sys.stderr)
                sys.exit(1)
            resolved = set_vault_path(value)
            print(f"vault_path → {resolved}")
        elif key == "issue_folder":
            normalized = set_issue_folder(value)
            print(f"issue_folder → {normalized}")
        elif key == "auto_watch":
            enabled = value.lower() in {"true", "1", "on", "yes"}
            set_auto_watch_enabled(enabled)
            print(f"auto_watch_enabled → {enabled}")
        elif key == "nlm_enabled":
            enabled = value.lower() in {"true", "1", "on", "yes"}
            set_nlm_enabled(enabled)
            print(f"nlm_enabled → {enabled}")
        else:
            print(f"오류: 알 수 없는 설정 키: {key}", file=sys.stderr)
            print("사용 가능: vault_path, issue_folder, auto_watch, nlm_enabled")
            sys.exit(1)


# ── 파일 명령어 ───────────────────────────────────────────────────────────────

TREE_VISIBLE_EXTENSIONS = {
    ".md", ".txt", ".pptx", ".png", ".jpg", ".jpeg", ".gif", ".pdf", ".svg", ".webp",
}
SEARCH_EXTENSIONS = {".md", ".txt"}


def _build_tree_text(path: Path, vault: Path, prefix: str = "", is_last: bool = True) -> list[str]:
    """파일 트리를 텍스트로 구성."""
    lines = []
    connector = "└── " if is_last else "├── "
    if path == vault:
        lines.append(str(vault))
    else:
        lines.append(f"{prefix}{connector}{path.name}")

    if path.is_dir():
        try:
            entries = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        except PermissionError:
            return lines
        children = []
        for entry in entries:
            if entry.name.startswith(".") or entry.name == "__pycache__":
                continue
            if entry.is_dir():
                children.append(entry)
            elif entry.suffix.lower() in TREE_VISIBLE_EXTENSIONS:
                children.append(entry)
        for i, child in enumerate(children):
            is_child_last = (i == len(children) - 1)
            if path == vault:
                child_prefix = ""
            else:
                extension = "    " if is_last else "│   "
                child_prefix = prefix + extension
            lines.extend(_build_tree_text(child, vault, child_prefix, is_child_last))
    return lines


def cmd_tree(args):
    """볼트 파일 트리 출력."""
    vault = get_vault_path()
    if not vault.exists():
        print(f"오류: 볼트 경로를 찾을 수 없습니다: {vault}", file=sys.stderr)
        sys.exit(1)
    lines = _build_tree_text(vault, vault)
    print("\n".join(lines))


def cmd_read(args):
    """파일 내용 읽기."""
    vault = get_vault_path()
    target = _resolve_in_vault(vault, args.path)
    if not target.exists():
        print(f"오류: 파일을 찾을 수 없습니다: {args.path}", file=sys.stderr)
        sys.exit(1)
    if not target.is_file():
        print(f"오류: 파일이 아닙니다: {args.path}", file=sys.stderr)
        sys.exit(1)
    content = target.read_text(encoding="utf-8", errors="replace")
    print(content)


def cmd_search(args):
    """볼트 내 텍스트 검색."""
    vault = get_vault_path()
    query = args.query.strip()
    if not query:
        print("오류: 검색어를 입력해 주세요.", file=sys.stderr)
        sys.exit(1)
    limit = args.limit
    results = []
    for root, dirs, files in os.walk(vault):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
        root_path = Path(root)
        for filename in files:
            if filename.startswith("."):
                continue
            path = root_path / filename
            if path.suffix.lower() not in SEARCH_EXTENSIONS:
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            if query.lower() not in content.lower():
                continue
            rel = str(path.relative_to(vault))
            # 스니펫 생성
            idx = content.lower().find(query.lower())
            start = max(0, idx - 70)
            end = min(len(content), idx + len(query) + 70)
            snippet = content[start:end].replace("\n", " ").strip()
            if start > 0:
                snippet = "..." + snippet
            if end < len(content):
                snippet += "..."
            results.append({"path": rel, "snippet": snippet})
            if len(results) >= limit:
                break
        if len(results) >= limit:
            break

    if not results:
        print(f"'{query}'에 대한 검색 결과가 없습니다.")
        return
    print(f"검색 결과: {len(results)}건\n")
    for r in results:
        print(f"  📄 {r['path']}")
        print(f"     {r['snippet']}\n")


# ── AI 명령어 ─────────────────────────────────────────────────────────────────

def _clean_env():
    """Claude Code 내부 실행 시 nested session 오류 방지."""
    return {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}


def cmd_ai_run(args):
    """AI 엔진으로 콘텐츠 분석 (실시간 스트리밍)."""
    vault = get_vault_path()
    engine = args.engine.lower()

    # 파일 내용 로드
    if args.file:
        target = _resolve_in_vault(vault, args.file)
        if not target.exists():
            print(f"오류: 파일을 찾을 수 없습니다: {args.file}", file=sys.stderr)
            sys.exit(1)
        content = target.read_text(encoding="utf-8", errors="replace")
    elif args.text:
        content = args.text
    else:
        # stdin에서 읽기
        if sys.stdin.isatty():
            print("오류: --file, --text, 또는 stdin으로 입력을 제공해 주세요.", file=sys.stderr)
            sys.exit(1)
        content = sys.stdin.read()

    prompt = args.prompt

    # 컨텍스트 빌드
    context_parts = []
    if args.file:
        path_parts = Path(args.file).parts
        account = path_parts[0] if len(path_parts) > 1 else ""
        context_parts.append(
            f"[파일 정보]\n- 파일 경로: {args.file}\n- Account(상위 폴더): {account or '(볼트 루트)'}"
        )
        template_path = vault / "_Templates" / "Template_Issue.md"
        if template_path.exists():
            tmpl = template_path.read_text(encoding="utf-8", errors="replace")
            context_parts.append(f"[Template_Issue.md 내용 — 이 포맷에 맞춰 작성]\n{tmpl}")

    context = "\n\n".join(context_parts)
    parts = [prompt.strip()]
    if context:
        parts.append(context)
    parts.append(f"[파일 내용]\n{content.strip()}")
    full_input = "\n\n".join(parts) + "\n"

    # 명령어 결정
    if engine == "codex":
        command = ["codex", "exec"]
    else:
        command = ["claude", "-p"]

    try:
        proc = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(vault),
            env=_clean_env(),
        )
        proc.stdin.write(full_input.encode("utf-8"))
        proc.stdin.close()

        # 실시간 스트리밍 출력
        while True:
            line = proc.stdout.readline()
            if not line:
                break
            sys.stdout.write(line.decode("utf-8", errors="replace"))
            sys.stdout.flush()

        proc.wait()
        stderr_text = proc.stderr.read().decode("utf-8", errors="replace").strip()

        if proc.returncode != 0:
            print(f"\n오류: AI 실행 실패 (returncode={proc.returncode})", file=sys.stderr)
            if stderr_text:
                print(stderr_text, file=sys.stderr)
            sys.exit(1)
    except FileNotFoundError:
        print(f"오류: '{command[0]}' 명령어를 찾을 수 없습니다. 설치 및 PATH를 확인해 주세요.", file=sys.stderr)
        sys.exit(1)


def cmd_ai_summarize(args):
    """파일을 AI로 요약하고 Issue 폴더에 저장."""
    asyncio.run(_async_summarize(args))


async def _async_summarize(args):
    from web.routers.ai import summarize_file_to_issue, DEFAULT_PROMPT

    prompt = args.prompt if args.prompt else DEFAULT_PROMPT
    try:
        result = await summarize_file_to_issue(
            file_path=args.file,
            engine=args.engine.lower(),
            prompt=prompt,
            timeout_sec=args.timeout,
        )
        print(f"저장 완료: {result['saved_path']}")
        print(f"파일명: {result['name']}")

        # NLM 슬라이드 생성
        if get_nlm_enabled() and args.slides:
            saved_path = result.get("saved_path", "")
            if saved_path:
                vault = get_vault_path()
                saved_rel = Path(saved_path)
                account = saved_rel.parts[0] if len(saved_rel.parts) > 1 else ""
                if account:
                    saved_abs = vault / saved_rel
                    if saved_abs.exists():
                        issue_content = saved_abs.read_text(encoding="utf-8", errors="replace")
                        if issue_content:
                            from services.notebooklm_service import generate_slides_for_issue
                            print("슬라이드 생성 중...")
                            slide_result = await generate_slides_for_issue(
                                account=account,
                                issue_content=issue_content,
                                issue_title=saved_abs.stem,
                                vault=vault,
                                issue_md_name=saved_abs.name,
                            )
                            print(f"슬라이드 생성 완료: {slide_result.get('slide_path', '')}")
    except FileNotFoundError as e:
        print(f"오류: {e}", file=sys.stderr)
        sys.exit(1)
    except RuntimeError as e:
        print(f"오류: {e}", file=sys.stderr)
        sys.exit(1)


# ── Git 명령어 ────────────────────────────────────────────────────────────────

def _run_git(args_list: list[str], vault: Path) -> int:
    """git 명령어 실행 (실시간 출력)."""
    try:
        proc = subprocess.run(
            ["git"] + args_list,
            cwd=str(vault),
            capture_output=False,
        )
        return proc.returncode
    except FileNotFoundError:
        print("오류: git 명령어를 찾을 수 없습니다.", file=sys.stderr)
        return 1


def cmd_git(args):
    """Git 명령어 실행."""
    vault = get_vault_path()
    if not vault.exists():
        print(f"오류: 볼트 경로를 찾을 수 없습니다: {vault}", file=sys.stderr)
        sys.exit(1)

    action = args.action
    if action == "status":
        _run_git(["status", "--short"], vault)
    elif action == "pull":
        _run_git(["pull", "origin"], vault)
    elif action == "push":
        message = args.message or "CLI에서 업데이트"
        if args.files:
            files = [f.strip() for f in args.files.split(",") if f.strip()]
        else:
            # 변경된 파일 전체
            result = subprocess.run(
                ["git", "status", "--short"],
                cwd=str(vault),
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                print("오류: git status 실행 실패", file=sys.stderr)
                sys.exit(1)
            files = []
            for line in result.stdout.strip().splitlines():
                if len(line) >= 3:
                    path = line[3:].strip()
                    if "->" in path:
                        path = path.split("->", 1)[1].strip()
                    if path.startswith('"') and path.endswith('"'):
                        path = path[1:-1]
                    if path:
                        files.append(path)
        if not files:
            print("Push할 변경 파일이 없습니다.")
            return

        print(f"대상 파일 {len(files)}개:")
        for f in files:
            print(f"  • {f}")
        print()

        rc = _run_git(["add", "--"] + files, vault)
        if rc != 0:
            sys.exit(rc)
        rc = _run_git(["commit", "-m", f"auto: {message}"], vault)
        if rc != 0:
            sys.exit(rc)
        rc = _run_git(["push", "origin"], vault)
        sys.exit(rc)
    elif action == "changes":
        result = subprocess.run(
            ["git", "status", "--short"],
            cwd=str(vault),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print("오류: git status 실행 실패", file=sys.stderr)
            sys.exit(1)
        lines = result.stdout.strip().splitlines()
        if not lines:
            print("변경된 파일이 없습니다.")
            return
        print(f"변경 파일 {len(lines)}개:\n")
        for line in lines:
            status = line[:2].strip() or "?"
            path = line[3:].strip()
            print(f"  [{status}] {path}")


# ── 슬라이드 명령어 ──────────────────────────────────────────────────────────

def cmd_slides(args):
    """NotebookLM 슬라이드 생성."""
    asyncio.run(_async_slides(args))


async def _async_slides(args):
    from services.notebooklm_service import generate_slides_for_issue, get_notebook_map

    if args.action == "notebooks":
        mapping = get_notebook_map()
        if not mapping:
            print("등록된 노트북이 없습니다.")
            return
        _print_json(mapping)
        return

    if args.action == "generate":
        if not args.file:
            print("오류: --file이 필요합니다.", file=sys.stderr)
            sys.exit(1)
        vault = get_vault_path()
        target = _resolve_in_vault(vault, args.file)
        if not target.exists():
            print(f"오류: 파일을 찾을 수 없습니다: {args.file}", file=sys.stderr)
            sys.exit(1)

        content = target.read_text(encoding="utf-8", errors="replace")
        path_parts = Path(args.file).parts
        account = args.account or (path_parts[0] if len(path_parts) > 1 else "default")

        print(f"슬라이드 생성 중... (account: {account})")
        try:
            result = await generate_slides_for_issue(
                account=account,
                issue_content=content,
                issue_title=target.stem,
                vault=vault,
                issue_md_name=target.name,
            )
            print(f"슬라이드 생성 완료!")
            _print_json(result)
        except RuntimeError as e:
            print(f"오류: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.action == "status":
        print(f"NLM 활성화: {get_nlm_enabled()}")


# ── 서버 명령어 ───────────────────────────────────────────────────────────────

def cmd_serve(args):
    """웹 서버 시작."""
    port = args.port
    vault = args.vault
    if vault:
        os.environ["OBSIDIAN_VAULT_PATH"] = vault
    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f" AI Meeting Flow")
    print(f" http://localhost:{port}")
    print(f" Vault: {get_vault_path()}")
    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    import uvicorn
    uvicorn.run("web.main:app", host="0.0.0.0", port=port, reload=args.reload)


# ── 메인 파서 ─────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aimf",
        description="AIMeetingFlow CLI — AI 기반 콘텐츠 생성 및 관리 도구",
    )
    subparsers = parser.add_subparsers(dest="command", help="실행할 명령어")

    # ── config ──
    p_config = subparsers.add_parser("config", help="설정 조회/변경")
    p_config.add_argument("action", choices=["show", "set"], help="show: 조회, set: 변경")
    p_config.add_argument("--key", help="설정 키 (vault_path, issue_folder, auto_watch, nlm_enabled)")
    p_config.add_argument("--value", help="설정 값")
    p_config.set_defaults(func=cmd_config)

    # ── tree ──
    p_tree = subparsers.add_parser("tree", help="볼트 파일 트리 출력")
    p_tree.set_defaults(func=cmd_tree)

    # ── read ──
    p_read = subparsers.add_parser("read", help="파일 내용 읽기")
    p_read.add_argument("path", help="볼트 내 파일 경로 (상대 경로)")
    p_read.set_defaults(func=cmd_read)

    # ── search ──
    p_search = subparsers.add_parser("search", help="볼트 내 텍스트 검색")
    p_search.add_argument("query", help="검색어")
    p_search.add_argument("--limit", type=int, default=20, help="최대 결과 수 (기본: 20)")
    p_search.set_defaults(func=cmd_search)

    # ── ai run ──
    p_ai = subparsers.add_parser("ai", help="AI 엔진으로 콘텐츠 분석")
    p_ai.add_argument("--engine", choices=["claude", "codex"], default="claude", help="AI 엔진 (기본: claude)")
    p_ai.add_argument("--file", help="분석할 파일 경로 (볼트 내 상대 경로)")
    p_ai.add_argument("--text", help="직접 텍스트 입력")
    p_ai.add_argument("--prompt", default="다음 내용을 핵심 위주로 요약해 주세요.", help="AI 프롬프트")
    p_ai.set_defaults(func=cmd_ai_run)

    # ── summarize ──
    p_sum = subparsers.add_parser("summarize", help="파일 AI 요약 + Issue 저장")
    p_sum.add_argument("file", help="요약할 파일 경로 (볼트 내 상대 경로)")
    p_sum.add_argument("--engine", choices=["claude", "codex"], default="claude", help="AI 엔진")
    p_sum.add_argument("--prompt", default="", help="커스텀 프롬프트 (비우면 기본 프롬프트)")
    p_sum.add_argument("--timeout", type=int, default=600, help="타임아웃 (초, 기본: 600)")
    p_sum.add_argument("--slides", action="store_true", help="NLM 슬라이드도 생성")
    p_sum.set_defaults(func=cmd_ai_summarize)

    # ── git ──
    p_git = subparsers.add_parser("git", help="Git 작업 (status, pull, push, changes)")
    p_git.add_argument("action", choices=["status", "pull", "push", "changes"], help="Git 작업")
    p_git.add_argument("--message", "-m", help="커밋 메시지 (push 시)")
    p_git.add_argument("--files", help="Push 대상 파일 (쉼표 구분)")
    p_git.set_defaults(func=cmd_git)

    # ── slides ──
    p_slides = subparsers.add_parser("slides", help="NotebookLM 슬라이드 관리")
    p_slides.add_argument("action", choices=["generate", "notebooks", "status"], help="슬라이드 작업")
    p_slides.add_argument("--file", help="슬라이드 생성할 파일 경로")
    p_slides.add_argument("--account", help="NotebookLM account 이름")
    p_slides.set_defaults(func=cmd_slides)

    # ── serve ──
    p_serve = subparsers.add_parser("serve", help="웹 서버 시작")
    p_serve.add_argument("--port", type=int, default=8101, help="포트 번호 (기본: 8101)")
    p_serve.add_argument("--vault", help="볼트 경로 지정")
    p_serve.add_argument("--reload", action="store_true", help="개발 모드 (자동 리로드)")
    p_serve.set_defaults(func=cmd_serve)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    args.func(args)


if __name__ == "__main__":
    main()
