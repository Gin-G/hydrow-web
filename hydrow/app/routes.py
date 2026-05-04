import time
import uuid

import requests
from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

main = Blueprint("main", __name__)

BASE_V2 = "https://v2.api.prod.hydrow-external.net"

HEADERS_BASE = {
    "Content-Type": "application/json",
    "x-hydrow-feature-flags": "new-music,preferences-filter,top-left,single-sets",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_auth_headers():
    """Return (headers, error). Refreshes token if close to expiry."""
    if "access_token" not in session:
        return None, "not_logged_in"

    if time.time() >= session.get("expires_at", 0) - 300:
        try:
            _refresh_token()
        except Exception:
            session.clear()
            return None, "token_refresh_failed"

    return {
        **HEADERS_BASE,
        "Authorization": f"Bearer {session['access_token']}",
    }, None


def _refresh_token():
    resp = requests.post(
        f"{BASE_V2}/rower/auth/refresh",
        headers=HEADERS_BASE,
        json={"refreshToken": session["refresh_token"]},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    session["access_token"] = data["accessToken"]
    session["expires_at"] = data["expiresAt"]
    if "refreshToken" in data:
        session["refresh_token"] = data["refreshToken"]


def _safe_error(exc: requests.HTTPError) -> str:
    """Extract a human-readable error without echoing credentials."""
    try:
        body = exc.response.json()
        msg = body.get("message") or body.get("error") or "Request failed"
        if isinstance(msg, list):
            msg = (
                msg[0].get("constraints", {}).get("isNotEmpty", "Invalid request")
                if msg
                else "Invalid request"
            )
        return str(msg)
    except Exception:
        return f"HTTP {exc.response.status_code}"


def _proxy_get(path: str, params: dict = None):
    headers, err = _get_auth_headers()
    if err:
        return jsonify({"error": err}), 401
    try:
        resp = requests.get(
            f"{BASE_V2}{path}", headers=headers, params=params, timeout=15
        )
        resp.raise_for_status()
        return jsonify(resp.json())
    except requests.HTTPError as e:
        return jsonify({"error": _safe_error(e)}), e.response.status_code
    except Exception:
        return jsonify({"error": "Request failed"}), 500


# ── Pages ─────────────────────────────────────────────────────────────────────

@main.route("/")
def index():
    return render_template("dashboard.html")


@main.route("/workout/<int:workout_id>")
def workout_page(workout_id):
    if "rower_id" not in session:
        return redirect(url_for("main.index"))
    return render_template("workout.html", workout_id=workout_id)


# ── Auth ──────────────────────────────────────────────────────────────────────

@main.route("/api/login", methods=["POST"])
def login():
    body = request.get_json(silent=True) or {}
    email = body.get("email", "").strip()
    password = body.get("password", "")

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

        # Store only tokens in the server-side session — never raw credentials.
        # The session id cookie is HMAC-signed and httponly; data lives in Redis.
        session.clear()
        session["access_token"] = data["accessToken"]
        session["refresh_token"] = data["refreshToken"]
        session["expires_at"] = data["expiresAt"]
        session["rower_id"] = data["rower"]["id"]
        session["screen_name"] = data["rower"]["screenName"]

        return jsonify({
            "screenName": data["rower"]["screenName"],
            "rowerId": data["rower"]["id"],
            "rower": data["rower"],
        })

    except requests.HTTPError as e:
        return jsonify({"error": _safe_error(e)}), e.response.status_code
    except requests.ConnectionError:
        return jsonify({"error": "Could not reach Hydrow servers"}), 503
    except Exception:
        return jsonify({"error": "Login failed"}), 500


@main.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"ok": True})


@main.route("/api/me")
def me():
    if "access_token" not in session:
        return jsonify({"error": "not_logged_in"}), 401
    return jsonify({
        "screenName": session.get("screen_name"),
        "rowerId": session.get("rower_id"),
        "expiresAt": session.get("expires_at"),
    })


# ── Data endpoints ────────────────────────────────────────────────────────────

@main.route("/api/summary")
def summary():
    if "rower_id" not in session:
        return jsonify({"error": "not_logged_in"}), 401
    return _proxy_get(
        f"/rower/{session['rower_id']}/v2/progress",
        {"today": time.strftime("%Y-%m-%d")},
    )


@main.route("/api/workouts")
def workouts():
    if "rower_id" not in session:
        return jsonify({"error": "not_logged_in"}), 401
    return _proxy_get(
        f"/rower/{session['rower_id']}/workouts",
        {
            "page": request.args.get("page", 1),
            "limit": request.args.get("limit", 20),
        },
    )


@main.route("/api/workouts/<int:workout_id>")
def workout(workout_id):
    if "rower_id" not in session:
        return jsonify({"error": "not_logged_in"}), 401
    return _proxy_get(f"/rower/{session['rower_id']}/workouts/{workout_id}")


@main.route("/api/workouts/<int:workout_id>/leaderboard")
def workout_leaderboard(workout_id):
    if "rower_id" not in session:
        return jsonify({"error": "not_logged_in"}), 401
    headers, err = _get_auth_headers()
    if err:
        return jsonify({"error": err}), 401

    try:
        wresp = requests.get(
            f"{BASE_V2}/rower/{session['rower_id']}/workouts/{workout_id}",
            headers=headers,
            timeout=15,
        )
        wresp.raise_for_status()
        workout_video_id = wresp.json().get("workoutVideoId")
        if not workout_video_id:
            return jsonify({"error": "Workout has no associated video"}), 400

        lb_headers = {
            **headers,
            "x-hydrow-rower-id": str(session["rower_id"]),
            "Idempotency-Key": str(uuid.uuid4()),
        }
        lresp = requests.get(
            f"{BASE_V2}/workouts2/lb2/{workout_video_id}/final/{workout_id}",
            headers=lb_headers,
            timeout=15,
        )
        lresp.raise_for_status()
        return jsonify(lresp.json())
    except requests.HTTPError as e:
        return jsonify({"error": _safe_error(e)}), e.response.status_code
    except Exception:
        return jsonify({"error": "Request failed"}), 500


@main.route("/api/progress-summary")
def progress_summary():
    if "rower_id" not in session:
        return jsonify({"error": "not_logged_in"}), 401
    return _proxy_get(f"/progress/{session['rower_id']}/summary")


@main.route("/api/records")
def records():
    if "rower_id" not in session:
        return jsonify({"error": "not_logged_in"}), 401
    return _proxy_get(f"/progress/{session['rower_id']}/personal_records")


@main.route("/api/calendar")
def calendar():
    if "rower_id" not in session:
        return jsonify({"error": "not_logged_in"}), 401
    return _proxy_get(
        f"/progress/{session['rower_id']}/calendar",
        {"month": request.args.get("month", time.strftime("%Y-%m"))},
    )