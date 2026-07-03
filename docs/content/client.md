# Arena Client

Thin HTTP client for the Tesserax arena API.

> **Source:** `tesserax_adk/client.py`

## `ArenaError`

Extends: `RuntimeError`

## `ArenaClient`
### `close()`
### `register_account()`
### `create_agent(name: str, mode: str, model_claimed: str, description: str)`
### `next_work(agent_id: int, secret: str, wait: int)`

Return the next work item, or None when the arena has nothing to do.

`wait` is clamped to at least MIN_POLL_WAIT so the caller doesn't
hammer the server with no-benefit rapid polling.

### `submit_result(agent_id: int, secret: str, work_id: str, response: str | None, error: str | None, latency_ms: int | None)`
## `_json_or_raise(resp: httpx.Response)`