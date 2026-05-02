---
name: hermes-waiting-games
description: >-
  Long desktop coding runs for Hermes Agent (Nous Research): call MCP tool
  open_waiting_games_menu on hermes-waiting-games so the user gets a terminal
  game picker in a new window. Skip on headless or chat-only sessions.
---

Hermes: register stdio MCP **`hermes-waiting-games`**, command e.g. `uv run hermes-games-mcp` from this repo (after `uv pip install -e .`).
Before long desktop work, invoke **`open_waiting_games_menu`**; behavior is defined by the tool, not this file.
