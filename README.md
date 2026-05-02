# hermes-games-mcp

Hermes-only: one module [`src/hermes_games_mcp/plugin.py`](src/hermes_games_mcp/plugin.py) registers plugin **`waiting-games`**. No MCP — the plugin opens/resumes the menu every CLI turn and freezes it when the turn ends (Unix: `SIGSTOP` / `SIGCONT`).

## Install

```bash
/path/to/hermes/.venv/bin/pip install -e /path/to/this/repo
```

```yaml
# ~/.hermes/config.yaml
plugins:
  enabled:
    - waiting-games
```

See [skills.md](skills.md).
