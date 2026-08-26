"""LLMService - Wrapper around Ollama API for document analysis."""

import os
import json
import time
import logging
import asyncio
import httpx
from typing import AsyncGenerator, Optional

from services.multilingual_system_prompt import get_multilingual_system_prompt

logger = logging.getLogger(__name__)

# Configuration
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
# Optional API key for Ollama Cloud (https://ollama.com). When present,
# requests are authenticated with `Authorization: Bearer <key>`.
# When absent, plain local Ollama is used exactly as before.
OLLAMA_API_KEY = os.environ.get("OLLAMA_API_KEY", "")
# Best available now: llama3.1:8b
# Recommended upgrade: qwen2.5:7b
# Best multilingual choice: qwen3:8b (if hardware can run it)
DEFAULT_LLM_MODEL = os.environ.get("DEFAULT_LLM_MODEL", "llama3.1:8b")
OLLAMA_TIMEOUT = int(os.environ.get("OLLAMA_TIMEOUT", 60))
STREAM_CHUNK_SIZE = int(os.environ.get("ANALYSIS_STREAM_CHUNK_SIZE", 10))


class LLMService:
    """Service for interacting with Ollama LLM."""

    def __init__(self):
        self.base_url = OLLAMA_URL.rstrip("/")
        self.default_model = DEFAULT_LLM_MODEL
        self.timeout = OLLAMA_TIMEOUT
        self.api_key = OLLAMA_API_KEY
        # Cloud mode is active whenever an API key is configured.
        self.is_cloud = bool(self.api_key)

    def _headers(self) -> dict:
        """Auth headers for Ollama Cloud. Empty for local Ollama.

        The API key must never be logged or included in error messages.
        """
        if not self.api_key:
            return {}
        return {"Authorization": f"Bearer {self.api_key}"}

    def _describe_host(self) -> str:
        """Human-readable target for logs/responses (never includes the key)."""
        return self.base_url

    async def health_check(self) -> bool:
        """Check if Ollama (local or Cloud) is available."""
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(
                    f"{self.base_url}/api/tags",
                    headers=self._headers(),
                )
                if response.status_code == 200:
                    return True
                logger.error(
                    "Ollama health check returned HTTP %s from %s (%s mode)",
                    response.status_code,
                    self._describe_host(),
                    "cloud" if self.is_cloud else "local",
                )
                return False
        except Exception as e:
            logger.error(f"Ollama health check failed ({self._describe_host()}): {e}")
            return False

    async def get_available_models(self) -> list[str]:
        """Get list of available models."""
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(
                    f"{self.base_url}/api/tags",
                    headers=self._headers(),
                )
                if response.status_code == 200:
                    data = response.json()
                    return [model["name"] for model in data.get("models", [])]
                logger.error(
                    "Failed to list models: HTTP %s from %s",
                    response.status_code,
                    self._describe_host(),
                )
                return []
        except Exception as e:
            logger.error(f"Failed to get models: {e}")
            return []

    async def validate_model(self, model: str) -> bool:
        """Check if model is available."""
        models = await self.get_available_models()
        return model in models

    async def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        stream: bool = False,
    ) -> str:
        """
        Generate response from LLM.

        Args:
            prompt: User prompt
            model: Model name (default: DEFAULT_LLM_MODEL)
            system_prompt: System prompt (optional)
            stream: Whether to stream response

        Returns:
            Generated text (or async generator if stream=True)
        """
        model = model or self.default_model

        payload = {
            "model": model,
            "prompt": prompt,
            "stream": stream,
        }

        if system_prompt:
            payload["system"] = system_prompt

        if stream:
            return self._stream_generate(payload, model)
        else:
            return await self._generate_sync(payload, model)

    async def _generate_sync(self, payload: dict, model: str) -> str:
        """Generate response synchronously."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/generate",
                    json=payload,
                    headers=self._headers(),
                )
                response.raise_for_status()
                data = response.json()
                return data.get("response", "")
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            raise RuntimeError(f"LLM generation failed: {e}")

    async def _stream_generate(self, payload: dict, model: str) -> AsyncGenerator[str, None]:
        """Stream response from LLM."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/api/generate",
                    json=payload,
                    headers=self._headers(),
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if line.strip():
                            try:
                                data = json.loads(line)
                                if "response" in data:
                                    yield data["response"]
                                if data.get("done", False):
                                    break
                            except json.JSONDecodeError:
                                continue
        except Exception as e:
            logger.error(f"LLM streaming failed: {e}")
            raise RuntimeError(f"LLM streaming failed: {e}")

    async def chat_async(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        stream: bool = False,
    ) -> str | AsyncGenerator[str, None]:
        """
        Chat with LLM using message format.

        NOTE: Named chat_async (not chat) because the sync compatibility
        wrapper below (used by api/routes/llm.py) also defines `chat()` and
        would otherwise shadow this async method — which is the method
        analysis_service.py relies on for the Documents > Ask AI feature.

        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model name (default: DEFAULT_LLM_MODEL)
            stream: Whether to stream response

        Returns:
            Generated text (or async generator if stream=True)
        """
        model = model or self.default_model

        payload = {
            "model": model,
            "messages": messages,
            "stream": stream,
        }

        if stream:
            return self._stream_chat(payload, model)
        else:
            return await self._chat_sync(payload, model)

    async def _chat_sync(self, payload: dict, model: str) -> str:
        """Chat synchronously."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/chat",
                    json=payload,
                    headers=self._headers(),
                )
                response.raise_for_status()
                data = response.json()
                return data.get("message", {}).get("content", "")
        except Exception as e:
            logger.error(f"LLM chat failed: {e}")
            raise RuntimeError(f"LLM chat failed: {e}")

    async def _stream_chat(self, payload: dict, model: str) -> AsyncGenerator[str, None]:
        """Stream chat response."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/api/chat",
                    json=payload,
                    headers=self._headers(),
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if line.strip():
                            try:
                                data = json.loads(line)
                                if "message" in data and "content" in data["message"]:
                                    yield data["message"]["content"]
                                if data.get("done", False):
                                    break
                            except json.JSONDecodeError:
                                continue
        except Exception as e:
            logger.error(f"LLM chat streaming failed: {e}")
            raise RuntimeError(f"LLM chat streaming failed: {e}")

    # ------------------------------------------------------------------
    # Compatibility wrappers (sync interface expected by api/routes/llm.py)
    # ------------------------------------------------------------------

    def check_health(self) -> dict:
        """Sync health check — returns dict matching HealthResponse schema."""
        is_healthy = asyncio.run(self.health_check())
        models = asyncio.run(self.get_available_models()) if is_healthy else []
        mode = "cloud" if self.is_cloud else "local"
        if is_healthy:
            detail = None
        else:
            detail = (
                f"Ollama Cloud ({self._describe_host()}) is not reachable "
                "or rejected the API key — verify OLLAMA_URL and OLLAMA_API_KEY"
                if self.is_cloud
                else "Ollama service is not reachable"
            )
        return {
            "status": "healthy" if is_healthy else "unavailable",
            "mode": mode,
            "model": self.default_model,
            "model_available": is_healthy,
            "available_models": models if models else None,
            "detail": detail,
        }

    def chat(
        self,
        message: str,
        history: Optional[list] = None,
        health_context: Optional[str] = None,
        preferred_language: Optional[str] = None,
    ) -> dict:
        """Sync chat — builds messages list and delegates to async chat_async()."""
        # Use the multilingual system prompt with health context embedded
        system_prompt = get_multilingual_system_prompt(
            additional_context=health_context or "",
            preferred_language=preferred_language or "",
        )
        messages: list[dict] = [
            {"role": "system", "content": system_prompt}
        ]
        for entry in (history or []):
            role = entry.get("role", "user")
            content = entry.get("content", "")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": message})

        reply = asyncio.run(self._chat_sync(
            {"model": self.default_model, "messages": messages, "stream": False},
            self.default_model,
        ))
        return {
            "reply": reply,
            "disclaimer": "This response is generated by an AI assistant and should not replace professional medical advice.",
        }

    def analyze(self, health_context: str, preferred_language: Optional[str] = None) -> dict:
        """Sync analyze — delegates to async generate() with multilingual system prompt."""
        prompt = f"Analyze the following health data and provide insights:\n\n{health_context}"
        system_prompt = get_multilingual_system_prompt(
            preferred_language=preferred_language or ""
        )
        result = asyncio.run(self._generate_sync(
            {
                "model": self.default_model,
                "prompt": prompt,
                "system": system_prompt,
                "stream": False,
            },
            self.default_model,
        ))
        return {
            "analysis": result,
            "disclaimer": "This analysis is generated by an AI assistant and should not replace professional medical advice.",
        }

    def suggestions(self, health_context: str, preferred_language: Optional[str] = None) -> dict:
        """Sync suggestions — delegates to async generate() with multilingual system prompt."""
        prompt = f"Based on the following health data, provide wellness suggestions:\n\n{health_context}"
        system_prompt = get_multilingual_system_prompt(
            preferred_language=preferred_language or ""
        )
        result = asyncio.run(self._generate_sync(
            {
                "model": self.default_model,
                "prompt": prompt,
                "system": system_prompt,
                "stream": False,
            },
            self.default_model,
        ))
        return {
            "suggestions": result,
            "disclaimer": "These suggestions are generated by an AI assistant and should not replace professional medical advice.",
        }


# Global instance
llm_service = LLMService()
