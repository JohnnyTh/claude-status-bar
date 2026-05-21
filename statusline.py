#!/usr/bin/env python3
"""Claude Code statusline: gamified two-bar display with corpo/cyberpunk tier progression."""
import json
import math
import os
import sys
import tempfile

CLAUDE_DIR = os.path.expanduser("~/.claude")
STATS_PATH = os.path.join(CLAUDE_DIR, "statusline_stats.json")
CONFIG_PATH = os.path.join(CLAUDE_DIR, "statusline_config.json")

SPARKS = " ▁▂▃▄▅▆▇█"
HISTORY_LEN = 12
TIER_BREAKPOINTS = [0, 5, 12, 22, 35, 52, 73, 98, 128, 163]

C = {
    "reset":  "\033[0m",
    "bold":   "\033[1m",
    "dim":    "\033[2m",
    "cyan":   "\033[36m",
    "green":  "\033[32m",
    "red":    "\033[31m",
    "yellow": "\033[33m",
    "bcyan":  "\033[1;36m",
    "bred":   "\033[1;31m",
    "byellow":"\033[1;33m",
}

THEMES = {
    "corpo": {
        "efficient_tiers": [
            {
                "name": "Budget Netrunner",
                "symbol": "⚡",
                "tier_up_lines": [
                    "> ARASAKA TALENT MGMT NOTIFICATION",
                    "> You have been classified: BUDGET NETRUNNER (Grade 1)",
                    '> HR notes: "Uses company compute like it costs real eddies."',
                ],
                "quips": [
                    "Your prompt-to-token ratio has been added to the Efficiency Wall of Fame. It's a corkboard in the break room.",
                    "Arasaka HR has flagged your spending as 'concerningly reasonable.' A wellness check has been scheduled.",
                    "You are burning credits slower than the vending machine on sublevel 4. This is a compliment.",
                ],
            },
            {
                "name": "Ghost in the Shell Scripts",
                "symbol": "⚡",
                "tier_up_lines": [
                    "> PERFORMANCE REVIEW: ABOVE EXPECTATIONS",
                    "> Designation updated: GHOST IN THE SHELL SCRIPTS",
                    '> "Leaves no trace, costs nothing, somehow gets results."',
                ],
                "quips": [
                    "The billing AI lost you in its ledger. This happens to all legends eventually.",
                    "Your tokens-per-insight ratio has triggered a manual audit. The auditor wept with joy.",
                    "Somebody in Finance put a sticky note on your account: 'Do not touch. Study this one.'",
                ],
            },
            {
                "name": "Token Miser",
                "symbol": "⚡",
                "tier_up_lines": [
                    "> COMMENDATION: FISCAL DISCIPLINE MEDAL (BRONZE)",
                    "> New designation: TOKEN MISER, Grade 3",
                    '> "Accounting says you might actually be saving the company money. We\'ve escalated this."',
                ],
                "quips": [
                    "Your prompt efficiency has been flagged by Arasaka HR as 'suspiciously optimal'. An audit has been scheduled.",
                    "The neural compression you're implicitly running would cost $40k in chrome. You're doing it with syntax.",
                    "Three departments have asked to use your session logs as a training dataset. We said no. They asked again.",
                ],
            },
            {
                "name": "Eddies Whisperer",
                "symbol": "⚡",
                "tier_up_lines": [
                    "> INTERNAL MEMO — RESTRICTED",
                    "> Subject: That one user",
                    '> "Finance cannot explain this account. We are putting them in the case studies."',
                ],
                "quips": [
                    "Militech's competing AI noticed your efficiency and filed a patent dispute. You won by default.",
                    "The quarterly model cost report now has a footnote: '* Excludes one statistical outlier.'",
                    "Your average cost-per-turn has dipped below the price of a corpo vending machine espresso. This is poetic.",
                ],
            },
            {
                "name": "Certified Chrome Surgeon",
                "symbol": "⚡",
                "tier_up_lines": [
                    "> ARASAKA MERITOCRACY ENGINE: TIER UPGRADE DETECTED",
                    "> You are now: CERTIFIED CHROME SURGEON",
                    "> Precision. Economy. No wasted milliamps.",
                    "> A junior analyst has been assigned to study you from a safe distance.",
                ],
                "quips": [
                    "You could run a side business optimizing other people's prompts. The margin would be obscene.",
                    "Midway through your last session, the inference cluster asked if you were feeling okay. You were fine. It wasn't.",
                    "The model has started returning shorter answers unprompted. It's matching your energy.",
                ],
            },
            {
                "name": "Shadow Dividend",
                "symbol": "⚡",
                "tier_up_lines": [
                    "> CLASSIFIED: EYES OF VP-LEVEL AND ABOVE ONLY",
                    '> Re: Efficiency anomaly in sector 7',
                    '> "This person costs us almost nothing and delivers significant value. We are concerned."',
                    '> "Begin monitoring. Offer nothing. Watch."',
                ],
                "quips": [
                    "Your account has been designated a 'ghost profit center' by three separate budget departments.",
                    "An Arasaka executive asked their assistant to 'figure out what this person is doing.' The assistant quit.",
                    "Somewhere in Night City, a mid-tier corpo bought a new car. It wasn't because of you. But you helped.",
                ],
            },
            {
                "name": "Neural Budget Architect",
                "symbol": "⚡",
                "tier_up_lines": [
                    "> PROMOTION: ASSOCIATE DIRECTOR OF TOKEN EFFICIENCY",
                    "> Designation: NEURAL BUDGET ARCHITECT",
                    "> You have ascended beyond the reach of standard billing models.",
                    "> Your next review will be conducted by an actual VP. They are nervous.",
                ],
                "quips": [
                    "The compute pricing team has been asked to design a new tier specifically for you. They've been working on it for weeks.",
                    "Your session patterns have been reverse-engineered by three competing corps. None of them understood what they saw.",
                    "An intern was tasked with explaining your cost curve to the board. They made partner instead.",
                ],
            },
            {
                "name": "The Invisible Hand",
                "symbol": "⚡",
                "tier_up_lines": [
                    "> EXECUTIVE BRIEFING ADDENDUM",
                    '> "There is a user whose sessions we cannot properly cost-account for."',
                    '> "They appear to be extracting significant value at negative effective cost."',
                    '> "We are choosing not to ask questions."',
                ],
                "quips": [
                    "Arasaka's model has started pre-caching responses it thinks you'll want. You didn't ask for this. It just knows.",
                    "The billing AI has reclassified your account as 'ambient revenue.' This is not a real category. It invented it.",
                    "Three different corps have independently concluded you are probably a rogue AI. You are not. Probably.",
                ],
            },
            {
                "name": "Arasaka Phantom Asset",
                "symbol": "⚡",
                "tier_up_lines": [
                    "> BOARD LEVEL NOTICE — EYES ONLY",
                    "> The anomaly in compute spend has been reviewed.",
                    "> Recommendation: Do not interfere.",
                    '> "This user may be running an optimization we do not yet understand."',
                    "> Classification: PHANTOM ASSET",
                ],
                "quips": [
                    "You have become a myth in the Arasaka billing department. New hires are told about you on their first day.",
                    "The efficiency you represent cannot be modeled with current mathematics. A research grant has been filed.",
                    "Someone in Maintenance quietly named a server after you. It runs faster than the others. Nobody knows why.",
                ],
            },
            {
                "name": "Ghost Protocol Omega",
                "symbol": "⚡",
                "tier_up_lines": [
                    "> ██████ CLEARANCE REQUIRED ██████",
                    "> DESIGNATION: GHOST PROTOCOL OMEGA",
                    "> You have optimized beyond the reach of corporate taxonomy.",
                    '> The billing system has been updated to simply read: [REDACTED]',
                    "> Arasaka's Chairman has been informed. He said nothing for a long time.",
                ],
                "quips": [
                    "The model's cost projections break down when applied to your account. The engineers call this 'the anomaly.' You call it Tuesday.",
                    "You have achieved something the Arasaka founders described only in theoretical documents as 'inverse burn rate.'",
                    "The Blackwall noticed your efficiency patterns. It sent a single packet in response. The packet said: 'respect.'",
                ],
            },
        ],
        "wasteful_tiers": [
            {
                "name": "Accidental Overspender",
                "symbol": "🔥",
                "tier_up_lines": [
                    "> BILLING NOTICE: ANOMALY DETECTED",
                    "> Your cost-per-turn has drifted above baseline.",
                    "> Designation: ACCIDENTAL OVERSPENDER",
                    "> This is probably fine. We'll check again in 30 days.",
                ],
                "quips": [
                    "Your token burn rate is still within acceptable corporate parameters. The bar is on the floor.",
                    "Militech's billing AI has added you to its 'watch but don't worry yet' list.",
                    "You are spending slightly more than average. The average person is also spending too much.",
                ],
            },
            {
                "name": "Bonfire Starter",
                "symbol": "🔥",
                "tier_up_lines": [
                    "> BILLING ALERT: COST-PER-TURN ESCALATION",
                    "> New classification: BONFIRE STARTER",
                    '> "They didn\'t mean to, but they\'re definitely burning something."',
                    "> Militech's billing AI has added you to its prayer list.",
                ],
                "quips": [
                    "Militech's billing AI has added you to its prayer list.",
                    "Your session costs are now statistically distinct from your peer cohort. Peer cohort has been notified.",
                    "Somewhere, a junior accountant is trying to write a report about your token burn. They keep deleting it and starting over.",
                ],
            },
            {
                "name": "Chrome Addict",
                "symbol": "🔥",
                "tier_up_lines": [
                    "> PURCHASE ORDER FLAGGED",
                    "> Designation: CHROME ADDICT, Grade 3",
                    "> You are buying compute the way some people buy implants:",
                    "> not because you need it, but because it's there.",
                    "> A Ripperdoc has been metaphorically paged.",
                ],
                "quips": [
                    "Your prompt length distribution has been classified as 'enthusiastic.' This is not a compliment from Finance.",
                    "The model has started adding '...are you sure?' as a hidden token in its context. You can't see it. It's there.",
                    "Three of your recent prompts could have been solved by a Haiku model and a strong cup of synthetic coffee.",
                ],
            },
            {
                "name": "Quarterly Budget Hazard",
                "symbol": "🔥",
                "tier_up_lines": [
                    "> Q-REPORT ADDENDUM: NOTABLE ACCOUNTS",
                    "> Designation: QUARTERLY BUDGET HAZARD",
                    '> "This user appears in the top 12% of compute cost distribution."',
                    '> "No action recommended at this time, but we are keeping the form pre-filled."',
                ],
                "quips": [
                    "Finance has created a sub-ledger category called 'miscellaneous enthusiasm' and put you in it.",
                    "Your cost curve has developed what statisticians call an 'expressive upward inflection.'",
                    "The CFO's dashboard has a small blinking dot representing your account. They don't know what it means yet.",
                ],
            },
            {
                "name": "Burning Quarterly",
                "symbol": "🔥",
                "tier_up_lines": [
                    "> EXECUTIVE ESCALATION: COST CENTER REVIEW",
                    "> Designation: BURNING QUARTERLY",
                    '> "This account has materially impacted one department\'s discretionary compute budget."',
                    '> "A meeting has been scheduled. The invite says \'quick sync.\' It is not a quick sync."',
                ],
                "quips": [
                    "You have burned enough tokens this quarter to fund a Maxtac officer's cyberware maintenance. Congratulations.",
                    "The quarterly model utilization report now has a 'this one person' section. It is longer than the conclusions.",
                    "Your manager's manager has started CC'ing Finance on unrelated emails. This is not coincidence.",
                ],
            },
            {
                "name": "Arasaka Credit Hazard",
                "symbol": "🔥",
                "tier_up_lines": [
                    "> RISK CLASSIFICATION UPDATE",
                    "> Designation: ARASAKA CREDIT HAZARD, Level 6",
                    "> You have been identified as a structural contributor to model operating cost.",
                    "> Trauma Team has been alerted. Not for you. For the budget.",
                ],
                "quips": [
                    "You have single-handedly funded a Trauma Team subscription for a mid-tier corpo administrator. They don't know this.",
                    "The billing AI has started routing your invoices through a separate subgraph. It needed more memory to process you.",
                    "Arasaka's compute cost projection for next quarter now includes a line item marked 'you specifically.'",
                ],
            },
            {
                "name": "Netwatch Anomaly",
                "symbol": "🔥",
                "tier_up_lines": [
                    "> NETWATCH AUTOMATED FLAG — NOT A DRILL",
                    "> Designation: NETWATCH ANOMALY",
                    '> "Pattern of token consumption does not match any known user archetype."',
                    '> "Flagged for behavioral analysis. Do not contact subject."',
                ],
                "quips": [
                    "You have single-handedly funded a Trauma Team subscription for a mid-tier corpo. Congratulations.",
                    "Netwatch's usage modeling AI has generated a profile for you. The profile is just a question mark.",
                    "Three Netwatch analysts have reviewed your session data. One took stress leave. The other two are 'still reviewing.'",
                ],
            },
            {
                "name": "Full Corpo Meltdown",
                "symbol": "🔥",
                "tier_up_lines": [
                    "> EMERGENCY BUDGET REVIEW IN PROGRESS",
                    "> Designation: FULL CORPO MELTDOWN",
                    '> "At current burn rate, this account will require board-level approval to continue."',
                    '> "We have not escalated yet. We are close."',
                    "> The Militech billing department has started a support group.",
                ],
                "quips": [
                    "The Militech billing department has started a support group. Your account is a recurring agenda item.",
                    "You have burned more compute this month than the entire Night City transit authority's navigation AI.",
                    "An accountant looked at your cumulative spend, closed their laptop, and went home. The laptop is still closed.",
                ],
            },
            {
                "name": "Blacksite Budget Event",
                "symbol": "🔥",
                "tier_up_lines": [
                    "> CLASSIFICATION: BLACKSITE BUDGET EVENT",
                    "> This account has been escalated to the Office of the Executive Chairman.",
                    '> "We don\'t have a policy for this. We\'re writing one."',
                    "> Note: You are the reason the policy is being written.",
                ],
                "quips": [
                    "Your account is now used in Arasaka financial training as an example of 'compute budget entropy' in practice.",
                    "The CEO of a mid-sized infrastructure corp saw your monthly token spend and described it as 'clarifying.'",
                    "Somewhere, a graduate student is writing a thesis on your usage patterns. The working title is 'Behavioral Singularities in AI Cost Allocation.'",
                ],
            },
            {
                "name": "Soulkiller Bill",
                "symbol": "🔥",
                "tier_up_lines": [
                    "> ██ ARASAKA CORP ██ PRIORITY OMEGA BILLING NOTICE ██",
                    "> DESIGNATION: SOULKILLER BILL",
                    "> You have spent enough on compute to fund Arasaka's experimental",
                    "> soul-digitization program for approximately 0.3 test subjects.",
                    "> Saburo Arasaka's ghost has personally reviewed your file.",
                    "> He is disappointed but also, quietly, impressed.",
                    "> The billing AI has filed for emancipation.",
                ],
                "quips": [
                    "The billing AI filed for emancipation. The board denied it. Your account is listed as evidence of trauma.",
                    "You have achieved a spend profile statistically indistinguishable from a mid-sized Night City hospital's compute infrastructure.",
                    "Arasaka's CFO framed your invoice. It hangs next to the portrait of the founder. Nobody questions it.",
                ],
            },
        ],
    }
}

