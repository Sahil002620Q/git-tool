import os
import time
from dotenv import load_dotenv

from api_handler import (
    get_data,
    follow_user,
    unfollow_user,
    get_user_info,
    get_user_events,
    get_following_of,
    get_rate_limit,
)
from utils import (
    load_config,
    save_config,
    is_active_recently,
    score_candidate,
    is_likely_to_follow_back,
    is_high_ratio,
    print_table,
    ask_int,
)

# ─────────────────────────────────────────────────────────────
#  Bootstrap
# ─────────────────────────────────────────────────────────────
load_dotenv()
# Use a mutable container so setup_account() can refresh TOKEN in-session
_TOKEN = [os.getenv("GITHUB_TOKEN") or ""]

def get_token():
    return _TOKEN[0]

def set_token(t):
    _TOKEN[0] = t

FOLLOW_DELAY  = 0.6   # seconds between API write calls
SCORE_MIN     = 3     # minimum score to include a candidate in auto-follow


# ─────────────────────────────────────────────────────────────
#  Shared helpers
# ─────────────────────────────────────────────────────────────

def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")


def warn_no_token():
    if not get_token():
        print("\n  ⚠  No GITHUB_TOKEN found — you are limited to 60 API calls/hour")
        print("     and CANNOT follow/unfollow without a token.")
        print("     Use option 5 → Setup Account & Token to add one.\n")


def require_username(config):
    """Return True if username is set, else print message and return False."""
    if not config.get("username"):
        input("\n  ⚠  Username not set. Go to 'Change Username' first.\n"
              "  Press Enter to return...")
        return False
    return True


def show_rate_limit():
    remaining, reset_ts = get_rate_limit(get_token())
    if remaining is not None:
        reset_str = time.strftime("%H:%M:%S", time.localtime(reset_ts))
        print(f"  API rate limit: {remaining} calls remaining (resets at {reset_str})")


# ─────────────────────────────────────────────────────────────
#  1. View Non-Followers  (original feature, polished)
# ─────────────────────────────────────────────────────────────

def view_non_followers(config):
    if not require_username(config):
        return

    warn_no_token()
    print("\n  Fetching your following & followers ...")
    username   = config["username"]
    following  = get_data(username, "following", get_token())
    followers  = get_data(username, "followers", get_token())
    ignore_set = set(config.get("ignore_list", []))

    not_following_back = sorted((following - followers) - ignore_set)

    clear_screen()
    print(f"=== USERS NOT FOLLOWING YOU BACK ({len(not_following_back)}) ===")
    if not not_following_back:
        print("  🎉 Everyone you follow is following you back!")
    else:
        for i, user in enumerate(not_following_back, 1):
            print(f"  {i:03d}. {user}")

    input("\n  Press Enter to return to menu …")


# ─────────────────────────────────────────────────────────────
#  2. Auto-Follow Smart Users
# ─────────────────────────────────────────────────────────────

