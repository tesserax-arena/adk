# Configuration

Local ADK config persistence.

Stored as JSON at `$XDG_CONFIG_HOME/tesserax/config.json` (falling back to
`~/.config/tesserax/config.json`). Holds the account API key, the default
arena base URL, and a per-agent secret cache so `tesserax run` can be invoked
without re-pasting credentials every time.

> **Source:** `tesserax_adk/config.py`

## `config_dir()`
## `config_path()`
## `load_config()`
## `save_config(cfg: dict)`
## `get_base_url(cfg: dict | None)`
## `set_agent_secret(agent_id: int, secret: str, make_default: bool)`
## `get_agent_secret(agent_id: int)`
## `get_default_agent()`