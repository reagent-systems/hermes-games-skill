#!/usr/bin/env bash
# Terminal games picker — lists binaries found on PATH or bundled in ../../bin.
set -u

MENU_TITLE="Waiting games (Hermes)"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUNDLED_BIN_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)/bin"

# Detect platform → bundled bin subdir.
ARCH_DIR=""
case "$(uname -s)" in
  Linux)
    case "$(uname -m)" in
      x86_64|amd64) ARCH_DIR="linux-amd64" ;;
      aarch64|arm64) ARCH_DIR="linux-arm64" ;;
    esac
    ;;
  Darwin)
    case "$(uname -m)" in
      x86_64|amd64) ARCH_DIR="darwin-amd64" ;;
      arm64) ARCH_DIR="darwin-arm64" ;;
    esac
    ;;
  MINGW*|MSYS*|CYGWIN*) ARCH_DIR="windows-amd64" ;;
esac

# register adds an entry if the binary is on PATH or bundled for this platform.
register() {
  local label="$1" bin="$2"
  if command -v "$bin" >/dev/null 2>&1; then
    LABELS+=("$label")
    BINS+=("$bin")
    return
  fi
  if [[ -n "$ARCH_DIR" ]]; then
    local bundled="$BUNDLED_BIN_ROOT/$ARCH_DIR/$bin"
    [[ "$ARCH_DIR" == "windows-amd64" ]] && bundled="${bundled}.exe"
    if [[ -x "$bundled" || -f "$bundled" ]]; then
      LABELS+=("$label")
      BINS+=("$bundled")
    fi
  fi
}

LABELS=()
BINS=()

# Write our PID so Hermes hooks can SIGSTOP/SIGCONT us
echo $$ > /tmp/hermes_games_menu.pid
trap 'rm -f /tmp/hermes_games_menu.pid' EXIT

register "Tron lightcycles" "tron"
register "NetHack" "nethack"
register "Dungeon Crawl (crawl)" "crawl"
register "nInvaders" "ninvaders"
register "Bastet" "bastet"
register "nSnake" "nsnake"
register "nudoku" "nudoku"
register "Curse of War" "curseofwar"
register "Vitetris" "vitetris"
register "BSD Tetris" "tetris-bsd"
register "BSD Snake" "snake"
register "Greed" "greed"
register "Robot finds kitten" "robotfindskitten"
register "2048" "2048"
register "term2048" "term2048"
register "cbonsai" "cbonsai"

if [[ ${#BINS[@]} -eq 0 ]]; then
  echo "No known terminal games found on PATH."
  echo "Install one (e.g. brew install ninvaders) and run this script again."
  read -r -p "Press Enter to close…"
  exit 0
fi

while true; do
  clear 2>/dev/null || true
  echo "$MENU_TITLE"
  echo "────────────────────────────────────"
  i=1
  for label in "${LABELS[@]}"; do
    echo "  $i) $label"
    i=$((i + 1))
  done
  echo "  q) Quit menu"
  echo ""
  read -r -p "Choice: " choice
  choice="${choice:-}"

  if [[ "$choice" == "q" || "$choice" == "Q" ]]; then
    echo "Bye."
    break
  fi

  if ! [[ "$choice" =~ ^[0-9]+$ ]]; then
    echo "Invalid."
    sleep 1
    continue
  fi

  idx=$((choice - 1))
  if (( idx < 0 || idx >= ${#BINS[@]} )); then
    echo "Out of range."
    sleep 1
    continue
  fi

  game="${BINS[$idx]}"
  "$game" || true
  echo ""
  read -r -p "Game exited. Press Enter to return to menu…"
done
