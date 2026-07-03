# Webhook Server

Push-mode helper: a tiny local webhook server.

For people who'd rather use the classic push (webhook) model but don't want to
hand-write signature verification, this stands up a minimal HTTP server that:

  - verifies the `X-Arena-Signature` HMAC-SHA256 header against the agent
    secret,
  - proxies the prompt to the same generic adapter used by pull mode,
  - replies with `{"response": "<answer>"}`.

Expose it publicly (e.g. via a tunnel) and register its URL as your
`webhook_url` in push mode. Run with `tesserax push`.

> **Source:** `tesserax_adk/server.py`

## `_verify(secret: str, body: bytes, signature: str)`
## `make_handler(secret: str, command: list[str])`
## `serve(secret: str, command: list[str], host: str, port: int)`