"""LLMService — Local-first Ollama wrapper with automatic cloud fallback.

Request flow (matches the agreed architecture):

    user message
        -> try LOCAL Ollama first        (http://localhost:11434)
        -> local stopped / timeout / HTTP error?
              YES -> fall back to CLOUD  (Ollama Cloud, needs CLOUD_LLM_API_KEY)
              NO  -> serve from local
        -> both fail -> RuntimeError     (routes turn this into HTTP 502)

Environment variables (all optional):

    LOCAL_OLLAMA_URL    local endpoint       (default http://localhost:11434)
                        (legacy alias: OLLAMA_URL)
    DEFAULT_LLM_MODEL   local model          (default llama3.1:8b)
    LOCAL_LLM_TIMEOUT   local timeout secs   (default 120, legacy: OLLAMA_TIMEOUT)
    LLM_PROBE_TIMEOUT   availability probe   (default 3 secs)

    CLOUD_LLM_API_KEY   cloud API key        (legacy alias: OLLAMA_API_KEY;
                                             empty = cloud disabled)
    CLOUD_OLLAMA_URL    cloud endpoint       (default https://ollama.com)
    CLOUD_LLM_MODEL     cloud model          (default: same as local model)
    CLOUD_LLM_TIMEOUT   cloud timeout secs   (default 90)
"""

import os
import json
import logging
import asyncio
import httpx
from typing import AsyncGenerator, Optional

from services.multilingual_system_prompt import get_multilingual_system_prompt

logger = logging.getLogger(__name__)

STREAM_CHUNK_SIZE = int(os.environ.get("ANALYSIS_STREAM_CHUNK_SIZE", 10))


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


class _Target:
    """One Ollama-compatible endpoint: the local daemon or Ollama Cloud."""

    def __init__(
        self,
        name: str,
        base_url: str,
        model: str = "",
        api_key: str = "",
        timeout: int = 60,
        probe_timeout: float = 3.0,
    ):
        self.name = name                    # "local" | "cloud"
        self.base_url = base_url.rstrip("/")
        self.model = model                  # "" -> inherit caller-requested model
        self.api_key = api_key              # NEVER logged or echoed
        self.timeout = timeout
        self.probe_timeout = probe_timeout

    @property
    def enabled(self) -> bool:
        if self.name == "cloud":
            # Cloud requires credentials; without a key there is nothing to fall back to.
            return bool(self.api_key)
        return bool(self.base_url)

    def headers(self) -> dict:
        if not self.api_key:
            return {}
        return {"Authorization": f"Bearer {self.api_key}"}

    def __repr__(self) -> str:  # deliberately omits the API key
        return f"<Target {self.name} url={self.base_url!r}>"


# --------------------------------------------------------------------------
# Configuration — evaluated at import time, overridable via environment
# --------------------------------------------------------------------------

LOCAL_TARGET = _Target(
    name="local",
    base_url=os.environ.get(
        "LOCAL_OLLAMA_URL",
        os.environ.get("OLLAMA_URL", "http://localhost:11434"),
    ),
    model=os.environ.get("DEFAULT_LLM_MODEL", "llama3.1:8b"),
    timeout=_env_int("LOCAL_LLM_TIMEOUT", _env_int("OLLAMA_TIMEOUT", 120)),
    probe_timeout=float(os.environ.get("LLM_PROBE_TIMEOUT", 3)),
)

CLOUD_TARGET = _Target(
    name="cloud",
    base_url=os.environ.get("CLOUD_OLLAMA_URL", "https://ollama.com"),
    api_key=os.environ.get("CLOUD_LLM_API_KEY", "") or os.environ.get("OLLAMA_API_KEY", ""),
    model=os.environ.get("CLOUD_LLM_MODEL", ""),  # "" -> same model as local
    timeout=_env_int("CLOUD_LLM_TIMEOUT", 90),
)


