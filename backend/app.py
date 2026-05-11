"""
vault-demo-web – Flask application entry point.

REST API
--------
GET  /api/health           Vault + app health status
GET  /api/config           Active configuration (token redacted)
GET  /api/secrets          List keys at the root of the KV mount
GET  /api/secrets/<path>   List keys (if path ends with /) or read secret data
POST /api/secrets/<path>   Create / update a secret  (JSON body: {"key": "value", ...})
DELETE /api/secrets/<path> Delete a secret

All JSON responses have the shape:
  { "ok": true,  "data": <payload> }
  { "ok": false, "error": "<message>" }
"""

import logging
import os

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

from config import load_config
from vault_client import VaultClient, SecretNotFoundError, VaultOperationError

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------
cfg = load_config()
vault = VaultClient(cfg)

# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")

app = Flask(__name__, static_folder=None)
CORS(app)  # allow browser requests from any origin during development


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _ok(data):
    return jsonify({"ok": True, "data": data})


def _err(message: str, status: int = 400):
    return jsonify({"ok": False, "error": message}), status


# ---------------------------------------------------------------------------
# Frontend
# ---------------------------------------------------------------------------

@app.route("/")
@app.route("/<path:filename>")
def serve_frontend(filename="index.html"):
    """Serve the static frontend files."""
    return send_from_directory(FRONTEND_DIR, filename)


# ---------------------------------------------------------------------------
# API – health & config
# ---------------------------------------------------------------------------

@app.get("/api/health")
def api_health():
    vault_health = vault.health()
    authenticated = vault.is_authenticated() if vault_health.get("reachable") else False
    return _ok({
        "status": "ok",
        "vault": vault_health,
        "authenticated": authenticated,
    })


@app.get("/api/config")
def api_config():
    return _ok(cfg.to_dict())


# ---------------------------------------------------------------------------
# API – secrets
# ---------------------------------------------------------------------------

@app.get("/api/secrets")
def api_list_root():
    try:
        keys = vault.list_secrets("")
        return _ok({"path": "/", "keys": keys})
    except VaultOperationError as exc:
        return _err(str(exc), 502)


@app.get("/api/secrets/<path:secret_path>")
def api_secrets_get(secret_path: str):
    """
    If the path ends with '/' (or is a prefix), list keys.
    Otherwise read the secret data.
    """
    try:
        if secret_path.endswith("/"):
            keys = vault.list_secrets(secret_path)
            return _ok({"path": secret_path, "keys": keys})
        else:
            data = vault.read_secret(secret_path)
            return _ok({"path": secret_path, "data": data})
    except SecretNotFoundError as exc:
        return _err(str(exc), 404)
    except VaultOperationError as exc:
        return _err(str(exc), 502)


@app.post("/api/secrets/<path:secret_path>")
def api_secrets_write(secret_path: str):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return _err("Request body must be a JSON object.")
    try:
        vault.write_secret(secret_path, payload)
        return _ok({"path": secret_path, "message": "Secret written successfully."})
    except VaultOperationError as exc:
        return _err(str(exc), 502)


@app.delete("/api/secrets/<path:secret_path>")
def api_secrets_delete(secret_path: str):
    try:
        vault.delete_secret(secret_path)
        return _ok({"path": secret_path, "message": "Secret deleted successfully."})
    except SecretNotFoundError as exc:
        return _err(str(exc), 404)
    except VaultOperationError as exc:
        return _err(str(exc), 502)


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------

@app.errorhandler(404)
def not_found(e):
    return _err("Not found", 404)


@app.errorhandler(405)
def method_not_allowed(e):
    return _err("Method not allowed", 405)


@app.errorhandler(500)
def internal_error(e):
    logger.exception("Unhandled error")
    return _err("Internal server error", 500)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logger.info("Configuration source: %s", cfg.source)
    logger.info("Vault address: %s", cfg.vault_addr)
    logger.info("Starting server on %s:%d (debug=%s)", cfg.server_host, cfg.server_port, cfg.server_debug)
    app.run(host=cfg.server_host, port=cfg.server_port, debug=cfg.server_debug)
