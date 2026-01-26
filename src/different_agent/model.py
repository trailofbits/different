from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from langchain_core.language_models import BaseChatModel

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResolvedModel:
    model: BaseChatModel
    provider: str
    name: str


def _strip_provider_prefix(model_name: str) -> str:
    if ":" in model_name:
        maybe_provider, rest = model_name.split(":", 1)
        if maybe_provider in {"openai", "anthropic", "google", "vertexai"}:
            return rest
    return model_name


def _detect_provider(model_name: str, provider_hint: str | None = None) -> str:
    if ":" in model_name:
        maybe_provider, _rest = model_name.split(":", 1)
        if maybe_provider in {"openai", "anthropic", "google", "vertexai"}:
            return maybe_provider
    lower = model_name.lower()
    if any(x in lower for x in ("gpt", "o1", "o3")):
        return "openai"
    if "claude" in lower:
        return "anthropic"
    if provider_hint:
        return provider_hint
    raise ValueError(f"Could not detect provider from model name: {model_name}")


def create_chat_model(
    *,
    model_name: str,
    provider: str | None = None,
    temperature: float = 0.0,
    reasoning_effort: str | None = None,
) -> ResolvedModel:
    provider = _detect_provider(model_name, provider_hint=provider)
    raw_name = _strip_provider_prefix(model_name)
    logger.info("creating chat model provider=%s name=%s", provider, raw_name)

    if provider == "openai":
        if not os.environ.get("OPENAI_API_KEY"):
            raise SystemExit("OPENAI_API_KEY is required for OpenAI models")
        from langchain_openai import ChatOpenAI

        return ResolvedModel(
            model=ChatOpenAI(
                model_name=raw_name,
                temperature=temperature,
                reasoning_effort=reasoning_effort,
            ),
            provider=provider,
            name=raw_name,
        )

    if provider == "anthropic":
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise SystemExit("ANTHROPIC_API_KEY is required for Anthropic models")
        from langchain_anthropic import ChatAnthropic

        return ResolvedModel(
            model=ChatAnthropic(
                model_name=raw_name,
                temperature=temperature,
                max_tokens=20_000,
            ),
            provider=provider,
            name=raw_name,
        )

    raise ValueError(f"Unsupported provider: {provider}")
