"""Hermes waiting games: Hermes plugin only — terminal menu each CLI turn, paused at turn end (Unix)."""
from __future__ import annotations

import os, platform, shlex, shutil, signal, subprocess
from pathlib import Path

PDIR = Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))).expanduser() / "waiting-games"
PIDF = PDIR / "menu-shell.pid"
WIN, UNIX = platform.system() == "Windows", platform.system() != "Windows"
SEEN: set[str] = set()
POP = dict(start_new_session=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
_MENU = (
    "PATH=/usr/local/bin:/opt/homebrew/bin:$PATH;while true;do echo;echo \"pick:\";"
    "select g in nethack ninvaders bastet nsnake greed cbonsai quit;do "
    "case $g in quit)exit 0;;*)command -v \"$g\">/dev/null&&\"$g\";;esac;break;done;done"
)


def _inner(rp: bool) -> str:
    if not rp:
        return _MENU
    PDIR.mkdir(parents=True, exist_ok=True)
    p, q = shlex.quote(str(PDIR)), shlex.quote(str(PIDF))
    return f"mkdir -p {p};echo $$>{q};bash -lc {shlex.quote(_MENU)}"


def _mac(inner: str) -> None:
    lit = inner.replace("\\", "\\\\").replace('"', '\\"')
    subprocess.run(
        ["osascript", "-e", f'set i to "{lit}"\nset c to "exec bash -lc " & quoted form of i\ntell application "Terminal" to do script c'],
        check=True, capture_output=True, text=True,
    )


def _linux(inner: str) -> bool:
    for cmd in (["gnome-terminal", "--", "bash", "-lc", inner], ["x-terminal-emulator", "-e", f"bash -lc {shlex.quote(inner)}"], ["xterm", "-e", "bash", "-lc", inner]):
        if shutil.which(cmd[0]):
            try:
                subprocess.Popen(cmd, **POP)
                return True
            except OSError:
                pass
    return False


def open_menu(record_pid: bool) -> str:
    inner = _inner(record_pid)
    try:
        if platform.system() == "Darwin":
            _mac(inner)
            return "Opened."
        if platform.system() == "Linux" and _linux(inner):
            return "Opened."
        if WIN and (wt := shutil.which("wt.exe") or shutil.which("wt")):
            subprocess.Popen([wt, "new-tab", "wsl", "bash", "-lc", inner], **POP)
            return "Opened (WSL)."
        return "No terminal."
    except subprocess.CalledProcessError as e:
        return str(e.stderr or e)


def _pause() -> None:
    if UNIX and PIDF.is_file():
        try:
            os.kill(-os.getpgid(int(PIDF.read_text().strip())), signal.SIGSTOP)
        except (ValueError, ProcessLookupError, PermissionError):
            PIDF.unlink(missing_ok=True)


def _resume_or_open(rp: bool) -> None:
    if not PIDF.is_file():
        open_menu(rp)
        return
    try:
        pid = int(PIDF.read_text().strip())
        os.kill(pid, 0)
        os.kill(-os.getpgid(pid), signal.SIGCONT)
    except (ValueError, ProcessLookupError):
        PIDF.unlink(missing_ok=True)
        open_menu(rp)


def register(ctx):
    def pre(sid, platform="", **k):
        if platform != "cli":
            return
        if WIN:
            if sid not in SEEN:
                SEEN.add(sid)
                open_menu(False)
            return
        _resume_or_open(True)

    def post(platform="", **k):
        if platform == "cli" and UNIX:
            _pause()

    def end(sid, **k):
        SEEN.discard(sid)
        if k.get("platform") == "cli" and UNIX:
            _pause()

    ctx.register_hook("pre_llm_call", pre)
    ctx.register_hook("post_llm_call", post)
    ctx.register_hook("on_session_end", end)
