# AGENTS.md — orientation for AI agents

This file tells future-you (or any other agent) what this repo is, where to
look first, and what *not* to redo.

## TL;DR

A single-file Hermes plugin (`plugin/__init__.py`) that pauses/resumes a
vendored tron binary across LLM turns. No build, no install, no MCP, no
tests. Symlink → enable → restart.

## Where to look

| Question                      | File                                  |
|-------------------------------|---------------------------------------|
| What does it actually do?     | `plugin/__init__.py` (the whole thing) |
| How is it wired into Hermes?  | `plugin/plugin.yaml` + symlink in `~/.hermes/plugins/waiting-games` |
| What enables it?              | `plugins.enabled: [waiting-games]` in `~/.hermes/config.yaml` |
| Tron binaries                 | `bin/<arch>/tron` (vendored)           |
| Backstory / pitfalls          | `README.md`                            |

## Mental model

```
┌─────────────────────┐
│ user types message  │
└──────────┬──────────┘
           ▼
   pre_llm_call hook  ─► SIGCONT tron  (or launch fresh in Terminal.app)
           ▼
   Hermes generates response
           ▼
   post_llm_call hook ─► SIGSTOP tron
           ▼
   user reads / types next message
```

The PID file `/tmp/hermes_games_menu.pid` is the only handoff between
plugin and game. It's the PID of the bash subshell that `exec`s tron.
We `killpg` that subshell's process group so the controlling shell
stays in sync with tron.

## Hard-earned facts (don't relearn these)

- **Hermes plugins are loaded once at gateway startup.** Edit → `hermes
  restart` (from a *different* terminal so you don't kill the gateway you're
  talking to). The currently-running session keeps the old code in memory.
- **`Terminal.app do script` + an outer wrapper shell creates zombies on
  SIGSTOP.** Solution: have the inner shell `exec` tron in place
  (no parent bash hanging around to be stopped).
- **`os.killpg(os.getpgid(pid), sig)`** is the correct call — you want the
  whole pgrp so tron and its shell move together.
- **Don't re-add the MCP server.** The plugin is fully autonomous via
  hooks; an MCP tool would just be agent-launchable redundancy.
- **Tron binary perms reset after re-extracting.** `chmod +x` lives in
  README.md.

## Out-of-scope (don't go here unless asked)

- Linux / Windows launchers
- Picking a different game (tron is the chosen one for now)
- Restoring the MCP server
- Packaging as a pip-installable distribution

## Quick edit/test loop

1. Edit `plugin/__init__.py`
2. From another terminal: `hermes restart`
3. Send any message in your Hermes session
4. Inspect: `cat /tmp/hermes_games_menu.pid && ps -p $(cat /tmp/hermes_games_menu.pid) -o pid,stat,command`
   - `S+` = running (during pre_llm_call window)
   - `T+` = stopped (after post_llm_call)
