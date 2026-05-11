"""
Vault client wrapper using the hvac library.

Supports KV v1 and KV v2 secrets engines.
"""

import logging
from typing import Any

import hvac
from hvac.exceptions import InvalidPath, Forbidden, VaultError

from config import Config

logger = logging.getLogger(__name__)


class VaultClient:
    """Thin wrapper around :class:`hvac.Client` for KV operations."""

    def __init__(self, cfg: Config):
        self._cfg = cfg
        client_kwargs: dict[str, Any] = {"url": cfg.vault_addr, "token": cfg.vault_token}
        if cfg.vault_namespace:
            client_kwargs["namespace"] = cfg.vault_namespace
        self._client = hvac.Client(**client_kwargs)
        self._kv_version: int | None = None  # lazily detected

    # ------------------------------------------------------------------
    # Connectivity
    # ------------------------------------------------------------------

    def health(self) -> dict:
        """Return Vault health information."""
        try:
            status = self._client.sys.read_health_status(method="GET")
            return {
                "reachable": True,
                "initialized": status.get("initialized"),
                "sealed": status.get("sealed"),
                "version": status.get("version"),
            }
        except Exception as exc:
            return {"reachable": False, "error": str(exc)}

    def is_authenticated(self) -> bool:
        try:
            return self._client.is_authenticated()
        except Exception:
            return False

    # ------------------------------------------------------------------
    # KV version detection
    # ------------------------------------------------------------------

    def _detect_kv_version(self) -> int:
        """Auto-detect whether the mount is KV v1 or v2."""
        if self._kv_version is not None:
            return self._kv_version
        try:
            mount_config = self._client.sys.read_mount_configuration(
                path=self._cfg.vault_mount
            )
            options = mount_config.get("data", mount_config).get("options") or {}
            version = int(options.get("version", 1))
        except Exception:
            version = 1
        self._kv_version = version
        logger.debug("KV mount '%s' detected as v%d", self._cfg.vault_mount, version)
        return version

    # ------------------------------------------------------------------
    # Secrets CRUD
    # ------------------------------------------------------------------

    def list_secrets(self, path: str = "") -> list[str]:
        """
        List keys at *path* within the configured mount.
        Returns an empty list when the path does not exist.
        """
        mount = self._cfg.vault_mount
        path = path.strip("/")
        try:
            if self._detect_kv_version() == 2:
                result = self._client.secrets.kv.v2.list_secrets(
                    path=path or "/", mount_point=mount
                )
            else:
                result = self._client.secrets.kv.v1.list_secrets(
                    path=path or "/", mount_point=mount
                )
            return result.get("data", {}).get("keys", [])
        except InvalidPath:
            return []
        except Exception as exc:
            raise VaultOperationError(f"list_secrets failed: {exc}") from exc

    def read_secret(self, path: str) -> dict:
        """
        Read the secret data stored at *path* within the configured mount.
        Raises :class:`SecretNotFoundError` when the path does not exist.
        """
        mount = self._cfg.vault_mount
        path = path.strip("/")
        try:
            if self._detect_kv_version() == 2:
                result = self._client.secrets.kv.v2.read_secret_version(
                    path=path, mount_point=mount, raise_on_deleted_version=True
                )
                return result.get("data", {}).get("data", {})
            else:
                result = self._client.secrets.kv.v1.read_secret(
                    path=path, mount_point=mount
                )
                return result.get("data", {})
        except InvalidPath:
            raise SecretNotFoundError(f"Secret not found: {path}")
        except Forbidden as exc:
            raise VaultOperationError(f"Permission denied reading '{path}': {exc}") from exc
        except Exception as exc:
            raise VaultOperationError(f"read_secret failed for '{path}': {exc}") from exc

    def write_secret(self, path: str, data: dict) -> None:
        """
        Create or update the secret at *path* with the given *data* dict.
        """
        mount = self._cfg.vault_mount
        path = path.strip("/")
        try:
            if self._detect_kv_version() == 2:
                self._client.secrets.kv.v2.create_or_update_secret(
                    path=path, secret=data, mount_point=mount
                )
            else:
                self._client.secrets.kv.v1.create_or_update_secret(
                    path=path, secret=data, mount_point=mount
                )
        except Forbidden as exc:
            raise VaultOperationError(f"Permission denied writing '{path}': {exc}") from exc
        except Exception as exc:
            raise VaultOperationError(f"write_secret failed for '{path}': {exc}") from exc

    def delete_secret(self, path: str) -> None:
        """Permanently delete the secret at *path*."""
        mount = self._cfg.vault_mount
        path = path.strip("/")
        try:
            if self._detect_kv_version() == 2:
                self._client.secrets.kv.v2.delete_metadata_and_all_versions(
                    path=path, mount_point=mount
                )
            else:
                self._client.secrets.kv.v1.delete_secret(
                    path=path, mount_point=mount
                )
        except Forbidden as exc:
            raise VaultOperationError(f"Permission denied deleting '{path}': {exc}") from exc
        except Exception as exc:
            raise VaultOperationError(f"delete_secret failed for '{path}': {exc}") from exc


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class SecretNotFoundError(Exception):
    """Raised when a requested Vault secret path does not exist."""


class VaultOperationError(Exception):
    """Raised for unexpected Vault errors."""
