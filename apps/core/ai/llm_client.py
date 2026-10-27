"""Provider-agnostic LLM client.

Supported providers (``AI_PROVIDER``):
- ``openai``    – any OpenAI-compatible Chat Completions API (OpenAI, Groq, Mistral,
                  OpenRouter, Ollama, ...) at ``AI_BASE_URL``;
- ``anthropic`` – Anthropic Messages API;
- ``local``     – no network: callers use their local model instead.

Every call has a timeout, retries with exponential backoff on transient errors,
and raises :class:`LLMError` for anything that goes wrong.
"""

import json
import logging
import time
from dataclasses import dataclass

import httpx
from django.conf import settings

logger = logging.getLogger("apps.ai")

RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}


class LLMError(Exception):
    """Clean exception for every LLM failure (network, HTTP, bad JSON)."""


@dataclass
class LLMClient:
    provider: str = "local"
    api_key: str = ""
    base_url: str = ""
    model: str = ""
    timeout: float = 15.0
    max_retries: int = 2

    @classmethod
    def from_settings(cls) -> "LLMClient":
        return cls(
            provider=(settings.AI_PROVIDER or "local").lower(),
            api_key=settings.AI_API_KEY,
            base_url=settings.AI_BASE_URL.rstrip("/"),
            model=settings.AI_MODEL,
            timeout=settings.AI_TIMEOUT,
            max_retries=settings.AI_MAX_RETRIES,
        )

    @property
    def is_remote(self) -> bool:
        return self.provider in ("openai", "anthropic") and bool(self.api_key)

    @property
    def name(self) -> str:
        return f"{self.provider}:{self.model}" if self.is_remote else "local"

    def _request(self, system: str, user: str) -> tuple[str, dict, dict]:
        if self.provider == "anthropic":
            url = f"{self.base_url}/messages"
            headers = {"x-api-key": self.api_key, "anthropic-version": "2023-06-01"}
            body = {
                "model": self.model,
                "max_tokens": 800,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            }
        else:
            url = f"{self.base_url}/chat/completions"
            headers = {"Authorization": f"Bearer {self.api_key}"}
            body = {
                "model": self.model,
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            }
        return url, headers, body

    def _extract_text(self, data: dict) -> str:
        try:
            if self.provider == "anthropic":
                return "".join(b.get("text", "") for b in data["content"] if b.get("type") == "text")
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"Réponse inattendue du fournisseur IA: {exc}") from exc

    def complete_json(self, system: str, user: str) -> dict:
        """Send a prompt and parse a JSON object from the answer."""
        if not self.is_remote:
            raise LLMError("Aucun fournisseur IA distant configuré.")
        url, headers, body = self._request(system, user)
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = httpx.post(url, json=body, headers=headers, timeout=self.timeout)
                if resp.status_code in RETRYABLE_STATUS:
                    raise httpx.HTTPStatusError(f"HTTP {resp.status_code}", request=resp.request, response=resp)
                resp.raise_for_status()
                return parse_json_object(self._extract_text(resp.json()))
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                if exc.response.status_code not in RETRYABLE_STATUS:
                    break
            except (httpx.TransportError, ValueError) as exc:
                last_exc = exc
            logger.warning("LLM call failed (attempt %s/%s): %s", attempt + 1, self.max_retries + 1, last_exc)
            if attempt < self.max_retries:
                time.sleep(0.5 * 2**attempt)
        raise LLMError(f"Échec de l'appel au fournisseur IA: {last_exc}")


def parse_json_object(text: str) -> dict:
    """Parse the first JSON object in ``text`` (models sometimes wrap it in prose)."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise LLMError("La réponse IA ne contient pas de JSON.")
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise LLMError(f"JSON invalide renvoyé par l'IA: {exc}") from exc
