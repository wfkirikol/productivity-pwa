from dataclasses import dataclass
from time import monotonic

import httpx

from core.config import Settings, get_settings
from core.logger import get_logger


_FALLBACKS = {
    "motivation": "Не нужно решать всё сразу. Откройте задачу и уделите ей первые пять минут: этого достаточно, чтобы начать.",
    "time_management": "Выберите одну задачу с ближайшим сроком и выделите на неё короткий рабочий блок. Остальное перенесите в следующий свободный слот.",
    "decomposition": "1. Запишите самый первый физический шаг.\n2. Выполните его за 10 минут.\n3. Зафиксируйте следующий шаг и продолжите с него.",
}


@dataclass(frozen=True, slots=True)
class AIResult:
    text: str
    fallback: bool
    scenario: str


class OpenRouterAdapter:
    def __init__(
        self,
        settings: Settings | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.transport = transport
        self.logger = get_logger("openrouter")

    async def complete(
        self,
        scenario: str,
        system_prompt: str,
        user_prompt: str,
        response_format: dict[str, str] | None = None,
    ) -> AIResult:
        fallback = _FALLBACKS.get(scenario, _FALLBACKS["motivation"])
        api_key = self.settings.openrouter_api_key
        if api_key is None or not api_key.get_secret_value().strip():
            self.logger.warning("OpenRouter request skipped: API key is not configured")
            return AIResult(fallback, True, scenario)

        endpoint = f"{self.settings.openrouter_base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key.get_secret_value()}",
            "Content-Type": "application/json",
            "HTTP-Referer": self.settings.app_url,
            "X-Title": self.settings.app_name,
        }
        payload = {
            "model": self.settings.openrouter_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        if response_format is not None:
            payload["response_format"] = response_format
        started = monotonic()
        self.logger.info("OpenRouter request started scenario=%s model=%s", scenario, self.settings.openrouter_model)
        try:
            async with httpx.AsyncClient(
                timeout=self.settings.openrouter_timeout_seconds,
                transport=self.transport,
            ) as client:
                response = await client.post(endpoint, headers=headers, json=payload)
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
                if not isinstance(content, str) or not content.strip():
                    raise ValueError("The model returned an empty response")
        except httpx.HTTPStatusError as error:
            status_code = error.response.status_code
            if status_code == 429:
                self.logger.warning("OpenRouter rate limit reached scenario=%s", scenario)
            else:
                self.logger.error("OpenRouter returned HTTP %s scenario=%s", status_code, scenario)
            return AIResult(fallback, True, scenario)
        except (httpx.TimeoutException, httpx.RequestError) as error:
            self.logger.warning(
                "OpenRouter network failure scenario=%s error=%s",
                scenario,
                type(error).__name__,
            )
            return AIResult(fallback, True, scenario)
        except (KeyError, IndexError, TypeError, ValueError):
            self.logger.exception("OpenRouter response could not be parsed scenario=%s", scenario)
            return AIResult(fallback, True, scenario)

        elapsed_ms = int((monotonic() - started) * 1000)
        self.logger.info("OpenRouter response received scenario=%s elapsed_ms=%s", scenario, elapsed_ms)
        return AIResult(content.strip(), False, scenario)
