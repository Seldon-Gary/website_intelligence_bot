"""Отправка результата скана в Telegram.

Работает напрямую через Bot API по HTTP, без aiogram: процессу api не нужен
весь фреймворк ради двух методов. Идёт через прокси, если он задан.
"""

from __future__ import annotations

import logging
from pathlib import Path

import httpx

from config import BOT_TOKEN, PROXY_URL

log = logging.getLogger(__name__)

_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
_TIMEOUT = httpx.Timeout(60.0, connect=15.0)

# Telegram режет подписи к фото на 1024 символах.
CAPTION_LIMIT = 1024
MESSAGE_LIMIT = 4096


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(proxy=PROXY_URL, timeout=_TIMEOUT)


async def send_message(chat_id: int, text: str) -> None:
    async with _client() as client:
        try:
            response = await client.post(
                f"{_API}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": text[:MESSAGE_LIMIT],
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            log.error("Не отправилось сообщение в чат %s: %s", chat_id, exc)


async def send_photo(chat_id: int, photo_path: str | Path, caption: str = "") -> None:
    """Отправить скриншот. Если файла нет — уходит только текст."""
    path = Path(photo_path)
    if not path.exists():
        log.warning("Скриншот не найден: %s — шлю только текст", path)
        await send_message(chat_id, caption)
        return

    async with _client() as client:
        try:
            with path.open("rb") as file:
                response = await client.post(
                    f"{_API}/sendPhoto",
                    data={
                        "chat_id": str(chat_id),
                        "caption": caption[:CAPTION_LIMIT],
                        "parse_mode": "HTML",
                    },
                    files={"photo": (path.name, file, "image/png")},
                )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            log.error("Не отправился скриншот в чат %s: %s", chat_id, exc)
            await send_message(chat_id, caption)
