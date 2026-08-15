"""HTTP-клиент к своему API.

Прокси здесь намеренно не используется: API живёт на 127.0.0.1, гнать
локальный трафик через внешний прокси незачем и вредно.
"""

from __future__ import annotations

import httpx

from config import API_BASE_URL


class ApiError(Exception):
    """Ошибка от API с человекочитаемым текстом."""


_TIMEOUT = httpx.Timeout(30.0, connect=5.0)


async def _request(method: str, path: str, **kwargs) -> object:
    async with httpx.AsyncClient(base_url=API_BASE_URL, timeout=_TIMEOUT) as client:
        try:
            response = await client.request(method, path, **kwargs)
        except httpx.ConnectError as exc:
            raise ApiError("API не отвечает. Запущен ли run_api.ps1?") from exc
        except httpx.HTTPError as exc:
            raise ApiError(f"Сеть подвела: {exc}") from exc

    if response.status_code >= 400:
        try:
            detail = response.json().get("detail", response.text)
        except Exception:
            detail = response.text
        raise ApiError(str(detail))

    return response.json()


async def add_competitor(url: str, name: str | None, owner_tg_id: int) -> dict:
    return await _request(
        "POST", "/competitors", json={"url": url, "name": name, "owner_tg_id": owner_tg_id}
    )


async def list_competitors(owner_tg_id: int) -> list[dict]:
    return await _request("GET", "/competitors", params={"owner_tg_id": owner_tg_id})


async def remove_competitor(competitor_id: int, owner_tg_id: int) -> dict:
    return await _request(
        "DELETE", f"/competitors/{competitor_id}", params={"owner_tg_id": owner_tg_id}
    )


async def start_scan(competitor_id: int, owner_tg_id: int, chat_id: int) -> dict:
    return await _request(
        "POST",
        "/scans",
        json={"competitor_id": competitor_id, "owner_tg_id": owner_tg_id, "chat_id": chat_id},
    )


async def get_snapshot(competitor_id: int, owner_tg_id: int) -> dict:
    return await _request(
        "GET", f"/competitors/{competitor_id}/snapshot", params={"owner_tg_id": owner_tg_id}
    )


async def get_diff(competitor_id: int, owner_tg_id: int) -> dict:
    return await _request(
        "GET", f"/competitors/{competitor_id}/diff", params={"owner_tg_id": owner_tg_id}
    )


async def compare_all(owner_tg_id: int) -> list[dict]:
    return await _request("GET", "/compare", params={"owner_tg_id": owner_tg_id})
