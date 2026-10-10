# Claude Code usage tracking

Local, per-task token accounting for Claude Code. Nothing leaves this machine.
Scripts live in this repo and are symlinked into `~/.claude/`; all data files
stay in `~/.claude/` and are never committed.

## Why this exists

Daily spend totals can't tell a *busy* day from an *expensive* one: 34 tasks
at $0.68 and 10 tasks at $2.09 add up to similar totals, but the second day
cost 3× more per unit of work. This tooling records usage **per task** (one
typed prompt plus its whole agent loop) so cost can be normalized by work
done, and compared across models, effort levels, and session length.

It also keeps a durable record: Claude Code deletes transcripts after
`cleanupPeriodDays` (default 30), and `task_log.jsonl` survives that.

## Files

| Path | What it is |
|---|---|
| `collect_usage.py` | Parses transcripts → rewrites per-task rows. Idempotent, read-only on transcripts. |
| `task_log.jsonl` | The durable record. Rewritten each collection run; rows survive transcript cleanup. |
| `usage_report.py` | Prints normalized tables from `task_log.jsonl`. |
| `statusline.py` | Statusline; also records real cost, `model_id` and last per-call usage per session. |
| `test_statusline.py` | Tests for the statusline (`python3 test_statusline.py`). |
| `statusline_stats.json` | Per-session real cost, written by the statusline. |

## Usage

```sh
python3 ~/.claude/collect_usage.py        # collect (runs automatically via hooks)
python3 ~/.claude/usage_report.py         # full report
python3 ~/.claude/usage_report.py --days 7
```

Report columns: `out/task`, `cacheR/task`, `calls/task` are the normalizations —
per-task, so busy days don't masquerade as expensive ones. `ctx/call` is mean
context size, the direct measure of context bloat. The **BY COMPLEXITY** table
buckets tasks by `api_calls` before comparing models, so a model handed harder
tasks isn't unfairly penalized.

## `task_log.jsonl` fields

One line per task. A "task" is one typed prompt plus its entire completion loop.

| Field | Unit | Source |
|---|---|---|
| `task_id` | `session:uuid` | dedup key; makes re-runs idempotent |
| `date` | `YYYY-MM-DD` | timestamp of the typed prompt |
| `session` | uuid | join key to `statusline_stats.json` for cost |
| `project` | name | basename of the record's `cwd` |
| `branch` | git branch | `gitBranch` |
| `effort` | `low`/`medium`/… | `effort` on assistant records |
| `models` | list | a task can span models if switched mid-task |
| `api_calls` | count | usage-bearing records = loop length; **main complexity proxy** |
| `input_tokens` | tokens | `usage.input_tokens`, summed |
| `output_tokens` | tokens | `usage.output_tokens`, summed |
| `cache_read` | tokens | `usage.cache_read_input_tokens` — usually the bulk of tokens moved |
| `cache_creation` | tokens | `usage.cache_creation_input_tokens` |
| `sidechain_calls` | count | usage-bearing records in the task's subagent transcripts |
| `sub_models` | list | models the task's subagents ran on |
| `sub_input_tokens`, `sub_output_tokens`, `sub_cache_read`, `sub_cache_creation` | tokens | same as the main fields, summed over subagent transcripts; **not** included in the main fields |
| `duration_ms` | ms | `durationMs` on `system` records |

Cache tokens are tracked separately from `input_tokens` because they are priced
differently — cache reads are ~10× cheaper than fresh input, and they dominate
the bill purely by volume.

## Data sources and their limits

Neither source alone is sufficient:

- **Transcripts** (`~/.claude/projects/**/*.jsonl`) — the only place tasks can be
  delimited, and they carry the full token split. **No cost data.**
- **Statusline payload** — the only place real billed cost
  (`cost.total_cost_usd`) is observable. But `current_usage` is per-API-call with
  **no task attribution**, so it cannot be grouped into tasks.

A session's real cost is `cost_base + last_cost_usd`: the statusline banks the
previous total into `cost_base` when the CLI's cost counter restarts under the
same `session_id` (e.g. a resume in a new process). The statusline also holds an `flock` on
`statusline_stats.json.lock` so concurrent sessions don't overwrite each
other's updates.

They join on `session_id`. **`$/task` is a session's real cost split across
its tasks in proportion to each task's list-rate token cost** (main +
subagent tokens): exact per session, approximate per task. Splitting per task
(not per day) means a session spanning several days is counted once.

> **Per-token rates may not be observable.** Behind an API proxy
> (`ANTHROPIC_BASE_URL`) with non-public pricing, only the per-session total
> is known. The report uses public list rates solely for *relative* weights
> (splitting a session's cost across tasks, and the token-type % split), then
> rescales to real dollars. Its "PROXY vs LIST PRICE" table shows the
> real/list ratio per model, which also reveals price changes over time.

## Parsing gotchas

These cost real time to discover. Don't rediscover them.

- **`promptId` is useless for task segmentation.** It appears only on metadata
  records, never on the assistant messages carrying `usage` — in one sample file
  all 102 usage records were orphans. Segment on
  **`type == "user" and promptSource == "typed"`** instead: that marks a genuine
  human prompt, while tool-result user records have `promptSource: None`.
- **`usage.iterations` is a list, not an int.** Summing it raises `TypeError`.
- `durationMs` lives on `system` records (which have no `usage`), and `effort`
  lives on `assistant` records — neither is on the typed user record.
- **Subagents write separate transcripts** at
  `projects/<proj>/<session>/subagents/agent-*.jsonl` (plus a `.meta.json`),
  not into the session file — a `projects/*/*.jsonl` glob misses them (~10% of
  tokens). Each subagent file is attributed to the last task whose typed prompt
  precedes the subagent's first record.
- `/clear` does **not** start a new transcript file, and `local_command` records
  store only `<local-command-stdout>` with no command name, so `/clear` is
  invisible in the data. Irrelevant here, since segmentation keys off
  `promptSource`.

## Operational notes

**Hooks** (in `settings.json`, global so it runs for every project):

- `SessionEnd` — collects the session that just finished, no lag. Not guaranteed
  to fire on crash or `kill -9`.
- `SessionStart` — the catch-up for whatever `SessionEnd` missed.

**No exit path loses data.** Transcripts are written incrementally, per record,
while the session runs — not flushed at exit. Verified by watching a live session's file grow
between two commands, with the latest assistant record and its usage already
on disk. So `/clear`, Ctrl+C, and `kill -9` are all
safe; the hooks only control *when* collection happens, never *whether* the data
exists. Worst case (Ctrl+C): tasks land at the next SessionStart.

The collector re-derives every row from transcripts on each run and rewrites
the log atomically (tmp file + `os.replace`), keeping old rows whose
transcripts are gone. This is idempotent, safe when both hooks fire at once,
and corrects rows that were collected while their task was still running. (An
earlier append-only version raced between concurrent hooks and wrote
duplicate rows.) A run takes a couple of seconds.

**Retention:** `cleanupPeriodDays: 365` (default is 30). Expect several hundred MB of
transcripts per year of heavy use. Keeping raw
transcripts matters because the parsing logic can be re-run if it needs fixing
or a field not currently extracted is wanted later — `task_log.jsonl` only holds
what the parser thought to save.
