"""
vault-demo-web – Flask application entry point.

This application does NOT talk to Vault directly.
Secrets are injected by:
  • Vault Agent       – rendered as files into a directory (default: /vault/secrets)
  • Vault Secrets Operator – projected as environment variables or mounted K8s Secrets

REST API
--------
GET  /api/health          App health status
GET  /api/config          Active configuration
GET  /api/secrets         List all injected secrets (names + source)
GET  /api/secrets/<name>  Read fields of a specific injected secret

All JSON responses have the shape:
  { "ok": true,  "data": <payload> }
  { "ok": false, "error": "<message>" }
"""

import logging
import os

from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS

from config import load_config
from secrets_reader import SecretsReader

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
reader = SecretsReader(cfg)

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
    return _ok({"status": "ok"})


@app.get("/api/config")
def api_config():
    return _ok(cfg.to_dict())


# ---------------------------------------------------------------------------
# API – injected secrets (read-only)
# ---------------------------------------------------------------------------

@app.get("/api/secrets")
def api_list_secrets():
    secrets = reader.list_secrets()
    return _ok([
        {"name": s.name, "source": s.source, "field_count": len(s.fields)}
        for s in secrets
    ])


@app.get("/api/secrets/<path:name>")
def api_get_secret(name: str):
    secret = reader.get_secret(name)
    if secret is None:
        return _err(f"Secret '{name}' not found.", 404)
    return _ok({"name": secret.name, "source": secret.source, "fields": secret.fields})


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
    logger.info("Secrets source: %s", cfg.secrets_source)
    logger.info("Starting server on %s:%d (debug=%s)", cfg.server_host, cfg.server_port, cfg.server_debug)
    app.run(host=cfg.server_host, port=cfg.server_port, debug=cfg.server_debug)
