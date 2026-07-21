from __future__ import annotations

import os
from dataclasses import dataclass


class CredentialUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True)
class CredentialValue:
    value: str | None
    source: str


class CredentialStore:
    """Read environment credentials first, then the OS credential vault."""

    service_name = "PromptArchitectAgent"
    username = "deepseek-api-key"
    environment_name = "DEEPSEEK_API_KEY"

    def __init__(self, backend=None) -> None:
        self._backend = backend

    def get(self) -> CredentialValue:
        environment = os.environ.get(self.environment_name, "").strip()
        if environment:
            return CredentialValue(environment, "environment")
        try:
            value = self._keyring().get_password(self.service_name, self.username)
        except Exception:
            return CredentialValue(None, "none")
        return CredentialValue(value.strip() if value else None, "credential_store" if value else "none")

    def set(self, value: str) -> None:
        normalized = value.strip()
        if not normalized:
            raise ValueError("API Key 不能为空。")
        if os.environ.get(self.environment_name, "").strip():
            raise CredentialUnavailableError("当前密钥由 DEEPSEEK_API_KEY 环境变量管理。")
        try:
            self._keyring().set_password(self.service_name, self.username, normalized)
        except Exception as exc:
            raise CredentialUnavailableError(
                "无法使用系统凭据库，请设置 DEEPSEEK_API_KEY 环境变量。"
            ) from exc

    def delete(self) -> bool:
        if os.environ.get(self.environment_name, "").strip():
            raise CredentialUnavailableError("当前密钥由 DEEPSEEK_API_KEY 环境变量管理。")
        current = self.get()
        if not current.value:
            return False
        try:
            self._keyring().delete_password(self.service_name, self.username)
        except Exception as exc:
            raise CredentialUnavailableError("无法从系统凭据库移除密钥。") from exc
        return True

    def _keyring(self):
        if self._backend is not None:
            return self._backend
        try:
            import keyring
        except ImportError as exc:
            raise CredentialUnavailableError(
                "系统凭据组件不可用，请设置 DEEPSEEK_API_KEY 环境变量。"
            ) from exc
        return keyring

    @staticmethod
    def hint(value: str | None) -> str | None:
        if not value:
            return None
        return f"•••• {value[-4:]}"
