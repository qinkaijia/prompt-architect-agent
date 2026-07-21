from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Callable
from typing import Any

import httpx

from prompt_architect.llm.credentials import CredentialStore
from prompt_architect.llm.models import ModelInfo, ModelUsage, ProviderStatus


class ProviderError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.retryable = retryable


class DeepSeekProvider:
    provider_id = "deepseek"
    base_url = "https://api.deepseek.com"

    def __init__(
        self,
        credentials: CredentialStore | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 120.0,
        sleep: Callable[[float], Any] = asyncio.sleep,
    ) -> None:
        self.credentials = credentials or CredentialStore()
        self.transport = transport
        self.timeout = timeout
        self.sleep = sleep

    async def status(self, *, default_model: str = "auto", probe: bool = False) -> ProviderStatus:
        credential = self.credentials.get()
        result = ProviderStatus(
            configured=bool(credential.value),
            source=credential.source,
            key_hint=self.credentials.hint(credential.value),
            default_model=default_model,
            message="尚未设置 DeepSeek API Key。" if not credential.value else "DeepSeek 已配置。",
        )
        if probe and credential.value:
            models = await self.list_models()
            result.connected = True
            result.models = models
            result.message = "DeepSeek 已连接。"
        return result

    async def test_key(self, api_key: str) -> list[ModelInfo]:
        return await self.list_models(api_key=api_key.strip())

    async def list_models(self, *, api_key: str | None = None) -> list[ModelInfo]:
        key = self._key(api_key)
        response = await self._request("GET", "/models", key=key)
        payload = self._json(response)
        models = [
            ModelInfo(id=str(item.get("id", "")).strip(), owned_by=str(item.get("owned_by", "deepseek")))
            for item in payload.get("data", [])
            if isinstance(item, dict) and str(item.get("id", "")).strip()
        ]
        if not models:
            raise ProviderError("no_models", "DeepSeek 未返回可用模型。")
        return sorted(models, key=lambda item: item.id.casefold())

    async def complete_json(
        self,
        messages: list[dict[str, str]],
        *,
        model: str,
        temperature: float = 0.2,
    ) -> tuple[dict[str, Any], ModelUsage]:
        key = self._key(None)
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
            "stream": False,
        }
        response = await self._request("POST", "/chat/completions", key=key, json_body=payload)
        body = self._json(response)
        try:
            content = body["choices"][0]["message"]["content"]
            parsed = self._parse_content(content)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise ProviderError("invalid_response", "DeepSeek 返回了无法解析的结构化结果。") from exc
        usage_data = body.get("usage") or {}
        usage = ModelUsage(
            input_tokens=int(usage_data.get("prompt_tokens", 0) or 0),
            output_tokens=int(usage_data.get("completion_tokens", 0) or 0),
            total_tokens=int(usage_data.get("total_tokens", 0) or 0),
        )
        return parsed, usage

    async def _request(
        self,
        method: str,
        path: str,
        *,
        key: str,
        json_body: dict[str, Any] | None = None,
    ) -> httpx.Response:
        headers = {"Authorization": f"Bearer {key}", "Accept": "application/json"}
        if json_body is not None:
            headers["Content-Type"] = "application/json"
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(
                    base_url=self.base_url,
                    timeout=self.timeout,
                    transport=self.transport,
                    trust_env=True,
                ) as client:
                    response = await client.request(method, path, headers=headers, json=json_body)
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt < 2:
                    await self.sleep(0.25 * (2**attempt))
                    continue
                raise ProviderError("network_error", "无法连接 DeepSeek，请检查网络后重试。", retryable=True) from exc
            if response.status_code in {429, 500, 502, 503, 504} and attempt < 2:
                retry_after = response.headers.get("retry-after")
                delay = float(retry_after) if retry_after and retry_after.replace(".", "", 1).isdigit() else 0.25 * (2**attempt)
                await self.sleep(min(delay, 5.0))
                continue
            if response.is_success:
                return response
            self._raise_for_status(response)
        raise ProviderError("provider_error", "DeepSeek 请求失败。")

    def _key(self, candidate: str | None) -> str:
        if candidate and candidate.strip():
            return candidate.strip()
        credential = self.credentials.get()
        if not credential.value:
            raise ProviderError("not_configured", "请先设置 DeepSeek API Key。", status_code=401)
        return credential.value

    @staticmethod
    def _json(response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise ProviderError("invalid_response", "DeepSeek 返回了无效响应。") from exc
        if not isinstance(payload, dict):
            raise ProviderError("invalid_response", "DeepSeek 返回了无效响应。")
        return payload

    @staticmethod
    def _parse_content(content: Any) -> dict[str, Any]:
        if not isinstance(content, str):
            raise TypeError("content must be a string")
        normalized = content.strip()
        fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", normalized, flags=re.DOTALL | re.IGNORECASE)
        if fenced:
            normalized = fenced.group(1)
        parsed = json.loads(normalized)
        if not isinstance(parsed, dict):
            raise TypeError("JSON result must be an object")
        return parsed

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        status = response.status_code
        if status in {401, 403}:
            raise ProviderError("invalid_api_key", "API Key 无效，请重新复制或创建新密钥。", status_code=status)
        if status == 402:
            raise ProviderError("insufficient_balance", "DeepSeek 余额或额度不足，请充值后重试。", status_code=status)
        if status == 429:
            raise ProviderError("rate_limited", "DeepSeek 请求过于频繁，请稍后重试。", status_code=status, retryable=True)
        if status >= 500:
            raise ProviderError("service_unavailable", "DeepSeek 服务暂时不可用，请稍后重试。", status_code=status, retryable=True)
        raise ProviderError("provider_error", f"DeepSeek 请求失败（HTTP {status}）。", status_code=status)
