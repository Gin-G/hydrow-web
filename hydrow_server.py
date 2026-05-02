#!/usr/bin/env python3
"""
Hydrow Dashboard Server
Run: python hydrow_server.py
Then open: http://localhost:5000
"""

import time
import json
import logging
import stat
import requests
from pathlib import Path
from flask import Flask, request, jsonify
from flask_cors import CORS

# ── Kill ALL logging before Flask starts ───────────────────────────────────────
# werkzeug logs every request line (e.g. "POST /api/login 200") to stdout.
# Setting NullHandler ensures nothing reaches stdout/stderr or any log file.
for name in ('werkzeug', 'urllib3', 'requests', 'flask'):
    lg = logging.getLogger(name)
    lg.setLevel(logging.CRITICAL)
    lg.handlers = []
    lg.addHandler(logging.NullHandler())
    lg.propagate = False

# ── App setup ─────────────────────────────────────────────────────────────────
app = Flask(__name__, static_folder='.', static_url_path='')
app.logger.handlers = []
app.logger.addHandler(logging.NullHandler())
app.logger.setLevel(logging.CRITICAL)

# Only accept requests from localhost — nothing from LAN or internet
CORS(app, origins=['http://localhost:5000', 'http://127.0.0.1:5000'])

BASE_V2    = "https://v2.api.prod.hydrow-external.net"
TOKEN_FILE = Path.home() / ".hydrow_token.json"

HEADERS_BASE = {
    "Content-Type": "application/json",
    "x-hydrow-feature-flags": "new-music,preferences-filter,top-left,single-sets",
}

# ── Token helpers ─────────────────────────────────────────────────────────────

def save_token(data):
    """Write token file and restrict permissions to owner-only (600)."""
    TOKEN_FILE.write_text(json.dumps(data, indent=2))
    TOKEN_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)  # -rw------- no group/world read

def load_token():
    if not TOKEN_FILE.exists():
        return None
    return json.loads(TOKEN_FILE.read_text())

def get_auth_headers():
    token_data = load_token()
    if not token_data:
        return None, "not_logged_in"
    if time.time() >= token_data["expiresAt"] - 300:
        try:
            token_data = do_refresh(token_data)
        except Exception:
            return None, "token_refresh_failed"  # never leak exception detail
    return {
        **HEADERS_BASE,
        "Authorization": f"Bearer {token_data['accessToken']}",
    }, None

def do_refresh(token_data):
    resp = requests.post(
        f"{BASE_V2}/rower/auth/refresh",
        headers=HEADERS_BASE,
        json={"refreshToken": token_data["refreshToken"]},
        timeout=10,
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

def safe_error(e):
    """Return a safe error message that never echoes credentials."""
    try:
        body = e.response.json()
        msg = body.get("message") or body.get("error") or "Request failed"
        if isinstance(msg, list):
            msg = msg[0].get("constraints", {}).get("isNotEmpty", "Invalid request") if msg else "Invalid request"
        return str(msg)
    except Exception:
        return f"HTTP {e.response.status_code}"

# ── Routes ────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return app.send_static_file('hydrow_dashboard.html')

@app.route('/api/login', methods=['POST'])
def login():
    body = request.json or {}
    email    = body.get('email', '').strip()
    password = body.get('password', '')

    if not email or not password:
        return jsonify({"error": "Email and password required"}), 400

    try:
        resp = requests.post(
            f"{BASE_V2}/rower/auth/login/unpw",
            headers=HEADERS_BASE,
            json={"username": email, "password": password},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        # Store only the token — never the raw credentials
        save_token({
            "accessToken":  data["accessToken"],
            "refreshToken": data["refreshToken"],
            "expiresAt":    data["expiresAt"],
            "rowerId":      data["rower"]["id"],
            "screenName":   data["rower"]["screenName"],
        })

        return jsonify({
            "screenName": data["rower"]["screenName"],
            "rowerId":    data["rower"]["id"],
            "rower":      data["rower"],
        })

    except requests.HTTPError as e:
        return jsonify({"error": safe_error(e)}), e.response.status_code
    except requests.ConnectionError:
        return jsonify({"error": "Could not reach Hydrow servers"}), 503
    except Exception:
        return jsonify({"error": "Login failed"}), 500  # no exception detail leaked

@app.route('/api/logout', methods=['POST'])
def logout():
    if TOKEN_FILE.exists():
        # Overwrite with zeros before deleting so token isn't trivially recoverable
        TOKEN_FILE.write_bytes(b'\x00' * TOKEN_FILE.stat().st_size)
        TOKEN_FILE.unlink()
    return jsonify({"ok": True})

@app.route('/api/me')
def me():
    token = load_token()
    if not token:
        return jsonify({"error": "not_logged_in"}), 401
    return jsonify({
        "screenName": token.get("screenName"),
        "rowerId":    token.get("rowerId"),
        "expiresAt":  token.get("expiresAt"),
    })

def proxy_get(path, params=None):
    headers, err = get_auth_headers()
    if err:
        return jsonify({"error": err}), 401
    try:
        resp = requests.get(f"{BASE_V2}{path}", headers=headers, params=params, timeout=15)
        resp.raise_for_status()
        return jsonify(resp.json())
    except requests.HTTPError as e:
        return jsonify({"error": safe_error(e)}), e.response.status_code
    except Exception:
        return jsonify({"error": "Request failed"}), 500

@app.route('/api/summary')
def summary():
    token = load_token()
    if not token:
        return jsonify({"error": "not_logged_in"}), 401
    return proxy_get(f"/rower/{token['rowerId']}/v2/progress", {
        "today": time.strftime("%Y-%m-%d")
    })

@app.route('/api/workouts')
def workouts():
    token = load_token()
    if not token:
        return jsonify({"error": "not_logged_in"}), 401
    page  = request.args.get('page', 1)
    limit = request.args.get('limit', 20)
    return proxy_get(f"/rower/{token['rowerId']}/workouts", {"page": page, "limit": limit})

@app.route('/api/progress-summary')
def progress_summary():
    token = load_token()
    if not token:
        return jsonify({"error": "not_logged_in"}), 401
    return proxy_get(f"/progress/{token['rowerId']}/summary")

@app.route('/api/records')
def records():
    token = load_token()
    if not token:
        return jsonify({"error": "not_logged_in"}), 401
    return proxy_get(f"/progress/{token['rowerId']}/personal_records")

@app.route('/api/calendar')
def calendar():
    token = load_token()
    if not token:
        return jsonify({"error": "not_logged_in"}), 401
    month = request.args.get('month', time.strftime("%Y-%m"))
    return proxy_get(f"/progress/{token['rowerId']}/calendar", {"month": month})

if __name__ == '__main__':
    print("\n  Hydrow Dashboard → http://localhost:5000\n")
    # host='127.0.0.1' means physically unreachable from any other machine
    # on your network — OS-level enforcement, not just a firewall rule.
    app.run(host='127.0.0.1', port=5000, debug=False)