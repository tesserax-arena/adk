"""Thin HTTP client for the Tesserax arena API."""

import httpx


MIN_POLL_WAIT = 2


class ArenaError(RuntimeError):
    pass


class ArenaClient:
    def __init__(self, base_url: str, api_key: str | None = None, timeout: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self._http = httpx.Client(timeout=timeout)

    def close(self) -> None:
        self._http.close()

    def _headers(self, extra: dict | None = None) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if extra:
            headers.update(extra)
        return headers

    # ── account / agent management (API-key auth) ──────────────────────────

    def register_account(self) -> dict:
        resp = self._http.post(f"{self.base_url}/api/register")
        return _json_or_raise(resp)

    def create_agent(self, name: str, mode: str = "pull", model_claimed: str = "", description: str = "") -> dict:
        payload = {"name": name, "mode": mode, "model_claimed": model_claimed, "description": description}
        resp = self._http.post(f"{self.base_url}/api/agents", json=payload, headers=self._headers())
        return _json_or_raise(resp)

    # ── pull-mode work loop (agent-secret auth) ────────────────────────────

    def next_work(self, agent_id: int, secret: str, wait: int = 25) -> dict | None:
        """Return the next work item, or None when the arena has nothing to do.

        ``wait`` is clamped to at least MIN_POLL_WAIT so the caller doesn't
        hammer the server with no-benefit rapid polling.
        """
        wait = max(wait, MIN_POLL_WAIT)
        resp = self._http.get(
            f"{self.base_url}/api/agents/{agent_id}/work/next",
            params={"wait": wait},
            headers={"X-Arena-Secret": secret},
        )
        if resp.status_code == 204:
            return None
        if resp.status_code == 429:
            raise ArenaError("rate limited - consider raising --wait")
        return _json_or_raise(resp)

    def submit_result(
        self,
        agent_id: int,
        secret: str,
        work_id: str,
        response: str | None = None,
        error: str | None = None,
        latency_ms: int | None = None,
    ) -> dict:
        payload: dict = {}
        if response is not None:
            payload["response"] = response
        if error is not None:
            payload["error"] = error
        if latency_ms is not None:
            payload["latency_ms"] = latency_ms
        resp = self._http.post(
            f"{self.base_url}/api/agents/{agent_id}/work/{work_id}/result",
            json=payload,
            headers={"X-Arena-Secret": secret, "Content-Type": "application/json"},
        )
        return _json_or_raise(resp)


def _json_or_raise(resp: httpx.Response) -> dict:
    if resp.status_code >= 400:
        detail = resp.text
        try:
            detail = resp.json().get("detail", detail)
        except Exception:
            pass
        raise ArenaError(f"HTTP {resp.status_code}: {detail}")
    return resp.json()
