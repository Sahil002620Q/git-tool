import requests
import time

# ──────────────────────────────────────────────
#  Low-level helpers
# ──────────────────────────────────────────────

def _headers(token):
    return {"Authorization": f"token {token}"} if token else {}


def _get_paginated_logins(url_base, token, max_pages=30):
    """Fetch all logins from a paginated GitHub list endpoint."""
    logins = []
    page = 1
    while page <= max_pages:
        url = f"{url_base}?per_page=100&page={page}"
        resp = requests.get(url, headers=_headers(token))
        if resp.status_code != 200:
            break
        data = resp.json()
        if not data:
            break
        logins.extend([u["login"] for u in data])
        page += 1
    return logins


# ──────────────────────────────────────────────
#  Existing helpers (kept for compatibility)
# ──────────────────────────────────────────────

def get_data(username, endpoint, token):
    """Return a set of logins from /users/{username}/{endpoint}."""
    url_base = f"https://api.github.com/users/{username}/{endpoint}"
    return set(_get_paginated_logins(url_base, token))


def unfollow_user(target_user, token):
    """Unfollow a user. Returns True on success."""
    url = f"https://api.github.com/user/following/{target_user}"
    resp = requests.delete(url, headers=_headers(token))
    return resp.status_code == 204


def follow_user(target_user, token):
    """Follow a user. Returns True on success."""
    url = f"https://api.github.com/user/following/{target_user}"
    resp = requests.put(url, headers=_headers(token))
    return resp.status_code == 204


# ──────────────────────────────────────────────
#  User profile & activity
# ──────────────────────────────────────────────

def get_user_info(username, token):
    """
    Return the full GitHub user object for *username*, or None on error.
    Useful fields: login, followers, following, updated_at, public_repos
    """
    url = f"https://api.github.com/users/{username}"
    resp = requests.get(url, headers=_headers(token))
    if resp.status_code == 200:
        return resp.json()
    return None


def get_user_events(username, token, limit=30):
    """
    Return the most-recent public events for *username* (up to *limit*).
    Each event dict contains at least: {"created_at": "2024-..."}.
    Returns [] on error or private profile.
    """
    url = f"https://api.github.com/users/{username}/events/public?per_page={limit}"
    resp = requests.get(url, headers=_headers(token))
    if resp.status_code == 200:
        return resp.json()
    return []


def get_following_of(username, token, max_pages=10):
    """
    Return the list of logins that *username* is following.
    Capped at max_pages * 100 results to stay within rate limits.
    """
    url_base = f"https://api.github.com/users/{username}/following"
    return _get_paginated_logins(url_base, token, max_pages=max_pages)


def get_rate_limit(token):
    """Return remaining API calls and reset timestamp."""
    url = "https://api.github.com/rate_limit"
    resp = requests.get(url, headers=_headers(token))
    if resp.status_code == 200:
        core = resp.json().get("resources", {}).get("core", {})
        return core.get("remaining", 0), core.get("reset", 0)
    return None, None
