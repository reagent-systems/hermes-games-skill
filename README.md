# waiting-games

A Hermes plugin that plays tron-lightcycles in a side Terminal window
**while you wait for Hermes to think**, and pauses it when Hermes finishes
so you can read the response.

## What it does

Two hooks fire on the Hermes CLI lifecycle:

| Hook            | When                          | Action                                              |
|-----------------|-------------------------------|-----------------------------------------------------|
| `pre_llm_call`  | You hit enter, Hermes thinks  | `SIGCONT` existing tron, or launch a new one        |
| `post_llm_call` | Hermes finished responding    | `SIGSTOP` tron — frozen until your next message     |

The same tron process persists across turns. Die or quit tron → next turn
launches a fresh one. The launched tron lives in its own `Terminal.app`
window (macOS only).

## Layout

```
.
├── plugin/                   ← the plugin (Hermes loads this)
│   ├── __init__.py           ← all logic: hooks, launcher, signal helpers
│   └── plugin.yaml           ← name, version, hook list
├── bin/<arch>/tron           ← prebuilt tron binaries (vendored)
├── README.md
├── AGENTS.md                 ← orientation for AI agents working in this repo
└── skills.md                 ← short skill description for Hermes catalog
```

There is no Python package install, no MCP server, no build step.
Hermes loads the plugin from a directory under `~/.hermes/plugins/`.

## Install

Symlink the `plugin/` directory into the Hermes plugins folder under the
plugin name:

```bash
ln -s "$(pwd)/plugin" ~/.hermes/plugins/waiting-games
```

Enable in `~/.hermes/config.yaml`:

```yaml
plugins:
  enabled:
    - waiting-games
```

Restart Hermes (`hermes restart`). The next turn will pop a Terminal window
running tron.

## How it coordinates with the game process

- The plugin's `_launch_tron` runs `osascript` → `Terminal.app do script "exec bash -lc <inner>"`
- `<inner>` writes the subshell PID to `/tmp/hermes_games_menu.pid` then `exec`s tron
- The plugin signals that PID's process group (`SIGCONT`/`SIGSTOP`) via `os.killpg`
- That same PID file is also referenced by Claude Code hooks in `~/.claude/settings.json`,
  so both runtimes coordinate on a single game instance.

## Pitfalls / things to know

1. **Plugin code is loaded once at Hermes startup.** Edit the plugin → run
   `hermes restart` (in a *separate* terminal — don't kill your active
   session). Restarting from inside a Hermes turn kills the gateway you're
   talking to.
2. **macOS only right now.** Linux/Windows would need a different terminal
   launcher in `_launch_tron` (e.g. `gnome-terminal --` or `wt.exe`).
3. **`tron` binary must be executable.** If you re-clone or re-extract:
   `chmod +x bin/darwin-arm64/tron`.
4. **PID-file race.** A *fresh* launch needs a beat for the inner shell to
   write its PID. `_on_post_llm_call` polls for up to ~1s before giving up.
5. **`Z+` zombies after SIGSTOP** were the symptom of an earlier, broken
   wrapper-shell setup. The current `exec`-based launcher avoids them.

## Provenance

Originally a Hermes MCP server that exposed an `open_waiting_games_menu`
tool. The MCP layer was removed once the plugin became fully autonomous —
hooks alone are enough; no agent action is needed to start a game.
