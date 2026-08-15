"""Фаза 1: агент водит браузер и пишет заметки о том, что увидел.

Модель сама решает, по каким ссылкам пройти — ориентируется на содержимое
страницы, а не на заранее прописанные селекторы. Поэтому один и тот же код
работает на сайтах, которые мы никогда не видели.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from api.agent.client import MAX_TOKENS, MODEL, OUTPUT_CONFIG, client
from api.agent.mcp_session import playwright_mcp
from api.agent.prompts import CRAWL_SYSTEM, CRAWL_USER
from api.agent.usage import TokenUsage
from config import MAX_PAGES_PER_SCAN, SCREENSHOTS_DIR

log = logging.getLogger(__name__)

# Потолок ходов цикла: на каждую страницу уходит переход + чтение, плюс запас
# на поиск нужных ссылок. Страховка от агента, ушедшего гулять по всему сайту.
MAX_ITERATIONS = 20


@dataclass
class CrawlResult:
    notes: str
    tool_calls: int
    pages_visited: int
    screenshot_path: str | None
    usage: TokenUsage


async def crawl_site(*, name: str, url: str, scan_id: int) -> CrawlResult:
    notes: list[str] = []
    tool_calls = 0
    navigations = 0
    usage = TokenUsage()

    async with playwright_mcp() as mcp:
        log.info("Скан %s: инструменты агента — %s", scan_id, ", ".join(mcp.tool_names))

        runner = client.beta.messages.tool_runner(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=CRAWL_SYSTEM.format(max_pages=MAX_PAGES_PER_SCAN),
            messages=[{"role": "user", "content": CRAWL_USER.format(name=name, url=url)}],
            tools=mcp.tools,
            max_iterations=MAX_ITERATIONS,
            output_config=OUTPUT_CONFIG,
        )

        async for message in runner:
            # Каждый ход цикла — отдельный запрос, и вся история летит заново.
            # Складываем, иначе цена обхода останется невидимой.
            usage.add(message.usage)
            for block in message.content:
                if block.type == "text" and block.text.strip():
                    notes.append(block.text.strip())
                elif block.type == "tool_use":
                    tool_calls += 1
                    if block.name == "browser_navigate":
                        navigations += 1

        log.info(
            "Скан %s: обход закончен, вызовов инструментов %s, переходов %s",
            scan_id,
            tool_calls,
            navigations,
        )
        log.info("Скан %s: фаза 1 — %s", scan_id, usage.summary())

        # Скриншот снимаем сами, уже после обхода: браузер всё ещё жив в той же
        # MCP-сессии, достаточно вернуться на стартовую страницу.
        screenshot = await mcp.screenshot(url, SCREENSHOTS_DIR / f"scan_{scan_id}.png")

    return CrawlResult(
        notes="\n\n".join(notes),
        tool_calls=tool_calls,
        pages_visited=navigations,
        screenshot_path=screenshot,
        usage=usage,
    )
