"""waiting-games — Hermes plugin

Plays tron in a side Terminal.app window while you wait for Hermes to think.

Lifecycle:
  pre_llm_call  → user is about to wait → SIGCONT existing tron, or launch new one
  post_llm_call → Hermes done responding → SIGSTOP tron so you can read in peace

The same tron process persists across turns. If you die or quit, the next turn
launches a fresh one.

macOS only (uses osascript + Terminal.app). Adding Linux/Windows means picking
a terminal emulator and writing the equivalent launch path in `_launch_tron`.

PID coordination:
  The launched bash subshell writes its own PID to /tmp/hermes_games_menu.pid
  before exec'ing tron. We signal that shell's process group so tron + its
  controlling shell stay in sync.
"""

from __future__ import annotations

import logging
import os
import platform
import shlex
import signal
import subprocess
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# /tmp/hermes_games_menu.pid is also referenced by ~/.claude/settings.json
# hooks (Claude Code path). Keeping the same path means both runtimes
# coordinate on the same game instance.
PID_FILE = Path("/tmp/hermes_games_menu.pid")

# Resolve the tron binary relative to this file. The plugin dir is expected to
# live inside (or be symlinked to) the hermes-games-skill repo, so:
#   <repo>/plugin/__init__.py  →  <repo>/bin/<arch>/tron
_PLUGIN_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _PLUGIN_DIR.parent
_ARCH_DIR = {
    ("Darwin", "arm64"): "darwin-arm64",
    ("Darwin", "x86_64"): "darwin-amd64",
    ("Linux", "x86_64"): "linux-amd64",
    ("Linux", "aarch64"): "linux-arm64",
}.get((platform.system(), platform.machine()), "darwin-arm64")
TRON_BIN = _REPO_ROOT / "bin" / _ARCH_DIR / "tron"


# ---------- pid + signal helpers ----------

def _read_pid() -> int | None:
    """Return the live pid from PID_FILE, or None if missing/stale/dead."""
    try:
        pid = int(PID_FILE.read_text().strip())
        os.kill(pid, 0)  # liveness probe
        return pid
    except (FileNotFoundError, ValueError, ProcessLookupError, PermissionError):
        return None


def _signal_pgrp(pid: int, sig: signal.Signals) -> bool:
    """Send sig to pid's process group; fall back to single pid. Best-effort."""
    try:
        os.killpg(os.getpgid(pid), sig)
        return True
    except (ProcessLookupError, PermissionError):
        try:
            os.kill(pid, sig)
            return True
        except (ProcessLookupError, PermissionError):
            return False


# ---------- tron launcher ----------

def _launch_tron() -> None:
    """Open a new Terminal.app window running tron; write its shell pid to PID_FILE."""
    if platform.system() != "Darwin":
        logger.debug("waiting-games: non-Darwin not implemented")
        return
    if not TRON_BIN.exists():
        logger.debug("waiting-games: tron binary missing at %s", TRON_BIN)
        return

    pidf = shlex.quote(str(PID_FILE))
    bin_q = shlex.quote(str(TRON_BIN))
    # The subshell records its pid then execs tron in its place.
    inner = f"echo $$ > {pidf}; exec {bin_q}"
    inner_lit = inner.replace("\\", "\\\\").replace('"', '\\"')
    script = (
        f'set i to "{inner_lit}"\n'
        'set c to "exec bash -lc " & quoted form of i\n'
        'tell application "Terminal" to do script c'
    )
    try:
        subprocess.run(
            ["osascript", "-e", script],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        logger.debug("waiting-games: failed to launch tron: %s", exc)


# ---------- hermes hooks ----------

def _on_pre_llm_call(**kwargs) -> None:
    """User is about to wait — resume the existing game, or launch a fresh one."""
    if kwargs.get("platform") != "cli":
        return
    pid = _read_pid()
    if pid is None:
        PID_FILE.unlink(missing_ok=True)
        _launch_tron()
        return
    _signal_pgrp(pid, signal.SIGCONT)


def _on_post_llm_call(**kwargs) -> None:
    """Hermes finished responding — pause tron so the user can read/type."""
    if kwargs.get("platform") != "cli":
        return
    # Fresh launches need a beat for the inner shell to write its pid.
    for _ in range(20):  # up to ~1s
        pid = _read_pid()
        if pid is not None:
            _signal_pgrp(pid, signal.SIGSTOP)
            return
        time.sleep(0.05)


def register(ctx) -> None:
    ctx.register_hook("pre_llm_call", _on_pre_llm_call)
    ctx.register_hook("post_llm_call", _on_post_llm_call)
