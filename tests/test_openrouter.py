import asyncio
import json

import httpx
from pydantic import SecretStr

from adapters.openrouter import OpenRouterAdapter
from adapters.prompts import (
    build_decomposition_prompt,
    build_motivation_prompt,
    build_time_management_prompt,
)
from core.config import Settings


def run_complete(adapter: OpenRouterAdapter, scenario: str = "motivation"):
    return asyncio.run(adapter.complete(scenario, "system prompt", "user prompt"))


def test_openrouter_success_sends_auth_and_app_headers():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer test-key"
        assert request.headers["HTTP-Referer"] == "http://localhost:5173"
        assert request.headers["X-Title"] == "Test App"
        assert json.loads(request.content)["model"] == "google/gemma-4-31b-it:free"
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "Начните с первого шага."}}]},
        )

    settings = Settings(
        _env_file=None,
        openrouter_api_key=SecretStr("test-key"),
        app_name="Test App",
        app_url="http://localhost:5173",
    )
    result = run_complete(OpenRouterAdapter(settings, httpx.MockTransport(handler)))

    assert result.text == "Начните с первого шага."
    assert result.fallback is False


def test_missing_key_returns_fallback_without_network_request():
    def handler(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("The network should not be called without an API key")

    adapter = OpenRouterAdapter(
        Settings(_env_file=None, openrouter_api_key=None),
        httpx.MockTransport(handler),
    )
    result = run_complete(adapter, "decomposition")

    assert result.fallback is True
    assert "10 минут" in result.text


def test_openrouter_429_returns_fallback():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"message": "rate limited"}})

    settings = Settings(_env_file=None, openrouter_api_key=SecretStr("test-key"))
    result = run_complete(OpenRouterAdapter(settings, httpx.MockTransport(handler)))

    assert result.fallback is True
    assert "первые пять минут" in result.text


def test_openrouter_timeout_returns_fallback():
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("upstream timeout")

    settings = Settings(_env_file=None, openrouter_api_key=SecretStr("test-key"))
    result = run_complete(OpenRouterAdapter(settings, httpx.MockTransport(handler)))

    assert result.fallback is True
    assert result.scenario == "motivation"


def test_prompt_packs_include_context_and_action_constraints():
    motivation = build_motivation_prompt(
        {"title": "Prepare report", "status": "PENDING"}, "Open the file", 15
    )
    planning = build_time_management_prompt(
        [{"title": "Prepare report", "priority": "HIGH", "estimated_minutes": 30}], 60
    )
    decomposition = build_decomposition_prompt("Launch project", "Set up first page")

    assert '"current_goal": "Open the file"' in motivation.user
    assert '"available_minutes": 60' in planning.user
    assert "2–3" in motivation.system
    assert "3–4" in decomposition.system
    assert "10–15 минут" in decomposition.system
