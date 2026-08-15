"""Фаза 2: заметки об обходе превращаются в строгую схему.

Отдельным вызовом, без инструментов. Разделение спасает результат: если агент
дошёл только до половины страниц, заметки всё равно есть и карточка соберётся
из того, что успели увидеть.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from api.agent.client import MODEL, client
from api.agent.prompts import EXTRACT_SYSTEM, EXTRACT_USER
from api.agent.usage import TokenUsage
from api.schemas import Offer

log = logging.getLogger(__name__)

# Заметок обычно немного, а схема компактная — большой лимит здесь не нужен.
MAX_TOKENS = 8000


@dataclass
class ExtractResult:
    offer: Offer
    usage: TokenUsage


async def extract_offer(*, name: str, url: str, notes: str) -> ExtractResult:
    usage = TokenUsage()

    if not notes.strip():
        log.warning("Пустые заметки по %s — возвращаю пустую карточку", url)
        return ExtractResult(offer=Offer(headline="", pages_visited=[url]), usage=usage)

    response = await client.messages.parse(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=EXTRACT_SYSTEM,
        messages=[
            {"role": "user", "content": EXTRACT_USER.format(name=name, url=url, notes=notes)}
        ],
        output_format=Offer,
    )
    usage.add(response.usage)

    offer = response.parsed_output
    if offer is None:
        # Схема не собралась — не роняем скан, отдаём пустую карточку.
        log.error("Не удалось разобрать оффер для %s", url)
        return ExtractResult(offer=Offer(headline="", pages_visited=[url]), usage=usage)

    if not offer.pages_visited:
        offer.pages_visited = [url]

    log.info(
        "Оффер собран: %s тарифов, %s выгод%s",
        len(offer.plans),
        len(offer.value_props),
        ", цены текстом" if not offer.plans and offer.pricing_note else "",
    )
    log.info("Фаза 2 — %s", usage.summary())
    return ExtractResult(offer=offer, usage=usage)
