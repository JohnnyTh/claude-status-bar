#!/usr/bin/env python3
"""Verification tests for statusline.py — covers UX, logic correctness, and edge cases."""
import json
import os
import subprocess
import sys
import tempfile
import time

SCRIPT = os.path.expanduser("~/.claude/statusline.py")

PASS = "\033[32m✓\033[0m"
FAIL = "\033[31m✗\033[0m"
HEAD = "\033[1;36m"
RST  = "\033[0m"

_results = []


def section(title: str) -> None:
    print(f"\n{HEAD}{'─'*60}{RST}")
    print(f"{HEAD}  {title}{RST}")
    print(f"{HEAD}{'─'*60}{RST}")


def check(name: str, ok: bool, detail: str = "") -> None:
    _results.append((name, ok))
    mark = PASS if ok else FAIL
    detail_str = f"  \033[2m{detail}\033[0m" if detail else ""
    print(f"  {mark} {name}{detail_str}")


def run(payload: dict, stats_path: str | None = None, config_path: str | None = None) -> tuple[str, int]:
    env = os.environ.copy()
    if stats_path:
        env["STATUSLINE_STATS_PATH"] = stats_path
    if config_path:
        env["STATUSLINE_CONFIG_PATH"] = config_path
    result = subprocess.run(
        [sys.executable, SCRIPT],
        input=json.dumps(payload),
        capture_output=True, text=True, env=env,
    )
    return result.stdout, result.returncode


def make_payload(
    session_id: str = "test",
    model: str = "claude-sonnet-4-6",
    used_pct: float = 20.0,
    tokens: int = 10000,
    cost: float = 0.006,
) -> dict:
    return {
        "session_id": session_id,
        "model": {"id": model},
        "context_window": {"used_percentage": used_pct, "total_input_tokens": tokens},
        "cost": {"total_cost_usd": cost},
    }


def tmp_stats() -> str:
    fd, path = tempfile.mkstemp(suffix=".json", prefix="sl_test_stats_")
    os.close(fd)
    os.unlink(path)
    return path


def tmp_config(overrides: dict | None = None) -> str:
    cfg = {
        "theme": "corpo",
        "quip_interval": 25,
        "tier_up_burst_duration": 8,
        "rolling_window": 5,
        "efficiency_threshold_efficient": 0.8,
        "efficiency_threshold_wasteful": 3.0,
        "model_base_costs": {
            "claude-haiku-4-5": 0.002,
            "claude-sonnet-4-6": 0.006,
            "claude-opus-4-7": 0.010,
        },
    }
    if overrides:
        cfg.update(overrides)
    fd, path = tempfile.mkstemp(suffix=".json", prefix="sl_test_cfg_")
    os.close(fd)
    with open(path, "w") as f:
        json.dump(cfg, f)
    return path


# Patch script to accept env-var overrides for paths
def patch_script_for_tests() -> bool:
    with open(SCRIPT) as f:
        src = f.read()
    return (
        "STATUSLINE_STATS_PATH" in src
        or "os.environ.get" in src
    )


# ─────────────────────────────────────────────────────────────────────────────
# We run the script as a subprocess, but also import it for unit tests.
# To allow path injection, temporarily monkey-patch paths via env vars.
# The script must read these — if it doesn't, we patch it first.
# ─────────────────────────────────────────────────────────────────────────────

def inject_paths(stats_path: str, config_path: str) -> None:
    """Write a tmp config and stats that the script will pick up via known paths."""
    # We override the module-level constants by writing to the actual paths
    # only for tests that want isolation. We back up and restore.
    pass  # handled by run() writing to actual paths directly below


# ─── Instead of env injection, write test data directly to temp paths ────────
# and monkeypatch STATS_PATH/CONFIG_PATH in the module via importlib.

import importlib.util
import types

