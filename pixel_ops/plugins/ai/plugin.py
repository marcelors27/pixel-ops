from __future__ import annotations

import json
import os
import sys
from hashlib import sha256
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import requests


@dataclass(frozen=True)
class AiDecisionRequest:
    system_prompt: str
    user_payload: dict[str, Any]
    schema_name: str
    json_schema: dict[str, Any]
    max_output_tokens: int = 160


class AiDecisionPlugin(Protocol):
    enabled: bool

    def decide_json(self, request: AiDecisionRequest) -> dict[str, Any] | None:
        ...


class OpenAiChatGptPlugin:
    """Generic Pixel OPs AI decision plugin backed by the OpenAI Responses API."""

    name = "openai_chatgpt"

    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self.enabled = bool(self.config.get("enabled", False))
        self.model = str(self.config.get("model", "gpt-5-mini"))
        self.reasoning_effort = str(self.config.get("reasoning_effort", "low"))
        self.timeout_seconds = int(self.config.get("timeout_seconds", 8))
        self.api_key_env = str(self.config.get("api_key_env", "OPENAI_API_KEY"))
        self.cache_enabled = bool(self.config.get("cache_enabled", True))
        self.cache_dir = Path(str(self.config.get("cache_dir", "pixel_ops/cache/ai_decisions")))
        self.debug = _env_bool("PIXEL_OPS_DEBUG_AI") or _env_bool("PIXEL_OPS_DEBUG_EVENTS")

    def decide_json(self, request: AiDecisionRequest) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        cache_key = self._cache_key(request)
        cached = self._read_cache(cache_key)
        if cached is not None:
            self._debug(f"cache hit model={self.model} schema={request.schema_name}")
            return cached

        api_key = os.environ.get(self.api_key_env, "")
        if not api_key:
            self._debug(f"missing api key env {self.api_key_env}")
            return None

        try:
            self._debug(f"request start model={self.model} schema={request.schema_name}")
            response = requests.post(
                "https://api.openai.com/v1/responses",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=self._payload(request),
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            data = response.json()
            self._debug(f"request done status={data.get('status')} model={data.get('model', self.model)}")
            if data.get("status") == "incomplete":
                self._debug(f"incomplete response: {data.get('incomplete_details')}")
            text = self._response_text(data)
            result = json.loads(text) if text else None
            if isinstance(result, dict):
                self._write_cache(cache_key, result)
                return result
            self._debug("response did not contain JSON object text")
            return None
        except (requests.RequestException, TypeError, ValueError, json.JSONDecodeError) as error:
            self._debug(f"request failed: {type(error).__name__}: {error}")
            return None

    def _payload(self, request: AiDecisionRequest) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "input": [
                {
                    "role": "system",
                    "content": request.system_prompt,
                },
                {
                    "role": "user",
                    "content": json.dumps(request.user_payload, ensure_ascii=True, sort_keys=True),
                },
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": request.schema_name,
                    "strict": True,
                    "schema": request.json_schema,
                }
            },
            "max_output_tokens": request.max_output_tokens,
        }
        if self.reasoning_effort:
            payload["reasoning"] = {"effort": self.reasoning_effort}
        return payload

    def _cache_key(self, request: AiDecisionRequest) -> str:
        payload = {
            "model": self.model,
            "system_prompt": request.system_prompt,
            "user_payload": request.user_payload,
            "schema_name": request.schema_name,
            "json_schema": request.json_schema,
        }
        raw = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        return sha256(raw.encode("utf-8")).hexdigest()

    def _read_cache(self, key: str) -> dict[str, Any] | None:
        if not self.cache_enabled:
            return None
        path = self.cache_dir / f"{key}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return data if isinstance(data, dict) else None

    def _write_cache(self, key: str, data: dict[str, Any]) -> None:
        if not self.cache_enabled:
            return
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            path = self.cache_dir / f"{key}.json"
            path.write_text(json.dumps(data, ensure_ascii=True, sort_keys=True), encoding="utf-8")
        except OSError:
            return

    def _response_text(self, data: Any) -> str | None:
        if isinstance(data, dict):
            if isinstance(data.get("output_text"), str):
                return data["output_text"]
            for value in data.values():
                found = self._response_text(value)
                if found:
                    return found
        elif isinstance(data, list):
            for item in data:
                found = self._response_text(item)
                if found:
                    return found
        elif isinstance(data, str):
            stripped = data.strip()
            if stripped.startswith("{") and stripped.endswith("}"):
                return stripped
        return None

    def _debug(self, message: str) -> None:
        if self.debug:
            print(f"[pixel-ops ai] {message}", file=sys.stderr)


def build_ai_plugin(config: dict | None) -> AiDecisionPlugin | None:
    cfg = config or {}
    provider = str(cfg.get("provider", "openai_chatgpt"))
    if provider in ("openai", "openai_chatgpt", "chatgpt"):
        return OpenAiChatGptPlugin(cfg)
    return None


def _env_bool(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")
