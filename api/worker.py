"""Фоновая обработка сканов.

Обход конкурента занимает минуты — Telegram столько не ждёт. Бот кладёт
задачу в очередь и сразу отвечает, а результат уходит в чат отсюда.
"""

from __future__ import annotations

import asyncio
import logging

from api import notify
from api.agent.crawl import crawl_site
from api.agent.extract import extract_offer
from api.db import Competitor, Scan, Snapshot, get_session, utcnow
from api.render import render_offer

log = logging.getLogger(__name__)

_queue: asyncio.Queue[int] = asyncio.Queue()
_worker_task: asyncio.Task | None = None


def enqueue(scan_id: int) -> None:
    _queue.put_nowait(scan_id)


def start() -> None:
    global _worker_task
    if _worker_task is None or _worker_task.done():
        _worker_task = asyncio.create_task(_loop(), name="scan-worker")
        log.info("Воркер сканов запущен")


async def stop() -> None:
    if _worker_task is not None and not _worker_task.done():
        _worker_task.cancel()
        try:
            await _worker_task
        except asyncio.CancelledError:
            pass


async def _loop() -> None:
    while True:
        scan_id = await _queue.get()
        try:
            await _process(scan_id)
        except Exception:
            # Один упавший скан не должен убивать воркер целиком.
            log.exception("Скан %s упал", scan_id)
        finally:
            _queue.task_done()


async def _process(scan_id: int) -> None:
    with get_session() as session:
        scan = session.get(Scan, scan_id)
        if scan is None:
            log.warning("Скан %s исчез из БД", scan_id)
            return
        competitor = session.get(Competitor, scan.competitor_id)
        if competitor is None:
            log.warning("Конкурент %s исчез из БД", scan.competitor_id)
            return

        scan.status = "running"
        scan.started_at = utcnow()
        session.add(scan)
        session.commit()

        chat_id = scan.chat_id
        name, url = competitor.name, competitor.url
        competitor_id = competitor.id

    log.info("Скан %s: обход %s (%s)", scan_id, name, url)

    try:
        # Фаза 1 — агент водит браузер и пишет заметки о том, что увидел.
        crawl = await crawl_site(name=name, url=url, scan_id=scan_id)
        # Фаза 2 — заметки превращаются в строгую схему.
        extracted = await extract_offer(name=name, url=url, notes=crawl.notes)
        offer = extracted.offer
        usage = crawl.usage.merge(extracted.usage)
    except Exception as exc:
        log.exception("Скан %s: ошибка обхода", scan_id)
        with get_session() as session:
            scan = session.get(Scan, scan_id)
            if scan is not None:
                scan.status = "error"
                scan.error = f"{type(exc).__name__}: {exc}"[:500]
                scan.finished_at = utcnow()
                session.add(scan)
                session.commit()
        await notify.send_message(
            chat_id, f"❌ Не смог обойти <b>{name}</b>\n<code>{type(exc).__name__}</code>"
        )
        return

    with get_session() as session:
        scan = session.get(Scan, scan_id)
        if scan is not None:
            scan.status = "done"
            scan.finished_at = utcnow()
            scan.pages_visited = len(offer.pages_visited) or crawl.pages_visited
            scan.tool_calls_count = crawl.tool_calls
            scan.input_tokens = usage.input_tokens + usage.cache_read_tokens
            scan.output_tokens = usage.output_tokens
            scan.cost = usage.cost
            session.add(scan)

        snapshot = Snapshot(
            competitor_id=competitor_id,
            scan_id=scan_id,
            offer_json=offer.model_dump_json(),
            screenshot_path=crawl.screenshot_path,
        )
        session.add(snapshot)
        session.commit()

    log.info(
        "Скан %s готов: страниц %s, вызовов инструментов %s, итого %s",
        scan_id,
        crawl.pages_visited,
        crawl.tool_calls,
        usage.summary(),
    )

    caption = render_offer(
        name, offer, tool_calls=crawl.tool_calls, usage_note=usage.summary()
    )
    if crawl.screenshot_path:
        await notify.send_photo(chat_id, crawl.screenshot_path, caption)
    else:
        await notify.send_message(chat_id, caption)
