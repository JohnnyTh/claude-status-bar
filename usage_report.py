#!/usr/bin/env python3
"""Report normalized per-task token usage from task_log.jsonl.

Usage:  python3 ~/.claude/usage_report.py [--days N]

See ~/.claude/USAGE_TRACKING.md for field meanings and caveats.
"""
import collections
import json
import os
import statistics as st
import sys

CLAUDE_DIR = os.path.expanduser("~/.claude")
LOG_PATH = os.path.join(CLAUDE_DIR, "task_log.jsonl")
STATS_PATH = os.path.join(CLAUDE_DIR, "statusline_stats.json")

# Public Anthropic list prices, $/MTok: (input, cache_write, cache_read, output).
# ballpark only -- proxy rates aren't public (see USAGE_TRACKING.md). cache_write
# assumes the default 5m TTL (1.25x input); cache_read is ~0.1x input.
# ponytail: hardcoded table, update when models.md prices change
RATES = {
    "claude-opus-5": (5.00, 6.25, 0.50, 25.00),
    "claude-opus-4-8": (5.00, 6.25, 0.50, 25.00),
    "claude-opus-4-7": (5.00, 6.25, 0.50, 25.00),
    "claude-opus-4-6": (5.00, 6.25, 0.50, 25.00),
    "claude-opus-4-5": (5.00, 6.25, 0.50, 25.00),
    "claude-sonnet-5": (3.00, 3.75, 0.30, 15.00),
    "claude-sonnet-4-6": (3.00, 3.75, 0.30, 15.00),
    "claude-sonnet-4-5": (3.00, 3.75, 0.30, 15.00),
    "claude-haiku-4-5": (1.00, 1.25, 0.10, 5.00),
    "claude-fable-5": (10.00, 12.50, 1.00, 50.00),
    "claude-mythos-5": (10.00, 12.50, 1.00, 50.00),
}
DEFAULT_RATE = RATES["claude-sonnet-5"]  # fallback for unlisted/future models


def rate_for(model_ids):
    for m in model_ids:
        for key, r in RATES.items():
            if key.replace("claude-", "") in m:
                return r
    return DEFAULT_RATE


def task_cost_breakdown(row):
    """Estimated $ split by token type, using public list rates. Not real billing.
    Subagent tokens are priced at the subagent's own model rate."""
    out = {}
    for prefix, models in (("", row.get("models")), ("sub_", row.get("sub_models"))):
        r_in, r_cw, r_cr, r_out = rate_for(models or [])
        for k, field, rate in (("input", "input_tokens", r_in),
                               ("cache_write", "cache_creation", r_cw),
                               ("cache_read", "cache_read", r_cr),
                               ("output", "output_tokens", r_out)):
            out[k] = out.get(k, 0.0) + (row.get(prefix + field) or 0) * rate / 1e6
    return out


def allocate_real_cost(rows, costs):
    """Set row['real']: the session's real cost split across its tasks in
    proportion to each task's estimated cost (None if the session has no cost).
    Splitting per task, not per day, means a session spanning days is counted once.
    """
    by_sess = collections.defaultdict(list)
    for r in rows:
        r["est"] = sum(task_cost_breakdown(r).values())
        by_sess[r["session"]].append(r)
    for sess, v in by_sess.items():
        c = costs.get(sess)
        total = sum(x["est"] for x in v)
        for x in v:
            x["real"] = c * (x["est"] / total if total else 1 / len(v)) if c else None


def load():
    if not os.path.exists(LOG_PATH):
        sys.exit(f"no {LOG_PATH} yet - run collect_usage.py first")
    rows = []
    with open(LOG_PATH, errors="ignore") as fh:
        for line in fh:
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    return rows


def session_costs():
    """Real (proxy-billed) cost per session, from the statusline's records."""
    try:
        with open(STATS_PATH) as fh:
            # cost_base: total banked when the CLI's counter restarted (resume)
            return {k: v.get("cost_base", 0.0) + v.get("last_cost_usd", 0.0)
                    for k, v in (json.load(fh).get("sessions") or {}).items()}
    except Exception:
        return {}


def mtok(n):
    return f"{n / 1e6:.2f}M" if n >= 1e5 else f"{n / 1000:.0f}k"


