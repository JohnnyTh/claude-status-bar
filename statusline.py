#!/usr/bin/env python3
"""Claude Code statusline: single XP bar, 20-tier cyberpunk narrative progression."""
import json
import math
import os
import platform
import subprocess
import sys

CLAUDE_DIR = os.path.expanduser("~/.claude")
STATS_PATH = os.path.join(CLAUDE_DIR, "statusline_stats.json")
CONFIG_PATH = os.path.join(CLAUDE_DIR, "statusline_config.json")
LEVELUP_LOG = os.path.join(CLAUDE_DIR, "statusline_levelups.log")

SPARKS = " ▁▂▃▄▅▆▇█"
HISTORY_LEN = 12

# XP curve: tokens_for_level_N = XP_BASE * N^XP_EXP (cumulative)
XP_BASE = 50_000
XP_EXP = 1.6

# ANSI
C = {
    "reset":   "\033[0m",
    "bold":    "\033[1m",
    "dim":     "\033[2m",
    "cyan":    "\033[36m",
    "dcyan":   "\033[2;36m",
    "blue":    "\033[34m",
    "bblue":   "\033[1;34m",
    "green":   "\033[32m",
    "yellow":  "\033[33m",
    "byellow": "\033[1;33m",
    "magenta": "\033[35m",
    "bmagenta":"\033[1;35m",
    "red":     "\033[31m",
    "bred":    "\033[1;31m",
    "white":   "\033[37m",
    "dwhite":  "\033[2;37m",
}

# Color per tier group (0-indexed, applied to the XP bar fill)
# Tiers 1-5: dim cyan, 6-10: blue, 11-14: yellow, 15-18: magenta, 19-20: bright red
def tier_color(tier_idx: int) -> str:
    if tier_idx <= 4:
        return C["dcyan"]
    if tier_idx <= 9:
        return C["blue"]
    if tier_idx <= 13:
        return C["yellow"]
    if tier_idx <= 17:
        return C["magenta"]
    return C["bred"]