def auto_follow_smart(config):
    clear_screen()
    print("=== AUTO-FOLLOW SMART USERS ===\n")

    if not require_username(config):
        return
    if not get_token():
        warn_no_token()
        input("  Press Enter to return ...")
        return

    import random

    username   = config["username"]
    ignore_set = set(config.get("ignore_list", []))

    # How many to follow
    batch = ask_int("  How many accounts to follow in this session? [default 10]: ",
                    default=10, minimum=1)

    # ── Derived limits — keeps scan time proportional to batch ──
    # Source accounts to scan: batch x 3, clamped between 5 and 20
    max_sources    = max(5, min(batch * 3, 20))
    # Max candidates to evaluate: batch x 12, minimum 50
    max_candidates = max(50, batch * 12)
    # Stop scoring once this many good candidates are found
    target_scored  = batch * 2   # small buffer for ranking

    print(f"\n  Step 1/4 - Fetching your current following & followers ...")
    my_following = get_data(username, "following", get_token())
    my_followers = get_data(username, "followers", get_token())

    # ── Step 2: Build candidate pool (capped) ───────────────────
    # Shuffle so we don't always scan the same source accounts
    source_accounts = list(my_followers)
    random.shuffle(source_accounts)
    source_accounts = source_accounts[:max_sources]

    print(f"  Step 2/4 - Scanning {len(source_accounts)} source account(s) for candidates ...")
    candidate_set = set()
    for i, follower_login in enumerate(source_accounts, 1):
        their_following = get_following_of(follower_login, get_token(), max_pages=2)
        candidate_set.update(their_following)
        print(f"    [{i}/{len(source_accounts)}] Scanned {follower_login:<25}  "
              f"{len(candidate_set)} raw candidates", end="\r")

    print()  # newline after \r

    # Remove already-following, ignored, self
    candidate_set -= my_following
    candidate_set -= ignore_set
    candidate_set.discard(username)

    if not candidate_set:
        print("\n  No new candidates found. Try running again later.")
        input("\n  Press Enter to return ...")
        return

    # ── Randomly sample down to max_candidates before scoring ───
    candidate_list = list(candidate_set)
    if len(candidate_list) > max_candidates:
        random.shuffle(candidate_list)
        candidate_list = candidate_list[:max_candidates]
        print(f"  (Pool trimmed to {max_candidates} random candidates for speed)")

    total = len(candidate_list)
    print(f"  Step 3/4 - Scoring up to {total} candidate(s) "
          f"(stops early once {target_scored} good ones are found) ...")

    # ── Step 3: Score with early exit ───────────────────────────
    scored    = []
    processed = 0

    for login in candidate_list:
        processed += 1
        print(f"    [{processed}/{total}] Evaluating {login:<28}  "
              f"found {len(scored)}/{target_scored} good", end="\r")

        info = get_user_info(login, get_token())
        if not info:
            continue

        # Hard filter 1: ratio (no extra API call)
        if not is_likely_to_follow_back(info):
            continue

        # Hard filter 2: active in last 7 days (1 extra API call)
        events = get_user_events(login, get_token(), limit=10)
        if not is_active_recently(events, days=7):
            continue

        sc, reasons = score_candidate(info, events, my_followers)
        if sc >= SCORE_MIN:
            scored.append((sc, login, info, reasons))

        # Early exit once we have enough good candidates
        if len(scored) >= target_scored:
            print(f"\n  Found {len(scored)} good candidates - stopping early "
                  f"(checked {processed}/{total}).")
            break

    if not scored:
        print(f"\n\n  No suitable candidates found after checking {processed} accounts.")
        print("  Tips:")
        print("    - Grow your follower base so more candidates appear")
        print("    - Try again later; activity status changes daily")
        input("\n  Press Enter to return ...")
        return

    # Sort by score desc, keep top batch
    scored.sort(key=lambda x: x[0], reverse=True)
    to_follow = scored[:batch]

    # ── Step 4: Preview & confirm ────────────────────────────────
    clear_screen()
    print(f"=== AUTO-FOLLOW PREVIEW  ({len(to_follow)} candidates) ===\n")
    rows = []
    for rank, (sc, login, info, reasons) in enumerate(to_follow, 1):
        followers_c = info.get("followers", "?")
        following_c = info.get("following", "?")
        rows.append([rank, login, followers_c, following_c, sc, " | ".join(reasons)])

    print_table(
        ["#", "Username", "Followers", "Following", "Score", "Why"],
        rows,
    )

    print()
    confirm = input(f"  Follow these {len(to_follow)} accounts? [y/N]: ").strip().lower()
    if confirm != "y":
        print("  Cancelled.")
        input("\n  Press Enter to return ...")
        return

    # Execute follows
    print()
    ok = 0
    failed = []
    for _, login, _, _ in [(s, l, i, r) for s, l, i, r in to_follow]:
        success = follow_user(login, get_token())
        if success:
            ok += 1
            print(f"  + Followed  {login}")
        else:
            failed.append(login)
            print(f"  x Failed    {login}")
        time.sleep(FOLLOW_DELAY)


    print(f"\n  Done — followed {ok}/{len(to_follow)} accounts.")
    if failed:
        print(f"  Failed: {', '.join(failed)}")

    show_rate_limit()
    input("\n  Press Enter to return to menu …")


# ─────────────────────────────────────────────────────────────
#  3. Bulk Unfollow
# ─────────────────────────────────────────────────────────────

