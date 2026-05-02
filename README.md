# hermes-games-mcp

Small [Model Context Protocol](https://modelcontextprotocol.io/) (stdio) server for [Hermes Agent](https://hermes-agent.nousresearch.com/) (and any other MCP client): it exposes **`open_waiting_games_menu`**, which opens a **new terminal** with a **numbered menu** of terminal games found on `PATH`. Use it during long desktop coding runs so the person waiting can play something without blocking the agent.

See [`skills.md`](skills.md) for the minimal Hermes skill pointer.

## Install

From the repository root (requires Python 3.10+):

```bash
uv venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
uv pip install -e .
```

Smoke test:

```bash
hermes-games-mcp --help 2>/dev/null || true   # stdio server; may print nothing — clients spawn it
python -c "from hermes_games_mcp.server import open_waiting_games_menu; print('import ok')"
```

## Hermes Agent MCP config

Hermes reads MCP servers from **`~/.hermes/config.yaml`** under `mcp_servers`. Official reference: [MCP config reference](https://hermes-agent.nousresearch.com/docs/reference/mcp-config-reference/) and [Use MCP with Hermes](https://hermes-agent.nousresearch.com/docs/guides/use-mcp-with-hermes/).

Merge a block like this (replace the path with your clone of this repo):

```yaml
mcp_servers:
  waiting_games:
    command: "uv"
    args:
      - "run"
      - "--directory"
      - "/absolute/path/to/hermes-games-skill"
      - "hermes-games-mcp"
```

If you prefer a fixed virtualenv (no `uv run`), use the installed console script:

```yaml
mcp_servers:
  waiting_games:
    command: "/absolute/path/to/hermes-games-skill/.venv/bin/hermes-games-mcp"
    args: []
```

Optional: restrict utility MCP wrappers on this server:

```yaml
mcp_servers:
  waiting_games:
    command: "/absolute/path/to/hermes-games-skill/.venv/bin/hermes-games-mcp"
    args: []
    tools:
      include: [open_waiting_games_menu]
      resources: false
      prompts: false
```

After editing config, reload MCP in Hermes (see docs): run **`/reload-mcp`**.

Hermes exposes server tools with a prefix of the form **`mcp_<server_key>_<tool>`** (see [tool naming](https://hermes-agent.nousresearch.com/docs/reference/mcp-config-reference/)). With the key `waiting_games`, the tool appears as **`mcp_waiting_games_open_waiting_games_menu`**.

## Cursor / Claude Desktop–style `mcp.json`

If another MCP host uses a JSON config, add:

```json
{
  "mcpServers": {
    "hermes-waiting-games": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/absolute/path/to/hermes-games-skill",
        "hermes-games-mcp"
      ]
    }
  }
}
```

Or point `command` at `.venv/bin/hermes-games-mcp` with `"args": []` after a local editable install.

## Tool

| Name | Role |
|------|------|
| `open_waiting_games_menu` | Opens a new terminal running the bundled bash menu (`games_menu.sh`); only lists games whose binaries exist on `PATH`. |

Headless SSH sessions and chat-only gateways may not be able to open a GUI terminal; the tool returns a short message suggesting a manual `bash …/games_menu.sh` command when auto-launch fails.

## License

Match the rest of your hackathon or repo policy; the upstream Hermes ecosystem is described on [Nous Research](https://www.nousresearch.com/) and the [Hermes Agent site](https://hermes-agent.nousresearch.com/).