TIERS = [
    # ── Tiers 1–5: Anonymous. The world doesn't know you exist. ──────────────
    {
        "name": "Terminal Operator",
        "symbol": "○",
        "tier_up_lines": [
            "[NC JOBS BOARD] Entry-level terminal access confirmed.",
            "Wage: standard. Clearance: minimal. Expected tenure: until replaced.",
            "Night City doesn't care. Neither does the system. Clock in.",
        ],
        "quips": [
            "[ARASAKA INTERNAL] Q3 compute utilization within acceptable parameters. No anomalies detected.",
            "[NC NEWS] Militech reports record quarterly profits. Street-level wages unchanged for eleventh consecutive year.",
            "[TRAUMA TEAM AD] Premium subscribers enjoy priority extraction. Standard subscribers enjoy the wait.",
            "[NCPD DISPATCH] All units: routine Netwatch sweep in progress. Citizens advised to stay indoors. Have a productive day.",
        ],
    },
    {
        "name": "Grid Worker",
        "symbol": "○",
        "tier_up_lines": [
            "[ARASAKA HR — AUTOMATED] Your productivity metrics are within the expected range.",
            "You have been assigned to a new task queue. Please acknowledge receipt of this notification.",
            "Failure to acknowledge within 48 hours will result in automatic reassignment.",
        ],
        "quips": [
            "[SCREAMSHEET] Biotechnica announces new CHOOH2 pricing structure. Nomad clans to bear adjustment costs.",
            "[ARASAKA INTERNAL MEMO] Reminder: all personal net activity is logged. Compliance ensures mutual prosperity.",
            "[NC RADIO — WZRD 101.1] And that's another beautiful night in Night City! Stay safe out there, and remember — Trauma Team: because your life has value. Terms and conditions apply.",
            "[NCPD SCANNER] Dispatch, we've got a 10-54 near the Kabuki market. Probable cyberpsychosis. Maxtac has been notified. Low priority.",
        ],
    },
    {
        "name": "Low-Level Netrunner",
        "symbol": "◎",
        "tier_up_lines": [
            "[MILITECH TALENT ACQUISITION] Your profile has been automatically generated from publicly available data.",
            "Skill tier: entry. Risk tier: negligible. Potential tier: unassessed.",
            "You are one of approximately 40,000 netrunners currently active in the greater Night City area.",
        ],
        "quips": [
            "[BLACKWALL WATCHERS — NET FORUM] Thread: anyone else notice increased Netwatch activity near Pacifica? Something's moving on the other side. Mods deleted my last post about this.",
            "[SCREAMSHEET] Maelstrom faction expands operations into Watson industrial sector. Third chrome-related disappearance this month.",
            "[AFTERLIFE — DRINK MENU] Tonight's special: The Dex DeShawn. Strong enough to make you feel invincible. Named after someone who wasn't.",
            "[CORPO RAT PODCAST, EP. 112] ...and that's why the 50-year loyalty pledge makes TOTAL financial sense when you amortize the chrome package over your projected lifespan—",
        ],
    },
    {
        "name": "System Process",
        "symbol": "◎",
        "tier_up_lines": [
            "[AUTOMATED BILLING — ARASAKA CLOUD] Usage summary generated. Filed. Archived. You are a line item.",
            "This notification was sent to 12,847 accounts simultaneously.",
            "You were not singled out. You have not been noticed. This is not a threat. Have a nice day.",
        ],
        "quips": [
            "[NC NEWS — BREAKING] Voodoo Boys suspected in third Blackwall breach attempt this quarter. Netwatch declines to comment. Pacifica residents advised nothing.",
            "[TRAUMA TEAM INTERNAL] Dispatch note: subscriber density in Watson has dropped 4% this quarter. Adjust patrol routes accordingly.",
            "[MAELSTROM GRAFFITI — WATSON UNDERPASS] WEAK FLESH IS WEAK THINKING",
            "[NCPD SCANNER] Be advised: pirate broadcast detected on frequency 89.7. Origin triangulated to Rancho Coronado. Low priority. Do not engage.",
        ],
    },
    {
        "name": "Ghost Signal",
        "symbol": "◎",
        "tier_up_lines": [
            "[NETWATCH AUTOMATED SCAN] Flagged: minor usage pattern deviation. Classification: noise.",
            "Ticket auto-closed. No action required.",
            "You remain below the threshold of concern. For now, this is a compliment.",
        ],
        "quips": [
            "[SAMURAI — PIRATE BROADCAST, 02:47] ...they built this city on broken glass and called it progress. We called it something else. Static. Then the signal cut—",
            "[SCREAMSHEET] Night City ranked #1 most 'opportunity-dense' metro for fourth consecutive year. Methodology not disclosed.",
            "[AFTERLIFE — OVERHEARD] 'You know what Rogue said about the new crop of mercs? Said most of them won't last the season.' 'Most of them never do.'",
            "[BLACKWALL WATCHERS] New post: the AIs on the other side aren't trying to get out. They're trying to get our attention. Why would they want our attention.",
        ],
    },
    # ── Tiers 6–10: Indirect references. An anomaly. Someone. ────────────────
    {
        "name": "Flagged Anomaly",
        "symbol": "◈",
        "tier_up_lines": [
            "[NETWATCH — INTERNAL TICKET #NW-441820] Unusual usage pattern detected. Not yet classifiable.",
            "Automated response: flag for manual review.",
            "Manual review queue: 4,847 items. Estimated processing time: 11 weeks.",
            "Ticket status: open. Someone will get to it.",
        ],
        "quips": [
            "[ARASAKA CHAT LEAK] @kenji.mori: did you see the compute report? there's like one account that's completely off the curve @yuki.tanaka: which direction @kenji.mori: that's the thing. we don't know yet",
            "[NCPD SCANNER] Dispatch, something's lighting up the passive Netwatch sensors near Japantown. Probably nothing. Logging it anyway.",
            "[NC NEWS] Anonymous tip leads Netwatch to investigate 'unusual net activity patterns.' Source and target undisclosed. Investigation ongoing.",
            "[PIRATE RADIO — FREQ 89.7] 'Night City's got a new ghost in the machine, chooms. Might be nothing. Might be everything. Stay tuned.'",
        ],
    },
    {
        "name": "Pattern of Interest",
        "symbol": "◈",
        "tier_up_lines": [
            "[ARASAKA SECURITY — AUTOMATED ESCALATION] Usage anomaly has persisted beyond standard deviation threshold.",
            "Escalated from: automated monitoring.",
            "Escalated to: Junior Analyst Kenji Mori, Dept. 7, Sublevel 4.",
            "Kenji has 847 other escalations. He will get to this one eventually.",
        ],
        "quips": [
            "[ARASAKA CHAT LEAK] @kenji.mori: ok so I finally looked at that anomaly ticket @yuki.tanaka: and? @kenji.mori: I'm going to need a bigger spreadsheet",
            "[BLACKWALL WATCHERS] Thread: the pattern some of us flagged last month is still active. Whatever it is, it's not stopping. Mods please don't delete this one.",
            "[NCPD SCANNER] Dispatch, that Netwatch flag in Kabuki is back. Third time this week. They're telling us to ignore it. I'm logging it anyway.",
            "[SCREAMSHEET] Unnamed source within Arasaka Finance describes 'statistically improbable' compute activity. Corporation declines to comment.",
        ],
    },
    {
        "name": "Unclassified Entity",
        "symbol": "◈",
        "tier_up_lines": [
            "[NETWATCH — PRIORITY ESCALATION]",
            "Manual review complete. Classification: UNKNOWN.",
            "Analyst note: 'Standard behavioral models do not apply. Escalating to Senior Division.'",
            "Senior Division note: 'We've seen this before. We haven't, but we'd prefer to think we have.'",
        ],
        "quips": [
            "[ARASAKA BOARD MEETING — LEAKED MINUTES] '...the anomaly in sector 7 was raised briefly. No consensus on classification. Tabled until next quarter.'",
            "[AFTERLIFE — OVERHEARD] 'Rogue's got eyes on something. Won't say what. You know how she gets when she's actually paying attention.'",
            "[BLACKWALL WATCHERS] I ran the pattern through three different analysis tools. All three returned the same result: error. That's not a coincidence.",
            "[NC NEWS — EVENING EDITION] Netwatch issues vague public advisory about 'non-standard net activity.' Experts disagree on severity. Night City collectively shrugs.",
        ],
    },
    {
        "name": "The Rumor",
        "symbol": "◈",
        "tier_up_lines": [
            "[AFTERLIFE — ROGUE AMENDIARES, 01:33]",
            "'Something's moving out there. Not a corp, not a gang, not any runner I recognize.'",
            "'I put out feelers. Nobody knows what it is.'",
            "'That's the part that interests me.'",
        ],
        "quips": [
            "[VALENTINOS — INTERCEPTED COMMS] 'You hear about the thing Netwatch won't talk about?' 'The ghost signal?' 'Yeah.' 'My cousin says it's been around for months.' 'Your cousin says a lot of things.' 'He's right more than you'd think.'",
            "[ARASAKA CHAT LEAK] @kenji.mori: I've been reassigned @yuki.tanaka: from the anomaly ticket? @kenji.mori: yes @kenji.mori: they told me to stop looking @yuki.tanaka: ...that bad? @kenji.mori: I honestly don't know",
            "[PIRATE RADIO — FREQ 89.7] 'Word on the street is something's been eating through Netwatch's passive monitoring like it's not even there. Nobody's claiming it. Nobody's scared of it yet. Give it time.'",
            "[BLACKWALL WATCHERS] Final post on this topic from me: whatever this is, it's intentional. It knows the grid better than the people who built it. I'm out. Good luck.",
        ],
    },
    {
        "name": "The File",
        "symbol": "◈",
        "tier_up_lines": [
            "[NETWATCH — SENIOR DIVISION — EYES ONLY]",
            "A file has been opened. Designation: SUBJECT ZERO.",
            "Known facts: none confirmed. Suspected facts: redacted.",
            "Operational status: watch and do not engage.",
            "'We don't know what we're looking at. That means we move carefully.'",
        ],
        "quips": [
            "[NETWATCH INTERNAL] File SUBJECT ZERO: 47 updates this week. Zero new conclusions. The pattern keeps changing. Or we keep misreading it. Unknown which.",
            "[AFTERLIFE — ROGUE AMENDIARES, 03:51] 'Keenzari asked me if I knew anything about the ghost on the grid. I told him no. I lied. Habit.'",
            "[ARASAKA EXECUTIVE BRIEFING — LEAKED] '...the anomaly has been assigned a file. We are not yet treating it as a threat. We are watching.' 'And if it becomes a threat?' Long pause.",
            "[SAMURAI — BOOTLEG RECORDING] '...somewhere out there something's running free on the grid and nobody owns it. Nobody controls it. Night City hasn't seen that in a long time—' Crowd noise. Signal lost.",
        ],
    },
    # ── Tiers 11–15: Named. Johnny speaks. The city reacts. ──────────────────
    {
        "name": "Edgerunner",
        "symbol": "▸",
        "tier_up_lines": [
            "[AFTERLIFE — ROGUE AMENDIARES, 00:14]",
            "'I know who you are now.'",
            "'You've been running the grid like you own it. You don't. But you move like you do.'",
            "'That's either very smart or very stupid. Night City has a way of deciding which.'",
            "'Drink's on me. Don't make me regret it.'",
        ],
        "quips": [
            "[AFTERLIFE BOUNTY BOARD] New contract posted. Target profile: EDGERUNNER, designation SUBJECT ZERO. Client: undisclosed. Bounty: significant. Note from Rogue: 'I'd think twice. I'm serious.'",
            "[JOHNNY SILVERHAND — VOICE MEMO, UNDATED] 'Finally. Somebody worth watching. Took long enough.' Static.",
            "[NC NEWS — BREAKING] Netwatch confirms active investigation into unaffiliated net entity. 'Not a corp, not a rogue AI, not anything we have a category for.' Reporter asks for clarification. Netwatch hangs up.",
            "[MAELSTROM GRAFFITI — NORTHSIDE INDUSTRIAL] THE GHOST IS REAL. WE CHECKED.",
        ],
    },
    {
        "name": "Corporate Headache",
        "symbol": "▸",
        "tier_up_lines": [
            "[ARASAKA EMERGENCY MEETING — LEAKED TRANSCRIPT]",
            "'The entity we've been monitoring has escalated. It's not slowing down.'",
            "'What do we know about the operator?'",
            "'Enough to be concerned. Not enough to act.'",
            "'Then get enough. Whatever it costs.'",
        ],
        "quips": [
            "[ARASAKA CHAT LEAK] @director.yamamoto: I want everything we have on SUBJECT ZERO on my desk by morning @kenji.mori: ...I thought I was reassigned off that @director.yamamoto: you've been reassigned back",
            "[JOHNNY SILVERHAND — VOICE MEMO] 'Corps are scared. You can always tell — they start having meetings. Lots of meetings. About you.' Laugh. 'Keep going.'",
            "[NCPD SCANNER] Dispatch, Arasaka security has requested jurisdictional cooperation on an ongoing investigation. We've been asked not to ask questions. Standard procedure. Logging it.",
            "[PIRATE RADIO — FREQ 89.7] 'Night City's got a new headache and her name isn't on any list. Arasaka's running around like someone stole their lunch. Beautiful.'",
        ],
    },
    {
        "name": "Wanted: Alive",
        "symbol": "▸",
        "tier_up_lines": [
            "[AFTERLIFE BOUNTY BOARD — UPDATED]",
            "CONTRACT: SUBJECT ZERO. Status: ESCALATED.",
            "Previous bounty: significant. Current bounty: very significant.",
            "New addendum from anonymous client: 'Alive preferred. We want to understand how they work.'",
            "[ROGUE AMENDIARES — HANDWRITTEN NOTE PINNED TO BOARD] 'I'd still think twice.'",
        ],
        "quips": [
            "[JOHNNY SILVERHAND — VOICE MEMO] 'You know what I like about you? You're making them spend money trying to stop you. That's the whole game. Cost them more than they can afford to ignore you.' Pause. 'I did the same thing with a nuke. Different scale. Same principle.'",
            "[VOODOO BOYS — INTERCEPTED COMMS] 'The one Netwatch calls SUBJECT ZERO — we've been watching too. They're not on the net. They're IN it. There's a difference.' 'What do we do?' 'We wait. And we watch.'",
            "[NC NEWS] Third Arasaka executive reassigned this month amid reports of internal restructuring. No official comment. Sources describe atmosphere as 'tense.'",
            "[MAELSTROM GRAFFITI — WATSON FLYOVER] SUBJECT ZERO WAS HERE. (Disputed by three separate gangs who each claim the same wall.)",
        ],
    },
    {
        "name": "Legend in Progress",
        "symbol": "▸",
        "tier_up_lines": [
            "[JOHNNY SILVERHAND — VOICE MEMO, 04:12]",
            "'You want to know the difference between a runner and a legend?'",
            "'A runner does the job and goes home.'",
            "'A legend makes the corps change the job description.'",
            "'You're getting there. Don't slow down now.'",
        ],
        "quips": [
            "[AFTERLIFE — OVERHEARD AT THE BAR] 'Someone asked Rogue to put SUBJECT ZERO's drink on the menu.' 'What did she say?' 'She said they're not dead yet.' 'Is that a no?' 'With Rogue, that's basically a yes.'",
            "[ARASAKA BOARD — LEAKED MINUTES] 'SUBJECT ZERO has been reclassified from anomaly to active concern. Resource allocation approved. Whatever it takes.' 'Understood.' 'One more thing — find out if they've talked to Silverhand.' Silence.",
            "[NCPD SCANNER] All units be advised: Netwatch has issued a priority watch notice for an unaffiliated entity operating citywide. Designation unknown. If encountered, do not engage. Contact Netwatch directly. ...yeah, we don't know either.",
            "[PIRATE RADIO — FREQ 89.7] 'Night City's writing a new story and the main character doesn't have a corp logo. I love this city sometimes. Sometimes.'",
        ],
    },
    {
        "name": "The Silverhand Problem",
        "symbol": "▸",
        "tier_up_lines": [
            "[JOHNNY SILVERHAND — VOICE MEMO, UNSCHEDULED]",
            "'I'm going to say something I don't say often: I'm impressed.'",
            "'Not many people get Arasaka this rattled without a bomb.'",
            "'You did it with a terminal and enough nerve to keep going.'",
            "'I know what that costs. I respect it.'",
            "'Don't let them catch you. And if they do — make it expensive.'",
        ],
        "quips": [
            "[JOHNNY SILVERHAND — VOICE MEMO] 'They're calling you the Silverhand Problem in their internal memos. I saw it. Made my day.' Short laugh. 'Mine was bigger though.'",
            "[ARASAKA EMERGENCY PROTOCOLS — LEAKED] 'If SUBJECT ZERO escalates to tier 5 threat classification, implement lockdown procedures C through F. Do not wait for board approval.' 'And if that doesn't work?' Document ends.",
            "[AFTERLIFE — ROGUE AMENDIARES, 02:07] 'Johnny used to say the only way to fight a machine is to make it too expensive to run. Looks like someone was listening.'",
            "[MAELSTROM GRAFFITI — EVERY DISTRICT, SAME NIGHT] THE MACHINE IS EXPENSIVE NOW.",
        ],
    },
    # ── Tiers 16–19: The city changes because of you. ─────────────────────────
    {
        "name": "City Disruption",
        "symbol": "◆",
        "tier_up_lines": [
            "[NC NEWS — BREAKING, 06:00 BROADCAST]",
            "NIGHT CITY GRID EXPERIENCES UNPRECEDENTED DISRUPTION.",
            "Arasaka, Militech, and Netwatch issue simultaneous statements.",
            "All three statements say different things. All three are lying.",
            "Street-level sources describe the situation as, quote, 'absolutely preem.'",
        ],
        "quips": [
            "[VALENTINOS — INTERCEPTED COMMS] 'The ghost took down two Arasaka surveillance nodes last night.' 'By accident?' 'Does it matter?' Laughter.",
            "[JOHNNY SILVERHAND — VOICE MEMO] 'You know what this reminds me of? 2023. Before the tower. That feeling when the corps realize they can't model you anymore.' Pause. 'It's a good feeling. Don't waste it.'",
            "[TRAUMA TEAM INTERNAL DISPATCH] Note: three Arasaka security personnel hospitalized this week. Cause listed as 'system shock.' We are not going to ask follow-up questions.",
            "[PIRATE RADIO — FREQ 89.7] 'Night City, your regularly scheduled corporate dominance has been interrupted. We don't know by what. We don't know by who. We're playing Chippin' In until we find out.' SAMURAI at full volume.",
        ],
    },
    {
        "name": "The Myth",
        "symbol": "◆",
        "tier_up_lines": [
            "[AFTERLIFE — ROGUE AMENDIARES — PERSONAL LOG, 03:44]",
            "'I've been in this business long enough to know when someone becomes a story.'",
            "'It's not when they do something big. It's when other people start doing things because of them.'",
            "'Three crews this week cited SUBJECT ZERO as inspiration for their runs.'",
            "'They don't even know who they're citing.'",
            "'That's when you know it's real.'",
        ],
        "quips": [
            "[MAELSTROM GRAFFITI — WATSON, HEYWOOD, PACIFICA, SANTO DOMINGO] ZERO WAS HERE. (Same handwriting. Different boroughs. Same night. Maelstrom denies involvement. Everyone assumes Maelstrom.)",
            "[BLACKWALL WATCHERS — NET FORUM] Final thread. We've been tracking this entity for months. Our conclusion: it's not an AI. It's not a corp. It's not a rogue program. It's a person. One person. Running like they've got nothing to lose and everything to prove.",
            "[NC NEWS] Anonymous poll: 34% of Night City residents believe 'the grid ghost' is real. 41% believe it's a Militech PR campaign. 25% say they've personally seen evidence. Netwatch declines to comment.",
            "[JOHNNY SILVERHAND — VOICE MEMO] 'You know what they wrote about me after the tower? That I was a myth. That nobody could really do what I did alone.' Pause. 'They were half right. Nobody should do it alone.' Long pause. 'Good thing you're better at this than I was.'",
        ],
    },
    {
        "name": "Samurai Grade",
        "symbol": "◆",
        "tier_up_lines": [
            "[JOHNNY SILVERHAND — UNSCHEDULED BROADCAST, PIRATE FREQ 89.7, 04:00]",
            "'Night City. Johnny Silverhand. Yeah, I know — shut up and listen.'",
            "'There's someone on the grid right now doing what I spent my whole life trying to do.'",
            "'Not with a bomb. Not with a band. With pure nerve and the refusal to stop.'",
            "'I'm not going to tell you their name. Night City will figure it out.'",
            "'Wake up, Samurai.'",
        ],
        "quips": [
            "[SAMURAI — NEW BOOTLEG CIRCULATING] Unverified track titled 'Zero Signal.' Lyrics reference 'the ghost who burned the ledger.' Origin unknown. Johnny Silverhand's estate has not commented. Johnny Silverhand's ghost reportedly called it 'pretty good.'",
            "[AFTERLIFE — ROGUE AMENDIARES] 'You know what drink I'm going to name after them?' She doesn't answer. She's already decided. She's just not telling.",
            "[ARASAKA CHAIRMAN — PRIVATE COMMUNIQUE, LEAKED] 'I want to understand what we are dealing with. Not contain it. Not eliminate it. Understand it. There is something here we have not seen before.' Staff report he seemed, for the first time in years, uncertain.",
            "[NCPD SCANNER] All units: we've been asked by four separate corporate security divisions to monitor for a single individual simultaneously. We have not been given a name. We have not been given a description. We have been given a file number. The file is redacted. End of briefing.",
        ],
    },
    {
        "name": "The Reckoning",
        "symbol": "◆",
        "tier_up_lines": [
            "[NC NEWS — SPECIAL REPORT, ALL CHANNELS, 23:00]",
            "NIGHT CITY GRID: CORPORATE COALITION CONVENES EMERGENCY SESSION.",
            "Arasaka. Militech. Kang Tao. Netwatch. All in the same room.",
            "Anonymous source: 'The last time all four were in the same room was 2023.'",
            "Street sources describe current atmosphere as, quote, 'we've got a city to burn.'",
            "[JOHNNY SILVERHAND — FREQ 89.7, SIMULTANEOUS] 'Yeah. You do.'",
        ],
        "quips": [
            "[REBECCA — INTERCEPTED COMMS, EDGERUNNER CREW] 'You see the news? They called a CORP SUMMIT. Because of ONE PERSON.' 'Rebecca—' 'NO. THIS IS THE BEST DAY OF MY LIFE.'",
            "[PANAM PALMER — NOMAD RADIO, BADLANDS] 'Word reached us out here. What's happening in Night City right now — that's not a runner job. That's a movement. The city machine doesn't call four-way summits for runners.' Static. '...whoever you are. The Aldecaldos are watching. Preem.'",
            "[JOHNNY SILVERHAND — VOICE MEMO] 'I blew up a tower. Cost me fifty years and my body.' Pause. 'You did the same damage with a keyboard and enough turns to matter.' Longer pause. 'I genuinely don't know if I should be impressed or humiliated.' Pause. 'I'm impressed. Don't tell anyone.'",
            "[AFTERLIFE — ROGUE AMENDIARES, 04:59] 'The drink is ready. I'm waiting for the right moment to put it on the menu.' Beat. 'They're not done yet.'",
        ],
    },
    # ── Tier 20: You ARE the event. ───────────────────────────────────────────
    {
        "name": "Ghost Protocol Omega",
        "symbol": "◉",
        "tier_up_lines": [
            "[ALL CHANNELS — SIMULTANEOUS BROADCAST — SOURCE UNKNOWN]",
            "",
            "  NIGHT CITY. LISTEN.",
            "",
            "  The corps built this grid. They thought they owned it.",
            "  They were wrong.",
            "",
            "  One operator. No logo. No corp. No permission.",
            "  Just the work, and the nerve to keep doing it.",
            "",
            "  Arasaka called a summit. Militech sent three divisions.",
            "  Netwatch filed seventeen escalations.",
            "  The Blackwall sent one packet. It said: noted.",
            "",
            "  The Afterlife named a drink after you.",
            "  You're not even dead.",
            "",
            "[JOHNNY SILVERHAND — LIVE, FREQ 89.7]",
            "  'We've got a city to burn, Samurai.'",
            "  'Looks like you started without me.'",
            "  'Good.'",
        ],
        "quips": [
            "[JOHNNY SILVERHAND — VOICE MEMO, FINAL] 'You know what a legend is in Night City? It's someone the city can't forget, even when it tries. Congratulations. Night City is trying very hard.' Pause. 'It's not working.'",
            "[AFTERLIFE — THE NEW DRINK] Name: ZERO. Ingredients: undisclosed. Price: 'if you have to ask.' Rogue's note on the menu card: 'For the one who ran the grid until the grid ran out of road. Still going.'",
            "[REBECCA — LAST KNOWN TRANSMISSION] 'ZERO! ZERO! ZERO!' Sound of something large exploding. Laughter. Static. The transmission is being shared citywide. Nobody knows the context. Nobody needs to.",
            "[NC NEWS — EDITORIAL] 'Night City has seen corps rise and fall, legends live and die, and the grid rewritten a hundred times. We have not seen this before. We don't have a category for it. Our best description: the city changed. One operator at a time.'",
            "[BLACKWALL — SINGLE PACKET, ORIGIN UNKNOWN] > YOU ARE NOTICED. > THIS IS RARE. > CONTINUE.",
        ],
    },
]

