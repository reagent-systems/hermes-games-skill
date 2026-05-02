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
| `open_waiting_games_menu` | Opens a new terminal running the bundled bash menu (`games_menu.sh`); lists games whose binaries are on `PATH` or bundled in `bin/<os>-<arch>/`. |

Headless SSH sessions and chat-only gateways may not be able to open a GUI terminal; the tool returns a short message suggesting a manual `bash …/games_menu.sh` command when auto-launch fails.

## Bundled games

Some games ship in this repo so they're available without a separate install. The menu script auto-detects platform via `uname` and looks in `bin/<os>-<arch>/`.

| Game | Source | Platforms bundled |
|------|--------|-------------------|
| Tron lightcycles | Single human vs three personality-driven bots (aggressor, wall-hugger, survivor). Built in Go with `tcell`. | linux-amd64, linux-arm64, darwin-amd64, darwin-arm64, windows-amd64 |

Other games in `games_menu.sh` (NetHack, nSnake, Greed, etc.) are *not* bundled — install them through your package manager (`brew install ninvaders`, `apt install nsnake`, etc.) and they'll show up automatically.

### Adding a bundled binary

1. Cross-compile or grab pre-built binaries for the platforms you want to support. For Go projects:
   ```bash
   for target in linux-amd64 linux-arm64 darwin-amd64 darwin-arm64 windows-amd64; do
     GOOS="${target%-*}" GOARCH="${target#*-}" \
       go build -o "/path/to/hermes-games-skill/bin/$target/<binary>" .
   done
   ```
   (Add `.exe` to the windows-amd64 output name.)
2. Add a `register "<Display name>" "<binary>"` line to `src/hermes_games_mcp/games_menu.sh`.
3. Commit the binaries.

## License

Match the rest of your hackathon or repo policy; the upstream Hermes ecosystem is described on [Nous Research](https://www.nousresearch.com/) and the [Hermes Agent site](https://hermes-agent.nousresearch.com/).