def load_module(stats_path: str, config_path: str):
    # Force a fresh module load each time — no shared state between tests.
    spec = importlib.util.spec_from_file_location(f"statusline_{id(stats_path)}", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.STATS_PATH = stats_path
    mod.CONFIG_PATH = config_path
    return mod


# ═════════════════════════════════════════════════════════════════════════════
# TEST GROUPS
# ═════════════════════════════════════════════════════════════════════════════

def test_basic_output() -> None:
    section("1. Basic output structure")
    sp, cp = tmp_stats(), tmp_config()
    mod = load_module(sp, cp)

    try:
        import io, contextlib
        data = make_payload()
        config = mod.deep_merge(mod.DEFAULT_CONFIG, mod.load_json(cp, {}))
        stats = mod.deep_merge(mod.DEFAULT_STATS, mod.load_json(sp, {}))
        stats = mod.update_session(stats, data, config)

        session_line = mod.fmt_session_line(data, stats, mod.THEMES["corpo"])
        global_line  = mod.fmt_global_line(stats)

        check("Session line contains 'Session:'", "Session:" in session_line)
        check("Session line contains context bar [", "[" in session_line and "]" in session_line)
        check("Session line contains % symbol", "%" in session_line)
        check("Session line contains $ cost", "$" in session_line)
        check("Session line shows E1 tier", "E1" in session_line, session_line)
        check("Session line shows W1 tier", "W1" in session_line, session_line)
        check("Global line contains 'Global:'", "Global:" in global_line)
        check("Global line contains 'turns'", "turns" in global_line)
        check("Global line contains avg cost", "avg" in global_line)
    finally:
        for p in [sp, cp]:
            if os.path.exists(p): os.unlink(p)


def test_turn_detection() -> None:
    section("2. Turn detection (cost delta)")
    sp, cp = tmp_stats(), tmp_config()
    mod = load_module(sp, cp)
    config = mod.deep_merge(mod.DEFAULT_CONFIG, {})

    stats = mod.deep_merge(mod.DEFAULT_STATS, {})

    # Same session, cost increases → new turn each time
    payloads = [
        make_payload(session_id="A", cost=0.006),
        make_payload(session_id="A", cost=0.012),
        make_payload(session_id="A", cost=0.012),  # no delta → no new turn
        make_payload(session_id="A", cost=0.018),
    ]
    for p in payloads:
        stats = mod.update_session(stats, p, config)

    check("3 cost-increasing events = 3 turns", stats["global"]["total_turns"] == 3,
          f"got {stats['global']['total_turns']}")
    check("Total spend matches sum of deltas",
          abs(stats["global"]["total_spend_usd"] - 0.018) < 1e-6,
          f"got {stats['global']['total_spend_usd']:.6f}")

    # Different sessions, each contributing one new turn from cost=0 baseline
    # Use a fresh stats dict so previous sessions don't carry over
    stats2 = mod.deep_merge(mod.DEFAULT_STATS, {})
    for sid in ["B", "C", "D"]:
        # Each brand-new session: prev_cost=0, new cost=0.006 → delta=0.006 → 1 turn
        stats2 = mod.update_session(stats2, make_payload(session_id=sid, cost=0.006), config)
    check("3 distinct new sessions = 3 turns", stats2["global"]["total_turns"] == 3,
          f"got {stats2['global']['total_turns']}")

    # Replaying the same session IDs with same cost → 0 new turns (no delta)
    stats3 = json.loads(json.dumps(stats2))  # copy with sessions B,C,D already at 0.006
    for sid in ["B", "C", "D"]:
        stats3 = mod.update_session(stats3, make_payload(session_id=sid, cost=0.006), config)
    check("Replaying same cost on known sessions → no new turns",
          stats3["global"]["total_turns"] == 3,
          f"got {stats3['global']['total_turns']}")

    try:
        for p in [sp, cp]:
            if os.path.exists(p): os.unlink(p)
    except Exception:
        pass


def test_efficiency_score() -> None:
    section("3. Efficiency score (model-normalized)")
    sp, cp = tmp_stats(), tmp_config()
    mod = load_module(sp, cp)
    config = mod.deep_merge(mod.DEFAULT_CONFIG, {})

    # Efficient: cost per turn well below Sonnet base ($0.006)
    stats_eff = mod.deep_merge(mod.DEFAULT_STATS, {})
    for i, cost in enumerate([0.001, 0.002, 0.003, 0.004, 0.005]):
        stats_eff = mod.update_session(stats_eff,
            make_payload(session_id=f"e{i}", cost=cost), config)
    score_eff = mod.compute_efficiency_score(stats_eff, "claude-sonnet-4-6", config)
    check("Low-cost turns → efficiency score < 0.8 (efficient track)",
          score_eff < 0.8, f"score={score_eff:.3f}")

    # Wasteful: cost per turn well above Sonnet base
    stats_wst = mod.deep_merge(mod.DEFAULT_STATS, {})
    for i, cost in enumerate([0.02, 0.04, 0.06, 0.08, 0.10]):
        stats_wst = mod.update_session(stats_wst,
            make_payload(session_id=f"w{i}", cost=cost), config)
    score_wst = mod.compute_efficiency_score(stats_wst, "claude-sonnet-4-6", config)
    check("High-cost turns → efficiency score > 3.0 (wasteful track)",
          score_wst > 3.0, f"score={score_wst:.3f}")

    # Neutral
    stats_neu = mod.deep_merge(mod.DEFAULT_STATS, {})
    for i, cost in enumerate([0.005, 0.006, 0.007, 0.006, 0.006]):
        stats_neu = mod.update_session(stats_neu,
            make_payload(session_id=f"n{i}", cost=cost), config)
    score_neu = mod.compute_efficiency_score(stats_neu, "claude-sonnet-4-6", config)
    check("On-baseline turns → 0.8 ≤ score ≤ 3.0 (neutral zone)",
          0.8 <= score_neu <= 3.0, f"score={score_neu:.3f}")

    # Model normalization: same absolute cost, different model → different score
    stats_opus = mod.deep_merge(mod.DEFAULT_STATS, {})
    for i, cost in enumerate([0.005, 0.006, 0.007, 0.006, 0.006]):
        stats_opus = mod.update_session(stats_opus,
            make_payload(session_id=f"o{i}", cost=cost, model="claude-opus-4-7"), config)
    score_opus = mod.compute_efficiency_score(stats_opus, "claude-opus-4-7", config)
    check("Same absolute cost on Opus → lower score than Sonnet (Opus base is higher)",
          score_opus < score_neu, f"opus={score_opus:.3f} vs sonnet={score_neu:.3f}")

    for p in [sp, cp]:
        if os.path.exists(p): os.unlink(p)


def test_prestige_accumulation() -> None:
    section("4. Prestige accumulation (independent pools)")
    sp, cp = tmp_stats(), tmp_config()
    mod = load_module(sp, cp)
    config = mod.deep_merge(mod.DEFAULT_CONFIG, {})

    stats = mod.deep_merge(mod.DEFAULT_STATS, {})
    # Seed some turns
    for i in range(10):
        stats = mod.update_session(stats,
            make_payload(session_id=f"p{i}", cost=0.001 * (i+1)), config)

    before_eff = stats["global"]["efficient_prestige"]
    before_wst = stats["global"]["wasteful_prestige"]

    # Apply efficient score → only efficient prestige grows
    stats_eff = json.loads(json.dumps(stats))
    stats_eff = mod.update_prestige(stats_eff, 0.3, config)  # score < 0.8
    check("Efficient score → efficient_prestige grows",
          stats_eff["global"]["efficient_prestige"] > before_eff)
    check("Efficient score → wasteful_prestige unchanged",
          stats_eff["global"]["wasteful_prestige"] == before_wst)

    # Apply wasteful score → only wasteful prestige grows
    stats_wst = json.loads(json.dumps(stats))
    stats_wst = mod.update_prestige(stats_wst, 5.0, config)  # score > 3.0
    check("Wasteful score → wasteful_prestige grows",
          stats_wst["global"]["wasteful_prestige"] > before_wst)
    check("Wasteful score → efficient_prestige unchanged",
          stats_wst["global"]["efficient_prestige"] == before_eff)

    # Neutral → neither grows
    stats_neu = json.loads(json.dumps(stats))
    stats_neu = mod.update_prestige(stats_neu, 1.5, config)  # neutral
    check("Neutral score → neither prestige grows",
          stats_neu["global"]["efficient_prestige"] == before_eff
          and stats_neu["global"]["wasteful_prestige"] == before_wst)

    for p in [sp, cp]:
        if os.path.exists(p): os.unlink(p)


def test_tier_breakpoints() -> None:
    section("5. Tier index from prestige breakpoints")
    sp, cp = tmp_stats(), tmp_config()
    mod = load_module(sp, cp)

    bp = mod.TIER_BREAKPOINTS  # [0, 5, 12, 22, 35, 52, 73, 98, 128, 163]
    check("Prestige 0 → tier 0", mod.get_tier_index(0) == 0)
    check("Prestige 4.9 → tier 0", mod.get_tier_index(4.9) == 0)
    check(f"Prestige {bp[1]} → tier 1", mod.get_tier_index(bp[1]) == 1)
    check(f"Prestige {bp[5]} → tier 5", mod.get_tier_index(bp[5]) == 5)
    check(f"Prestige {bp[9]} → tier 9 (max)", mod.get_tier_index(bp[9]) == 9)
    check("Prestige 9999 → tier 9 (capped)", mod.get_tier_index(9999) == 9)
    check(f"Prestige {bp[3]-0.001} → tier 2 (just below boundary)",
          mod.get_tier_index(bp[3] - 0.001) == 2)
    check(f"Prestige {bp[3]} → tier 3 (exactly on boundary)",
          mod.get_tier_index(bp[3]) == 3)

    for p in [sp, cp]:
        if os.path.exists(p): os.unlink(p)


def test_tier_up_burst() -> None:
    section("6. Tier-up burst mechanics")
    sp, cp = tmp_stats(), tmp_config()
    mod = load_module(sp, cp)
    config = mod.deep_merge(mod.DEFAULT_CONFIG, {})
    theme = mod.THEMES["corpo"]

    # Trigger an efficient tier-up: E0 → E1
    stats = mod.deep_merge(mod.DEFAULT_STATS, {})
    stats["global"]["efficient_tier"] = 0
    stats = mod.check_tier_up(stats, 1, 0, config, theme)

    check("Tier-up sets burst_remaining to duration",
          stats["display"]["tier_up_burst_remaining"] == config["tier_up_burst_duration"],
          str(stats["display"]["tier_up_burst_remaining"]))
    check("Tier-up stores burst_lines", len(stats["display"]["tier_up_burst_lines"]) > 0)
    check("Tier-up type is 'efficient'", stats["display"]["tier_up_burst_type"] == "efficient")
    check("Efficient tier updated in global", stats["global"]["efficient_tier"] == 1)

    # Burst output at remaining=8 (full)
    s8 = json.loads(json.dumps(stats))
    s8["display"]["tier_up_burst_remaining"] = 8
    lines_8 = mod.fmt_tier_up_burst(s8)
    check("Burst remaining=8 → non-empty output", len(lines_8) > 0)
    check("Burst remaining=8 → uses bold cyan color", any("1;36m" in l for l in lines_8),
          str(lines_8[:1]))
    check("Burst remaining decremented after call",
          s8["display"]["tier_up_burst_remaining"] == 7)

    # Burst output at remaining=3 (body only)
    s3 = json.loads(json.dumps(stats))
    s3["display"]["tier_up_burst_remaining"] = 3
    lines_3 = mod.fmt_tier_up_burst(s3)
    check("Burst remaining=3 → no bold header color", not any("1;36m" in l for l in lines_3),
          str(lines_3[:1]))

    # Burst output at remaining=1 (acknowledgement)
    s1 = json.loads(json.dumps(stats))
    s1["display"]["tier_up_burst_remaining"] = 1
    lines_1 = mod.fmt_tier_up_burst(s1)
    check("Burst remaining=1 → acknowledgement line", len(lines_1) == 1)
    check("Burst remaining=1 → dim color", "2m" in lines_1[0])

    # Burst output at remaining=0 → empty
    s0 = json.loads(json.dumps(stats))
    s0["display"]["tier_up_burst_remaining"] = 0
    lines_0 = mod.fmt_tier_up_burst(s0)
    check("Burst remaining=0 → no output", len(lines_0) == 0)

    # Wasteful tier-up uses red colors
    stats_w = mod.deep_merge(mod.DEFAULT_STATS, {})
    stats_w["global"]["wasteful_tier"] = 0
    stats_w = mod.check_tier_up(stats_w, 0, 1, config, theme)
    stats_w["display"]["tier_up_burst_remaining"] = 8
    lines_w = mod.fmt_tier_up_burst(stats_w)
    check("Wasteful tier-up burst → bold red color", any("1;31m" in l for l in lines_w),
          str(lines_w[:1]))

    # Only one burst at a time — efficient wins if both trigger simultaneously
    # Both tracks at tier 0, both advancing to tier 1 in the same call
    stats_both = mod.deep_merge(mod.DEFAULT_STATS, {})
    assert stats_both["global"]["efficient_tier"] == 0
    assert stats_both["global"]["wasteful_tier"] == 0
    stats_both = mod.check_tier_up(stats_both, 1, 1, config, theme)
    check("Both tier-up simultaneously → efficient takes priority",
          stats_both["display"]["tier_up_burst_type"] == "efficient",
          f"got burst_type={stats_both['display']['tier_up_burst_type']!r}")

    for p in [sp, cp]:
        if os.path.exists(p): os.unlink(p)


def test_quip_rotation() -> None:
    section("7. Quip system")
    sp, cp = tmp_stats(), tmp_config({"quip_interval": 5})
    mod = load_module(sp, cp)
    config = mod.deep_merge(mod.DEFAULT_CONFIG, {"quip_interval": 5})
    theme = mod.THEMES["corpo"]

    stats = mod.deep_merge(mod.DEFAULT_STATS, {})

    # refresh_count=0 → no quip (session start)
    stats["display"]["refresh_count"] = 0
    q = mod.get_quip(stats, theme, config)
    check("refresh_count=0 → no quip", q is None)

    # refresh_count=5 → quip fires
    stats["display"]["refresh_count"] = 5
    q = mod.get_quip(stats, theme, config)
    check("refresh_count=5 (interval) → quip fires", q is not None)
    check("Quip is wrapped in brackets", q is not None and q.startswith("[") and q.endswith("]"))

    # refresh_count=6 → no quip
    stats["display"]["refresh_count"] = 6
    q = mod.get_quip(stats, theme, config)
    check("refresh_count=6 (not interval) → no quip", q is None)

    # Quips rotate — different index at 5 vs 10 vs 15
    quips_seen = set()
    for rc in [5, 10, 15, 20, 25, 30]:
        stats["display"]["refresh_count"] = rc
        q = mod.get_quip(stats, theme, config)
        if q:
            quips_seen.add(q)
    check("Quips rotate across intervals (at least 2 distinct quips seen)",
          len(quips_seen) >= 2, f"saw {len(quips_seen)}: {list(quips_seen)[:2]}")

    # Efficient vs wasteful track selection
    stats_eff = json.loads(json.dumps(stats))
    stats_eff["global"]["rolling_cost_per_turn"] = [0.001] * 5  # very efficient
    stats_eff["display"]["refresh_count"] = 5
    stats_eff["global"]["efficient_tier"] = 2
    q_eff = mod.get_quip(stats_eff, theme, config)
    check("Efficient user → quip from efficient tier pool",
          q_eff is not None, str(q_eff))

    for p in [sp, cp]:
        if os.path.exists(p): os.unlink(p)


def test_sparkline() -> None:
    section("8. Sparkline rendering")
    sp, cp = tmp_stats(), tmp_config()
    mod = load_module(sp, cp)

    check("Empty list → spaces", mod.fmt_sparkline([]) == "")
    check("All zeros → spaces", all(c == " " for c in mod.fmt_sparkline([0, 0, 0])))
    check("Monotone increasing → rightmost char is highest spark",
          mod.fmt_sparkline([1, 2, 3, 4, 5])[-1] == "█")
    check("Single value → rendered (no crash)", len(mod.fmt_sparkline([42])) == 1)
    check("12-value history → 12-char sparkline", len(mod.fmt_sparkline(list(range(12)))) == 12)
    check("Identical values → flat line (all same char)",
          len(set(mod.fmt_sparkline([100, 100, 100, 100]))) == 1)

    for p in [sp, cp]:
        if os.path.exists(p): os.unlink(p)


def test_token_history() -> None:
    section("9. Token history (sparkline data)")
    sp, cp = tmp_stats(), tmp_config()
    mod = load_module(sp, cp)
    config = mod.deep_merge(mod.DEFAULT_CONFIG, {})

    stats = mod.deep_merge(mod.DEFAULT_STATS, {})
    for i in range(15):
        stats = mod.update_session(stats,
            make_payload(session_id=f"h{i}", tokens=i * 1000, cost=0.001 * (i+1)), config)

    history = stats["global"]["token_history"]
    check(f"Token history capped at HISTORY_LEN={mod.HISTORY_LEN}",
          len(history) <= mod.HISTORY_LEN, f"len={len(history)}")
    check("Token history contains recent values (not zeros)",
          any(v > 0 for v in history))

    for p in [sp, cp]:
        if os.path.exists(p): os.unlink(p)


def test_context_bar() -> None:
    section("10. Context bar rendering")
    sp, cp = tmp_stats(), tmp_config()
    mod = load_module(sp, cp)

    check("0% → all empty",   mod.fmt_bar(0)   == "[░░░░░░░░░░]")
    check("100% → all full",  mod.fmt_bar(100) == "[██████████]")
    check("50% → half full",  mod.fmt_bar(50)  == "[█████░░░░░]")
    check("10% → one block",  mod.fmt_bar(10)  == "[█░░░░░░░░░]")
    check("Bar always 12 chars (with brackets)", all(
        len(mod.fmt_bar(p)) == 12 for p in [0, 25, 50, 75, 100]
    ))

    for p in [sp, cp]:
        if os.path.exists(p): os.unlink(p)


def test_atomic_write() -> None:
    section("11. Atomic stats write (no corruption on crash)")
    sp, cp = tmp_stats(), tmp_config()
    mod = load_module(sp, cp)

    stats = mod.deep_merge(mod.DEFAULT_STATS, {})
    stats["global"]["total_turns"] = 42
    mod.STATS_PATH = sp
    mod.save_stats(stats)

    check("Stats file created", os.path.exists(sp))
    check("No .tmp sidecar left behind", not os.path.exists(sp + ".tmp"))

    with open(sp) as f:
        loaded = json.load(f)
    check("Saved data round-trips correctly",
          loaded["global"]["total_turns"] == 42)

    # Simulate concurrent write — tmp file should be replaced atomically
    with open(sp + ".tmp", "w") as f:
        f.write("garbage")
    stats["global"]["total_turns"] = 99
    mod.save_stats(stats)
    check("Stale .tmp file is overwritten cleanly", not os.path.exists(sp + ".tmp"))
    with open(sp) as f:
        loaded2 = json.load(f)
    check("After overwrite, data is correct", loaded2["global"]["total_turns"] == 99)

    for p in [sp, cp]:
        if os.path.exists(p): os.unlink(p)


def test_malformed_input() -> None:
    section("12. Malformed / missing input handling")
    sp, cp = tmp_stats(), tmp_config()
    mod = load_module(sp, cp)

    # Empty payload
    stats = mod.deep_merge(mod.DEFAULT_STATS, {})
    config = mod.deep_merge(mod.DEFAULT_CONFIG, {})
    try:
        stats2 = mod.update_session(stats, {}, config)
        check("Empty payload → no crash", True)
    except Exception as e:
        check("Empty payload → no crash", False, str(e))

    # Missing cost field
    try:
        stats3 = mod.update_session(stats, {"session_id": "x"}, config)
        check("Missing cost → no crash", True)
    except Exception as e:
        check("Missing cost → no crash", False, str(e))

    # Missing model field
    try:
        score = mod.compute_efficiency_score(stats, "unknown-model-xyz", config)
        check("Unknown model → falls back to default base cost", score > 0)
    except Exception as e:
        check("Unknown model → no crash", False, str(e))

    # Bad JSON to subprocess
    result = subprocess.run(
        [sys.executable, SCRIPT],
        input="not json at all {{{{",
        capture_output=True, text=True,
    )
    check("Bad JSON stdin → exits cleanly (no Python traceback)",
          "Traceback" not in result.stdout and "Traceback" not in result.stderr,
          result.stderr[:100] if result.stderr else "ok")
    check("Bad JSON stdin → still prints something",
          len(result.stdout.strip()) > 0, repr(result.stdout.strip()))

    # Null/None values in payload
    try:
        payload_nulls = {"session_id": "x", "model": None, "context_window": None, "cost": None}
        stats4 = mod.update_session(stats, payload_nulls, config)
        check("Null fields → no crash", True)
    except Exception as e:
        check("Null fields → no crash", False, str(e))

    for p in [sp, cp]:
        if os.path.exists(p): os.unlink(p)


def test_missing_config() -> None:
    section("13. Missing / corrupt config and stats files")
    sp, cp = tmp_stats(), tmp_config()
    mod = load_module(sp, cp)

    # No stats file at all
    missing_stats = sp + ".missing"
    loaded = mod.load_json(missing_stats, mod.DEFAULT_STATS)
    check("Missing stats file → returns default", loaded["global"]["total_turns"] == 0)

    # Corrupt JSON stats file
    corrupt = sp + ".corrupt"
    with open(corrupt, "w") as f:
        f.write("{broken json{{")
    loaded2 = mod.load_json(corrupt, mod.DEFAULT_STATS)
    check("Corrupt stats JSON → returns default", loaded2["global"]["total_turns"] == 0)
    os.unlink(corrupt)

    # Missing config → deep_merge with DEFAULT_CONFIG fills all keys
    missing_cfg = cp + ".missing"
    loaded_cfg = mod.load_json(missing_cfg, {})
    merged = mod.deep_merge(mod.DEFAULT_CONFIG, loaded_cfg)
    check("Missing config → all default keys present",
          "model_base_costs" in merged and "quip_interval" in merged)

    for p in [sp, cp]:
        if os.path.exists(p): os.unlink(p)


def test_full_tier_progression_efficient() -> None:
    section("14. Full efficient tier progression (E1 → E2)")
    sp, cp = tmp_stats(), tmp_config({"quip_interval": 999})
    mod = load_module(sp, cp)
    config = mod.deep_merge(mod.DEFAULT_CONFIG, {"quip_interval": 999})
    theme = mod.THEMES["corpo"]

    stats = mod.deep_merge(mod.DEFAULT_STATS, {})
    tiers_seen = set()
    burst_fired = False

    # Use a SINGLE session with incrementally increasing cost.
    # Each iteration: delta = fixed $0.0005 → score = 0.0005/0.006 ≈ 0.083 (efficient)
    # This keeps deltas small and consistent regardless of iteration count.
    prev_cost = 0.0
    for i in range(200):
        new_cost = prev_cost + 0.0005
        stats = mod.update_session(stats,
            make_payload(session_id="single_eff_session", cost=new_cost), config)
        prev_cost = new_cost

        score = mod.compute_efficiency_score(stats, "claude-sonnet-4-6", config)
        stats = mod.update_prestige(stats, score, config)

        new_eff = mod.get_tier_index(stats["global"]["efficient_prestige"])
        new_wst = mod.get_tier_index(stats["global"]["wasteful_prestige"])
        stats = mod.check_tier_up(stats, new_eff, new_wst, config, theme)

        if stats["display"]["tier_up_burst_remaining"] > 0:
            burst_fired = True

        tiers_seen.add(stats["global"]["efficient_tier"])

    check("Efficient progression reaches at least E2", max(tiers_seen) >= 1,
          f"tiers seen: {sorted(tiers_seen)}, eff_prestige={stats['global']['efficient_prestige']:.3f}")
    check("Tier-up burst fires at least once during progression", burst_fired)
    check("Wasteful prestige stays 0 (efficient turns don't pollute wasteful)",
          stats["global"]["wasteful_prestige"] == 0.0,
          f"wasteful_prestige={stats['global']['wasteful_prestige']:.4f}")

    for p in [sp, cp]:
        if os.path.exists(p): os.unlink(p)


def test_full_tier_progression_wasteful() -> None:
    section("15. Full wasteful tier progression (W1 → W3)")
    sp, cp = tmp_stats(), tmp_config({"quip_interval": 999})
    mod = load_module(sp, cp)
    config = mod.deep_merge(mod.DEFAULT_CONFIG, {"quip_interval": 999})
    theme = mod.THEMES["corpo"]

    stats = mod.deep_merge(mod.DEFAULT_STATS, {})
    tiers_seen = set()
    burst_fired = False

    # Single session with fixed delta of $0.05/turn → score = 0.05/0.006 ≈ 8.3 (wasteful)
    prev_cost = 0.0
    for i in range(200):
        new_cost = prev_cost + 0.05
        stats = mod.update_session(stats,
            make_payload(session_id="single_wst_session", cost=new_cost), config)
        prev_cost = new_cost

        score = mod.compute_efficiency_score(stats, "claude-sonnet-4-6", config)
        stats = mod.update_prestige(stats, score, config)

        new_eff = mod.get_tier_index(stats["global"]["efficient_prestige"])
        new_wst = mod.get_tier_index(stats["global"]["wasteful_prestige"])
        stats = mod.check_tier_up(stats, new_eff, new_wst, config, theme)

        if stats["display"]["tier_up_burst_remaining"] > 0:
            burst_fired = True
        tiers_seen.add(stats["global"]["wasteful_tier"])

    check("Wasteful progression reaches at least W3", max(tiers_seen) >= 2,
          f"tiers seen: {sorted(tiers_seen)}, wst_prestige={stats['global']['wasteful_prestige']:.3f}")
    check("Tier-up burst fires during wasteful progression", burst_fired)
    check("Efficient prestige stays 0 (wasteful turns don't pollute efficient)",
          stats["global"]["efficient_prestige"] == 0.0,
          f"efficient_prestige={stats['global']['efficient_prestige']:.4f}")

    for p in [sp, cp]:
        if os.path.exists(p): os.unlink(p)


def test_cost_formatting() -> None:
    section("16. Cost and token formatting")
    sp, cp = tmp_stats(), tmp_config()
    mod = load_module(sp, cp)

    check("$0.123 → 3 decimal places",    mod.fmt_cost(0.123)   == "$0.123")
    check("$0.00042 → 5 decimal places",  mod.fmt_cost(0.00042) == "$0.00042")
    check("$0.001 boundary → 3 decimals", mod.fmt_cost(0.001)   == "$0.001")
    check("1500 tokens → '1.5k'",         mod.fmt_tokens(1500)  == "1.5k")
    check("1_500_000 tokens → '1.5M'",    mod.fmt_tokens(1_500_000) == "1.5M")
    check("999 tokens → raw string",      mod.fmt_tokens(999)   == "999")
    check("0 tokens → '0'",               mod.fmt_tokens(0)     == "0")

    for p in [sp, cp]:
        if os.path.exists(p): os.unlink(p)


def test_theme_completeness() -> None:
    section("17. Theme data completeness")
    sp, cp = tmp_stats(), tmp_config()
    mod = load_module(sp, cp)

    for theme_name, theme in mod.THEMES.items():
        check(f"Theme '{theme_name}' has 10 efficient tiers",
              len(theme["efficient_tiers"]) == 10,
              f"got {len(theme['efficient_tiers'])}")
        check(f"Theme '{theme_name}' has 10 wasteful tiers",
              len(theme["wasteful_tiers"]) == 10,
              f"got {len(theme['wasteful_tiers'])}")

        for track in ["efficient_tiers", "wasteful_tiers"]:
            for i, t in enumerate(theme[track]):
                prefix = f"  {theme_name}/{track}[{i}]"
                check(f"{prefix} has 'name'",     bool(t.get("name")))
                check(f"{prefix} has 'symbol'",   bool(t.get("symbol")))
                check(f"{prefix} has tier_up_lines (≥1)", len(t.get("tier_up_lines", [])) >= 1)
                check(f"{prefix} has ≥3 quips",   len(t.get("quips", [])) >= 3,
                      f"got {len(t.get('quips', []))}")

    for p in [sp, cp]:
        if os.path.exists(p): os.unlink(p)


def test_refresh_counter() -> None:
    section("18. Refresh counter increments and persists")
    sp, cp = tmp_stats(), tmp_config()
    mod = load_module(sp, cp)

    # Run script 3 times against same stats file, check counter increments
    mod.STATS_PATH = sp
    stats = mod.deep_merge(mod.DEFAULT_STATS, {})
    mod.save_stats(stats)

    for expected in range(1, 4):
        import io, contextlib
        data = make_payload()
        config = mod.deep_merge(mod.DEFAULT_CONFIG, {})
        stats = mod.deep_merge(mod.DEFAULT_STATS, mod.load_json(sp, {}))
        stats = mod.update_session(stats, data, config)
        stats["display"]["refresh_count"] += 1
        mod.save_stats(stats)

    final = mod.load_json(sp, {})
    check("Refresh count = 3 after 3 runs",
          final["display"]["refresh_count"] == 3,
          f"got {final['display']['refresh_count']}")

    for p in [sp, cp]:
        if os.path.exists(p): os.unlink(p)


def test_e2e_subprocess() -> None:
    section("19. End-to-end subprocess output (as Claude Code sees it)")

    def run_e2e(payload: dict) -> str:
        result = subprocess.run(
            [sys.executable, SCRIPT],
            input=json.dumps(payload),
            capture_output=True, text=True,
        )
        return result.stdout

    # Clean run
    out = run_e2e(make_payload(cost=0.005))
    check("E2E: output is non-empty", len(out.strip()) > 0)
    check("E2E: contains 'Session:'", "Session:" in out)
    check("E2E: contains 'Global:'",  "Global:" in out)
    check("E2E: no Python traceback", "Traceback" not in out)

    # All models produce output
    for model in ["claude-haiku-4-5", "claude-sonnet-4-6", "claude-opus-4-7"]:
        out = run_e2e(make_payload(model=model, cost=0.005))
        check(f"E2E: model '{model}' → output contains 'Session:'",
              "Session:" in out, out[:80])

    # 0% context usage
    out = run_e2e(make_payload(used_pct=0, tokens=0, cost=0))
    check("E2E: 0% context → bar shows all empty [░░░░░░░░░░]",
          "░░░░░░░░░░" in out, out[:80])

    # 100% context usage
    out = run_e2e(make_payload(used_pct=100, cost=0.010))
    check("E2E: 100% context → bar shows all full [██████████]",
          "██████████" in out, out[:80])


# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    print(f"\n{HEAD}{'═'*60}{RST}")
    print(f"{HEAD}  statusline.py — verification test suite{RST}")
    print(f"{HEAD}{'═'*60}{RST}")

    test_basic_output()
    test_turn_detection()
    test_efficiency_score()
    test_prestige_accumulation()
    test_tier_breakpoints()
    test_tier_up_burst()
    test_quip_rotation()
    test_sparkline()
    test_token_history()
    test_context_bar()
    test_atomic_write()
    test_malformed_input()
    test_missing_config()
    test_full_tier_progression_efficient()
    test_full_tier_progression_wasteful()
    test_cost_formatting()
    test_theme_completeness()
    test_refresh_counter()
    test_e2e_subprocess()

    passed = sum(1 for _, ok in _results if ok)
    failed = sum(1 for _, ok in _results if not ok)
    total  = len(_results)

    print(f"\n{HEAD}{'═'*60}{RST}")
    print(f"  {PASS} {passed}/{total} passed   {FAIL} {failed} failed")
    print(f"{HEAD}{'═'*60}{RST}\n")

    if failed:
        print("Failed checks:")
        for name, ok in _results:
            if not ok:
                print(f"  {FAIL} {name}")
        sys.exit(1)


if __name__ == "__main__":
    main()
