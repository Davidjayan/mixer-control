# mixer-control

Claude Code setup for running the church's Soundcraft Ui mixer (192.168.0.133).

- `.claude/skills/soundcraft-ui-worship-mix/` - the mixing skill and `ui_mixer.py`
- `.mixer-backups/` - mixer state snapshots
- `.playwright-mcp/` - screenshots and captures from mixing sessions
- `claude-sessions/` - Claude Code transcripts and memory

This repo holds full session transcripts. Keep it private.

## Set up on another computer

```bash
git clone git@github.com:Davidjayan/mixer-control.git
cd mixer-control
./claude-sessions.sh restore
pip install websockets
claude --resume
```

The computer must be on the same network as the mixer. If you also want the
browser mixer UI, add the Playwright MCP server there:
`claude mcp add playwright -- npx @playwright/mcp@latest`

## Keep sessions up to date

Before committing, copy the latest sessions into the repo:

```bash
./claude-sessions.sh save
git add -A && git commit -m "Update Claude sessions" && git push
```

On the other computer, `git pull` and then `./claude-sessions.sh restore`.
