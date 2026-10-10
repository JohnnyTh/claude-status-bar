#!/usr/bin/env python3
"""Collect per-task token usage from Claude Code transcripts into task_log.jsonl.

Read-only over ~/.claude/projects/**/*.jsonl. Idempotent: safe to re-run, and
safe to run from both SessionStart and SessionEnd hooks. Each run re-derives
every row from transcripts and rewrites the log, so rows for tasks still in
progress at the previous run get corrected; rows whose transcripts were
cleaned up are kept as-is.

See ~/.claude/USAGE_TRACKING.md for why this exists and what the fields mean.
"""
import glob
import json
import os
import sys

CLAUDE_DIR = os.path.expanduser("~/.claude")
PROJECTS = os.path.join(CLAUDE_DIR, "projects")
LOG_PATH = os.path.join(CLAUDE_DIR, "task_log.jsonl")


def iter_records(path):
    with open(path, errors="ignore") as fh:
        for line in fh:
            try:
                yield json.loads(line)
            except (ValueError, TypeError):
                continue  # partial last line while a session is live


def segment_tasks(path):
    """Yield one dict per task. A task starts at a user record with
    promptSource == 'typed' (a real human prompt) and runs until the next one.
    Tool-result user records have promptSource None, so they don't split tasks.
    """
    cur = None
    project = None
    for d in iter_records(path):
        # cwd is authoritative for the repo name; the dir name is a mangled path
        if project is None and d.get("cwd"):
            project = os.path.basename(d["cwd"])
        if d.get("type") == "user" and d.get("promptSource") == "typed":
            if cur:
                cur["project"] = project
                yield cur
            uuid = d.get("uuid")
            start = d.get("timestamp") or ""
            cur = {
                "task_id": f"{d.get('sessionId') or d.get('session_id')}:{uuid}",
                "date": (d.get("timestamp") or "")[:10],
                "session": d.get("sessionId") or d.get("session_id"),
                "project": None,  # filled in at yield time from cwd
                "branch": d.get("gitBranch"),
                "effort": None,  # filled from the task's assistant records
                "models": set(),
                "api_calls": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "cache_read": 0,
                "cache_creation": 0,
                "sidechain_calls": 0,
                "duration_ms": 0,
                # subagent transcripts live in <session>/subagents/, attributed below
                "sub_models": set(),
                "sub_input_tokens": 0,
                "sub_output_tokens": 0,
                "sub_cache_read": 0,
                "sub_cache_creation": 0,
                "_start": start,
            }
            continue
        if cur is None:
            continue  # records before the first typed prompt (session preamble)
        # durationMs rides on 'system' turn_duration records, which carry no usage
        if d.get("durationMs") is not None:
            cur["duration_ms"] += d["durationMs"]
        msg = d.get("message") or {}
        usage = msg.get("usage")
        if not usage:
            continue
        # effort is on assistant records, not on the typed user record
        if d.get("effort") and not cur["effort"]:
            cur["effort"] = d["effort"]
        cur["api_calls"] += 1
        cur["input_tokens"] += usage.get("input_tokens") or 0
        cur["output_tokens"] += usage.get("output_tokens") or 0
        cur["cache_read"] += usage.get("cache_read_input_tokens") or 0
        cur["cache_creation"] += usage.get("cache_creation_input_tokens") or 0
        if d.get("isSidechain"):
            cur["sidechain_calls"] += 1
        if msg.get("model"):
            cur["models"].add(msg["model"])
    if cur:
        cur["project"] = project
        yield cur


def add_subagents(path, tasks):
    """Fold <session>/subagents/*.jsonl usage into the task that spawned it:
    the last task whose typed prompt precedes the subagent's first record.
    """
    sub_dir = os.path.join(path[:-len(".jsonl")], "subagents")
    for sub in glob.glob(os.path.join(sub_dir, "*.jsonl")):
        task = None
        for d in iter_records(sub):
            if task is None:
                ts = d.get("timestamp") or ""
                before = [t for t in tasks if t["_start"] <= ts]
                task = before[-1] if before else (tasks[0] if tasks else None)
                if task is None:
                    break
            msg = d.get("message") or {}
            usage = msg.get("usage")
            if not usage:
                continue
            task["sidechain_calls"] += 1
            task["sub_input_tokens"] += usage.get("input_tokens") or 0
            task["sub_output_tokens"] += usage.get("output_tokens") or 0
            task["sub_cache_read"] += usage.get("cache_read_input_tokens") or 0
            task["sub_cache_creation"] += usage.get("cache_creation_input_tokens") or 0
            if msg.get("model"):
                task["sub_models"].add(msg["model"])


def main():
    old = {d["task_id"]: d for d in iter_records(LOG_PATH) if d.get("task_id")} \
        if os.path.exists(LOG_PATH) else {}
    merged = dict(old)  # never drop a row, even if its transcript is gone
    for path in glob.glob(os.path.join(PROJECTS, "*", "*.jsonl")):
        tasks = list(segment_tasks(path))
        add_subagents(path, tasks)
        for task in tasks:
            if not task["api_calls"]:
                continue
            del task["_start"]
            task["models"] = sorted(task["models"])
            task["sub_models"] = sorted(task["sub_models"])
            merged[task["task_id"]] = task

    rows = sorted(merged.values(), key=lambda r: r["date"])
    tmp = LOG_PATH + ".tmp"
    with open(tmp, "w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    os.replace(tmp, LOG_PATH)  # atomic: concurrent hook runs can't interleave
    added = len(merged) - len(old)
    if added:
        print(f"collect_usage: +{added} tasks -> {LOG_PATH}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 - a hook must never break the session
        print(f"collect_usage: {exc}", file=sys.stderr)
        sys.exit(0)
