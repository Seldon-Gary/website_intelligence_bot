"""Сравнение двух снапшотов оффера.

Детерминированное сравнение на Python, без модели: диф должен быть
воспроизводимым и объяснимым, а не пересказанным.
"""

from __future__ import annotations

from api.schemas import Offer

# Поля, где важен факт изменения текста.
_SCALAR_FIELDS = {
    "headline": "Заголовок",
    "subheadline": "Подзаголовок",
    "target_audience": "Аудитория",
    # Ловит подорожание там, где тарифных планов нет и цена живёт текстом.
    "pricing_note": "Цены",
}

# Поля-списки строк: сравниваем как множества.
_LIST_FIELDS = {
    "value_props": "Выгоды",
    "social_proof": "Соцдоказательства",
}


def _plans_map(offer: Offer) -> dict[str, tuple[str, str]]:
    """Ключ сравнения -> (как назван на сайте, цена с периодом).

    Ключ нормализован, чтобы «Про» и «про» считались одним тарифом,
    но в сообщениях показываем исходное написание.
    """
    result: dict[str, tuple[str, str]] = {}
    for plan in offer.plans:
        price = plan.price or "—"
        if plan.period:
            price = f"{price} / {plan.period}"
        result[plan.name.strip().lower()] = (plan.name.strip(), price)
    return result


def _cta_texts(offer: Offer) -> set[str]:
    return {cta.text.strip() for cta in offer.ctas if cta.text.strip()}


def compare(old: Offer, new: Offer) -> list[str]:
    """Список человекочитаемых изменений. Пустой список = ничего не поменялось."""
    changes: list[str] = []

    for field, label in _SCALAR_FIELDS.items():
        before = (getattr(old, field) or "").strip()
        after = (getattr(new, field) or "").strip()
        if before != after:
            if not before:
                changes.append(f"{label}: появился — «{after}»")
            elif not after:
                changes.append(f"{label}: убран (было «{before}»)")
            else:
                changes.append(f"{label}: «{before}» → «{after}»")

    for field, label in _LIST_FIELDS.items():
        before = {s.strip() for s in getattr(old, field) if s.strip()}
        after = {s.strip() for s in getattr(new, field) if s.strip()}
        for added in sorted(after - before):
            changes.append(f"{label} +: {added}")
        for removed in sorted(before - after):
            changes.append(f"{label} −: {removed}")

    old_plans, new_plans = _plans_map(old), _plans_map(new)
    for key in sorted(set(new_plans) - set(old_plans)):
        title, price = new_plans[key]
        changes.append(f"Новый тариф: {title} — {price}")
    for key in sorted(set(old_plans) - set(new_plans)):
        changes.append(f"Тариф убран: {old_plans[key][0]}")
    for key in sorted(set(old_plans) & set(new_plans)):
        title, new_price = new_plans[key]
        old_price = old_plans[key][1]
        if old_price != new_price:
            changes.append(f"Цена «{title}»: {old_price} → {new_price}")

    old_ctas, new_ctas = _cta_texts(old), _cta_texts(new)
    for added in sorted(new_ctas - old_ctas):
        changes.append(f"Новая кнопка: «{added}»")
    for removed in sorted(old_ctas - new_ctas):
        changes.append(f"Кнопка убрана: «{removed}»")

    return changes
