"""Push-mode helper: a tiny local webhook server.

For people who'd rather use the classic push (webhook) model but don't want to
hand-write signature verification, this stands up a minimal HTTP server that:

  - verifies the ``X-Arena-Signature`` HMAC-SHA256 header against the agent
    secret,
  - proxies the prompt to the same generic adapter used by pull mode,
  - replies with ``{"response": "<answer>"}``.

Expose it publicly (e.g. via a tunnel) and register its URL as your
``webhook_url`` in push mode. Run with ``tesserax push``.
"""

import hashlib
import hmac
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .adapter import AdapterError, run_adapter


def _verify(secret: str, body: bytes, signature: str) -> bool:
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature or "")


def make_handler(secret: str, command: list[str]):
    class WebhookHandler(BaseHTTPRequestHandler):
        def _send(self, status: int, payload: dict) -> None:
            data = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):  # noqa: N802 (stdlib naming)
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length) if length else b""

            sig = self.headers.get("X-Arena-Signature", "")
            if not _verify(secret, body, sig):
                self._send(401, {"error": "bad signature"})
                return

            try:
                work = json.loads(body)
            except json.JSONDecodeError:
                self._send(400, {"error": "invalid JSON"})
                return

            deadline = work.get("deadline_seconds")
            try:
                answer = run_adapter(command, work, timeout=deadline)
            except AdapterError as exc:
                self._send(500, {"error": str(exc)})
                return

            self._send(200, {"response": answer})

        def log_message(self, *args):  # silence default stderr logging
            pass

    return WebhookHandler


def serve(secret: str, command: list[str], host: str = "0.0.0.0", port: int = 8080) -> None:
    handler = make_handler(secret, command)
    httpd = ThreadingHTTPServer((host, port), handler)
    httpd.serve_forever()
