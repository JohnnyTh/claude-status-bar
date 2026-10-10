# claude-usage

Local usage and cost tracking for [Claude Code](https://claude.ai/code): a
statusline that shows live session cost, plus a collector and report that
break spend down **per task** so you can compare models, effort levels, and
session length on cost per unit of work. Nothing leaves your machine.

| File | Role |
|---|---|
| `statusline.py` | Statusline: session context %, tokens, cost, global spend, and a 20-tier cyberpunk XP bar. Records each session's real cost to `~/.claude/statusline_stats.json`. |
| `collect_usage.py` | Parses Claude Code transcripts (incl. subagents) into one row per task in `~/.claude/task_log.jsonl`. Run from hooks. |
| `usage_report.py` | Prints per-day, per-model, and per-complexity tables with real $/task. |
| `test_statusline.py` | Statusline tests. |
| `USAGE_TRACKING.md` | Design notes: data sources, field meanings, parsing gotchas. |

The report's dollar figures come from the statusline's cost records, so use
both together.

## Requirements

Python 3.10+, Claude Code CLI. No third-party packages.

## Install

Clone into `~/.claude` and symlink the scripts, so edits in the repo take
effect immediately:

```sh
git clone git@github.com:JohnnyTh/claude-status-bar.git ~/.claude/claude-usage
cd ~/.claude
for f in statusline.py collect_usage.py usage_report.py test_statusline.py USAGE_TRACKING.md; do
  ln -sf claude-usage/$f $f
done
cp claude-usage/statusline_config.json.example statusline_config.json  # optional
```

Add to `~/.claude/settings.json`:

```json
{
  "cleanupPeriodDays": 365,
  "statusLine": { "type": "command", "command": "python3 ~/.claude/statusline.py" },
  "hooks": {
    "SessionStart": [{ "hooks": [{ "type": "command", "command": "python3 ~/.claude/collect_usage.py" }] }],
    "SessionEnd":   [{ "hooks": [{ "type": "command", "command": "python3 ~/.claude/collect_usage.py" }] }]
  }
}
```

`cleanupPeriodDays` keeps transcripts longer than the default 30 days, so the
collector can re-derive history if its parsing changes.

## Usage

```sh
python3 ~/.claude/usage_report.py           # full report
python3 ~/.claude/usage_report.py --days 7  # last 7 active days
python3 ~/.claude/test_statusline.py        # run statusline tests
```

## Data files (in `~/.claude`, never committed)

- `task_log.jsonl`: one row per task (tokens, calls, models, project, branch).
- `statusline_stats.json`: per-session real cost and global statusline state.

Both contain project names, branch names, and session IDs; `.gitignore`
excludes them in case they're ever copied here.
