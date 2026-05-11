"""
Configuration loader for vault-demo-web.

Priority (highest to lowest):
  1. Environment variables
  2. Config file (path from CONFIG_FILE env var, or searched in standard locations)
  3. Built-in defaults

Supported environment variables:
  CONFIG_FILE       – explicit path to a YAML config file
  VAULT_ADDR        – Vault server address
  VAULT_TOKEN       – Vault token
  VAULT_NAMESPACE   – Vault namespace (Enterprise / HCP)
  VAULT_MOUNT       – KV secrets engine mount path  (default: secret)
  SERVER_HOST       – Flask bind host                (default: 0.0.0.0)
  SERVER_PORT       – Flask bind port                (default: 8080)
  SERVER_DEBUG      – Enable Flask debug mode        (default: false)
"""

import os
import logging
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# Locations searched for a config file when CONFIG_FILE is not set
_DEFAULT_CONFIG_PATHS = [
    "/etc/vault-demo/config.yaml",
    "/etc/vault-demo/config.yml",
    "./config/config.yaml",
    "./config/config.yml",
    "./config.yaml",
    "./config.yml",
]

_DEFAULTS: dict[str, Any] = {
    "vault": {
        "addr": "http://127.0.0.1:8200",
        "token": "",
        "namespace": "",
        "mount": "secret",
    },
    "server": {
        "host": "0.0.0.0",
        "port": 8080,
        "debug": False,
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge *override* into a copy of *base*."""
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _load_yaml_file(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
            return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML in config file '{path}': {exc}") from exc


def _find_config_file() -> str | None:
    explicit = os.environ.get("CONFIG_FILE")
    if explicit:
        if not os.path.isfile(explicit):
            raise FileNotFoundError(
                f"CONFIG_FILE is set to '{explicit}' but the file does not exist."
            )
        return explicit
    for path in _DEFAULT_CONFIG_PATHS:
        if os.path.isfile(path):
            return path
    return None


def _env_overrides() -> dict:
    """Build a partial config dict from environment variables."""
    overrides: dict[str, Any] = {"vault": {}, "server": {}}

    for env_key, cfg_path in [
        ("VAULT_ADDR", ("vault", "addr")),
        ("VAULT_TOKEN", ("vault", "token")),
        ("VAULT_NAMESPACE", ("vault", "namespace")),
        ("VAULT_MOUNT", ("vault", "mount")),
    ]:
        val = os.environ.get(env_key)
        if val is not None:
            section, field = cfg_path
            overrides[section][field] = val

    for env_key, cfg_path, cast in [
        ("SERVER_HOST", ("server", "host"), str),
        ("SERVER_PORT", ("server", "port"), int),
        ("SERVER_DEBUG", ("server", "debug"), lambda v: v.lower() in ("1", "true", "yes")),
    ]:
        val = os.environ.get(env_key)
        if val is not None:
            section, field = cfg_path
            overrides[section][field] = cast(val)

    # Remove empty sub-dicts so deep_merge stays clean
    return {k: v for k, v in overrides.items() if v}


class Config:
    """Immutable application configuration."""

    def __init__(self, raw: dict, source: str):
        self._raw = raw
        self.source = source  # human-readable description of where config came from

        vault = raw.get("vault", {})
        self.vault_addr: str = vault.get("addr", "")
        self.vault_token: str = vault.get("token", "")
        self.vault_namespace: str = vault.get("namespace", "")
        self.vault_mount: str = vault.get("mount", "secret")

        server = raw.get("server", {})
        self.server_host: str = server.get("host", "0.0.0.0")
        self.server_port: int = int(server.get("port", 8080))
        self.server_debug: bool = bool(server.get("debug", False))

    def to_dict(self) -> dict:
        """Return a serialisable representation (token redacted)."""
        return {
            "source": self.source,
            "vault": {
                "addr": self.vault_addr,
                "token": "***" if self.vault_token else "(not set)",
                "namespace": self.vault_namespace or "(default)",
                "mount": self.vault_mount,
            },
            "server": {
                "host": self.server_host,
                "port": self.server_port,
                "debug": self.server_debug,
            },
        }


def load_config() -> Config:
    """
    Load and return the application :class:`Config`.

    Resolution order:
      defaults → config file (if found) → environment variables
    """
    cfg = dict(_DEFAULTS)
    sources: list[str] = ["defaults"]

    config_file = _find_config_file()
    if config_file:
        file_data = _load_yaml_file(config_file)
        cfg = _deep_merge(cfg, file_data)
        sources.append(f"file:{config_file}")
        logger.info("Loaded config from file: %s", config_file)
    else:
        logger.info("No config file found; using defaults + environment variables.")

    env_data = _env_overrides()
    if env_data:
        cfg = _deep_merge(cfg, env_data)
        sources.append("env")
        logger.info("Applied environment variable overrides.")

    source_description = " + ".join(sources)
    return Config(cfg, source_description)
