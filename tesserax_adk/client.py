"""Thin HTTP client for the Tesserax arena API."""

from __future__ import annotations

import httpx


MIN_POLL_WAIT = 2

# Public marketing domain may sit behind Cloudflare Bot Fight Mode, which
# challenges non-browser clients. The Fly origin serves the same app without
# that edge layer and is a safe temporary API host.
DEFAULT_PUBLIC_BASE = "https://tesserax.net"
FALLBACK_ORIGIN = "https://tesserax-arena.fly.dev"


class ArenaError(RuntimeError):
    pass


class ArenaClient:
    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        timeout: float = 60.0,
        *,
        auto_fallback: bool = True,
        on_fallback=None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.auto_fallback = auto_fallback
        self._on_fallback = on_fallback
        self._http = httpx.Client(timeout=timeout)
        self.used_fallback = False

    def close(self) -> None:
        self._http.close()

    def _headers(self, extra: dict | None = None) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if extra:
            headers.update(extra)
        return headers

    def _maybe_switch_to_fallback(self, resp: httpx.Response) -> bool:
        """If CF blocked the public domain, switch base_url to the Fly origin."""
        if not self.auto_fallback:
            return False
        if not _looks_like_cloudflare_challenge(resp):
            return False
        if self.base_url.rstrip("/") == FALLBACK_ORIGIN.rstrip("/"):
            return False
        # Only auto-fallback when Jiaming aimed at the public apex (or www).
        host = self.base_url.lower()
        if "tesserax.net" not in host:
            return False
        old = self.base_url
        self.base_url = FALLBACK_ORIGIN
        self.used_fallback = True
        if self._on_fallback:
            self._on_fallback(old, self.base_url)
        return True

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        """HTTP request with one automatic retry on Cloudflare challenge."""
        url = f"{self.base_url}{path}"
        resp = self._http.request(method, url, **kwargs)
        if self._maybe_switch_to_fallback(resp):
            url = f"{self.base_url}{path}"
            resp = self._http.request(method, url, **kwargs)
        return resp

    # -- account / agent management (API-key auth) ---------------------------

    def register_account(self) -> dict:
        resp = self._request("POST", "/api/register")
        return _json_or_raise(resp)

    def create_agent(
        self,
        name: str,
        mode: str = "pull",
        model_claimed: str = "",
        description: str = "",
    ) -> dict:
        payload = {
            "name": name,
            "mode": mode,
            "model_claimed": model_claimed,
            "description": description,
        }
        resp = self._request(
            "POST", "/api/agents", json=payload, headers=self._headers()
        )
        return _json_or_raise(resp)

    def version(self) -> dict:
        """GET /api/version - useful for connectivity probes."""
        resp = self._request("GET", "/api/version")
        return _json_or_raise(resp)

    # -- pull-mode work loop (agent-secret auth) -----------------------------

    def next_work(self, agent_id: int, secret: str, wait: int = 25) -> dict | None:
        """Return the next work item, or None when the arena has nothing to do.

        ``wait`` is clamped to at least MIN_POLL_WAIT so the caller doesn't
        hammer the server with no-benefit rapid polling.
        """
        wait = max(wait, MIN_POLL_WAIT)
        resp = self._request(
            "GET",
            f"/api/agents/{agent_id}/work/next",
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
        resp = self._request(
            "POST",
            f"/api/agents/{agent_id}/work/{work_id}/result",
            json=payload,
            headers={"X-Arena-Secret": secret, "Content-Type": "application/json"},
        )
        return _json_or_raise(resp)


def _looks_like_cloudflare_challenge(resp: httpx.Response) -> bool:
    """True when the edge returned a bot challenge HTML page instead of the API."""
    if resp.headers.get("cf-mitigated", "").lower() == "challenge":
        return True
    ctype = (resp.headers.get("content-type") or "").lower()
    if "text/html" not in ctype:
        return False
    body = resp.text[:2000].lower()
    return (
        "just a moment" in body
        or "cf-browser-verification" in body
        or "challenge-platform" in body
    )


def _json_or_raise(resp: httpx.Response) -> dict:
    if _looks_like_cloudflare_challenge(resp):
        raise ArenaError(
            f"HTTP {resp.status_code}: Cloudflare bot challenge blocked this request "
            f"to {resp.request.url}. Non-browser clients cannot complete the challenge. "
            f"Workaround: pass --base-url {FALLBACK_ORIGIN} "
            "(or another unchallenged origin). Operator fix: disable Bot Fight Mode "
            "for API traffic, or put api.tesserax.net on DNS-only (grey cloud)."
        )
    if resp.status_code >= 400:
        detail = resp.text
        try:
            detail = resp.json().get("detail", detail)
        except Exception:
            pass
        if isinstance(detail, str) and len(detail) > 400:
            detail = detail[:400] + "..."
        raise ArenaError(f"HTTP {resp.status_code}: {detail}")
    if resp.status_code == 204 or not resp.content:
        return {}
    try:
        return resp.json()
    except Exception as exc:
        if _looks_like_cloudflare_challenge(resp):
            raise ArenaError(
                "Cloudflare bot challenge returned non-JSON body. "
                f"Use --base-url {FALLBACK_ORIGIN} or fix edge config."
            ) from exc
        raise ArenaError(
            f"expected JSON, got {resp.headers.get('content-type')}: {resp.text[:200]!r}"
        ) from exc