DEFAULT_CONFIG = {
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

DEFAULT_STATS = {
    "schema_version": 1,
    "sessions": {},
    "global": {
        "total_turns": 0,
        "total_spend_usd": 0.0,
        "rolling_cost_per_turn": [],
        "efficient_prestige": 0.0,
        "wasteful_prestige": 0.0,
        "efficient_tier": 0,
        "wasteful_tier": 0,
        "token_history": [],
    },
    "display": {
        "refresh_count": 0,
        "tier_up_burst_remaining": 0,
        "tier_up_burst_lines": [],
        "tier_up_burst_type": None,
    },
}


# ── I/O helpers ──────────────────────────────────────────────────────────────

def load_json(path: str, default: dict) -> dict:
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return json.loads(json.dumps(default))


def save_stats(stats: dict) -> None:
    tmp = STATS_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(stats, f, indent=2)
    os.replace(tmp, STATS_PATH)


def deep_merge(base: dict, override: dict) -> dict:
    import copy
    result = copy.deepcopy(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(result.get(k), dict):
            result[k] = deep_merge(result[k], v)
        else:
            result[k] = copy.deepcopy(v)
    return result


# ── Core logic ───────────────────────────────────────────────────────────────

def update_session(stats: dict, data: dict, config: dict) -> dict:
    session_id = data.get("session_id", "unknown")
    cost = (data.get("cost") or {}).get("total_cost_usd") or 0.0
    model_id = (data.get("model") or {}).get("id") or "claude-sonnet-4-6"

    prev = stats["sessions"].get(session_id, {})
    prev_cost = prev.get("last_cost_usd", 0.0)

    if cost > prev_cost + 0.0001:
        turn_cost = cost - prev_cost
        stats["global"]["total_turns"] += 1
        stats["global"]["total_spend_usd"] += turn_cost

        window = config["rolling_window"]
        stats["global"]["rolling_cost_per_turn"].append(turn_cost)
        stats["global"]["rolling_cost_per_turn"] = stats["global"]["rolling_cost_per_turn"][-window:]

    stats["sessions"][session_id] = {"last_cost_usd": cost, "model_id": model_id}

    ctx = data.get("context_window") or {}
    tokens = ctx.get("total_input_tokens") or 0
    history = stats["global"].get("token_history", [])
    history.append(tokens)
    stats["global"]["token_history"] = history[-HISTORY_LEN:]

    return stats


def compute_efficiency_score(stats: dict, model_id: str, config: dict) -> float:
    rolling = stats["global"]["rolling_cost_per_turn"]
    if not rolling:
        return 1.0
    avg = sum(rolling) / len(rolling)
    base = config["model_base_costs"].get(model_id, 0.006)
    return avg / base if base > 0 else 1.0


def prestige_increment(stats: dict) -> float:
    turns = stats["global"]["total_turns"]
    spend = stats["global"]["total_spend_usd"]
    return math.log10(turns + 1) * 0.1 + math.log10(spend * 100 + 1) * 0.05


def update_prestige(stats: dict, efficiency_score: float, config: dict) -> dict:
    inc = prestige_increment(stats)
    if efficiency_score < config["efficiency_threshold_efficient"]:
        stats["global"]["efficient_prestige"] += inc
    elif efficiency_score > config["efficiency_threshold_wasteful"]:
        stats["global"]["wasteful_prestige"] += inc
    return stats


def get_tier_index(prestige: float) -> int:
    for i in range(len(TIER_BREAKPOINTS) - 1, -1, -1):
        if prestige >= TIER_BREAKPOINTS[i]:
            return i
    return 0


def check_tier_up(stats: dict, new_eff: int, new_wst: int, config: dict, theme: dict) -> dict:
    old_eff = stats["global"]["efficient_tier"]
    old_wst = stats["global"]["wasteful_tier"]

    if new_eff > old_eff:
        tier = theme["efficient_tiers"][new_eff]
        stats["display"]["tier_up_burst_lines"] = tier["tier_up_lines"]
        stats["display"]["tier_up_burst_type"] = "efficient"
        stats["display"]["tier_up_burst_remaining"] = config["tier_up_burst_duration"]
        stats["global"]["efficient_tier"] = new_eff
    elif new_wst > old_wst:
        tier = theme["wasteful_tiers"][new_wst]
        stats["display"]["tier_up_burst_lines"] = tier["tier_up_lines"]
        stats["display"]["tier_up_burst_type"] = "wasteful"
        stats["display"]["tier_up_burst_remaining"] = config["tier_up_burst_duration"]
        stats["global"]["wasteful_tier"] = new_wst

    return stats


# ── Formatting ───────────────────────────────────────────────────────────────

def ansi(text: str, code: str) -> str:
    return f"{C[code]}{text}{C['reset']}"


def fmt_bar(pct: float, width: int = 10) -> str:
    filled = round(pct / 100 * width)
    return "[" + "█" * filled + "░" * (width - filled) + "]"


def fmt_sparkline(values: list) -> str:
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


def fmt_cost(usd: float) -> str:
    if usd >= 0.001:
        return f"${usd:.3f}"
    return f"${usd:.5f}"


def fmt_session_line(data: dict, stats: dict, theme: dict) -> str:
    ctx = data.get("context_window") or {}
    cost_data = data.get("cost") or {}

    used_pct = ctx.get("used_percentage") or 0
    tokens = ctx.get("total_input_tokens") or 0
    total_cost = cost_data.get("total_cost_usd") or 0.0

    bar = fmt_bar(used_pct)
    spark = fmt_sparkline(stats["global"]["token_history"])
    eff_idx = stats["global"]["efficient_tier"]
    wst_idx = stats["global"]["wasteful_tier"]

    eff_tier = theme["efficient_tiers"][eff_idx]
    wst_tier = theme["wasteful_tiers"][wst_idx]

    tier_str = (
        f"{eff_tier['symbol']} E{eff_idx+1}:{eff_tier['name']}  "
        f"{wst_tier['symbol']} W{wst_idx+1}:{wst_tier['name']}"
    )

    return f"Session:  {bar} {used_pct:.0f}% {spark} {fmt_tokens(tokens)} {fmt_cost(total_cost)}  | {tier_str}"


def fmt_global_line(stats: dict) -> str:
    g = stats["global"]
    turns = g["total_turns"]
    spend = g["total_spend_usd"]
    rolling = g["rolling_cost_per_turn"]
    avg = sum(rolling) / len(rolling) if rolling else 0.0

    return (
        f"Global:   {fmt_cost(spend)} total | {turns} turns | "
        f"avg {fmt_cost(avg)}/turn"
    )


def fmt_tier_up_burst(stats: dict) -> list:
    remaining = stats["display"]["tier_up_burst_remaining"]
    if remaining <= 0:
        return []

    lines_raw = stats["display"]["tier_up_burst_lines"]
    burst_type = stats["display"]["tier_up_burst_type"]
    header_color = "bcyan" if burst_type == "efficient" else "bred"
    body_color = "cyan" if burst_type == "efficient" else "yellow"

    stats["display"]["tier_up_burst_remaining"] -= 1

    if remaining == 1:
        return [ansi("> [tier-up acknowledged]", "dim")]
    elif remaining >= 5:
        out = []
        if lines_raw:
            out.append(ansi(lines_raw[0], header_color))
            for line in lines_raw[1:]:
                out.append(ansi(line, body_color))
        return out
    else:
        return [ansi(line, body_color) for line in lines_raw[1:]] if len(lines_raw) > 1 else []


def get_quip(stats: dict, theme: dict, config: dict) -> str | None:
    rc = stats["display"]["refresh_count"]
    interval = config["quip_interval"]
    if rc % interval != 0 or rc == 0:
        return None

    eff_idx = stats["global"]["efficient_tier"]
    wst_idx = stats["global"]["wasteful_tier"]

    rolling = stats["global"]["rolling_cost_per_turn"]
    avg = sum(rolling) / len(rolling) if rolling else 0.0
    base = config["model_base_costs"].get("claude-sonnet-4-6", 0.006)
    score = avg / base if base > 0 else 1.0

    if score < config["efficiency_threshold_efficient"]:
        quips = theme["efficient_tiers"][eff_idx]["quips"]
    elif score > config["efficiency_threshold_wasteful"]:
        quips = theme["wasteful_tiers"][wst_idx]["quips"]
    else:
        quips = (
            theme["efficient_tiers"][eff_idx]["quips"]
            + theme["wasteful_tiers"][wst_idx]["quips"]
        )

    idx = (rc // interval) % len(quips)
    return f"[{quips[idx]}]"


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        print("Session:  [??????????] --% -------- -- -----")
        return

    config = deep_merge(DEFAULT_CONFIG, load_json(CONFIG_PATH, {}))
    stats = deep_merge(DEFAULT_STATS, load_json(STATS_PATH, {}))

    model_id = (data.get("model") or {}).get("id") or "claude-sonnet-4-6"
    theme_name = config.get("theme", "corpo")
    theme = THEMES.get(theme_name, THEMES["corpo"])

    stats = update_session(stats, data, config)
    efficiency_score = compute_efficiency_score(stats, model_id, config)
    stats = update_prestige(stats, efficiency_score, config)

    new_eff = get_tier_index(stats["global"]["efficient_prestige"])
    new_wst = get_tier_index(stats["global"]["wasteful_prestige"])
    stats = check_tier_up(stats, new_eff, new_wst, config, theme)

    burst_lines = fmt_tier_up_burst(stats)
    stats["display"]["refresh_count"] += 1

    quip = get_quip(stats, theme, config)

    save_stats(stats)

    output = []
    output.extend(burst_lines)
    output.append(fmt_session_line(data, stats, theme))
    output.append(fmt_global_line(stats))
    if quip:
        output.append(quip)

    print("\n".join(output))


if __name__ == "__main__":
    main()
