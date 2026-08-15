"""Форматирование результатов для Telegram (HTML parse_mode)."""

from __future__ import annotations

from html import escape

from api.schemas import Offer

# Подпись к фото Telegram режет на 1024 символах — держимся с запасом.
CAPTION_BUDGET = 950


def _bullets(items: list[str], limit: int = 4) -> list[str]:
    return [f"• {escape(item)}" for item in items[:limit]]


def render_offer(
    name: str, offer: Offer, *, tool_calls: int = 0, usage_note: str | None = None
) -> str:
    lines = [f"<b>{escape(name)}</b>"]

    if offer.headline:
        lines.append(f"<i>{escape(offer.headline)}</i>")
    if offer.subheadline:
        lines.append(escape(offer.subheadline))

    if offer.value_props:
        lines.append("\n<b>Выгоды</b>")
        lines += _bullets(offer.value_props)

    if offer.plans:
        lines.append("\n<b>Тарифы</b>")
        for plan in offer.plans[:5]:
            price = plan.price or "цена не указана"
            if plan.period:
                price = f"{price} / {plan.period}"
            lines.append(f"• {escape(plan.name)} — {escape(price)}")
    elif offer.pricing_note:
        # Планов нет, но цены есть — показываем их, иначе теряется главное.
        lines.append(f"\n<b>Цены:</b> {escape(offer.pricing_note)}")

    if offer.ctas:
        texts = ", ".join(escape(cta.text) for cta in offer.ctas[:3])
        lines.append(f"\n<b>Кнопки:</b> {texts}")

    if offer.target_audience:
        lines.append(f"<b>Аудитория:</b> {escape(offer.target_audience)}")

    if offer.social_proof:
        lines.append("\n<b>Соцдоказательства</b>")
        lines += _bullets(offer.social_proof, limit=3)

    footer = f"\n<i>Страниц: {len(offer.pages_visited)}"
    if tool_calls:
        footer += f", вызовов браузера: {tool_calls}"
    if usage_note:
        footer += f"\n{escape(usage_note)}"
    footer += "</i>"
    lines.append(footer)

    text = "\n".join(lines)
    if len(text) > CAPTION_BUDGET:
        text = text[:CAPTION_BUDGET].rsplit("\n", 1)[0] + "\n<i>…</i>"
    return text


def render_diff(name: str, changes: list[str], *, captured_at: str | None = None) -> str:
    if not changes:
        return f"<b>{escape(name)}</b>\nС прошлого замера ничего не изменилось."

    lines = [f"<b>{escape(name)}</b> — изменения"]
    if captured_at:
        lines.append(f"<i>с {escape(captured_at)}</i>")
    lines.append("")
    lines += [f"• {escape(change)}" for change in changes[:20]]
    if len(changes) > 20:
        lines.append(f"<i>…и ещё {len(changes) - 20}</i>")
    return "\n".join(lines)


def render_compare(rows: list[dict]) -> str:
    if not rows:
        return "Пока нет ни одного собранного оффера. Запусти /scan."

    lines = ["<b>Сводка по конкурентам</b>", ""]
    for row in rows:
        lines.append(f"<b>{escape(row['name'])}</b>")
        if row.get("headline"):
            lines.append(f"  <i>{escape(row['headline'])}</i>")
        if row.get("plans"):
            lines.append(f"  Тарифы: {escape(row['plans'])}")
        if row.get("captured_at"):
            lines.append(f"  <i>замер: {escape(row['captured_at'])}</i>")
        lines.append("")
    return "\n".join(lines).strip()
