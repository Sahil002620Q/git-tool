import json
import os
from datetime import datetime, timezone, timedelta

CONFIG_FILE = "config.json"


# ──────────────────────────────────────────────
#  Config helpers
# ──────────────────────────────────────────────

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            cfg = json.load(f)
        # back-fill any new keys added in later versions
        cfg.setdefault("ignore_list", [])
        cfg.setdefault("username", "")
        return cfg
    return {"username": "", "ignore_list": []}


def save_config(config):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)


# ──────────────────────────────────────────────
#  Activity helpers
# ──────────────────────────────────────────────

def is_active_recently(events, days=7):
    """
    Return True if any event in *events* occurred within the last *days* days.
    events: list of GitHub event dicts (each has "created_at" in ISO-8601).
    """
    if not events:
        return False
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    for evt in events:
        created = evt.get("created_at", "")
        if not created:
            continue
        try:
            dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            if dt >= cutoff:
                return True
        except ValueError:
            continue
    return False


# ──────────────────────────────────────────────
#  Follower-back likelihood scoring
# ──────────────────────────────────────────────

def score_candidate(user_info, events, my_followers_set):
    """
    Score how likely *user_info* is to follow back.
    Higher is better. Returns (score, reason_list).

    Scoring rubric:
      +3  following >= followers  (generous follower)
      +2  following > followers * 1.5  (very generous)
      +2  active within last 3 days
      +1  active within last 7 days  (exclusive with +2 above)
      +1  per shared follower overlap with my followers (max +5)
    """
    score = 0
    reasons = []

    followers = user_info.get("followers", 0)
    following = user_info.get("following", 0)

    if following >= followers:
        score += 3
        reasons.append("following ≥ followers (+3)")
    if following > followers * 1.5:
        score += 2
        reasons.append("following > 1.5× followers (+2)")

    cutoff_3 = datetime.now(timezone.utc) - timedelta(days=3)
    cutoff_7 = datetime.now(timezone.utc) - timedelta(days=7)
    active_3 = False
    active_7 = False
    for evt in events:
        created = evt.get("created_at", "")
        if not created:
            continue
        try:
            dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            if dt >= cutoff_3:
                active_3 = True
            if dt >= cutoff_7:
                active_7 = True
        except ValueError:
            continue

    if active_3:
        score += 2
        reasons.append("active in last 3 days (+2)")
    elif active_7:
        score += 1
        reasons.append("active in last 7 days (+1)")

    # overlap bonus
    login = user_info.get("login", "")
    # my_followers_set is passed in; overlap is detected elsewhere if needed
    # placeholder — overlap logic is computed in main.py using pre-fetched sets

    return score, reasons


def is_likely_to_follow_back(user_info):
    """
    Quick boolean check: candidate ratio must pass before deeper scoring.
    True if followers ≤ following  (they follow generously).
    """
    followers = user_info.get("followers", 0)
    following = user_info.get("following", 0)
    return following >= followers


def is_high_ratio(user_info):
    """
    True if followers > following — an account unlikely to follow back
    (celebrity / org / influencer pattern).
    """
    followers = user_info.get("followers", 0)
    following = user_info.get("following", 0)
    return followers > following


# ──────────────────────────────────────────────
#  CLI display helpers
# ──────────────────────────────────────────────

def print_table(headers, rows, col_widths=None):
    """
    Print a simple padded table.
    headers: list of column header strings
    rows: list of lists (same length as headers)
    col_widths: optional list of int widths (auto-computed if None)
    """
    if col_widths is None:
        col_widths = [len(h) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                col_widths[i] = max(col_widths[i], len(str(cell)))

    sep = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+"
    fmt = "|" + "|".join(f" {{:<{w}}} " for w in col_widths) + "|"

    print(sep)
    print(fmt.format(*headers))
    print(sep)
    for row in rows:
        print(fmt.format(*[str(c) for c in row]))
    print(sep)


def ask_int(prompt, default, minimum=0, maximum=None):
    """
    Prompt the user for an integer.  Returns *default* on empty input.
    """
    while True:
        raw = input(prompt).strip()
        if raw == "":
            return default
        if raw.isdigit():
            val = int(raw)
            if minimum is not None and val < minimum:
                print(f"  Please enter at least {minimum}.")
                continue
            if maximum is not None and val > maximum:
                print(f"  Please enter at most {maximum}.")
                continue
            return val
        print("  Invalid input — please enter a number.")
