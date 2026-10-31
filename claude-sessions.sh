#!/usr/bin/env bash
# Move Claude Code sessions and memory between this repo and ~/.claude.
#   ./claude-sessions.sh save      copy ~/.claude data for this project into the repo
#   ./claude-sessions.sh restore   copy the repo's sessions into ~/.claude on this machine
# Claude Code files a project's sessions under its absolute path, so the
# folder name is worked out here from wherever this repo is checked out.
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
store="$repo/claude-sessions"
live="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/projects/$(printf '%s' "$repo" | sed 's/[^a-zA-Z0-9]/-/g')"

case "${1:-}" in
  save)
    [ -d "$live" ] || { echo "No Claude data at $live" >&2; exit 1; }
    mkdir -p "$store"
    cp -a "$live/." "$store/"
    echo "Saved $live -> $store"
    ;;
  restore)
    [ -d "$store" ] || { echo "No saved sessions at $store" >&2; exit 1; }
    mkdir -p "$live"
    # --update keeps anything newer already on this machine.
    cp -a --update "$store/." "$live/"
    echo "Restored $store -> $live"
    ;;
  *)
    echo "Usage: $0 save|restore" >&2
    exit 2
    ;;
esac
