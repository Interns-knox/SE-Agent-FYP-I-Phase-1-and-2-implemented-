from abc import ABC, abstractmethod

import httpx

from app.config import settings


class LLMProvider(ABC):
    @abstractmethod
    def generate(self, prompt: str) -> str:
        """Send prompt; return raw string response."""
        ...


class OllamaProvider(LLMProvider):
    def __init__(self, url: str, model: str):
        self.url = url
        self.model = model

    def generate(self, prompt: str) -> str:
        payload: dict = {"model": self.model, "prompt": prompt, "stream": False}
        if settings.OLLAMA_THINK is not None:
            payload["think"] = settings.OLLAMA_THINK
        if settings.OLLAMA_NUM_CTX:
            payload["options"] = {"num_ctx": settings.OLLAMA_NUM_CTX}
        response = httpx.post(
            f"{self.url}/api/generate",
            json=payload,
            timeout=settings.LLM_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return response.json()["response"]


def get_llm_provider() -> LLMProvider:
    """Factory: reads LLM_PROVIDER env var, returns concrete implementation."""
    if settings.LLM_PROVIDER == "ollama":
        return OllamaProvider(url=settings.OLLAMA_URL, model=settings.OLLAMA_MODEL)
    raise ValueError(f"Unknown LLM_PROVIDER: {settings.LLM_PROVIDER}")
