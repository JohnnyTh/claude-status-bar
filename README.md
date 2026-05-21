# claude-statusline

A [Claude Code](https://claude.ai/code) statusline script that shows a context window bar, cumulative token sparkline, and running session cost.

```
[████░░░░░░] 42% ▂▃▅▆█ 38.2k $0.123
```

- **Block bar** — how full the context window is right now
- **Sparkline** — token growth curve across the last 12 snapshots this session
- **Token count** — cumulative input tokens (including cache reads)
- **Cost** — running USD total for the session

## Requirements

- Python 3.9+
- Claude Code CLI

## Installation

1. Copy `statusline.py` to `~/.claude/`:

```bash
curl -o ~/.claude/statusline.py \
  https://raw.githubusercontent.com/JohnnyTh/claude-status-bar/main/statusline.py
chmod +x ~/.claude/statusline.py
```

2. Add the following to `~/.claude/settings.json`:

```json
{
  "statusLine": {
    "type": "command",
    "command": "python3 ~/.claude/statusline.py"
  }
}
```

If you already have a `statusLine` entry, replace it. The file is at `~/.claude/settings.json` — this location is shared across all your projects.

## How it works

Each time Claude Code updates the statusline it pipes a JSON blob to the script's stdin. The script reads:

- `context_window.used_percentage` — for the bar
- `context_window.total_input_tokens` — for cumulative count and sparkline
- `cost.total_cost_usd` — for the cost display

Token history is persisted to `/tmp/claude-tokens-<session_id>.tsv` so the sparkline survives across multiple statusline refreshes within one session. Each new session starts fresh. Temp files are cleaned up automatically on reboot.

## Customization

| Constant | Default | Description |
|----------|---------|-------------|
| `HISTORY_LEN` | `12` | Number of snapshots kept for the sparkline |
| `SPARKS` | `" ▁▂▃▄▅▆▇█"` | Unicode block characters used for the sparkline |
