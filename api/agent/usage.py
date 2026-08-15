"""Учёт токенов и стоимости скана.

Обход — это не один запрос, а цикл: каждый ход агента отдельный вызов модели,
и вся история пересылается заново. Поэтому токены надо складывать по ходам,
иначе цена скана останется невидимой.
"""

from __future__ import annotations

from dataclasses import dataclass

from config import PRICE_INPUT_PER_MTOK, PRICE_OUTPUT_PER_MTOK


@dataclass
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    requests: int = 0

    def add(self, usage) -> None:
        """Прибавить usage из ответа API (поля кэша есть не всегда)."""
        if usage is None:
            return
        self.requests += 1
        self.input_tokens += getattr(usage, "input_tokens", 0) or 0
        self.output_tokens += getattr(usage, "output_tokens", 0) or 0
        self.cache_read_tokens += getattr(usage, "cache_read_input_tokens", 0) or 0
        self.cache_write_tokens += getattr(usage, "cache_creation_input_tokens", 0) or 0

    def merge(self, other: TokenUsage) -> TokenUsage:
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cache_read_tokens=self.cache_read_tokens + other.cache_read_tokens,
            cache_write_tokens=self.cache_write_tokens + other.cache_write_tokens,
            requests=self.requests + other.requests,
        )

    @property
    def cost(self) -> float | None:
        """Стоимость по ставкам из .env. None, если ставки не заданы.

        Ставки не зашиты в код намеренно: они зависят от модели и от того,
        через кого идёшь — у ProxyAPI свой прайс. Пусто = показываем только токены.
        """
        if not PRICE_INPUT_PER_MTOK and not PRICE_OUTPUT_PER_MTOK:
            return None
        billable_input = self.input_tokens + self.cache_read_tokens + self.cache_write_tokens
        return (
            billable_input / 1_000_000 * PRICE_INPUT_PER_MTOK
            + self.output_tokens / 1_000_000 * PRICE_OUTPUT_PER_MTOK
        )

    def summary(self) -> str:
        parts = [
            f"запросов {self.requests}",
            f"вход {self.input_tokens:,}".replace(",", " "),
            f"выход {self.output_tokens:,}".replace(",", " "),
        ]
        if self.cache_read_tokens:
            parts.append(f"из кэша {self.cache_read_tokens:,}".replace(",", " "))
        cost = self.cost
        if cost is not None:
            parts.append(f"≈ {cost:.2f}")
        return ", ".join(parts)