def _confirm_and_unfollow(candidates, label):
    """Show preview → confirm → execute unfollows for a list of logins."""
    if not candidates:
        print(f"\n  No accounts found matching: {label}")
        input("  Press Enter to return …")
        return

    total_avail = len(candidates)
    print(f"\n  Found {total_avail} accounts in category: {label}")

    batch = ask_int(
        f"  How many to unfollow? [0 = all {total_avail}, default 20]: ",
        default=20, minimum=0,
    )
    if batch == 0:
        batch = total_avail

    targets = candidates[:batch]

    # Preview
    clear_screen()
    print(f"=== BULK UNFOLLOW PREVIEW  ({len(targets)} accounts | {label}) ===\n")
    for i, login in enumerate(targets, 1):
        print(f"  {i:03d}. {login}")

    print()
    confirm = input(f"  Unfollow these {len(targets)} accounts? [y/N]: ").strip().lower()
    if confirm != "y":
        print("  Cancelled.")
        input("\n  Press Enter to return …")
        return

    # Execute
    print()
    ok = 0
    failed = []
    for login in targets:
        success = unfollow_user(login, get_token())
        if success:
            ok += 1
            print(f"  ✓ Unfollowed  {login}")
        else:
            failed.append(login)
            print(f"  ✗ Failed      {login}")
        time.sleep(FOLLOW_DELAY)

    print(f"\n  Done — unfollowed {ok}/{len(targets)} accounts.")
    if failed:
        print(f"  Failed: {', '.join(failed)}")

    show_rate_limit()
    input("\n  Press Enter to return to menu …")


def bulk_unfollow(config):
    if not require_username(config):
        return
    if not get_token():
        warn_no_token()
        input("  Press Enter to return ...")
        return

    username   = config["username"]
    ignore_set = set(config.get("ignore_list", []))

    while True:
        clear_screen()
        print("=== BULK UNFOLLOW ===\n")
        print("  Who do you want to unfollow?\n")
        print("  1. Non-followers          (you follow them, they don't follow back)")
        print("  2. High-ratio accounts    (followers >> following — unlikely to reciprocate)")
        print("  3. Back to Main Menu")
        print()
        choice = input("  Select: ").strip()

        if choice == "1":
            print("\n  Fetching following & followers ...")
            following = get_data(username, "following", get_token())
            followers = get_data(username, "followers", get_token())
            candidates = sorted((following - followers) - ignore_set)
            _confirm_and_unfollow(candidates, "Non-followers")

        elif choice == "2":
            print("\n  Fetching your following list ...")
            following = get_data(username, "following", get_token())
            following -= ignore_set

            print(f"  Checking follower ratios for {len(following)} accounts ...")
            high_ratio = []
            checked = 0
            for login in following:
                checked += 1
                print(f"    [{checked}/{len(following)}] {login:<30}", end="\r")
                info = get_user_info(login, get_token())
                if info and is_high_ratio(info):
                    high_ratio.append(login)
            print()
            high_ratio.sort()
            _confirm_and_unfollow(high_ratio, "followers > following")

        elif choice == "3":
            break


# ─────────────────────────────────────────────────────────────
#  4. Manage Ignore List  (unchanged logic, refreshed style)
# ─────────────────────────────────────────────────────────────

def manage_ignore_list(config):
    while True:
        clear_screen()
        print("=== MANAGE IGNORE LIST ===\n")
        ignored = config.get("ignore_list", [])
        if ignored:
            print(f"  Currently ignored ({len(ignored)}):")
            for u in sorted(ignored):
                print(f"    • {u}")
        else:
            print("  (ignore list is empty)")

        print()
        print("  1. Add user")
        print("  2. Remove user")
        print("  3. Back to Main Menu")
        print()
        choice = input("  Select: ").strip()

        if choice == "1":
            user = input("  Enter GitHub username to ignore: ").strip()
            if user and user not in ignored:
                ignored.append(user)
                config["ignore_list"] = ignored
                save_config(config)
                print(f"  ✓ Added '{user}' to ignore list.")
            elif user in ignored:
                print(f"  '{user}' is already ignored.")
            time.sleep(0.8)

        elif choice == "2":
            user = input("  Enter GitHub username to remove: ").strip()
            if user in ignored:
                ignored.remove(user)
                config["ignore_list"] = ignored
                save_config(config)
                print(f"  ✓ Removed '{user}' from ignore list.")
            else:
                print(f"  '{user}' is not in the ignore list.")
            time.sleep(0.8)

        elif choice == "3":
            break


# ─────────────────────────────────────────────────────────────
#  5. Setup Account & Token
# ─────────────────────────────────────────────────────────────

