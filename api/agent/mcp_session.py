"""Подключение к готовому MCP-серверу Playwright.

Сервер запускается как подпроцесс по stdio (`npx @playwright/mcp`) и живёт,
пока открыт контекст. Это и есть главная причина брать MCP, а не свою функцию:
браузер сохраняет состояние между вызовами — открытую страницу, куки, историю.
"""

from __future__ import annotations

import base64
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator

from anthropic.lib.tools.mcp import async_mcp_tool
from mcp import ClientSession, StdioServerParameters, stdio_client

from config import DATA_DIR, PROXY_URL

log = logging.getLogger(__name__)

# Playwright MCP сохраняет сюда свои промежуточные файлы (снапшоты страниц и т.п.).
MCP_OUTPUT_DIR = DATA_DIR / "mcp-output"
MCP_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Playwright MCP 0.0.79 отдаёт 24 инструмента. Все их схемы попадают в контекст
# каждого запроса и размывают внимание модели, поэтому оставляем шесть, которых
# хватает для чтения лендинга. Заполнение форм, загрузка файлов, выполнение
# произвольного кода на странице агенту здесь не нужны — и не должны быть доступны.
ALLOWED_TOOLS = {
    "browser_navigate",
    "browser_navigate_back",
    "browser_snapshot",
    "browser_find",
    "browser_click",
    "browser_wait_for",
}

SCREENSHOT_TOOL = "browser_take_screenshot"
NAVIGATE_TOOL = "browser_navigate"


@dataclass
class PlaywrightMCP:
    """Живая сессия с MCP-сервером."""

    session: ClientSession
    tools: list[Any]
    tool_names: list[str]

    async def call(self, name: str, arguments: dict[str, Any]) -> Any:
        """Прямой вызов инструмента, в обход модели."""
        return await self.session.call_tool(name, arguments)

    async def screenshot(self, url: str, save_to: Path) -> str | None:
        """Вернуться на страницу и снять скриншот.

        Делаем сами, а не просим модель: скриншот нужен всегда и всегда
        с одной и той же страницы — тут решение модели ничего не улучшит.
        """
        try:
            await self.call(NAVIGATE_TOOL, {"url": url})
            result = await self.call(SCREENSHOT_TOOL, {})
        except Exception as exc:
            log.warning("Скриншот не снялся: %s", exc)
            return None

        for block in getattr(result, "content", []) or []:
            data = getattr(block, "data", None)
            if data is None:
                continue
            try:
                save_to.parent.mkdir(parents=True, exist_ok=True)
                save_to.write_bytes(base64.b64decode(data))
            except Exception as exc:
                log.warning("Скриншот не сохранился: %s", exc)
                return None
            return str(save_to)

        log.warning("В ответе %s не нашлось картинки", SCREENSHOT_TOOL)
        return None


def _server_params() -> StdioServerParameters:
    # --isolated: профиль браузера живёт в памяти и не остаётся на диске между сканами.
    # --output-dir: свои файлы сервер складывает в data/, а не в корень проекта.
    args = [
        "@playwright/mcp@latest",
        "--headless",
        "--isolated",
        "--output-dir",
        str(MCP_OUTPUT_DIR),
    ]
    if PROXY_URL:
        args += ["--proxy-server", PROXY_URL]
    log.info("Playwright MCP: npx %s", " ".join(args))
    return StdioServerParameters(command="npx", args=args)


@asynccontextmanager
async def playwright_mcp(*, allowed: set[str] | None = None) -> AsyncIterator[PlaywrightMCP]:
    """Поднять MCP-сервер, отдать отфильтрованные инструменты, закрыть за собой.

    `allowed=None` — рабочий набор ALLOWED_TOOLS.
    `allowed=set()` — все инструменты сервера (нужно скрипту проверки).
    """
    async with stdio_client(_server_params()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            listed = await session.list_tools()
            available = {tool.name: tool for tool in listed.tools}
            log.info("MCP-сервер отдал %s инструментов", len(available))

            if allowed == set():
                selected = list(available.values())
            else:
                allow = ALLOWED_TOOLS if allowed is None else allowed
                selected = [tool for name, tool in available.items() if name in allow]
                missing = allow - set(available)
                if missing:
                    log.warning("Инструменты не найдены на сервере: %s", sorted(missing))
                if not selected:
                    # Имена в новой версии сервера могли поменяться — лучше отдать
                    # модели всё, чем оставить её вообще без браузера.
                    log.warning("Фильтр не выбрал ничего, беру все %s", len(available))
                    selected = list(available.values())
                else:
                    log.info("В работу взято %s из %s", len(selected), len(available))

            yield PlaywrightMCP(
                session=session,
                tools=[async_mcp_tool(tool, session) for tool in selected],
                tool_names=[tool.name for tool in selected],
            )
