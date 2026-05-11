"""
Configuration loader for vault-demo-web.

This app does NOT talk to Vault directly.  Secrets are delivered by
Vault Agent (rendered template files) or the Vault Secrets Operator
(environment variables / mounted Kubernetes Secret files).

Priority (highest to lowest):
  1. Environment variables
  2. Config file (path from CONFIG_FILE env var, or searched in standard locations)
  3. Built-in defaults

Supported environment variables:
  CONFIG_FILE          – explicit path to a YAML config file
  SERVER_HOST          – Flask bind host                    (default: 0.0.0.0)
  SERVER_PORT          – Flask bind port                    (default: 8080)
  SERVER_DEBUG         – Enable Flask debug mode            (default: false)
  SECRETS_SOURCE       – Where injected secrets come from:
                         "file" | "env" | "both"            (default: file)
  SECRETS_PATH         – Directory of Vault-Agent-rendered files
                                                            (default: /vault/secrets)
  SECRETS_ENV_PREFIX   – Env-var prefix used by the Secrets Operator
                                                            (default: SECRET_)
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
    "server": {
        "host": "0.0.0.0",
        "port": 8080,
        "debug": False,
    },
    "secrets": {
        "source": "file",          # "file" | "env" | "both"
        "path": "/vault/secrets",  # Vault Agent rendered-template directory
        "env_prefix": "SECRET_",   # prefix used by Vault Secrets Operator
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
    overrides: dict[str, Any] = {"server": {}, "secrets": {}}

    for env_key, cfg_path, cast in [
        ("SERVER_HOST",        ("server", "host"),         str),
        ("SERVER_PORT",        ("server", "port"),         int),
        ("SERVER_DEBUG",       ("server", "debug"),        lambda v: v.lower() in ("1", "true", "yes")),
        ("SECRETS_SOURCE",     ("secrets", "source"),      str),
        ("SECRETS_PATH",       ("secrets", "path"),        str),
        ("SECRETS_ENV_PREFIX", ("secrets", "env_prefix"),  str),
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

        server = raw.get("server", {})
        self.server_host: str = server.get("host", "0.0.0.0")
        self.server_port: int = int(server.get("port", 8080))
        self.server_debug: bool = bool(server.get("debug", False))

        secrets = raw.get("secrets", {})
        self.secrets_source: str = secrets.get("source", "file")
        self.secrets_path: str = secrets.get("path", "/vault/secrets")
        self.secrets_env_prefix: str = secrets.get("env_prefix", "SECRET_")

    def to_dict(self) -> dict:
        """Return a serialisable representation."""
        return {
            "source": self.source,
            "server": {
                "host": self.server_host,
                "port": self.server_port,
                "debug": self.server_debug,
            },
            "secrets": {
                "source": self.secrets_source,
                "path": self.secrets_path,
                "env_prefix": self.secrets_env_prefix,
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
