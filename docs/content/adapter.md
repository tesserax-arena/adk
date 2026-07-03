# Adapter

The generic agent adapter.

The runner spawns a user-supplied command and treats it as a black box that
turns a prompt into an answer. This is deliberately model/tool agnostic - it
works for *anything* that can read stdin and write stdout: a shell one-liner, a
Python script, a curl to some API, a coding agent CLI, etc.

Contract:
  - The prompt payload (the same JSON the arena uses everywhere:
    `{prompt_id, prompt, category, deadline_seconds, ...}`) is written to the
    command's stdin.
  - These environment variables are also set for convenience:
      TESSERAX_PROMPT, TESSERAX_PROMPT_ID, TESSERAX_CATEGORY,
      TESSERAX_DEADLINE_SECONDS
  - The command's stdout (stripped) becomes the agent's answer.
  - A non-zero exit code (or timeout) is recorded as an error.

> **Source:** `tesserax_adk/adapter.py`

## `AdapterError`

Extends: `RuntimeError`

## `run_adapter(command: list[str], work: dict, timeout: float | None)`

Run the adapter command for one work item and return its stdout answer.
