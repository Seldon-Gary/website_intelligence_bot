"""Проверка MCP-сервера отдельно от бота и API.

Показывает, что Playwright MCP — самостоятельная сущность: подключается по
stdio, отдаёт список инструментов, водит браузер. Это же материал для
демонстрации MCP-сервера при сдаче.

Запуск:
    .\\venv\\Scripts\\python.exe -m scripts.check_mcp [URL]
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

# Чтобы скрипт запускался и как `python scripts/check_mcp.py`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import PROXY_URL, SCREENSHOTS_DIR, describe  # noqa: E402
from api.agent.mcp_session import playwright_mcp  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

DEFAULT_URL = "https://example.com"


def _text_of(result) -> str:
    parts = []
    for block in getattr(result, "content", []) or []:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    return "\n".join(parts)


async def main() -> None:
    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL

    print("=" * 70)
    print("Конфигурация:", describe())
    print("Прокси:", PROXY_URL or "не задан, идём напрямую")
    print("=" * 70)

    # allowed=set() -> фильтр не сработает и вернётся полный список инструментов:
    # для проверки нам как раз интересно увидеть всё, что умеет сервер.
    async with playwright_mcp(allowed=set()) as mcp:
        print(f"\nИнструментов доступно: {len(mcp.tool_names)}")
        for name in sorted(mcp.tool_names):
            print("  -", name)

        if PROXY_URL:
            print("\n--- проверка прокси: чей IP видит браузер ---")
            await mcp.call("browser_navigate", {"url": "https://httpbin.org/ip"})
            print(_text_of(await mcp.call("browser_snapshot", {}))[:500])

        print(f"\n--- открываю {url} ---")
        await mcp.call("browser_navigate", {"url": url})
        snapshot = _text_of(await mcp.call("browser_snapshot", {}))
        print(snapshot[:2000])

        shot = SCREENSHOTS_DIR / "check_mcp.png"
        saved = await mcp.screenshot(url, shot)
        print("\nСкриншот:", saved or "не получился")


if __name__ == "__main__":
    asyncio.run(main())
