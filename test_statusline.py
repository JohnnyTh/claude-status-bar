#!/usr/bin/env python3
"""Verification tests for statusline.py."""
import json
import os
import subprocess
import sys
import tempfile

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
        "xp_base": 50000,
        "xp_exp": 1.6,
    }
    if overrides:
        cfg.update(overrides)
    fd, path = tempfile.mkstemp(suffix=".json", prefix="sl_test_cfg_")
    os.close(fd)
    with open(path, "w") as f:
        json.dump(cfg, f)
    return path


import importlib.util

def load_module(stats_path: str, config_path: str):
    spec = importlib.util.spec_from_file_location(f"statusline_{id(stats_path)}", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.STATS_PATH = stats_path
    mod.CONFIG_PATH = config_path
    return mod


# ═══════════════════════════════════════════════════════════════════════════════

def test_xp_curve() -> None:
    section("1. XP curve and level thresholds")
    sp, cp = tmp_stats(), tmp_config()
    mod = load_module(sp, cp)

    base, exp = 50_000, 1.6

    check("Level 0 threshold is 0 tokens", mod.xp_threshold(0, base, exp) == 0)
    check("Level 1 threshold is base tokens", mod.xp_threshold(1, base, exp) == int(base * 1**exp))
    check("Thresholds strictly increase", all(
        mod.xp_threshold(i+1, base, exp) > mod.xp_threshold(i, base, exp)
        for i in range(19)
    ))
    check("xp_for_level(1) == base", mod.xp_for_level(1, base, exp) == int(base * 1**exp))
    check("xp_for_level grows with level", mod.xp_for_level(5, base, exp) > mod.xp_for_level(1, base, exp))

    for p in [sp, cp]:
        if os.path.exists(p): os.unlink(p)


def test_get_tier() -> None:
    section("2. get_tier — correct tier for token counts")
    sp, cp = tmp_stats(), tmp_config()
    mod = load_module(sp, cp)

    base, exp = 50_000, 1.6

    check("0 tokens → tier 0", mod.get_tier(0, base, exp) == 0)
    check("1 token → tier 0", mod.get_tier(1, base, exp) == 0)

    t1 = mod.xp_threshold(1, base, exp)
    check(f"Exactly at tier 1 threshold ({t1} tok) → tier 1",
          mod.get_tier(t1, base, exp) == 1)
    check(f"One below tier 1 threshold → tier 0",
          mod.get_tier(t1 - 1, base, exp) == 0)

    t5 = mod.xp_threshold(5, base, exp)
    check(f"At tier 5 threshold → tier 5",
          mod.get_tier(t5, base, exp) == 5)

    # Massive token count → capped at max tier
    check("Very large token count → capped at tier 19",
          mod.get_tier(10**12, base, exp) == 19)

    for p in [sp, cp]:
        if os.path.exists(p): os.unlink(p)


def test_level_progress() -> None:
    section("3. level_progress — percentage within current tier")
    sp, cp = tmp_stats(), tmp_config()
    mod = load_module(sp, cp)

    base, exp = 50_000, 1.6

    # At exact tier boundary → 0%
    t1 = mod.xp_threshold(1, base, exp)
    _, _, pct = mod.level_progress(t1, 1, base, exp)
    check("At tier start → 0%", abs(pct) < 0.01, f"pct={pct:.2f}")

    # Halfway through tier 1
    t2 = mod.xp_threshold(2, base, exp)
    mid = t1 + (t2 - t1) // 2
    _, _, pct_mid = mod.level_progress(mid, 1, base, exp)
    check("Halfway through tier → ~50%", 45 <= pct_mid <= 55, f"pct={pct_mid:.2f}")

    # At tier 0 with 0 tokens → 0%
    _, _, pct0 = mod.level_progress(0, 0, base, exp)
    check("0 tokens at tier 0 → 0%", abs(pct0) < 0.01, f"pct={pct0:.2f}")

    for p in [sp, cp]:
        if os.path.exists(p): os.unlink(p)


def test_token_accumulation() -> None:
    section("4. Token accumulation across sessions")
    sp, cp = tmp_stats(), tmp_config()
    mod = load_module(sp, cp)
    config = mod.deep_merge(mod.DEFAULT_CONFIG, {})

    stats = mod.deep_merge(mod.DEFAULT_STATS, {})

    # Single session: tokens increase → delta accumulates
    stats = mod.update_session(stats, make_payload(session_id="A", tokens=1000), config)
    stats = mod.update_session(stats, make_payload(session_id="A", tokens=3000), config)
    stats = mod.update_session(stats, make_payload(session_id="A", tokens=3000), config)  # no delta
    check("Token delta accumulates correctly",
          stats["global"]["total_input_tokens"] == 3000,
          f"got {stats['global']['total_input_tokens']}")

    # Different sessions accumulate independently
    stats2 = mod.deep_merge(mod.DEFAULT_STATS, {})
    stats2 = mod.update_session(stats2, make_payload(session_id="B", tokens=5000), config)
    stats2 = mod.update_session(stats2, make_payload(session_id="C", tokens=8000), config)
    check("Two sessions sum correctly",
          stats2["global"]["total_input_tokens"] == 13000,
          f"got {stats2['global']['total_input_tokens']}")

    for p in [sp, cp]:
        if os.path.exists(p): os.unlink(p)


def test_tier_up_detection() -> None:
    section("5. Tier-up detection and notify_level_up call")
    sp, cp = tmp_stats(), tmp_config()
    mod = load_module(sp, cp)
    config = mod.deep_merge(mod.DEFAULT_CONFIG, {})

    # Seed stats with enough tokens to be just below tier 1
    base, exp = config["xp_base"], config["xp_exp"]
    t1 = mod.xp_threshold(1, base, exp)

    stats = mod.deep_merge(mod.DEFAULT_STATS, {})
    stats["global"]["total_input_tokens"] = t1 - 1
    stats["global"]["current_tier"] = 0

    new_tier = mod.get_tier(stats["global"]["total_input_tokens"], base, exp)
    check("Just below tier 1 threshold → still tier 0", new_tier == 0)

    stats["global"]["total_input_tokens"] = t1
    new_tier = mod.get_tier(stats["global"]["total_input_tokens"], base, exp)
    check("Exactly at tier 1 threshold → tier 1", new_tier == 1)
    check("Old tier (0) < new tier (1) → level-up condition met", new_tier > 0)

    for p in [sp, cp]:
        if os.path.exists(p): os.unlink(p)


def test_quip_persistence() -> None:
    section("6. Quip persists between refreshes")
    sp, cp = tmp_stats(), tmp_config({"quip_interval": 5})
    mod = load_module(sp, cp)
    config = mod.deep_merge(mod.DEFAULT_CONFIG, {"quip_interval": 5})

    stats = mod.deep_merge(mod.DEFAULT_STATS, {})
    stats["display"]["last_quip"] = "previous quip"

    # Non-interval refresh → no new quip, last_quip unchanged
    stats["display"]["refresh_count"] = 3
    q = mod.get_quip(stats, config)
    check("Non-interval → get_quip returns None", q is None)

    # Interval refresh → new quip
    stats["display"]["refresh_count"] = 5
    q = mod.get_quip(stats, config)
    check("Interval refresh → get_quip returns a string", q is not None)
    check("Quip is non-empty", q is not None and len(q) > 0)

    # refresh_count=0 → no quip (cold start shows intro)
    stats["display"]["refresh_count"] = 0
    q = mod.get_quip(stats, config)
    check("refresh_count=0 → no quip (intro shown)", q is None)

    for p in [sp, cp]:
        if os.path.exists(p): os.unlink(p)


def test_quip_rotation() -> None:
    section("7. Quip rotates across intervals")
    sp, cp = tmp_stats(), tmp_config({"quip_interval": 5})
    mod = load_module(sp, cp)
    config = mod.deep_merge(mod.DEFAULT_CONFIG, {"quip_interval": 5})

    stats = mod.deep_merge(mod.DEFAULT_STATS, {})
    quips_seen = set()
    for rc in [5, 10, 15, 20, 25, 30, 35, 40]:
        stats["display"]["refresh_count"] = rc
        q = mod.get_quip(stats, config)
        if q:
            quips_seen.add(q)

    check("At least 2 distinct quips seen across intervals",
          len(quips_seen) >= 2, f"saw {len(quips_seen)}")

    for p in [sp, cp]:
        if os.path.exists(p): os.unlink(p)


def test_output_shape() -> None:
    section("8. Three-line output shape")
    sp, cp = tmp_stats(), tmp_config()
    mod = load_module(sp, cp)
    config = mod.deep_merge(mod.DEFAULT_CONFIG, {})
    stats = mod.deep_merge(mod.DEFAULT_STATS, {})

    data = make_payload()
    stats = mod.update_session(stats, data, config)

    session_line = mod.fmt_session_line(data, stats, config)
    global_line = mod.fmt_global_line(stats, config)

    check("Session line contains 'Lv.'", "Lv." in session_line, session_line[:80])
    check("Session line contains '%'", "%" in session_line)
    check("Session line contains 'ctx'", "ctx" in session_line)
    check("Session line contains '$'", "$" in session_line)
    check("Session line contains '↑'", "↑" in session_line)
    check("Global line contains 'Global:'", "Global:" in global_line)
    check("Global line contains 'turns'", "turns" in global_line)
    check("Global line contains 'xp →'", "xp →" in global_line)

    for p in [sp, cp]:
        if os.path.exists(p): os.unlink(p)


def test_xp_bar_colors() -> None:
    section("9. XP bar color by tier group")
    sp, cp = tmp_stats(), tmp_config()
    mod = load_module(sp, cp)

    # tier_color returns different codes for different tier groups
    colors = [mod.tier_color(t) for t in [0, 5, 10, 15, 19]]
    check("tier 0 and tier 5 have different colors", colors[0] != colors[1])
    check("tier 5 and tier 10 have different colors", colors[1] != colors[2])
    check("tier 10 and tier 15 have different colors", colors[2] != colors[3])
    check("tier 15 and tier 19 have different colors", colors[3] != colors[4])

    # fmt_xp_bar produces a bar with ANSI codes
    bar = mod.fmt_xp_bar(50.0, mod.tier_color(0))
    check("XP bar contains bracket delimiters", "[" in bar and "]" in bar)
    check("XP bar contains filled blocks", "█" in bar)
    check("XP bar contains empty blocks", "░" in bar)
    check("XP bar contains ANSI reset", "\033[0m" in bar)

    for p in [sp, cp]:
        if os.path.exists(p): os.unlink(p)


def test_tier_data_completeness() -> None:
    section("10. Tier data completeness (20 tiers)")
    sp, cp = tmp_stats(), tmp_config()
    mod = load_module(sp, cp)

    check("Exactly 20 tiers defined", len(mod.TIERS) == 20, f"got {len(mod.TIERS)}")

    for i, t in enumerate(mod.TIERS):
        prefix = f"tier[{i}]"
        check(f"{prefix} has 'name'",          bool(t.get("name")))
        check(f"{prefix} has 'symbol'",        bool(t.get("symbol")))
        check(f"{prefix} has tier_up_lines ≥1", len(t.get("tier_up_lines", [])) >= 1)
        check(f"{prefix} has ≥3 quips",        len(t.get("quips", [])) >= 3,
              f"got {len(t.get('quips', []))}")

    for p in [sp, cp]:
        if os.path.exists(p): os.unlink(p)


def test_turn_and_cost_tracking() -> None:
    section("11. Turn and cost tracking")
    sp, cp = tmp_stats(), tmp_config()
    mod = load_module(sp, cp)
    config = mod.deep_merge(mod.DEFAULT_CONFIG, {})

    stats = mod.deep_merge(mod.DEFAULT_STATS, {})
    for cost in [0.006, 0.012, 0.012, 0.018]:
        stats = mod.update_session(stats, make_payload(session_id="A", cost=cost), config)

    check("3 cost-increasing events → 3 turns",
          stats["global"]["total_turns"] == 3, f"got {stats['global']['total_turns']}")
    check("Total spend accumulates correctly",
          abs(stats["global"]["total_spend_usd"] - 0.018) < 1e-6,
          f"got {stats['global']['total_spend_usd']:.6f}")

    # Counter restart under the same session_id (resume): old total is banked
    for cost in [0.0, 0.018]:  # transient 0, then the same total: not a restart
        stats = mod.update_session(stats, make_payload(session_id="A", cost=cost), config)
    check("Cost 0 (no info) is not treated as a reset",
          "cost_base" not in stats["sessions"]["A"], f"got {stats['sessions']['A']}")
    for cost in [0.005, 0.010]:
        stats = mod.update_session(stats, make_payload(session_id="A", cost=cost), config)
    entry = stats["sessions"]["A"]
    check("Session total = banked + current after restart",
          abs(entry["cost_base"] + entry["last_cost_usd"] - 0.028) < 1e-6, f"got {entry}")
    check("Global spend counts post-restart cost exactly once",
          abs(stats["global"]["total_spend_usd"] - 0.028) < 1e-6,
          f"got {stats['global']['total_spend_usd']:.6f}")

    for p in [sp, cp]:
        if os.path.exists(p): os.unlink(p)


def test_token_history() -> None:
    section("12. Token history capped at HISTORY_LEN")
    sp, cp = tmp_stats(), tmp_config()
    mod = load_module(sp, cp)
    config = mod.deep_merge(mod.DEFAULT_CONFIG, {})

    stats = mod.deep_merge(mod.DEFAULT_STATS, {})
    for i in range(20):
        stats = mod.update_session(stats,
            make_payload(session_id=f"h{i}", tokens=i * 1000, cost=0.001 * (i+1)), config)

    history = stats["global"]["token_history"]
    check(f"Token history capped at {mod.HISTORY_LEN}",
          len(history) <= mod.HISTORY_LEN, f"len={len(history)}")
    check("History has recent values", any(v > 0 for v in history))

    for p in [sp, cp]:
        if os.path.exists(p): os.unlink(p)


def test_sparkline() -> None:
    section("13. Sparkline rendering")
    sp, cp = tmp_stats(), tmp_config()
    mod = load_module(sp, cp)

    check("Empty list → empty string",   mod.fmt_sparkline([]) == "")
    check("All zeros → spaces",          all(c == " " for c in mod.fmt_sparkline([0, 0, 0])))
    check("Increasing → rightmost = █",  mod.fmt_sparkline([1,2,3,4,5])[-1] == "█")
    check("Single value → 1 char",       len(mod.fmt_sparkline([42])) == 1)
    check("12 values → 12 chars",        len(mod.fmt_sparkline(list(range(12)))) == 12)
    check("Identical values → flat",     len(set(mod.fmt_sparkline([100]*4))) == 1)

    for p in [sp, cp]:
        if os.path.exists(p): os.unlink(p)


def test_cost_formatting() -> None:
    section("14. Cost and token formatting")
    sp, cp = tmp_stats(), tmp_config()
    mod = load_module(sp, cp)

    check("$0.123 → 3 decimals",    mod.fmt_cost(0.123)       == "$0.123")
    check("$0.00042 → 5 decimals",  mod.fmt_cost(0.00042)     == "$0.00042")
    check("$0.001 boundary",        mod.fmt_cost(0.001)       == "$0.001")
    check("1500 → '1.5k'",          mod.fmt_tokens(1500)      == "1.5k")
    check("1_500_000 → '1.5M'",     mod.fmt_tokens(1_500_000) == "1.5M")
    check("999 → '999'",            mod.fmt_tokens(999)       == "999")
    check("0 → '0'",                mod.fmt_tokens(0)         == "0")

    for p in [sp, cp]:
        if os.path.exists(p): os.unlink(p)


def test_atomic_write() -> None:
    section("15. Atomic stats write")
    sp, cp = tmp_stats(), tmp_config()
    mod = load_module(sp, cp)
    mod.STATS_PATH = sp

    stats = mod.deep_merge(mod.DEFAULT_STATS, {})
    stats["global"]["total_turns"] = 42
    mod.save_stats(stats)

    check("Stats file created",          os.path.exists(sp))
    check("No .tmp sidecar left",        not os.path.exists(sp + ".tmp"))

    with open(sp) as f:
        loaded = json.load(f)
    check("Data round-trips correctly",  loaded["global"]["total_turns"] == 42)

    with open(sp + ".tmp", "w") as f:
        f.write("garbage")
    stats["global"]["total_turns"] = 99
    mod.save_stats(stats)
    check("Stale .tmp overwritten",      not os.path.exists(sp + ".tmp"))
    with open(sp) as f:
        loaded2 = json.load(f)
    check("Post-overwrite data correct", loaded2["global"]["total_turns"] == 99)

    for p in [sp, cp]:
        if os.path.exists(p): os.unlink(p)


def test_malformed_input() -> None:
    section("16. Malformed / missing input handling")
    sp, cp = tmp_stats(), tmp_config()
    mod = load_module(sp, cp)
    config = mod.deep_merge(mod.DEFAULT_CONFIG, {})
    stats = mod.deep_merge(mod.DEFAULT_STATS, {})

    try:
        mod.update_session(stats, {}, config)
        check("Empty payload → no crash", True)
    except Exception as e:
        check("Empty payload → no crash", False, str(e))

    try:
        mod.update_session(stats, {"session_id": "x"}, config)
        check("Missing cost → no crash", True)
    except Exception as e:
        check("Missing cost → no crash", False, str(e))

    try:
        payload_nulls = {"session_id": "x", "model": None, "context_window": None, "cost": None}
        mod.update_session(stats, payload_nulls, config)
        check("Null fields → no crash", True)
    except Exception as e:
        check("Null fields → no crash", False, str(e))

    result = subprocess.run(
        [sys.executable, SCRIPT],
        input="not json at all {{{{",
        capture_output=True, text=True,
    )
    check("Bad JSON stdin → no traceback",
          "Traceback" not in result.stdout and "Traceback" not in result.stderr,
          result.stderr[:100] if result.stderr else "ok")
    check("Bad JSON stdin → still prints something",
          len(result.stdout.strip()) > 0, repr(result.stdout.strip()))

    for p in [sp, cp]:
        if os.path.exists(p): os.unlink(p)


def test_missing_config() -> None:
    section("17. Missing / corrupt config and stats")
    sp, cp = tmp_stats(), tmp_config()
    mod = load_module(sp, cp)

    loaded = mod.load_json(sp + ".missing", mod.DEFAULT_STATS)
    check("Missing stats → returns default",
          loaded["global"]["total_turns"] == 0)

    corrupt = sp + ".corrupt"
    with open(corrupt, "w") as f:
        f.write("{broken json{{")
    loaded2 = mod.load_json(corrupt, mod.DEFAULT_STATS)
    check("Corrupt stats → returns default",
          loaded2["global"]["total_turns"] == 0)
    os.unlink(corrupt)

    merged = mod.deep_merge(mod.DEFAULT_CONFIG, mod.load_json(cp + ".missing", {}))
    check("Missing config → defaults filled in",
          "xp_base" in merged and "quip_interval" in merged)

    for p in [sp, cp]:
        if os.path.exists(p): os.unlink(p)


def test_e2e_subprocess() -> None:
    section("18. End-to-end subprocess output")

    # Temp HOME: the script resolves ~/.claude, so without this the test
    # writes a fake "test" session into the real statusline_stats.json.
    home = tempfile.mkdtemp(prefix="sl_test_home_")
    os.makedirs(os.path.join(home, ".claude"))

    def run_e2e(payload: dict) -> tuple[str, int]:
        result = subprocess.run(
            [sys.executable, SCRIPT],
            input=json.dumps(payload),
            capture_output=True, text=True,
            env={**os.environ, "HOME": home},
        )
        return result.stdout, result.returncode

    out, _ = run_e2e(make_payload(cost=0.005))
    check("Output is non-empty",         len(out.strip()) > 0)
    check("Contains 'Lv.'",              "Lv." in out)
    check("Contains 'Global:'",          "Global:" in out)
    check("No Python traceback",         "Traceback" not in out)
    lines = out.strip().split("\n")
    check("Exactly 3 output lines",      len(lines) == 3, f"got {len(lines)}: {lines}")

    out2, _ = run_e2e(make_payload(used_pct=0, tokens=0, cost=0))
    check("0% context → still renders",  "Lv." in out2)

    out3, _ = run_e2e(make_payload(used_pct=100, cost=0.010))
    check("100% context → still renders","Lv." in out3)


def test_intro_quip() -> None:
    section("19. Intro quip shown on first run")
    sp, cp = tmp_stats(), tmp_config()
    mod = load_module(sp, cp)

    stats = mod.deep_merge(mod.DEFAULT_STATS, {})
    check("Default last_quip is INTRO_QUIP",
          stats["display"]["last_quip"] == mod.INTRO_QUIP)
    check("INTRO_QUIP is non-empty", len(mod.INTRO_QUIP) > 0)
    check("INTRO_QUIP contains 'NIGHT CITY'", "NIGHT CITY" in mod.INTRO_QUIP)

    for p in [sp, cp]:
        if os.path.exists(p): os.unlink(p)


# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    print(f"\n{HEAD}{'═'*60}{RST}")
    print(f"{HEAD}  statusline.py — verification test suite{RST}")
    print(f"{HEAD}{'═'*60}{RST}")

    test_xp_curve()
    test_get_tier()
    test_level_progress()
    test_token_accumulation()
    test_tier_up_detection()
    test_quip_persistence()
    test_quip_rotation()
    test_output_shape()
    test_xp_bar_colors()
    test_tier_data_completeness()
    test_turn_and_cost_tracking()
    test_token_history()
    test_sparkline()
    test_cost_formatting()
    test_atomic_write()
    test_malformed_input()
    test_missing_config()
    test_e2e_subprocess()
    test_intro_quip()

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
