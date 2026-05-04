#!/usr/bin/env python3
"""
Hydrow API Client
Usage:
  python hydrow.py login <email> <password>
  python hydrow.py workouts
  python hydrow.py progress
  python hydrow.py workout <workoutId>
  python hydrow.py leaderboard <workoutId>
"""

import sys
import json
import os
import time
import uuid
import requests
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
BASE_V2   = "https://v2.api.prod.hydrow-external.net"
TOKEN_FILE = Path.home() / ".hydrow_token.json"

HEADERS_BASE = {
    "Content-Type": "application/json",
    "x-hydrow-feature-flags": "new-music,preferences-filter,top-left,single-sets",
}

# ── Token storage ─────────────────────────────────────────────────────────────
def save_token(data: dict):
    TOKEN_FILE.write_text(json.dumps(data, indent=2))
    print(f"Token saved to {TOKEN_FILE}")

def load_token() -> dict | None:
    if not TOKEN_FILE.exists():
        return None
    return json.loads(TOKEN_FILE.read_text())

def get_auth_headers() -> dict:
    token_data = load_token()
    if not token_data:
        sys.exit("Not logged in. Run: python hydrow.py login <email> <password>")

    # Refresh if expired (or within 5 mins of expiry)
    if time.time() >= token_data["expiresAt"] - 300:
        print("Token expired, refreshing...")
        token_data = refresh_token(token_data)

    return {
        **HEADERS_BASE,
        "Authorization": f"Bearer {token_data['accessToken']}",
    }

# ── Auth ──────────────────────────────────────────────────────────────────────
def login(email: str, password: str):
    resp = requests.post(
        f"{BASE_V2}/rower/auth/login/unpw",
        headers=HEADERS_BASE,
        json={"username": email, "password": password},
    )
    resp.raise_for_status()
    data = resp.json()
    save_token({
        "accessToken":  data["accessToken"],
        "refreshToken": data["refreshToken"],
        "expiresAt":    data["expiresAt"],
        "rowerId":      data["rower"]["id"],
        "screenName":   data["rower"]["screenName"],
    })
    print(f"Logged in as {data['rower']['screenName']} (id: {data['rower']['id']})")

def refresh_token(token_data: dict) -> dict:
    resp = requests.post(
        f"{BASE_V2}/rower/auth/refresh",
        headers=HEADERS_BASE,
        json={"refreshToken": token_data["refreshToken"]},
    )
    resp.raise_for_status()
    data = resp.json()
    updated = {
        **token_data,
        "accessToken": data["accessToken"],
        "expiresAt":   data["expiresAt"],
    }
    if "refreshToken" in data:
        updated["refreshToken"] = data["refreshToken"]
    save_token(updated)
    return updated

# ── API calls ─────────────────────────────────────────────────────────────────
def get_workouts(page: int = 1, limit: int = 20):
    token_data = load_token()
    rower_id = token_data["rowerId"]
    headers = get_auth_headers()
    resp = requests.get(
        f"{BASE_V2}/rower/{rower_id}/workouts",
        headers=headers,
        params={"page": page, "limit": limit},
    )
    resp.raise_for_status()
    return resp.json()

def get_workout(workout_id: str):
    token_data = load_token()
    rower_id = token_data["rowerId"]
    headers = get_auth_headers()
    resp = requests.get(
        f"{BASE_V2}/rower/{rower_id}/workouts/{workout_id}",
        headers=headers,
    )
    resp.raise_for_status()
    return resp.json()

def get_leaderboard(workout_id: str):
    token_data = load_token()
    rower_id = token_data["rowerId"]
    headers = {
        **get_auth_headers(),
        "x-hydrow-rower-id": str(rower_id),
        "Idempotency-Key": str(uuid.uuid4()),
    }

    workout = get_workout(workout_id)
    workout_video_id = workout["workoutVideoId"]

    resp = requests.get(
        f"{BASE_V2}/workouts2/lb2/{workout_video_id}/final/{workout_id}",
        headers=headers,
    )
    resp.raise_for_status()
    return resp.json()


def get_progress():
    token_data = load_token()
    rower_id = token_data["rowerId"]
    headers = get_auth_headers()
    today = time.strftime("%Y-%m-%d")
    resp = requests.get(
        f"{BASE_V2}/rower/{rower_id}/v2/progress",
        headers=headers,
        params={"today": today},
    )
    resp.raise_for_status()
    return resp.json()

def get_workout_history():
    token_data = load_token()
    rower_id = token_data["rowerId"]
    headers = get_auth_headers()
    resp = requests.get(
        f"{BASE_V2}/workouts_history/rower/{rower_id}",
        headers=headers,
    )
    resp.raise_for_status()
    return resp.json()

def get_personal_records():
    token_data = load_token()
    rower_id = token_data["rowerId"]
    headers = get_auth_headers()
    resp = requests.get(
        f"{BASE_V2}/progress/{rower_id}/personal_records",
        headers=headers,
    )
    resp.raise_for_status()
    return resp.json()

def get_summary():
    token_data = load_token()
    rower_id = token_data["rowerId"]
    headers = get_auth_headers()
    resp = requests.get(
        f"{BASE_V2}/progress/{rower_id}/summary",
        headers=headers,
    )
    resp.raise_for_status()
    return resp.json()

# ── CLI ───────────────────────────────────────────────────────────────────────
def print_json(data):
    print(json.dumps(data, indent=2))

def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(0)

    cmd = args[0]

    if cmd == "login":
        if len(args) < 3:
            sys.exit("Usage: python hydrow.py login <email> <password>")
        login(args[1], args[2])

    elif cmd == "workouts":
        page  = int(args[1]) if len(args) > 1 else 1
        limit = int(args[2]) if len(args) > 2 else 20
        print_json(get_workouts(page, limit))

    elif cmd == "workout":
        if len(args) < 2:
            sys.exit("Usage: python hydrow.py workout <workoutId>")
        print_json(get_workout(args[1]))

    elif cmd == "leaderboard":
        if len(args) < 2:
            sys.exit("Usage: python hydrow.py leaderboard <workoutId>")
        print_json(get_leaderboard(args[1]))

    elif cmd == "progress":
        print_json(get_progress())

    elif cmd == "history":
        print_json(get_workout_history())

    elif cmd == "records":
        print_json(get_personal_records())

    elif cmd == "summary":
        print_json(get_summary())

    elif cmd == "whoami":
        t = load_token()
        if t:
            print(f"Logged in as {t['screenName']} (rowerId: {t['rowerId']})")
            expires = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t["expiresAt"]))
            print(f"Token expires: {expires}")
        else:
            print("Not logged in.")

    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)

if __name__ == "__main__":
    main()