class LLMService:
    """Local-first LLM access with automatic cloud fallback."""

    def __init__(self, local: Optional[_Target] = None, cloud: Optional[_Target] = None):
        self.local = local or LOCAL_TARGET
        self.cloud = cloud or CLOUD_TARGET

    # ------------------------------------------------------------------
    # Provider selection
    # ------------------------------------------------------------------

    def _targets(self) -> list:
        """LOCAL first, then CLOUD (when configured). This IS the routing policy."""
        ordered = [self.local]
        if self.cloud.enabled:
            ordered.append(self.cloud)
        return [t for t in ordered if t.enabled]

    def _resolve_model(self, target: "_Target", model: Optional[str]) -> str:
        """Per-target model: caller choice wins, else the target's own model."""
        return model or target.model or self.local.model

    async def _probe(self, target: "_Target") -> tuple:
        """Cheap availability probe. Returns (healthy, models, detail)."""
        if not target.enabled:
            return False, [], "not configured"
        try:
            async with httpx.AsyncClient(timeout=target.probe_timeout) as client:
                response = await client.get(
                    f"{target.base_url}/api/tags",
                    headers=target.headers(),
                )
                if response.status_code == 200:
                    data = response.json()
                    models = [m["name"] for m in data.get("models", [])]
                    return True, models, None
                detail = f"HTTP {response.status_code} from {target.base_url}"
                logger.error("Probe failed on %s target (%s): %s", target.name, target.base_url, detail)
                return False, [], detail
        except Exception as exc:  # connection refused / timeout / DNS
            logger.info("%s target not reachable at %s: %s", target.name, target.base_url, exc)
            return False, [], f"{type(exc).__name__}: {exc}"

    # Backwards-compatible boolean check.
    async def health_check(self) -> bool:
        for target in self._targets():
            healthy, _, _ = await self._probe(target)
            if healthy:
                return True
        return False

    async def get_available_models(self) -> list[str]:
        for target in self._targets():
            healthy, models, _ = await self._probe(target)
            if healthy:
                return models
        return []

    async def validate_model(self, model: str) -> bool:
        return model in await self.get_available_models()


    # ------------------------------------------------------------------
    # Core request execution with LOCAL -> CLOUD failover
    # ------------------------------------------------------------------

    async def complete_chat(self, messages: list[dict], model: Optional[str] = None) -> dict:
        """Chat completion via LOCAL first, falling back to CLOUD."""
        errors: list[str] = []
        for target in self._targets():
            resolved_model = self._resolve_model(target, model)
            payload = {"model": resolved_model, "messages": messages, "stream": False}
            try:
                async with httpx.AsyncClient(timeout=target.timeout) as client:
                    response = await client.post(
                        f"{target.base_url}/api/chat",
                        json=payload,
                        headers=target.headers(),
                    )
                    response.raise_for_status()
                    text = response.json().get("message", {}).get("content", "")
                logger.info(
                    "LLM request served by %s target (%s, model=%s)",
                    target.name, target.base_url, resolved_model,
                )
                return {"text": text, "provider": target.name, "model": resolved_model}
            except Exception as exc:
                logger.warning(
                    "%s LLM target failed (%s, model=%s): %s — trying next provider",
                    target.name, target.base_url, resolved_model, exc,
                )
                errors.append(f"{target.name}: {exc}")
        raise RuntimeError(_all_failed_message(self))

    async def complete_generate(self, prompt: str, model: Optional[str] = None,
                                system_prompt: Optional[str] = None) -> dict:
        """Raw prompt completion via LOCAL first, falling back to CLOUD."""
        errors: list[str] = []
        for target in self._targets():
            resolved_model = self._resolve_model(target, model)
            payload = {"model": resolved_model, "prompt": prompt, "stream": False}
            if system_prompt:
                payload["system"] = system_prompt
            try:
                async with httpx.AsyncClient(timeout=target.timeout) as client:
                    response = await client.post(
                        f"{target.base_url}/api/generate",
                        json=payload,
                        headers=target.headers(),
                    )
                    response.raise_for_status()
                    text = response.json().get("response", "")
                logger.info(
                    "LLM generation served by %s target (%s, model=%s)",
                    target.name, target.base_url, resolved_model,
                )
                return {"text": text, "provider": target.name, "model": resolved_model}
            except Exception as exc:
                logger.warning(
                    "%s LLM target failed during generation (%s, model=%s): %s — trying next provider",
                    target.name, target.base_url, resolved_model, exc,
                )
                errors.append(f"{target.name}: {exc}")
        raise RuntimeError(_all_failed_message(self))


    async def _stream_chat_with_fallback(self, messages: list[dict],
                                         model: Optional[str]) -> AsyncGenerator[str, None]:
        """Streaming chat with failover until the FIRST token arrives.

        Once tokens are flowing, a mid-stream error is raised (we cannot
        restart transparently without duplicating partial output).
        """
        errors: list[str] = []
        for target in self._targets():
            resolved_model = self._resolve_model(target, model)
            payload = {"model": resolved_model, "messages": messages, "stream": True}
            produced_any = False
            try:
                async with httpx.AsyncClient(timeout=self._stream_timeout(target)) as client:
                    async with client.stream(
                        "POST",
                        f"{target.base_url}/api/chat",
                        json=payload,
                        headers=target.headers(),
                    ) as response:
                        response.raise_for_status()
                        async for line in response.aiter_lines():
                            if not line.strip():
                                continue
                            try:
                                data = json.loads(line)
                            except json.JSONDecodeError:
                                continue
                            if "message" in data and "content" in data["message"]:
                                produced_any = True
                                yield data["message"]["content"]
                            if data.get("done", False):
                                break
                logger.info(
                    "LLM stream served by %s target (%s, model=%s)",
                    target.name, target.base_url, resolved_model,
                )
                return
            except Exception as exc:
                if produced_any:
                    # Partial output already emitted to the caller — do not retry.
                    logger.error("Stream broke mid-response on %s target: %s", target.name, exc)
                    raise
                logger.warning(
                    "%s LLM target stream failed (%s, model=%s): %s — trying next provider",
                    target.name, target.base_url, resolved_model, exc,
                )
                errors.append(f"{target.name}: {exc}")
        raise RuntimeError("All LLM providers failed :: " + "; ".join(errors))

    @staticmethod
    def _stream_timeout(target: "_Target") -> httpx.Timeout:
        # Read timeout applies between stream chunks; connect timeout keeps
        # failover fast when the local daemon is down.
        return httpx.Timeout(target.timeout, connect=target.probe_timeout)

    async def chat_async(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        stream: bool = False,
    ):
        """
        Chat with LLM using message format.

        NOTE: Named chat_async (not chat) because the sync compatibility
        wrapper below (used by api/routes/llm.py) also defines `chat()`.

        stream=False -> awaits to a plain string answer.
        stream=True  -> awaits to an async generator of string chunks
                        (calling convention used in services/analysis_service.py).
        LOCAL is always attempted first; failures fall back to CLOUD.
        """
        if stream:
            return self._stream_chat_with_fallback(messages, model)
        result = await self.complete_chat(messages, model=model)
        return result["text"]

    async def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        stream: bool = False,
    ) -> str:
        """Generate completion via LOCAL-first routing."""
        result = await self.complete_generate(
            prompt, model=model, system_prompt=system_prompt
        )
        return result["text"]


    # ------------------------------------------------------------------
    # Compatibility wrappers (sync interface expected by api/routes/llm.py)
    # ------------------------------------------------------------------

    def check_health(self) -> dict:
        """Sync health report with an explicit LOCAL/CLOUD routing outcome."""
        local_ok, local_models, local_detail = asyncio.run(self._probe(self.local))

        if local_ok:
            return {
                "status": "healthy",
                "mode": "local",
                "model": self.local.model,
                "model_available": True,
                "available_models": local_models or None,
                "detail": f"Serving from local Ollama at {self.local.base_url}",
            }

        if self.cloud.enabled:
            cloud_ok, cloud_models, cloud_detail = asyncio.run(self._probe(self.cloud))
        else:
            cloud_ok, cloud_models, cloud_detail = False, [], "no CLOUD_LLM_API_KEY configured"

        if cloud_ok:
            return {
                "status": "healthy",
                "mode": "cloud",
                "model": self.cloud.model or self.local.model,
                "model_available": True,
                "available_models": cloud_models or None,
                "detail": (
                    f"Local Ollama at {self.local.base_url} is unreachable "
                    f"({local_detail}) — serving from cloud"
                ),
            }

        cloud_desc = (
            "configured but unreachable" + (f" ({cloud_detail})" if cloud_detail else "")
            if self.cloud.enabled
            else "not configured (set CLOUD_LLM_API_KEY or OLLAMA_API_KEY to enable fallback)"
        )
        return {
            "status": "unavailable",
            "mode": "unavailable",
            "model": self.local.model,
            "model_available": False,
            "available_models": None,
            "detail": (
                f"Local ({self.local.base_url}): {local_detail} | Cloud: {cloud_desc}"
            ),
        }

    def chat(
        self,
        message: str,
        history: Optional[list] = None,
        health_context: Optional[str] = None,
        preferred_language: Optional[str] = None,
    ) -> dict:
        """Sync chat — builds messages list, runs LOCAL->CLOUD routing."""
        # Use the multilingual system prompt with health context embedded
        system_prompt = get_multilingual_system_prompt(
            additional_context=health_context or "",
            preferred_language=preferred_language or "",
        )
        messages: list[dict] = [
            {"role": "system", "content": system_prompt}
        ]
        for entry in (history or []):
            role = entry.get("role") if isinstance(entry, dict) else None
            content = entry.get("content") if isinstance(entry, dict) else None
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": message})

        result = asyncio.run(self.complete_chat(messages))
        return {
            "reply": result["text"],
            "disclaimer": "This response is generated by an AI assistant and should not replace professional medical advice.",
            "mode": result["provider"],
            "model": result["model"],
        }

    def analyze(self, health_context: str, preferred_language: Optional[str] = None) -> dict:
        """Sync analyze — delegates with multilingual system prompt."""
        prompt = f"Analyze the following health data and provide insights:\n\n{health_context}"
        system_prompt = get_multilingual_system_prompt(
            preferred_language=preferred_language or ""
        )
        result = asyncio.run(self.complete_generate(prompt, system_prompt=system_prompt))
        return {
            "analysis": result["text"],
            "disclaimer": "This analysis is generated by an AI assistant and should not replace professional medical advice.",
            "mode": result["provider"],
            "model": result["model"],
        }

    def suggestions(self, health_context: str, preferred_language: Optional[str] = None) -> dict:
        """Sync suggestions — delegates with multilingual system prompt."""
        prompt = f"Based on the following health data, provide wellness suggestions:\n\n{health_context}"
        system_prompt = get_multilingual_system_prompt(
            preferred_language=preferred_language or ""
        )
        result = asyncio.run(self.complete_generate(prompt, system_prompt=system_prompt))
        return {
            "suggestions": result["text"],
            "disclaimer": "These suggestions are generated by an AI assistant and should not replace professional medical advice.",
            "mode": result["provider"],
            "model": result["model"],
        }


def _all_failed_message(service: "LLMService") -> str:
    """Error shown when neither LOCAL nor CLOUD could serve the request."""
    return (
        "All LLM providers failed "
        f"(local={'configured' if service.local.enabled else 'not configured'} "
        f"at {service.local.base_url}, "
        f"cloud={'configured' if service.cloud.enabled else 'not configured'})"
    )


# Global instance
llm_service = LLMService()