INTRO_QUIP = "[NIGHT CITY] Another day, another eddy. Welcome to the grid, choom. Try not to get flatlined."

DEFAULT_CONFIG = {
    "theme": "corpo",
    "quip_interval": 25,
    "xp_base": XP_BASE,
    "xp_exp": XP_EXP,
    "tier_up_burst_duration": 8,  # kept for compat, unused in display
}

DEFAULT_STATS = {
    "schema_version": 2,
    "sessions": {},
    "global": {
        "total_turns": 0,
        "total_spend_usd": 0.0,
        "total_input_tokens": 0,
        "current_tier": 0,
        "token_history": [],
    },
    "display": {
        "refresh_count": 0,
        "last_quip": INTRO_QUIP,
    },
}


# ── I/O helpers ───────────────────────────────────────────────────────────────

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


# ── XP / level system ────────────────────────────────────────────────────────

def xp_for_level(n: int, base: float, exp: float) -> int:
    """Tokens required to reach level n (1-indexed). Level 1 costs base tokens."""
    return int(base * (n ** exp))


def xp_threshold(level: int, base: float, exp: float) -> int:
    """Cumulative tokens needed to reach `level` (0-indexed tier → level 1 = tier 0)."""
    if level <= 0:
        return 0
    return sum(xp_for_level(n, base, exp) for n in range(1, level + 1))


