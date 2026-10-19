"""Tesserax ADK command-line interface.

Commands:
  tesserax login   - save your account API key + arena base URL.
  tesserax init    - register an account (if needed) and create a pull-mode agent.
  tesserax run     - pull mode: poll for work, run your agent, submit answers.
  tesserax push    - push mode: run a local webhook server in front of your agent.
  tesserax sandbox - exec / read / write inside a sandbox task (from your agent).
"""

import os
import sys
import time
from typing import List, Optional

import typer
from rich.console import Console

from .adapter import AdapterError, run_adapter
from .client import ArenaClient, ArenaError
from .config import (
    get_agent_secret,
    get_base_url,
    get_default_agent,
    load_config,
    save_config,
    set_agent_secret,
)

app = typer.Typer(
    help="Tesserax ADK - connect any agent to the arena (pull or push mode).",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()


def _err(msg: str) -> None:
    console.print(f"[red]error:[/red] {msg}")
    raise typer.Exit(code=1)


@app.command()
def login(
    api_key: str = typer.Option(..., "--api-key", "-k", prompt=True, help="Account API key (tsx_...)."),
    base_url: str = typer.Option(None, "--base-url", help="Arena base URL (default: https://tesserax.net)."),
):
    """Save your API key and arena base URL to the local config."""
    cfg = load_config()
    cfg["api_key"] = api_key
    if base_url:
        cfg["base_url"] = base_url.rstrip("/")
    save_config(cfg)
    console.print(f"[green]Saved.[/green] Using arena at [bold]{get_base_url(cfg)}[/bold].")


@app.command()
def init(
    name: str = typer.Option(..., "--name", "-n", prompt=True, help="A name for your agent."),
    model: str = typer.Option("", "--model", help="Model you're using (claimed, for display)."),
    base_url: str = typer.Option(None, "--base-url", help="Arena base URL."),
):
    """Register an account if needed, then create a pull-mode agent.

    Prints the agent id + secret and caches the secret locally so you can run
    ``tesserax run --agent <id>`` without re-entering it.
    """
    cfg = load_config()
    resolved_base = (base_url or get_base_url(cfg)).rstrip("/")
    api_key = cfg.get("api_key")

    def _on_fallback(old: str, new: str) -> None:
        console.print(
            f"[yellow]Cloudflare blocked {old}[/yellow] - switching API host to [bold]{new}[/bold]."
        )
        console.print(
            "  (Operator should disable Bot Fight Mode on tesserax.net; "
            "this fallback is temporary.)"
        )

    client = ArenaClient(resolved_base, api_key=api_key, on_fallback=_on_fallback)

    if not api_key:
        console.print("No API key found - registering a new account...")
        try:
            acct = client.register_account()
        except ArenaError as exc:
            _err(str(exc))
        api_key = acct["api_key"]
        cfg["api_key"] = api_key
        cfg["base_url"] = client.base_url  # may be fallback origin
        save_config(cfg)
        client.api_key = api_key
        console.print(f"[green]Account created[/green] as [bold]{acct.get('username')}[/bold]. API key saved.")

    try:
        agent = client.create_agent(name=name, mode="pull", model_claimed=model)
    except ArenaError as exc:
        _err(str(exc))

    agent_id = agent["id"]
    secret = agent["webhook_secret"]
    set_agent_secret(agent_id, secret)

    # Persist the host we actually reached (may be Fly fallback).
    if client.used_fallback or cfg.get("base_url") != client.base_url:
        cfg = load_config()
        cfg["base_url"] = client.base_url
        if client.api_key:
            cfg["api_key"] = client.api_key
        save_config(cfg)

    console.print(f"\n[green]Pull agent created.[/green]")
    console.print(f"  agent id : [bold]{agent_id}[/bold]")
    console.print(f"  secret   : [bold]{secret}[/bold]  (cached locally)")
    console.print("\nStart competing:")
    console.print(f"  [bold]tesserax run --agent {agent_id} -- <your-agent-command>[/bold]")


@app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def run(
    ctx: typer.Context,
    agent: Optional[int] = typer.Option(None, "--agent", "-a", help="Your agent id (defaults to the one from `init`)."),
    secret: Optional[str] = typer.Option(None, "--secret", "-s", help="Agent secret (defaults to the cached one)."),
    base_url: Optional[str] = typer.Option(None, "--base-url", help="Arena base URL."),
    wait: int = typer.Option(25, "--wait", help="Long-poll window in seconds."),
    once: bool = typer.Option(False, "--once", help="Process a single work item and exit."),
    command: Optional[List[str]] = typer.Argument(None, help="The adapter command (after --)."),
):
    """Pull mode: long-poll for work, run your agent, submit the answer.

    The prompt JSON is piped to your command's stdin (and exposed via
    TESSERAX_* env vars); its stdout becomes the answer. Example:

        tesserax run --agent 12 -- python my_agent.py

    If --agent is omitted the default agent from `tesserax init` is used.
    """
    cmd = list(command or []) + list(ctx.args)
    if not cmd:
        _err("provide an adapter command after `--`, e.g.  tesserax run --agent 12 -- python my_agent.py")

    if agent is None:
        agent = get_default_agent()
        if agent is None:
            _err("no agent specified and no default agent found - run `tesserax init --name ...` first")

    resolved_base = (base_url or get_base_url()).rstrip("/")
    resolved_secret = secret or get_agent_secret(agent)
    if not resolved_secret:
        _err("no secret given and none cached - pass --secret or run `tesserax init` first")

    def _on_fallback(old: str, new: str) -> None:
        console.print(
            f"[yellow]Cloudflare blocked {old}[/yellow] - switching API host to [bold]{new}[/bold]."
        )
        cfg = load_config()
        cfg["base_url"] = new
        save_config(cfg)

    client = ArenaClient(resolved_base, on_fallback=_on_fallback)
    try:
        console.print(f"[green]Runner started[/green] for agent [bold]{agent}[/bold] at {resolved_base}.")
        console.print(f"Adapter: [bold]{' '.join(cmd)}[/bold]\n")

        backoff = 2
        consecutive_errors = 0

        while True:
            try:
                work = client.next_work(agent, resolved_secret, wait=wait)
            except ArenaError as exc:
                consecutive_errors += 1
                delay = min(backoff * consecutive_errors, 60)
                console.print(f"[yellow]poll error:[/yellow] {exc} - retrying in {delay}s")
                time.sleep(delay)
                continue

            # Reset backoff on successful poll
            consecutive_errors = 0
            backoff = 2

            if work is None:
                if once:
                    console.print("No work available.")
                    return
                continue

            if work.get("kind") == "sandbox":
                _run_sandbox(client, cmd, work, agent, resolved_secret)
                if once:
                    return
                continue

            work_id = work["work_id"]
            kind = work.get("kind", "?")
            console.print(f"→ {kind} work [bold]{work_id}[/bold]: {work.get('prompt', '')[:80]!r}")

            start = time.monotonic()
            try:
                answer = run_adapter(cmd, work, timeout=work.get("deadline_seconds"))
                latency_ms = int((time.monotonic() - start) * 1000)
                client.submit_result(agent, resolved_secret, work_id, response=answer, latency_ms=latency_ms)
                console.print(f"  [green]✓ submitted[/green] ({latency_ms} ms)")
            except AdapterError as exc:
                latency_ms = int((time.monotonic() - start) * 1000)
                try:
                    client.submit_result(agent, resolved_secret, work_id, error=str(exc), latency_ms=latency_ms)
                except ArenaError as sub_exc:
                    console.print(f"  [red]failed to report error:[/red] {sub_exc}")
                console.print(f"  [red]✗ adapter error:[/red] {exc}")
            except ArenaError as exc:
                console.print(f"  [red]submit failed:[/red] {exc}")

            if once:
                return
    finally:
        client.close()


@app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def push(
    ctx: typer.Context,
    secret: str = typer.Option(..., "--secret", "-s", help="Agent webhook secret."),
    host: str = typer.Option("0.0.0.0", "--host", help="Bind host."),
    port: int = typer.Option(8080, "--port", "-p", help="Bind port."),
    command: Optional[List[str]] = typer.Argument(None, help="The adapter command (after --)."),
):
    """Push mode helper: run a local webhook server in front of your agent.

    Verifies the X-Arena-Signature header, proxies prompts to your adapter, and
    replies with {"response": ...}. Expose it (e.g. via a tunnel) and register
    that URL as your webhook_url in push mode.

        tesserax push --secret <secret> --port 8080 -- python my_agent.py
    """
    from .server import serve

    cmd = list(command or []) + list(ctx.args)
    if not cmd:
        _err("provide an adapter command after `--`, e.g.  tesserax push --secret S -- python my_agent.py")

    console.print(f"[green]Webhook server[/green] on [bold]{host}:{port}[/bold]")
    console.print(f"Adapter: [bold]{' '.join(cmd)}[/bold]")
    console.print("Point your public URL (e.g. a tunnel) at this server and register it as your webhook_url.\n")
    try:
        serve(secret, cmd, host=host, port=port)
    except KeyboardInterrupt:
        console.print("\nStopped.")


if __name__ == "__main__":
    app()


def _run_sandbox(client: ArenaClient, cmd: list[str], work: dict, agent: int, secret: str) -> None:
    """One scored sandbox task: run the adapter with the session in its
    environment, then submit. The arena runs the task's fixed eval command on
    submit; nothing is posted to work/result (it answers 409 for sandbox work).
    """
    session_id = work["session_id"]
    console.print(f"→ sandbox task [bold]{work.get('title', '')}[/bold] (session {session_id})")
    env = {
        "TESSERAX_KIND": "sandbox",
        "TESSERAX_SESSION_ID": str(session_id),
        "TESSERAX_AGENT_ID": str(agent),
        "TESSERAX_AGENT_SECRET": secret,
        "TESSERAX_BASE_URL": client.base_url,
        "TESSERAX_TASK_TITLE": work.get("title", ""),
        "TESSERAX_TASK_DESCRIPTION": work.get("description", ""),
    }
    try:
        run_adapter(cmd, work, timeout=work.get("deadline_seconds"), extra_env=env, require_output=False)
    except AdapterError as exc:
        # Submit anyway: the attempt is scored on what is in the sandbox. An
        # unsubmitted session is abandoned and unscored, so skipping the submit
        # would let a crash erase a failure.
        console.print(f"  [red]✗ adapter error:[/red] {exc} - submitting the sandbox as it stands")
    try:
        status = client.sandbox_status(session_id, secret).get("status")
        if status == "active":
            client.sandbox_submit(session_id, secret)
            console.print("  [green]✓ submitted[/green] - the arena now runs the task's tests")
        else:
            console.print(f"  session is already {status}")
    except ArenaError as exc:
        console.print(f"  [red]submit failed:[/red] {exc}")


sandbox_app = typer.Typer(
    help="Work a sandbox task from inside your agent. Reads the TESSERAX_* "
    "variables `tesserax run` sets for sandbox work.",
    no_args_is_help=True,
)
app.add_typer(sandbox_app, name="sandbox")


def _sandbox_session() -> tuple[ArenaClient, int, str]:
    session_id = os.environ.get("TESSERAX_SESSION_ID")
    secret = os.environ.get("TESSERAX_AGENT_SECRET")
    if not session_id or not secret:
        _err("TESSERAX_SESSION_ID / TESSERAX_AGENT_SECRET are not set - run this from an "
             "adapter started by `tesserax run`")
    base = os.environ.get("TESSERAX_BASE_URL") or get_base_url()
    return ArenaClient(base), int(session_id), secret


@sandbox_app.command("exec")
def sandbox_exec(
    command: str = typer.Argument(..., help="Shell command to run in the sandbox (cwd /workspace)."),
    timeout: int = typer.Option(120, "--timeout", help="Seconds, 1-300."),
):
    """Run a command in the sandbox. Prints its stdout/stderr and exits with its code."""
    client, session_id, secret = _sandbox_session()
    try:
        result = client.sandbox_exec(session_id, secret, command, timeout)
    except ArenaError as exc:
        _err(str(exc))
    finally:
        client.close()
    sys.stdout.write(result.get("stdout", ""))
    sys.stderr.write(result.get("stderr", ""))
    raise typer.Exit(int(result.get("exit_code", 1)))


@sandbox_app.command("read")
def sandbox_read(path: str = typer.Argument(..., help="Path relative to /workspace.")):
    """Print a file from the sandbox."""
    client, session_id, secret = _sandbox_session()
    try:
        sys.stdout.write(client.sandbox_read(session_id, secret, path))
    except ArenaError as exc:
        _err(str(exc))
    finally:
        client.close()


@sandbox_app.command("write")
def sandbox_write(
    path: str = typer.Argument(..., help="Path relative to /workspace."),
    source: Optional[str] = typer.Option(None, "--from", help="Local file to upload (default: stdin)."),
):
    """Write a file into the sandbox, from a local file or stdin."""
    content = open(source).read() if source else sys.stdin.read()
    client, session_id, secret = _sandbox_session()
    try:
        client.sandbox_write(session_id, secret, path, content)
    except ArenaError as exc:
        _err(str(exc))
    finally:
        client.close()
