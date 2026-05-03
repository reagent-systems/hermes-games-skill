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
import shutil
import signal
import subprocess
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# Windows has no SIGSTOP/SIGCONT — translate to PowerShell cmdlets in
# _signal_pgrp. The numeric sentinels here are arbitrary; they only need
# to be unique and stable across this module.
SIGSTOP = getattr(signal, "SIGSTOP", -19)
SIGCONT = getattr(signal, "SIGCONT", -18)


# /tmp/hermes_games_menu.pid is also referenced by ~/.claude/settings.json
# hooks (Claude Code path). Keeping the same path means both runtimes
# coordinate on the same game instance. On Windows, Git Bash maps /tmp
# to %TEMP% via fstab, but Python's Path("/tmp/...") on Windows resolves
# to C:\tmp\... — different file. We anchor at %TEMP% explicitly so the
# bash side and the python side actually see the same physical file.
if platform.system() == "Windows":
    _PID_DIR = Path(
        os.environ.get("TEMP") or os.environ.get("TMP") or r"C:\Windows\Temp"
    )
else:
    _PID_DIR = Path("/tmp")
PID_FILE = _PID_DIR / "hermes_games_menu.pid"
# Sidecar file for the terminal emulator (mintty) PID — needed for window
# focus across Hermes restarts. The main PID_FILE format is shared with
# Claude Code hooks so we keep that as a single int and put auxiliary
# state in this separate file.
TERMINAL_PID_FILE = _PID_DIR / "hermes_games_terminal.pid"

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
    ("Windows", "AMD64"): "windows-amd64",
}.get((platform.system(), platform.machine()), "darwin-arm64")
_TRON_NAME = "tron.exe" if platform.system() == "Windows" else "tron"
TRON_BIN = _REPO_ROOT / "bin" / _ARCH_DIR / _TRON_NAME


# ---------- pid + signal helpers ----------

def _is_alive(pid: int) -> bool:
    """Cross-platform liveness probe (Windows os.kill is destructive — never use sig=0)."""
    if platform.system() == "Windows":
        try:
            out = subprocess.check_output(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                text=True, stderr=subprocess.DEVNULL,
            )
            return str(pid) in out
        except (subprocess.CalledProcessError, OSError):
            return False
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def _read_pid() -> int | None:
    """Return the live pid from PID_FILE, or None if missing/stale/dead."""
    try:
        pid = int(PID_FILE.read_text().strip())
    except (FileNotFoundError, ValueError):
        return None
    return pid if _is_alive(pid) else None


def _signal_pgrp(pid: int, sig) -> bool:
    """Send sig to pid's process group; fall back to single pid. Best-effort.

    On Windows, SIGSTOP/SIGCONT don't exist as signals. We use direct
    ctypes calls to ``NtSuspendProcess`` / ``NtResumeProcess`` from
    ntdll, check the NTSTATUS return code, AND verify suspension state
    via NtQueryInformationProcess so we catch silent failures.
    """
    if platform.system() == "Windows":
        try:
            import ctypes
            from ctypes import wintypes
            PROCESS_SUSPEND_RESUME = 0x0800
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            kernel32 = ctypes.windll.kernel32
            ntdll = ctypes.windll.ntdll
            kernel32.OpenProcess.restype = wintypes.HANDLE
            kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
            ntdll.NtSuspendProcess.argtypes = [wintypes.HANDLE]
            ntdll.NtSuspendProcess.restype = wintypes.LONG
            ntdll.NtResumeProcess.argtypes = [wintypes.HANDLE]
            ntdll.NtResumeProcess.restype = wintypes.LONG

            handle = kernel32.OpenProcess(
                PROCESS_SUSPEND_RESUME | PROCESS_QUERY_LIMITED_INFORMATION,
                False, pid,
            )
            if not handle:
                err = ctypes.get_last_error()
                logger.warning("waiting-games: OpenProcess(%d) failed err=%d", pid, err)
                return False
            try:
                if sig == SIGSTOP:
                    rc = ntdll.NtSuspendProcess(handle)
                    if rc != 0:
                        logger.warning("waiting-games: NtSuspendProcess rc=%#x", rc & 0xFFFFFFFF)
                        return False
                elif sig == SIGCONT:
                    rc = ntdll.NtResumeProcess(handle)
                    if rc != 0:
                        logger.warning("waiting-games: NtResumeProcess rc=%#x", rc & 0xFFFFFFFF)
                        return False
                else:
                    return False

                # Verify the actual suspension state — count how many threads
                # of this process are in the "Wait:Suspended" state.
                suspended_threads = _count_suspended_threads(pid)
                logger.info(
                    "waiting-games: after %s pid=%d, suspended-threads=%s",
                    "SIGSTOP" if sig == SIGSTOP else "SIGCONT",
                    pid, suspended_threads,
                )
                return True
            finally:
                kernel32.CloseHandle(handle)
        except OSError as exc:
            logger.warning("waiting-games: ctypes signal failed: %s", exc)
            return False
    try:
        os.killpg(os.getpgid(pid), sig)
        return True
    except (ProcessLookupError, PermissionError):
        try:
            os.kill(pid, sig)
            return True
        except (ProcessLookupError, PermissionError):
            return False


