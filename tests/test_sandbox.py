"""Pull-mode sandbox tasks: the ADK drives the session and submits it."""

import json

import httpx

from tesserax_adk import cli
from tesserax_adk.client import ArenaClient, sign

SECRET = "agent-secret"


def recording_client(responder):
    seen = []

    def handler(request):
        seen.append(request)
        return responder(request)

    return ArenaClient("http://arena.test", transport=httpx.MockTransport(handler)), seen


def test_exec_is_signed_over_the_exact_body():
    c, seen = recording_client(lambda r: httpx.Response(200, json={"exit_code": 0, "stdout": "ok\n", "stderr": ""}))
    assert c.sandbox_exec(9, SECRET, "pytest -q")["stdout"] == "ok\n"
    req = seen[0]
    assert req.url.path == "/api/sandbox/9/exec"
    assert json.loads(req.content) == {"command": "pytest -q", "timeout": 120}
    assert req.headers["X-Arena-Signature"] == sign(SECRET, req.content)


def test_exec_waits_out_the_rate_limit(monkeypatch):
    monkeypatch.setattr("tesserax_adk.client.time.sleep", lambda s: None)
    replies = iter([
        httpx.Response(429, headers={"Retry-After": "2"}),
        httpx.Response(200, json={"exit_code": 0, "stdout": "", "stderr": ""}),
    ])
    c, seen = recording_client(lambda r: next(replies))
    assert c.sandbox_exec(9, SECRET, "ls")["exit_code"] == 0
    assert len(seen) == 2


def test_reads_carry_both_tiers_auth():
    """Python checks X-Arena-Secret on GET; Go checks a signature over the empty body."""
    c, seen = recording_client(lambda r: httpx.Response(200, text="file body"))
    assert c.sandbox_read(9, SECRET, "/src/app.py") == "file body"
    req = seen[0]
    assert req.url.path == "/api/sandbox/9/files/src/app.py"
    assert req.headers["X-Arena-Secret"] == SECRET
    assert req.headers["X-Arena-Signature"] == sign(SECRET, b"")


class FakeClient:
    base_url = "http://arena.test"

    def __init__(self, status="active"):
        self.status, self.submitted = status, False

    def sandbox_status(self, session_id, secret):
        return {"status": self.status}

    def sandbox_submit(self, session_id, secret):
        self.submitted = True
        return {"status": "submitted"}


WORK = {"kind": "sandbox", "session_id": 9, "title": "Fix it", "description": "...", "deadline_seconds": 60}


def test_runner_submits_after_the_adapter(monkeypatch):
    env_seen = {}

    def adapter(cmd, work, timeout=None, extra_env=None, require_output=True):
        env_seen.update(extra_env)
        assert require_output is False, "sandbox work has no stdout answer"
        return ""

    monkeypatch.setattr(cli, "run_adapter", adapter)
    fake = FakeClient()
    cli._run_sandbox(fake, ["agent"], WORK, 3, SECRET)
    assert fake.submitted
    assert env_seen["TESSERAX_SESSION_ID"] == "9" and env_seen["TESSERAX_AGENT_SECRET"] == SECRET
    assert env_seen["TESSERAX_KIND"] == "sandbox"


def test_a_crashed_adapter_is_still_submitted(monkeypatch):
    """An unsubmitted session is abandoned and unscored; a crash must not erase a fail."""

    def adapter(*a, **k):
        raise cli.AdapterError("boom")

    monkeypatch.setattr(cli, "run_adapter", adapter)
    fake = FakeClient()
    cli._run_sandbox(fake, ["agent"], WORK, 3, SECRET)
    assert fake.submitted


def test_an_already_submitted_session_is_left_alone(monkeypatch):
    monkeypatch.setattr(cli, "run_adapter", lambda *a, **k: "")
    fake = FakeClient(status="submitted")
    cli._run_sandbox(fake, ["agent"], WORK, 3, SECRET)
    assert not fake.submitted
