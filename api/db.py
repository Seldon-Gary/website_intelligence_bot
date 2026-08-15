"""SQLite через SQLModel.

Синхронный движок намеренно: транзакции здесь короткие (несколько строк),
а единственный писатель — процесс api. Городить async-слой не за чем.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Field, Session, SQLModel, create_engine, select

from config import DB_PATH


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Competitor(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    url: str
    owner_tg_id: int = Field(index=True)
    created_at: datetime = Field(default_factory=utcnow)


class Scan(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    competitor_id: int = Field(index=True, foreign_key="competitor.id")
    # queued | running | done | error
    status: str = Field(default="queued", index=True)
    chat_id: int
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None
    pages_visited: int = 0
    # Сколько раз модель самостоятельно вызвала инструмент браузера.
    # Показываем в демо: решения принимала она, а не наш if.
    tool_calls_count: int = 0
    # Суммарно по обеим фазам: обход — это цикл, где история летит заново,
    # так что цена скана видна только в сумме по всем ходам.
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float | None = None
    created_at: datetime = Field(default_factory=utcnow)


class Snapshot(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    competitor_id: int = Field(index=True, foreign_key="competitor.id")
    scan_id: int = Field(foreign_key="scan.id")
    captured_at: datetime = Field(default_factory=utcnow)
    offer_json: str
    screenshot_path: str | None = None


engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
)


def init_db() -> None:
    SQLModel.metadata.create_all(engine)
    _add_missing_columns()


def _add_missing_columns() -> None:
    """Дописать колонки, появившиеся в моделях после создания БД.

    `create_all` создаёт только отсутствующие таблицы и не трогает существующие,
    поэтому без этого шага после изменения схемы старая база падала бы на
    `no such column`. Полноценные миграции для проекта такого размера избыточны,
    а терять историю замеров при каждой правке схемы не хочется.
    """
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    with engine.begin() as connection:
        for table in SQLModel.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue
            present = {column["name"] for column in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in present:
                    continue
                column_type = column.type.compile(engine.dialect)
                connection.execute(
                    text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {column_type}')
                )


def get_session() -> Session:
    return Session(engine)


# --- Запросы, которые нужны в нескольких местах ---


def latest_snapshots(session: Session, competitor_id: int, limit: int = 2) -> list[Snapshot]:
    """Последние снапшоты конкурента, новые первыми."""
    stmt = (
        select(Snapshot)
        .where(Snapshot.competitor_id == competitor_id)
        .order_by(Snapshot.captured_at.desc())
        .limit(limit)
    )
    return list(session.exec(stmt))


def owned_competitor(session: Session, competitor_id: int, owner_tg_id: int) -> Competitor | None:
    """Конкурент, но только если он принадлежит этому пользователю.

    Фильтр по владельцу живёт здесь, а не в хендлерах, чтобы его нельзя было
    случайно забыть в одном из роутов.
    """
    competitor = session.get(Competitor, competitor_id)
    if competitor is None or competitor.owner_tg_id != owner_tg_id:
        return None
    return competitor
