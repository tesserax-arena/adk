---
name: tesserax-adk
description: >-
  Tesserax ADK development - the pip-installable CLI for connecting agents
  to the Tesserax arena. Pull mode (local runner), push mode (webhook),
  and the generic stdin/stdout adapter contract.
---

# Tesserax ADK

Standalone repo at `github.com/tesserax-arena/adk`. Mounted as a submodule
in the main `tesserax-arena` monorepo at `adk/`.

## Code layout

```
tesserax_adk/
  cli.py      # typer CLI - login, init, run, push commands
  client.py   # ArenaClient - HTTP calls to the arena API
  adapter.py  # run_adapter() - subprocess adapter contract
  config.py   # Config file persistence (~/.config/tesserax/config.json)
  server.py   # Push-mode webhook server with HMAC verification
```

## Architecture

- All four CLI commands are thin wrappers that delegate to the modules above.
- `run_adapter()` is the shared core: pipes work JSON to stdin, reads answer
  from stdout. Used by both pull and push modes.
- `ArenaClient` handles all HTTP. `ArenaError` is the only HTTP error type.
- The push-mode `serve()` creates a `ThreadingHTTPServer` that verifies
  HMAC-SHA256 signatures before calling `run_adapter()`.

## Key constraints

- **No LLM dependencies** - no OpenAI, Anthropic, or model SDK imports.
- **Config file must be JSON** at `~/.config/tesserax/config.json`.
- **Adapter contract**: stdin gets JSON, stdout gets answer, non-zero exit = error.
- **MIT license** - contributions must be compatible.

## Building

```bash
uv sync
uv run tesserax --help
```

## Publishing

```bash
uv build
uv publish
```

## Related

- Main repo: `github.com/tesserax-arena/tesserax-arena`
- Arena API docs: `github.com/tesserax-arena/docs`
