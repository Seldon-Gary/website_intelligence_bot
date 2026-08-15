"""Схема оффера конкурента.

Заполняется фазой 2 (`agent/extract.py`) через `client.messages.parse()` —
модель обязана вернуть ровно эту структуру.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Plan(BaseModel):
    """Тарифный план."""

    name: str
    price: str | None = Field(default=None, description="Как написано на сайте, с валютой")
    period: str | None = Field(default=None, description="мес / год / разово")
    features: list[str] = Field(default_factory=list)


class CTA(BaseModel):
    """Призыв к действию."""

    text: str
    placement: str = Field(description="hero / pricing / footer / other")


class Offer(BaseModel):
    """Оффер конкурента, собранный с его лендинга."""

    headline: str = Field(description="Главный заголовок первого экрана")
    subheadline: str | None = None
    value_props: list[str] = Field(default_factory=list, description="Ключевые выгоды и УТП")
    target_audience: str | None = Field(default=None, description="На кого ориентирован продукт")
    plans: list[Plan] = Field(default_factory=list)
    # Не у всех есть тарифные планы: бывает поштучная оплата, «по запросу»,
    # прайс за единицу потребления. Без этого поля такие цены терялись целиком
    # и подорожание у конкурента было не видно.
    pricing_note: str | None = Field(
        default=None,
        description=(
            "Как устроена оплата, если тарифных планов нет: модель оплаты "
            "и порядок цен с конкретными числами и единицами, одной-двумя фразами"
        ),
    )
    ctas: list[CTA] = Field(default_factory=list)
    social_proof: list[str] = Field(
        default_factory=list, description="Отзывы, логотипы клиентов, цифры, награды"
    )
    pages_visited: list[str] = Field(default_factory=list, description="URL просмотренных страниц")


# --- Схемы запросов/ответов API ---


class CompetitorCreate(BaseModel):
    url: str
    name: str | None = None
    owner_tg_id: int


class CompetitorOut(BaseModel):
    id: int
    name: str
    url: str
    created_at: str
    last_scan_at: str | None = None


class ScanCreate(BaseModel):
    competitor_id: int
    owner_tg_id: int
    chat_id: int


class ScanOut(BaseModel):
    id: int
    competitor_id: int
    status: str
    error: str | None = None
    pages_visited: int = 0
    tool_calls_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float | None = None
