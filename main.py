"""
Freebox API Proxy for Homepage dashboard.
Handles Freebox OS authentication (challenge + HMAC-SHA1) and exposes
simple JSON endpoints that Homepage's customapi widget can consume.

Usage:
  1. Start the container
  2. Go to http://<host>:5656/register to request an app_token
  3. Approve on the Freebox LCD screen
  4. Go to http://<host>:5656/register/status to confirm
  5. Done! /connection and /system endpoints are now available
"""

import os
import json
import hmac
import hashlib
import time
import logging
import requests
from flask import Flask, jsonify

# ---------------------------------------------------------------------------
# Configuration (all configurable via environment / .env)
# ---------------------------------------------------------------------------
FREEBOX_URL = os.environ.get("FREEBOX_URL", "http://mafreebox.freebox.fr")
API_VERSION = os.environ.get("FREEBOX_API_VERSION", "v4")
API_BASE = f"/api/{API_VERSION}"
TOKEN_FILE = os.environ.get("TOKEN_FILE", "/data/app_token.json")
APP_ID = os.environ.get("APP_ID", "fr.freebox.proxy")
APP_NAME = os.environ.get("APP_NAME", "Freebox Proxy")
APP_VERSION = os.environ.get("APP_VERSION", "1.0")
DEVICE_NAME = os.environ.get("DEVICE_NAME", "Docker Server")
LISTEN_PORT = int(os.environ.get("LISTEN_PORT", "5656"))

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("freebox-proxy")

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Token persistence
# ---------------------------------------------------------------------------

def load_token():
    """Load saved app_token from disk."""
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE) as f:
            return json.load(f)
    return None


def save_token(data):
    """Persist app_token to disk."""
    os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
    with open(TOKEN_FILE, "w") as f:
        json.dump(data, f, indent=2)
    log.info("App token saved to %s", TOKEN_FILE)

# ---------------------------------------------------------------------------
# Freebox Auth helpers
# ---------------------------------------------------------------------------

_session_cache = {"token": None, "expires": 0}


def _get_challenge():
    """Fetch the current authentication challenge."""
    r = requests.get(f"{FREEBOX_URL}{API_BASE}/login/", timeout=5)
    r.raise_for_status()
    return r.json()["result"]["challenge"]


def _compute_password(app_token: str, challenge: str) -> str:
    """HMAC-SHA1(app_token, challenge)"""
    return hmac.new(
        app_token.encode("utf-8"),
        challenge.encode("utf-8"),
        hashlib.sha1,
    ).hexdigest()


def get_session_token(force=False):
    """Return a valid session_token, refreshing if needed."""
    now = time.time()
    if not force and _session_cache["token"] and now < _session_cache["expires"]:
        return _session_cache["token"]

    token_data = load_token()
    if not token_data or "app_token" not in token_data:
        return None

    challenge = _get_challenge()
    password = _compute_password(token_data["app_token"], challenge)

    r = requests.post(
        f"{FREEBOX_URL}{API_BASE}/login/session/",
        json={"app_id": APP_ID, "password": password},
        timeout=5,
    )
    data = r.json()
    if data.get("success"):
        _session_cache["token"] = data["result"]["session_token"]
        _session_cache["expires"] = now + 600  # cache 10 min
        log.info("Session token refreshed")
        return _session_cache["token"]

    log.warning("Session open failed: %s", data.get("msg", data))
    return None


def fbx_get(endpoint: str):
    """Authenticated GET to the Freebox API. Auto-refreshes session."""
    session = get_session_token()
    if not session:
        return {"success": False, "error": "no_session", "msg": "Not authenticated. Visit /register first."}

    headers = {"X-Fbx-App-Auth": session}
    r = requests.get(f"{FREEBOX_URL}{API_BASE}{endpoint}", headers=headers, timeout=5)

    # If 403, force-refresh the session and retry once
    if r.status_code == 403:
        session = get_session_token(force=True)
        if not session:
            return {"success": False, "error": "auth_failed"}
        headers = {"X-Fbx-App-Auth": session}
        r = requests.get(f"{FREEBOX_URL}{API_BASE}{endpoint}", headers=headers, timeout=5)

    return r.json()

# ---------------------------------------------------------------------------
# Registration endpoints (one-time setup)
# ---------------------------------------------------------------------------

_pending_registration = {}


@app.route("/register")
def register():
    """Step 1: Request an app_token. User must approve on Freebox LCD."""
    global _pending_registration

    # Already registered?
    existing = load_token()
    if existing and "app_token" in existing:
        return jsonify({
            "success": True,
            "msg": "Already registered. Use /register/reset to re-register.",
        })

    r = requests.post(
        f"{FREEBOX_URL}{API_BASE}/login/authorize/",
        json={
            "app_id": APP_ID,
            "app_name": APP_NAME,
            "app_version": APP_VERSION,
            "device_name": DEVICE_NAME,
        },
        timeout=10,
    )
    data = r.json()
    if data.get("success"):
        _pending_registration = {
            "app_token": data["result"]["app_token"],
            "track_id": data["result"]["track_id"],
        }
        return jsonify({
            "success": True,
            "msg": "Autorisation demandée. Validez sur l'écran LCD de la Freebox, puis appelez /register/status",
            "track_id": data["result"]["track_id"],
        })
    return jsonify({"success": False, "msg": "Registration request failed", "detail": data}), 500


