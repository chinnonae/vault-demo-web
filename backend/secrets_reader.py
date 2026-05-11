"""
Injected-secrets reader for vault-demo-web.

Vault Agent and the Vault Secrets Operator deliver secrets to the pod in
two standard ways – this module supports both:

  1. **File** – Vault Agent renders a template to a directory
     (default: /vault/secrets/).  Each file is treated as one secret;
     the filename becomes the secret name.  Files may be plain-text
     (the entire content is the value) or JSON objects (each key inside
     the JSON becomes its own field).

  2. **Env** – The Vault Secrets Operator (or Vault Agent with env-inject)
     exposes secrets as environment variables, optionally under a common
     prefix (default: SECRET_).
"""

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any

from config import Config

logger = logging.getLogger(__name__)


@dataclass
class InjectedSecret:
    """One logical secret as delivered by Vault Agent / Secrets Operator."""

    name: str
    source: str          # "file" or "env"
    fields: dict[str, Any] = field(default_factory=dict)


class SecretsReader:
    """Read secrets injected by Vault Agent or the Vault Secrets Operator."""

    def __init__(self, cfg: Config):
        self._cfg = cfg

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def list_secrets(self) -> list[InjectedSecret]:
        """Return all secrets currently available from the configured source."""
        source = self._cfg.secrets_source
        if source == "file":
            return self._read_from_files()
        if source == "env":
            return self._read_from_env()
        if source == "both":
            return self._read_from_files() + self._read_from_env()
        raise ValueError(f"Unknown secrets.source: '{source}'")

    def get_secret(self, name: str) -> InjectedSecret | None:
        """Return a single secret by name, or None if not found."""
        for s in self.list_secrets():
            if s.name == name:
                return s
        return None

    # ------------------------------------------------------------------
    # File-based secrets (Vault Agent rendered templates)
    # ------------------------------------------------------------------

    def _read_from_files(self) -> list[InjectedSecret]:
        inject_dir = self._cfg.secrets_path
        secrets: list[InjectedSecret] = []

        if not os.path.isdir(inject_dir):
            logger.warning("Injection directory '%s' does not exist or is not a directory.", inject_dir)
            return secrets

        for fname in sorted(os.listdir(inject_dir)):
            fpath = os.path.join(inject_dir, fname)
            if not os.path.isfile(fpath):
                continue
            try:
                with open(fpath, "r", encoding="utf-8") as fh:
                    content = fh.read()
                fields = _parse_secret_file(fname, content)
                secrets.append(InjectedSecret(name=fname, source="file", fields=fields))
            except OSError as exc:
                logger.warning("Could not read injected file '%s': %s", fname, exc)

        return secrets

    # ------------------------------------------------------------------
    # Env-based secrets (Vault Secrets Operator / Vault Agent env inject)
    # ------------------------------------------------------------------

    def _read_from_env(self) -> list[InjectedSecret]:
        prefix = self._cfg.secrets_env_prefix
        fields: dict[str, str] = {}

        for key, value in os.environ.items():
            if key.startswith(prefix):
                short_key = key[len(prefix):]
                fields[short_key] = value

        if not fields:
            return []

        return [InjectedSecret(name=f"env:{prefix}*", source="env", fields=fields)]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_secret_file(name: str, content: str) -> dict[str, Any]:
    """
    Try to parse the file content as JSON.
    If it is not valid JSON, treat the entire content as a single value
    keyed by "value".
    """
    stripped = content.strip()
    if stripped.startswith("{"):
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    return {"value": content.rstrip("\n")}
