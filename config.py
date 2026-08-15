"""Общие настройки для api и bot. Читаются из .env один раз при импорте.

Пустой PROXY_URL означает работу напрямую, без прокси, — это позволяет
собирать и запускать проект до того, как определён адрес прокси.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")


def _flag(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


# --- Секреты ---
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()

# Хост API Claude. Пусто = официальный api.anthropic.com.
# ProxyAPI: https://api.proxyapi.ru/anthropic — формат запросов там идентичен
# оригиналу, поэтому меняется только адрес, а код остаётся тем же.
ANTHROPIC_BASE_URL: str | None = os.getenv("ANTHROPIC_BASE_URL", "").strip() or None

# --- Прокси ---
# None вместо пустой строки: клиенты httpx/aiohttp принимают None как "без прокси".
PROXY_URL: str | None = os.getenv("PROXY_URL", "").strip() or None
ANTHROPIC_VIA_PROXY = _flag("ANTHROPIC_VIA_PROXY")

# Прокси для запросов к Anthropic — только если явно разрешён флагом.
ANTHROPIC_PROXY: str | None = PROXY_URL if ANTHROPIC_VIA_PROXY else None

# --- Сеть ---
API_HOST = os.getenv("API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("API_PORT", "8000"))
# Локальный адрес: бот ходит к api напрямую, минуя прокси.
API_BASE_URL = os.getenv("API_BASE_URL", f"http://{API_HOST}:{API_PORT}").rstrip("/")

# --- Агент ---
MODEL = os.getenv("MODEL", "claude-sonnet-5")
EFFORT = os.getenv("EFFORT", "medium").strip().lower()
MAX_PAGES_PER_SCAN = int(os.getenv("MAX_PAGES_PER_SCAN", "4"))


def _price(name: str) -> float:
    try:
        return float(os.getenv(name, "0").strip() or 0)
    except ValueError:
        return 0.0


# Ставки за миллион токенов — из твоего кабинета (у ProxyAPI свой прайс).
# Оба нуля = цену не считаем, показываем только количество токенов.
PRICE_INPUT_PER_MTOK = _price("PRICE_INPUT_PER_MTOK")
PRICE_OUTPUT_PER_MTOK = _price("PRICE_OUTPUT_PER_MTOK")

# --- Пути ---
DATA_DIR = ROOT / "data"
SCREENSHOTS_DIR = DATA_DIR / "screenshots"
DB_PATH = DATA_DIR / "radar.db"

SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)


def describe() -> str:
    """Короткая сводка конфигурации для логов при старте (без секретов)."""
    return (
        f"model={MODEL} effort={EFFORT} "
        f"claude_host={ANTHROPIC_BASE_URL or 'api.anthropic.com'} "
        f"proxy={PROXY_URL or 'direct'} "
        f"anthropic_via_proxy={ANTHROPIC_VIA_PROXY} "
        f"api={API_BASE_URL} "
        f"max_pages={MAX_PAGES_PER_SCAN}"
    )
