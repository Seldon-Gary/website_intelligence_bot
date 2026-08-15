"""Telegram-бот: команды и рендер ответов.

Вся логика — в API. Бот разбирает команды, ходит по HTTP и печатает результат.
`owner_tg_id` берётся из апдейта Telegram, а не из текста сообщения: подставить
чужой ID через сообщение нельзя.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import FSInputFile, Message

from api.render import render_compare, render_diff, render_offer
from api.schemas import Offer
from bot import api_client
from bot.api_client import ApiError
from config import BOT_TOKEN, PROXY_URL, describe

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)

dp = Dispatcher()

HELP = """<b>Competitor Radar</b> — слежу за офферами конкурентов.

<b>/add</b> &lt;url&gt; [название] — добавить конкурента
<b>/list</b> — мои конкуренты
<b>/remove</b> &lt;id&gt; — удалить
<b>/scan</b> &lt;id&gt; — обойти сайт и собрать оффер
<b>/report</b> &lt;id&gt; — последний собранный оффер
<b>/diff</b> &lt;id&gt; — что изменилось с прошлого раза
<b>/compare</b> — сводка по всем

Обход занимает 1–3 минуты: сайт читает агент через живой браузер, \
он сам решает, по каким ссылкам пройти."""


def _arg_id(message: Message) -> int | None:
    parts = (message.text or "").split()
    if len(parts) < 2:
        return None
    try:
        return int(parts[1])
    except ValueError:
        return None


@dp.message(CommandStart())
@dp.message(Command("help"))
async def cmd_start(message: Message) -> None:
    await message.answer(HELP)


@dp.message(Command("add"))
async def cmd_add(message: Message) -> None:
    parts = (message.text or "").split(maxsplit=2)
    if len(parts) < 2:
        await message.answer("Формат: <code>/add https://site.com Название</code>")
        return

    url = parts[1]
    name = parts[2] if len(parts) > 2 else None
    try:
        competitor = await api_client.add_competitor(url, name, message.from_user.id)
    except ApiError as exc:
        await message.answer(f"❌ {exc}")
        return

    await message.answer(
        f"✅ Добавлен <b>{competitor['name']}</b> (id={competitor['id']})\n"
        f"Запусти обход: <code>/scan {competitor['id']}</code>"
    )


@dp.message(Command("list"))
async def cmd_list(message: Message) -> None:
    try:
        competitors = await api_client.list_competitors(message.from_user.id)
    except ApiError as exc:
        await message.answer(f"❌ {exc}")
        return

    if not competitors:
        await message.answer("Пока пусто. Добавь первого: <code>/add https://site.com</code>")
        return

    lines = ["<b>Конкуренты</b>", ""]
    for item in competitors:
        scanned = item.get("last_scan_at")
        mark = f"замер {scanned[:10]}" if scanned else "ещё не сканировался"
        lines.append(f"<b>{item['id']}</b>. {item['name']} — <i>{mark}</i>")
        lines.append(f"    {item['url']}")
    await message.answer("\n".join(lines))


@dp.message(Command("remove"))
async def cmd_remove(message: Message) -> None:
    competitor_id = _arg_id(message)
    if competitor_id is None:
        await message.answer("Формат: <code>/remove 1</code>")
        return

    try:
        result = await api_client.remove_competitor(competitor_id, message.from_user.id)
    except ApiError as exc:
        await message.answer(f"❌ {exc}")
        return
    await message.answer(f"🗑 Удалён <b>{result['deleted']}</b>")


@dp.message(Command("scan"))
async def cmd_scan(message: Message) -> None:
    competitor_id = _arg_id(message)
    if competitor_id is None:
        await message.answer("Формат: <code>/scan 1</code>")
        return

    try:
        scan = await api_client.start_scan(competitor_id, message.from_user.id, message.chat.id)
    except ApiError as exc:
        await message.answer(f"❌ {exc}")
        return

    await message.answer(
        f"🔎 Принял в работу (скан {scan['id']}).\n"
        "Агент открывает сайт в браузере и обходит его — это 1–3 минуты. "
        "Пришлю результат сюда."
    )


@dp.message(Command("report"))
async def cmd_report(message: Message) -> None:
    competitor_id = _arg_id(message)
    if competitor_id is None:
        await message.answer("Формат: <code>/report 1</code>")
        return

    try:
        data = await api_client.get_snapshot(competitor_id, message.from_user.id)
    except ApiError as exc:
        await message.answer(f"❌ {exc}")
        return

    offer = Offer.model_validate(data["offer"])
    competitors = await api_client.list_competitors(message.from_user.id)
    name = next((c["name"] for c in competitors if c["id"] == competitor_id), "конкурент")
    text = render_offer(name, offer)

    shot = data.get("screenshot_path")
    if shot and Path(shot).exists():
        await message.answer_photo(FSInputFile(shot), caption=text)
    else:
        await message.answer(text)


@dp.message(Command("diff"))
async def cmd_diff(message: Message) -> None:
    competitor_id = _arg_id(message)
    if competitor_id is None:
        await message.answer("Формат: <code>/diff 1</code>")
        return

    try:
        data = await api_client.get_diff(competitor_id, message.from_user.id)
    except ApiError as exc:
        await message.answer(f"❌ {exc}")
        return

    competitors = await api_client.list_competitors(message.from_user.id)
    name = next((c["name"] for c in competitors if c["id"] == competitor_id), "конкурент")
    await message.answer(render_diff(name, data["changes"], captured_at=data["from"][:16]))


@dp.message(Command("compare"))
async def cmd_compare(message: Message) -> None:
    try:
        rows = await api_client.compare_all(message.from_user.id)
    except ApiError as exc:
        await message.answer(f"❌ {exc}")
        return
    await message.answer(render_compare(rows))


@dp.message(F.text)
async def fallback(message: Message) -> None:
    await message.answer("Не знаю такой команды. /help — что я умею.")


async def main() -> None:
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN пуст. Заполни .env.")

    log.info("Бот стартует: %s", describe())
    session = AiohttpSession(proxy=PROXY_URL) if PROXY_URL else AiohttpSession()
    bot = Bot(
        token=BOT_TOKEN,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
