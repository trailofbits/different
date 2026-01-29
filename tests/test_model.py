from __future__ import annotations

import sys
import types

import pytest

from different_agent.model import (
    _detect_provider,
    _strip_provider_prefix,
    create_chat_model,
)


def test_strip_provider_prefix() -> None:
    assert _strip_provider_prefix("openai:gpt-5") == "gpt-5"
    assert _strip_provider_prefix("gpt-5") == "gpt-5"


def test_detect_provider_prefers_prefix() -> None:
    assert _detect_provider("anthropic:claude-3") == "anthropic"


def test_detect_provider_from_name_and_hint() -> None:
    assert _detect_provider("gpt-5") == "openai"
    assert _detect_provider("claude-sonnet") == "anthropic"
    assert _detect_provider("custom", provider_hint="openai") == "openai"


def test_detect_provider_unknown_raises() -> None:
    with pytest.raises(ValueError, match="Could not detect provider"):
        _detect_provider("mystery-model")


def test_create_chat_model_openai_requires_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(SystemExit, match="OPENAI_API_KEY is required"):
        create_chat_model(model_name="gpt-5")


def test_create_chat_model_openai_success(monkeypatch: pytest.MonkeyPatch) -> None:
    class DummyChat:
        def __init__(
            self, model_name: str, temperature: float, reasoning_effort: str | None = None
        ):
            self.model_name = model_name
            self.temperature = temperature
            self.reasoning_effort = reasoning_effort

    dummy_module = types.SimpleNamespace(ChatOpenAI=DummyChat)
    monkeypatch.setitem(sys.modules, "langchain_openai", dummy_module)
    monkeypatch.setenv("OPENAI_API_KEY", "ok")

    resolved = create_chat_model(
        model_name="openai:gpt-5.2",
        provider=None,
        temperature=0.1,
        reasoning_effort="medium",
    )
    assert resolved.provider == "openai"
    assert resolved.name == "gpt-5.2"
    assert isinstance(resolved.model, DummyChat)
    assert resolved.model.model_name == "gpt-5.2"


def test_create_chat_model_anthropic_success(monkeypatch: pytest.MonkeyPatch) -> None:
    class DummyChat:
        def __init__(self, model_name: str, temperature: float, max_tokens: int):
            self.model_name = model_name
            self.temperature = temperature
            self.max_tokens = max_tokens

    dummy_module = types.SimpleNamespace(ChatAnthropic=DummyChat)
    monkeypatch.setitem(sys.modules, "langchain_anthropic", dummy_module)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "ok")

    resolved = create_chat_model(
        model_name="anthropic:claude-sonnet",
        provider=None,
        temperature=0.0,
        reasoning_effort=None,
    )
    assert resolved.provider == "anthropic"
    assert resolved.name == "claude-sonnet"
    assert isinstance(resolved.model, DummyChat)
