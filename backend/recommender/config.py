from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

Provider = Literal["gemini", "ollama", "openai"]

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
OLLAMA_BASE_URL = "http://127.0.0.1:11434/v1"

_PLACEHOLDERS = {
    "",
    "sk-...",
    "sk-your-key-here",
    "AIza...",
    "your-gemini-api-key",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    llm_provider: Provider = "gemini"
    openai_api_key: str = ""
    gemini_api_key: str = ""
    openai_model: str = ""
    openai_base_url: str | None = None
    request_timeout_s: float = 50.0
    max_tool_rounds: int = 2
    recommendations_per_agent: int = 12

    @property
    def resolved_api_key(self) -> str:
        if self.llm_provider == "gemini":
            return (self.gemini_api_key or self.openai_api_key).strip()
        if self.llm_provider == "ollama":
            return (self.openai_api_key or "ollama").strip()
        return self.openai_api_key.strip()

    @property
    def resolved_base_url(self) -> str | None:
        if self.openai_base_url:
            return self.openai_base_url
        if self.llm_provider == "gemini":
            return GEMINI_BASE_URL
        if self.llm_provider == "ollama":
            return OLLAMA_BASE_URL
        return None

    @property
    def resolved_model(self) -> str:
        if self.openai_model:
            return self.openai_model
        if self.llm_provider == "gemini":
            return "gemini-3.8-flash"
        if self.llm_provider == "ollama":
            return "llama3.2"
        return "gpt-4.1-mini"

    @property
    def has_valid_api_key(self) -> bool:
        if self.llm_provider == "ollama":
            return True
        key = self.resolved_api_key
        if key in _PLACEHOLDERS:
            return False
        if key.startswith("sk-...") and len(key) < 20:
            return False
        if self.llm_provider == "gemini":
            return len(key) >= 20
        return len(key) >= 20


settings = Settings()