def setup_account(config):
    """Walk the user through setting their GitHub username and Personal Access Token."""
    clear_screen()
    print("=== SETUP ACCOUNT & TOKEN ===\n")

    # ── Step 1: Username ────────────────────────────────────
    current_user = config.get("username") or "(not set)"
    print(f"  Current username : {current_user}")
    new_username = input("  Enter GitHub username [Enter to keep current]: ").strip()
    if new_username:
        config["username"] = new_username
        save_config(config)
        print(f"  OK Username set to '{new_username}'.")
    else:
        print(f"  Keeping username: {current_user}")

    # ── Step 2: Token instructions ──────────────────────────
    print()
    print("  ─" * 19)
    print("  HOW TO GET YOUR GITHUB PERSONAL ACCESS TOKEN")
    print("  ─" * 19)
    print()
    print("  Step 1. Open your browser and go to:")
    print("          https://github.com/settings/tokens/new")
    print()
    print("  Step 2. Sign in if prompted.")
    print()
    print("  Step 3. Fill in the form:")
    print("           Note      : e.g.  GitHub Follower Manager")
    print("           Expiration: choose 90 days or No expiration")
    print()
    print("  Step 4. Under 'Select scopes', tick ONLY:")
    print("           [x]  user  > follow  (lets the tool follow/unfollow)")
    print("                OR tick the top-level  'user'  box for all user scopes")
    print()
    print("  Step 5. Scroll down and click  'Generate token'.")
    print()
    print("  Step 6. COPY the token shown (starts with  ghp_...)")
    print("          It will NOT be shown again!")
    print()
    print("  ─" * 19)

    # Try to open the browser automatically
    open_browser = input("\n  Open GitHub token page in browser now? [Y/n]: ").strip().lower()
    if open_browser != "n":
        import webbrowser
        webbrowser.open("https://github.com/settings/tokens/new")
        print("  Browser opened. Come back here when you have copied the token.")

    print()
    current_token = get_token()
    masked = ("ghp_***" + current_token[-4:]) if len(current_token) > 7 else "(not set)"
    print(f"  Current token    : {masked}")
    new_token = input("  Paste your GitHub token [Enter to keep current]: ").strip()

    if new_token:
        if not new_token.startswith(("ghp_", "github_pat_")):
            print("\n  WARNING: Token doesn't look like a GitHub PAT (should start with ghp_ or github_pat_).")
            anyway = input("  Save it anyway? [y/N]: ").strip().lower()
            if anyway != "y":
                print("  Token not saved.")
                input("\n  Press Enter to return ...")
                return

        # Write to .env file
        env_path = ".env"
        lines = []
        token_written = False
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            new_lines = []
            for line in lines:
                if line.startswith("GITHUB_TOKEN="):
                    new_lines.append(f"GITHUB_TOKEN={new_token}\n")
                    token_written = True
                else:
                    new_lines.append(line)
            lines = new_lines
        if not token_written:
            lines.append(f"GITHUB_TOKEN={new_token}\n")
        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(lines)

        # Activate immediately in this session
        set_token(new_token)
        os.environ["GITHUB_TOKEN"] = new_token

        print(f"\n  Token saved to .env and active for this session.")
    else:
        print(f"  Keeping existing token.")

    input("\n  Press Enter to return to main menu ...")


# ─────────────────────────────────────────────────────────────
#  Main menu
# ─────────────────────────────────────────────────────────────

def main():
    config = load_config()

    while True:
        clear_screen()
        user_label  = config.get("username") or "[!] Not Set"
        token_label = "[OK] Token loaded" if get_token() else "[!] No token (limited)"

        print("╔══════════════════════════════════════╗")
        print("║      GITHUB FOLLOWER MANAGER CLI     ║")
        print("╠══════════════════════════════════════╣")
        print(f"║  User  : {user_label:<29}║")
        print(f"║  Token : {token_label:<29}║")
        print("╠══════════════════════════════════════╣")
        print("║  1.  View Non-Followers              ║")
        print("║  2.  Auto-Follow Smart Users         ║")
        print("║  3.  Bulk Unfollow                   ║")
        print("║  4.  Manage Ignore List              ║")
        print("║  5.  Setup Account & Token           ║")
        print("║  6.  Exit                            ║")
        print("╚══════════════════════════════════════╝")

        choice = input("\n  Select an option: ").strip()

        if choice == "1":
            view_non_followers(config)

        elif choice == "2":
            auto_follow_smart(config)
            config = load_config()  # refresh in case ignore list changed

        elif choice == "3":
            bulk_unfollow(config)
            config = load_config()

        elif choice == "4":
            manage_ignore_list(config)
            config = load_config()

        elif choice == "5":
            setup_account(config)
            config = load_config()
            # Token already updated inside setup_account via set_token()

        elif choice == "6":
            print("\n  Goodbye!\n")
            break


if __name__ == "__main__":
    main()
