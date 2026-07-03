"""Local ADK config persistence.

Stored as JSON at ``$XDG_CONFIG_HOME/tesserax/config.json`` (falling back to
``~/.config/tesserax/config.json``). Holds the account API key, the default
arena base URL, and a per-agent secret cache so ``tesserax run`` can be invoked
without re-pasting credentials every time.
"""

import json
import os
from pathlib import Path

DEFAULT_BASE_URL = "https://tesserax.net"


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "tesserax"


def config_path() -> Path:
    return config_dir() / "config.json"


def load_config() -> dict:
    path = config_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def save_config(cfg: dict) -> None:
    d = config_dir()
    d.mkdir(parents=True, exist_ok=True)
    path = config_path()
    path.write_text(json.dumps(cfg, indent=2))
    # Credentials live here - keep it owner-only.
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def get_base_url(cfg: dict | None = None) -> str:
    cfg = cfg if cfg is not None else load_config()
    return cfg.get("base_url") or DEFAULT_BASE_URL


def set_agent_secret(agent_id: int, secret: str, make_default: bool = True) -> None:
    cfg = load_config()
    agents = cfg.setdefault("agents", {})
    agents[str(agent_id)] = {"secret": secret}
    if make_default:
        cfg["default_agent"] = agent_id
    save_config(cfg)


def get_agent_secret(agent_id: int) -> str | None:
    cfg = load_config()
    entry = cfg.get("agents", {}).get(str(agent_id))
    return entry.get("secret") if entry else None


def get_default_agent() -> int | None:
    cfg = load_config()
    return cfg.get("default_agent")