def main():
    days = None
    if "--days" in sys.argv:
        days = int(sys.argv[sys.argv.index("--days") + 1])
    costs = session_costs()
    rows = load()
    allocate_real_cost(rows, costs)  # before --days filtering, so session totals stay whole
    if days:
        keep = sorted({r["date"] for r in rows})[-days:]
        rows = [r for r in rows if r["date"] in keep]

    print(f"{len(rows)} tasks  {rows[0]['date']}..{rows[-1]['date']}\n")

    print("PER DAY (normalized by task count)")
    print(f"{'date':12}{'tasks':>6}{'out/task':>10}{'cacheR/task':>13}"
          f"{'calls/task':>11}{'ctx/call':>10}{'$/task':>9}")
    byd = collections.defaultdict(list)
    for r in rows:
        byd[r["date"]].append(r)
    for date in sorted(byd):
        v = byd[date]
        n = len(v)
        calls = sum(x["api_calls"] for x in v)
        cr = sum(x["cache_read"] for x in v)
        priced = [x["real"] for x in v if x["real"] is not None]
        cps = f"{sum(priced) / len(priced):>9.2f}" if priced else "        -"
        print(f"{date:12}{n:>6}{sum(x['output_tokens'] for x in v) / n:>10.0f}"
              f"{mtok(cr / n):>13}{calls / n:>11.1f}"
              f"{mtok(cr / max(calls, 1)):>10}{cps}")

    print("\nPER MODEL (median per task)")
    print(f"{'model':22}{'tasks':>6}{'calls':>7}{'out':>8}{'out/call':>10}"
          f"{'ctx/call':>10}{'$/task':>8}{'$ mean':>8}")
    bym = collections.defaultdict(list)
    for r in rows:
        bym["+".join(m.replace("claude-", "") for m in r["models"]) or "?"].append(r)
    for model, v in sorted(bym.items(), key=lambda x: -len(x[1])):
        if len(v) < 3:
            continue
        print(f"{model[:21]:22}{len(v):>6}"
              f"{st.median([x['api_calls'] for x in v]):>7.0f}"
              f"{st.median([x['output_tokens'] for x in v]):>8.0f}"
              f"{st.median([x['output_tokens'] / max(x['api_calls'], 1) for x in v]):>10.0f}"
              f"{mtok(st.median([x['cache_read'] / max(x['api_calls'], 1) for x in v])):>10}"
              + (f"{st.median(priced):>8.2f}{st.mean(priced):>8.2f}"
                 if (priced := [x["real"] for x in v if x["real"] is not None]) else ""))

    # Compare models fairly: a model handed harder tasks shouldn't look worse.
    print("\nBY COMPLEXITY (api_calls bucket x model, median out/call)")
    buckets = [(1, 5), (6, 15), (16, 10 ** 9)]
    labels = [f"{lo}-{hi}" if hi < 10 ** 9 else f"{lo}+" for lo, hi in buckets]
    models = [m for m, v in bym.items() if len(v) >= 3]
    print(f"{'bucket':10}" + "".join(f"{m.replace('claude-','')[:15]:>17}" for m in models))
    for (lo, hi), label in zip(buckets, labels):
        cells = []
        for m in models:
            v = [x for x in bym[m] if lo <= x["api_calls"] <= hi]
            cells.append(f"{st.median([x['output_tokens'] / max(x['api_calls'], 1) for x in v]):>17.0f}"
                         if v else f"{'-':>17}")
        print(f"{label:10}" + "".join(cells))

    print("\nCOST BREAKDOWN BY TOKEN TYPE (split from list rates, scaled to real $)")
    totals = collections.defaultdict(float)
    tok_totals = collections.defaultdict(int)
    for r in rows:
        for k, v in task_cost_breakdown(r).items():
            totals[k] += v
        for k in ("input_tokens", "cache_creation", "cache_read", "output_tokens"):
            tok_totals[k] += r[k] + (r.get("sub_" + k) or 0)
    grand = sum(totals.values()) or 1.0
    priced = [r for r in rows if r["real"] is not None]
    real_total = sum(r["real"] for r in priced)
    # only the priced subset's real $ is known; scale the share to all rows' est
    scale = real_total / (sum(r["est"] for r in priced) or 1.0)
    label_tok = {"input": "input_tokens", "cache_write": "cache_creation",
                 "cache_read": "cache_read", "output": "output_tokens"}
    print(f"{'type':14}{'tokens':>12}{'% of $':>8}{'$ real':>10}")
    for k in ("input", "cache_write", "cache_read", "output"):
        print(f"{k:14}{mtok(tok_totals[label_tok[k]]):>12}"
              f"{100 * totals[k] / grand:>7.0f}%{totals[k] * scale:>10.2f}")
    print(f"{'total':14}{'':>12}{'':>8}{grand * scale:>10.2f}")
    sub_tok = sum(r.get("sub_cache_read", 0) + r.get("sub_cache_creation", 0)
                  + r.get("sub_output_tokens", 0) for r in rows)
    print(f"  of which subagents: {mtok(sub_tok)} tokens")

    print("\nPROXY vs LIST PRICE (real $ / list-rate estimate, by main model)")
    ratio = collections.defaultdict(lambda: [0.0, 0.0])
    for r in priced:
        m = "+".join(x.replace("claude-", "") for x in r["models"]) or "?"
        ratio[m][0] += r["real"]
        ratio[m][1] += r["est"]
    for m, (real, est) in sorted(ratio.items(), key=lambda x: -x[1][0]):
        if real >= 1:
            print(f"  {m[:21]:22}{real / est:>6.2f}x  (${real:.0f} real)")

    if not costs:
        print("\nnote: no session costs found in statusline_stats.json")
    else:
        print("\nnote: $ columns are REAL proxy-billed session cost (statusline), split across"
              " a session's tasks in proportion to their list-rate token cost -- approximate"
              " per task, exact per session.")
    print("note: the % split uses Anthropic's public list prices because the proxy's per-token"
          " rates aren't observable; the proxy charges less than list (see ratio above), so"
          " the split is directional. '$ real' rescales it to the real total.")

if __name__ == "__main__":
    main()
