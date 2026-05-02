"""MCP server: open a separate terminal running the waiting-games menu."""

from __future__ import annotations

import platform
import shlex
import shutil
import subprocess
from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("hermes-waiting-games")


def _menu_script() -> Path:
    return Path(__file__).resolve().parent / "games_menu.sh"


def _applescript_text_literal(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _launch_macos(menu_sh: Path) -> None:
    posix = str(menu_sh.resolve())
    path_lit = _applescript_text_literal(posix)
    apple_script = f"""
set posixPath to "{path_lit}"
set goScript to "exec bash " & quoted form of posixPath
tell application "Terminal"
    activate
    do script goScript
end tell
"""
    subprocess.run(
        ["osascript", "-e", apple_script],
        check=True,
        capture_output=True,
        text=True,
    )


def _try_spawn(argv: list[str]) -> bool:
    exe = argv[0]
    if shutil.which(exe) is None:
        return False
    subprocess.Popen(
        argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return True


def _launch_linux(menu_sh: Path) -> bool:
    posix = str(menu_sh.resolve())
    inner = f"bash {shlex.quote(posix)}; exec bash"

    attempts: list[list[str]] = [
        ["gnome-terminal", "--", "bash", "-lc", inner],
        ["kgx", "--", "bash", "-lc", inner],
        [
            "x-terminal-emulator",
            "-e",
            f"bash -lc {shlex.quote(inner)}",
        ],
        ["xfce4-terminal", "-e", f"bash -lc {shlex.quote(inner)}"],
        ["konsole", "-e", "bash", "-lc", inner],
        ["kitty", "bash", "-lc", inner],
        ["alacritty", "-e", "bash", "-lc", inner],
        ["foot", "bash", "-lc", inner],
        ["xterm", "-e", "bash", "-lc", inner],
    ]

    for cmd in attempts:
        if _try_spawn(cmd):
            return True
    return False


def _launch_windows(menu_sh: Path) -> bool:
    posix = str(menu_sh.resolve())
    wt = shutil.which("wt.exe") or shutil.which("wt")
    if wt and _try_spawn(
        [wt, "new-tab", "cmd", "/k", f"bash -lc bash {shlex.quote(posix)}"]
    ):
        return True
    conemu = shutil.which("ConEmu64.exe")
    if conemu:
        return _try_spawn(
            [
                conemu,
                "-run",
                "cmd.exe",
                "/k",
                f"bash -lc bash {shlex.quote(posix)}",
            ]
        )
    return False


def _open_games_terminal() -> str:
    menu_sh = _menu_script()
    if not menu_sh.is_file():
        return f"Menu script missing: {menu_sh}"

    system = platform.system()
    try:
        if system == "Darwin":
            _launch_macos(menu_sh)
            return "Opened Terminal.app with the waiting-games menu."
        if system == "Linux":
            if _launch_linux(menu_sh):
                return "Opened a new terminal with the waiting-games menu."
            return (
                "No known terminal emulator found. Run manually: "
                f"bash {menu_sh}"
            )
        if system == "Windows":
            if _launch_windows(menu_sh):
                return "Opened Windows Terminal with the waiting-games menu."
            return (
                "Could not open a terminal automatically. Run from Git Bash/WSL: "
                f"bash {menu_sh}"
            )
        return f"Unsupported OS for auto-launch ({system}). Run: bash {menu_sh}"
    except subprocess.CalledProcessError as exc:
        return f"Failed to open terminal: {exc.stderr or exc}"
    except OSError as exc:
        return f"Failed to open terminal: {exc}"


@mcp.tool()
def open_waiting_games_menu() -> str:
    """Open a new terminal window with a numbered menu of installed CLI games. Call while a long coding task runs so the user can play without blocking the agent."""
    return _open_games_terminal()


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