@app.route("/register/status")
def register_status():
    """Step 2: Check if user approved, then save the token."""
    global _pending_registration
    if not _pending_registration:
        existing = load_token()
        if existing and "app_token" in existing:
            return jsonify({"success": True, "status": "granted", "msg": "Already registered."})
        return jsonify({"success": False, "msg": "No pending registration. Call /register first."})

    track_id = _pending_registration["track_id"]
    r = requests.get(f"{FREEBOX_URL}{API_BASE}/login/authorize/{track_id}", timeout=5)
    data = r.json()
    status = data.get("result", {}).get("status", "unknown")

    if status == "granted":
        save_token({"app_token": _pending_registration["app_token"]})
        _pending_registration = {}
        return jsonify({"success": True, "status": "granted", "msg": "Enregistré ! Les endpoints /connection et /system sont maintenant disponibles."})

    return jsonify({"success": True, "status": status, "msg": f"Status: {status}. En attente de validation sur l'écran de la Freebox..."})


@app.route("/register/reset")
def register_reset():
    """Remove saved token to allow re-registration."""
    if os.path.exists(TOKEN_FILE):
        os.remove(TOKEN_FILE)
    _session_cache["token"] = None
    return jsonify({"success": True, "msg": "Token supprimé. Appelez /register pour recommencer."})

# ---------------------------------------------------------------------------
# Data endpoints (used by Homepage customapi)
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    """Health check / status."""
    token = load_token()
    return jsonify({
        "service": "freebox-proxy",
        "registered": bool(token and "app_token" in token),
        "endpoints": ["/connection", "/system", "/ftth", "/connection/full"],
    })


@app.route("/connection")
def connection():
    """Connection status: state, bandwidth, rates."""
    data = fbx_get("/connection/")
    if not data.get("success"):
        return jsonify(data), 503

    r = data["result"]
    return jsonify({
        "success": True,
        "result": {
            "state": r.get("state", "unknown"),
            "media": r.get("media", "unknown"),
            "type": r.get("type", "unknown"),
            "rate_down": r.get("rate_down", 0),
            "rate_up": r.get("rate_up", 0),
            "bandwidth_down": r.get("bandwidth_down", 0),
            "bandwidth_up": r.get("bandwidth_up", 0),
            "bytes_down": r.get("bytes_down", 0),
            "bytes_up": r.get("bytes_up", 0),
            "ipv4": r.get("ipv4", ""),
            "ipv6": r.get("ipv6", ""),
            # Human-readable
            "rate_down_mbps": round(r.get("rate_down", 0) * 8 / 1_000_000, 1),
            "rate_up_mbps": round(r.get("rate_up", 0) * 8 / 1_000_000, 1),
            "bandwidth_down_gbps": round(r.get("bandwidth_down", 0) / 1_000_000_000, 1),
            "bandwidth_up_gbps": round(r.get("bandwidth_up", 0) / 1_000_000_000, 1),
        },
    })


@app.route("/system")
def system():
    """System info: temps, fan, uptime, firmware."""
    data = fbx_get("/system/")
    if not data.get("success"):
        return jsonify(data), 503

    r = data["result"]
    return jsonify({
        "success": True,
        "result": {
            "firmware_version": r.get("firmware_version", ""),
            "uptime": r.get("uptime", ""),
            "uptime_val": r.get("uptime_val", 0),
            "temp_cpum": r.get("temp_cpum", 0),
            "temp_cpub": r.get("temp_cpub", 0),
            "temp_sw": r.get("temp_sw", 0),
            "fan_rpm": r.get("fan_rpm", 0),
            "board_name": r.get("board_name", ""),
            "serial": r.get("serial", ""),
            "mac": r.get("mac", ""),
            "disk_status": r.get("disk_status", ""),
            "box_flavor": r.get("box_flavor", ""),
        },
    })


@app.route("/ftth")
def ftth():
    """FTTH status (fiber link info)."""
    data = fbx_get("/connection/ftth/")
    if not data.get("success"):
        return jsonify(data), 503
    return jsonify(data)


@app.route("/connection/full")
def connection_full():
    """Combined connection + system data in a single call for Homepage."""
    conn = fbx_get("/connection/")
    sys_data = fbx_get("/system/")

    c = conn.get("result", {}) if conn.get("success") else {}
    s = sys_data.get("result", {}) if sys_data.get("success") else {}

    return jsonify({
        "success": True,
        "result": {
            "state": c.get("state", "unknown"),
            "rate_down_mbps": round(c.get("rate_down", 0) * 8 / 1_000_000, 1),
            "rate_up_mbps": round(c.get("rate_up", 0) * 8 / 1_000_000, 1),
            "bandwidth_down_gbps": round(c.get("bandwidth_down", 0) / 1_000_000_000, 1),
            "bandwidth_up_gbps": round(c.get("bandwidth_up", 0) / 1_000_000_000, 1),
            "temp_cpum": s.get("temp_cpum", 0),
            "temp_cpub": s.get("temp_cpub", 0),
            "temp_sw": s.get("temp_sw", 0),
            "fan_rpm": s.get("fan_rpm", 0),
            "uptime": s.get("uptime", ""),
            "firmware": s.get("firmware_version", ""),
        },
    })


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=LISTEN_PORT)