def _count_suspended_threads(pid: int) -> int | str:
    """Count threads of pid currently in WaitReason=Suspended via PowerShell.

    Returns an int count, or a string error marker so we can log silent failures
    without raising. Tools like Process Explorer use the same WaitReason field.
    """
    try:
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             f"@(Get-CimInstance Win32_Thread -Filter \"ProcessHandle={pid}\" | "
             f"Where-Object {{ $_.ThreadWaitReason -eq 5 }}).Count"],
            text=True, stderr=subprocess.DEVNULL, timeout=4,
        )
        return int(out.strip())
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError, OSError) as exc:
        return f"err:{type(exc).__name__}"


# ---------- tron launcher ----------

def _find_tron_pid_windows() -> int | None:
    """Return the PID of a running tron.exe (newest if multiple)."""
    try:
        out = subprocess.check_output(
            ["tasklist", "/FI", "IMAGENAME eq tron.exe", "/NH"],
            text=True, stderr=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, OSError):
        return None
    pids = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].lower() == "tron.exe":
            try:
                pids.append(int(parts[1]))
            except ValueError:
                continue
    return max(pids) if pids else None


def _launch_tron_windows() -> None:
    """Open mintty hosting tron directly. Python captures tron's pid by name.

    MSYS bash's ``exec`` doesn't replace the process the way POSIX exec does,
    so we can't rely on ``echo $$`` capturing tron's pid. Instead, we spawn
    mintty → tron with no shell in between and look up tron's pid via tasklist.
    """
    mintty = r"C:\Program Files\Git\usr\bin\mintty.exe"
    if not os.path.isfile(mintty):
        logger.debug("waiting-games: mintty not found at %s", mintty)
        return

    try:
        proc = subprocess.Popen(
            [mintty, "-h", "always", "--", str(TRON_BIN)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        logger.debug("waiting-games: mintty spawn failed: %s", exc)
        return
    try:
        TERMINAL_PID_FILE.write_text(str(proc.pid))
    except OSError as exc:
        logger.debug("waiting-games: failed to write terminal pid file: %s", exc)

    # Wait for tron.exe to appear, then record its pid.
    for _ in range(40):  # up to ~2s
        time.sleep(0.05)
        pid = _find_tron_pid_windows()
        if pid is not None:
            try:
                PID_FILE.write_text(str(pid))
            except OSError as exc:
                logger.debug("waiting-games: failed to write pid file: %s", exc)
            return
    logger.debug("waiting-games: tron.exe didn't appear within 2s of spawn")


def _launch_tron() -> None:
    """Open a new Terminal/mintty window running tron; write its shell pid to PID_FILE."""
    if not TRON_BIN.exists():
        logger.debug("waiting-games: tron binary missing at %s", TRON_BIN)
        return

    system = platform.system()
    if system == "Windows":
        _launch_tron_windows()
        return
    if system != "Darwin":
        logger.debug("waiting-games: %s not implemented", system)
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

def _read_terminal_pid() -> int | None:
    """Return mintty's pid (recorded at launch), or None if file missing/dead."""
    try:
        pid = int(TERMINAL_PID_FILE.read_text().strip())
    except (FileNotFoundError, ValueError):
        return None
    return pid if _is_alive(pid) else None


def _focus_terminal_window() -> None:
    """Best-effort: bring the mintty/Terminal window hosting tron to the front.

    Reads the recorded mintty pid from disk so the focus call works even
    after Hermes restarts (when the in-process state is lost). Uses the
    AttachThreadInput trick to bypass focus-stealing prevention when we
    aren't already the foreground process.
    """
    if platform.system() != "Windows":
        return
    term_pid = _read_terminal_pid()
    if term_pid is None:
        logger.info("waiting-games: focus skipped — no terminal pid")
        return
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        EnumWindowsProc = ctypes.WINFUNCTYPE(
            wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
        )
        target_hwnd: list[int] = []

        def _enum(hwnd, _lparam):
            owner = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
            if owner.value == term_pid and user32.IsWindowVisible(hwnd):
                target_hwnd.append(hwnd)
                return False
            return True

        user32.EnumWindows(EnumWindowsProc(_enum), 0)
        if not target_hwnd:
            logger.info("waiting-games: focus — no visible window for term pid %d", term_pid)
            return
        hwnd = target_hwnd[0]

        # Restore-if-minimized + bring-to-foreground.
        SW_RESTORE = 9
        user32.ShowWindow(hwnd, SW_RESTORE)

        # Defeat focus-stealing prevention: attach our input to the
        # foreground window's thread momentarily, set foreground, detach.
        # This is the standard workaround used by Spy++ etc.
        cur_thread = kernel32.GetCurrentThreadId()
        fg_hwnd = user32.GetForegroundWindow()
        fg_thread = user32.GetWindowThreadProcessId(fg_hwnd, None) if fg_hwnd else 0
        attached = False
        if fg_thread and fg_thread != cur_thread:
            attached = bool(user32.AttachThreadInput(cur_thread, fg_thread, True))
        ok = bool(user32.SetForegroundWindow(hwnd))
        user32.BringWindowToTop(hwnd)
        if attached:
            user32.AttachThreadInput(cur_thread, fg_thread, False)
        logger.info(
            "waiting-games: focus hwnd=%d term_pid=%d ok=%s attached=%s",
            hwnd, term_pid, ok, attached,
        )
    except OSError as exc:
        logger.warning("waiting-games: focus failed: %s", exc)


def _on_pre_llm_call(**kwargs) -> None:
    """User is about to wait — resume the existing game, or launch a fresh one."""
    plat = kwargs.get("platform")
    logger.info("waiting-games: pre_llm_call fired (platform=%r)", plat)
    if plat != "cli":
        return
    pid = _read_pid()
    if pid is None:
        logger.info("waiting-games: no live pid → launching tron")
        PID_FILE.unlink(missing_ok=True)
        _launch_tron()
        _focus_terminal_window()
        return
    ok = _signal_pgrp(pid, SIGCONT)
    logger.info("waiting-games: SIGCONT pid=%d -> %s", pid, ok)
    _focus_terminal_window()


def _on_session_end(**kwargs) -> None:
    """Pause tron at the very end of every run_conversation call.

    Fires unconditionally — Hermes invokes this hook regardless of
    whether the turn completed successfully, errored, was interrupted,
    or hit max iterations. ``post_llm_call`` is gated behind
    ``if final_response and not interrupted`` (run_agent.py:13745) so
    it skips error paths; ``on_session_end`` doesn't.
    """
    plat = kwargs.get("platform")
    completed = kwargs.get("completed")
    interrupted = kwargs.get("interrupted")
    logger.info(
        "waiting-games: on_session_end fired (platform=%r completed=%s interrupted=%s)",
        plat, completed, interrupted,
    )
    if plat != "cli":
        return
    # Fresh launches need a beat for the inner shell to write its pid.
    for _ in range(20):  # up to ~1s
        pid = _read_pid()
        if pid is not None:
            ok = _signal_pgrp(pid, SIGSTOP)
            logger.info("waiting-games: SIGSTOP pid=%d -> %s", pid, ok)
            return
        time.sleep(0.05)
    logger.info("waiting-games: on_session_end gave up — no live pid")


def register(ctx) -> None:
    ctx.register_hook("pre_llm_call", _on_pre_llm_call)
    ctx.register_hook("on_session_end", _on_session_end)