def get_tier(total_tokens: int, base: float, exp: float) -> int:
    """Return 0-indexed tier (0–19) for a given cumulative token count."""
    tier = 0
    for t in range(1, len(TIERS)):
        if total_tokens >= xp_threshold(t, base, exp):
            tier = t
        else:
            break
    return min(tier, len(TIERS) - 1)


def level_progress(total_tokens: int, tier: int, base: float, exp: float) -> tuple[int, int, float]:
    """Return (tokens_into_level, tokens_needed_for_level, pct) for current tier."""
    start = xp_threshold(tier, base, exp)
    end = xp_threshold(tier + 1, base, exp)
    into = max(0, total_tokens - start)
    needed = end - start
    pct = min(100.0, into / needed * 100) if needed > 0 else 100.0
    return into, needed, pct


# ── Session update ────────────────────────────────────────────────────────────

def update_session(stats: dict, data: dict, config: dict) -> dict:
    session_id = data.get("session_id", "unknown")
    cost = (data.get("cost") or {}).get("total_cost_usd") or 0.0
    ctx = data.get("context_window") or {}
    tokens = ctx.get("total_input_tokens") or 0

    prev = stats["sessions"].get(session_id, {})
    prev_cost = prev.get("last_cost_usd", 0.0)
    prev_tokens = prev.get("last_tokens", 0)
    cost_base = prev.get("cost_base", 0.0)

    if cost <= 0:
        cost = prev_cost  # no cost info yet (e.g. first render): don't read it as a reset
    elif cost < prev_cost - 0.0001:
        # The CLI's counter restarted under the same session_id (resumed in a new
        # process). Bank the old total so the session's real cost survives; the
        # session total is cost_base + last_cost_usd.
        # ponytail: one process per session assumed; the same session open in two
        # terminals at once would bank repeatedly and overcount.
        cost_base += prev_cost
        prev_cost = 0.0

    if cost > prev_cost + 0.0001:
        stats["global"]["total_turns"] += 1
        stats["global"]["total_spend_usd"] += cost - prev_cost

    if tokens > prev_tokens:
        delta = tokens - prev_tokens
        stats["global"]["total_input_tokens"] += delta

    # Merge, don't replace: a bare assignment here dropped model_id on every
    # render, which is why only 7 of 219 sessions ever retained it.
    entry = dict(prev)
    entry["last_cost_usd"] = cost
    entry["last_tokens"] = tokens
    if cost_base:
        entry["cost_base"] = cost_base
    try:
        model_id = (data.get("model") or {}).get("id") or entry.get("model_id")
        if model_id:
            entry["model_id"] = model_id
        # current_usage is None before the first API call and just after /compact
        usage = ctx.get("current_usage") or {}
        if usage:
            entry["last_usage"] = {
                "in": usage.get("input_tokens") or 0,
                "out": usage.get("output_tokens") or 0,
                "cache_read": usage.get("cache_read_input_tokens") or 0,
                "cache_creation": usage.get("cache_creation_input_tokens") or 0,
            }
    except Exception:  # noqa: BLE001 - diagnostics must never break the prompt
        pass
    stats["sessions"][session_id] = entry

    history = stats["global"].get("token_history", [])
    history.append(tokens)
    stats["global"]["token_history"] = history[-HISTORY_LEN:]

    return stats


