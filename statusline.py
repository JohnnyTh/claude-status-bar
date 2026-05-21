#!/usr/bin/env python3
"""Claude Code statusline: sparkline of cumulative token usage + cost."""
import json
import os
import sys
import tempfile

HISTORY_LEN = 12
SPARKS = " ▁▂▃▄▅▆▇█"


def sparkline(values: list[int]) -> str:
    if not values or max(values) == 0:
        return " " * len(values)
    lo, hi = min(values), max(values)
    span = hi - lo or 1
    return "".join(SPARKS[round((v - lo) / span * (len(SPARKS) - 1))] for v in values)


def fmt_tokens(n: int) -> str:
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}k"
    return str(n)


def main() -> None:
    data = json.load(sys.stdin)

    session_id = data.get("session_id", "unknown")
    ctx = data.get("context_window", {})
    cost = data.get("cost", {})

    used_pct = ctx.get("used_percentage") or 0
    usage = ctx.get("current_usage") or {}
    # sum all token categories for a total "tokens in this turn"
    total_tokens = (
        (usage.get("input_tokens") or 0)
        + (usage.get("cache_read_input_tokens") or 0)
        + (usage.get("cache_creation_input_tokens") or 0)
    )
    cumulative_tokens = (
        (ctx.get("total_input_tokens") or 0)
    )
    total_cost = cost.get("total_cost_usd") or 0.0

    # persist history keyed by session
    history_file = os.path.join(tempfile.gettempdir(), f"claude-tokens-{session_id}.tsv")
    history: list[int] = []
    if os.path.exists(history_file):
        with open(history_file) as f:
            history = [int(line.strip()) for line in f if line.strip().isdigit()]
    history.append(cumulative_tokens)
    history = history[-HISTORY_LEN:]
    with open(history_file, "w") as f:
        f.write("\n".join(str(v) for v in history))

    spark = sparkline(history)
    bar_len = 10
    filled = round(used_pct / 100 * bar_len)
    bar = "█" * filled + "░" * (bar_len - filled)

    cost_str = f"${total_cost:.3f}" if total_cost >= 0.001 else f"${total_cost:.5f}"
    tokens_str = fmt_tokens(cumulative_tokens)

    print(f"[{bar}] {used_pct:.0f}% {spark} {tokens_str} {cost_str}")


if __name__ == "__main__":
    main()
