import json
import os
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
CONFIG_FILE = DATA_DIR / "viewer_config.json"

DEFAULT_VAULT = os.environ.get("OBSIDIAN_VAULT_PATH", str(Path.home()))
DEFAULT_ISSUE_FOLDER = os.environ.get("ISSUE_FOLDER", "issue")
DEFAULT_AUTO_WATCH_ENABLED = os.environ.get("AUTO_WATCH_ENABLED", "false").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}


def _load() -> dict:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save(data: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get_vault_path() -> Path:
    data = _load()
    raw = data.get("vault_path") or DEFAULT_VAULT
    return Path(raw).expanduser().resolve()


def set_vault_path(path: str) -> Path:
    resolved = Path(path).expanduser().resolve()
    data = _load()
    data["vault_path"] = str(resolved)
    _save(data)
    return resolved


def get_issue_folder() -> str:
    data = _load()
    return data.get("issue_folder") or DEFAULT_ISSUE_FOLDER


def get_auto_watch_enabled() -> bool:
    data = _load()
    raw = data.get("auto_watch_enabled")
    if raw is None:
        return DEFAULT_AUTO_WATCH_ENABLED
    if isinstance(raw, str):
        return raw.strip().lower() in {"1", "true", "yes", "on"}
    return bool(raw)


def set_auto_watch_enabled(enabled: bool) -> bool:
    data = _load()
    data["auto_watch_enabled"] = bool(enabled)
    _save(data)
    return bool(enabled)