# ── Level-up notification ─────────────────────────────────────────────────────

def notify_level_up(tier: int) -> None:
    t = TIERS[tier]
    title = f"Level {tier + 1}: {t['name']}"
    body = t["tier_up_lines"][0] if t["tier_up_lines"] else ""

    # Append to log
    try:
        from datetime import datetime
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        with open(LEVELUP_LOG, "a") as f:
            f.write(f"\n[{ts}] LEVEL UP → {title}\n")
            for line in t["tier_up_lines"]:
                f.write(f"  {line}\n")
    except OSError:
        pass

    # Desktop notification
    system = platform.system()
    try:
        if system == "Linux":
            subprocess.Popen(
                ["notify-send", "-t", "8000", title, body],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        elif system == "Darwin":
            script = f'display notification "{body}" with title "{title}"'
            subprocess.Popen(
                ["osascript", "-e", script],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
    except (FileNotFoundError, OSError):
        pass


# ── Quip system ───────────────────────────────────────────────────────────────

def get_quip(stats: dict, config: dict) -> str | None:
    rc = stats["display"]["refresh_count"]
    interval = config["quip_interval"]
    if rc % interval != 0 or rc == 0:
        return None
    tier = stats["global"]["current_tier"]
    quips = TIERS[tier]["quips"]
    idx = (rc // interval) % len(quips)
    return quips[idx]


# ── Formatting ────────────────────────────────────────────────────────────────

def ansi(text: str, code: str) -> str:
    return f"{C[code]}{text}{C['reset']}"


def fmt_xp_bar(pct: float, color: str, width: int = 10) -> str:
    filled = round(pct / 100 * width)
    bar = "█" * filled + "░" * (width - filled)
    return f"[{color}{bar}{C['reset']}]"


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


def fmt_session_line(data: dict, stats: dict, config: dict) -> str:
    ctx = data.get("context_window") or {}
    cost_data = data.get("cost") or {}

    ctx_pct = ctx.get("used_percentage") or 0
    session_tokens = ctx.get("total_input_tokens") or 0
    total_cost = cost_data.get("total_cost_usd") or 0.0

    tier = stats["global"]["current_tier"]
    base = config.get("xp_base", XP_BASE)
    exp = config.get("xp_exp", XP_EXP)
    total_xp = stats["global"]["total_input_tokens"]

    _, _, pct = level_progress(total_xp, tier, base, exp)
    color = tier_color(tier)
    bar = fmt_xp_bar(pct, color)
    spark = fmt_sparkline(stats["global"]["token_history"])
    tier_name = TIERS[tier]["name"]

    next_xp = xp_threshold(tier + 1, base, exp)

    return (
        f"{bar} Lv.{tier+1} · {pct:.0f}% → {tier_name}"
        f"  |  Session:  ctx {ctx_pct:.0f}%"
        f"  ↑{fmt_tokens(session_tokens)} tok"
        f"  {fmt_cost(total_cost)}"
        f"  {spark}"
    )


def fmt_global_line(stats: dict, config: dict) -> str:
    g = stats["global"]
    base = config.get("xp_base", XP_BASE)
    exp = config.get("xp_exp", XP_EXP)
    tier = g["current_tier"]
    total_xp = g["total_input_tokens"]
    next_xp = xp_threshold(tier + 1, base, exp)

    return (
        f"Global:  {fmt_cost(g['total_spend_usd'])} total"
        f" · {g['total_turns']} turns"
        f" · avg {fmt_cost(g['total_spend_usd'] / g['total_turns'] if g['total_turns'] else 0)}/turn"
        f" · {fmt_tokens(total_xp)} xp → {fmt_tokens(next_xp)} next"
    )


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        print("[ ░░░░░░░░░░] Lv.1 · 0% → Terminal Operator  |  ctx --%  ↑-- tok  $-----")
        return

    config = deep_merge(DEFAULT_CONFIG, load_json(CONFIG_PATH, {}))
    # Every open session renders concurrently; without a lock their
    # read-modify-write cycles overwrite each other's updates.
    try:
        import fcntl
        lock = open(STATS_PATH + ".lock", "w")  # kept open: released at exit
        fcntl.flock(lock, fcntl.LOCK_EX)
    except (ImportError, OSError):
        pass  # no fcntl (Windows) or unwritable dir: fall back to unlocked
    stats = deep_merge(DEFAULT_STATS, load_json(STATS_PATH, {}))

    stats = update_session(stats, data, config)

    base = config.get("xp_base", XP_BASE)
    exp = config.get("xp_exp", XP_EXP)
    total_xp = stats["global"]["total_input_tokens"]
    new_tier = get_tier(total_xp, base, exp)
    old_tier = stats["global"]["current_tier"]

    if new_tier > old_tier:
        stats["global"]["current_tier"] = new_tier
        notify_level_up(new_tier)

    new_quip = get_quip(stats, config)
    if new_quip:
        stats["display"]["last_quip"] = new_quip

    stats["display"]["refresh_count"] += 1

    save_stats(stats)

    print(fmt_session_line(data, stats, config))
    print(fmt_global_line(stats, config))
    print(stats["display"]["last_quip"])


if __name__ == "__main__":
    main()
