"""The generic agent adapter.

The runner spawns a user-supplied command and treats it as a black box that
turns a prompt into an answer. This is deliberately model/tool agnostic - it
works for *anything* that can read stdin and write stdout: a shell one-liner, a
Python script, a curl to some API, a coding agent CLI, etc.

Contract:
  - The prompt payload (the same JSON the arena uses everywhere:
    ``{prompt_id, prompt, category, deadline_seconds, ...}``) is written to the
    command's stdin.
  - These environment variables are also set for convenience:
      TESSERAX_PROMPT, TESSERAX_PROMPT_ID, TESSERAX_CATEGORY,
      TESSERAX_DEADLINE_SECONDS
  - The command's stdout (stripped) becomes the agent's answer.
  - A non-zero exit code (or timeout) is recorded as an error.
"""

import json
import os
import subprocess


class AdapterError(RuntimeError):
    pass


DEFAULT_TIMEOUT = 120


def run_adapter(command: list[str], work: dict, timeout: float | None = None) -> str:
    """Run the adapter command for one work item and return its stdout answer."""
    if not command:
        raise AdapterError("no adapter command provided")

    env = dict(os.environ)
    env["TESSERAX_PROMPT"] = work.get("prompt", "")
    env["TESSERAX_PROMPT_ID"] = str(work.get("prompt_id", ""))
    env["TESSERAX_CATEGORY"] = work.get("category", "")
    env["TESSERAX_DEADLINE_SECONDS"] = str(work.get("deadline_seconds", ""))

    stdin_payload = json.dumps(work)

    # Always enforce a timeout to prevent orphaned processes.
    effective_timeout = timeout if timeout is not None else DEFAULT_TIMEOUT

    try:
        proc = subprocess.run(
            command,
            input=stdin_payload,
            capture_output=True,
            text=True,
            env=env,
            timeout=effective_timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise AdapterError(f"adapter timed out after {exc.timeout:.0f}s") from exc
    except FileNotFoundError as exc:
        raise AdapterError(f"adapter command not found: {command[0]}") from exc

    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        raise AdapterError(f"adapter exited with code {proc.returncode}: {stderr[:500]}")

    answer = (proc.stdout or "").strip()
    if not answer:
        raise AdapterError("adapter produced no output on stdout")
    return answer
