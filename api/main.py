"""REST API Competitor Radar.

Границы доверия: `owner_tg_id` приходит из апдейта Telegram, а не из текста
сообщения, и фильтрация по нему живёт в `db.owned_competitor`. Модель к этим
данным доступа не имеет вовсе — она умеет только водить браузер.
"""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException
from sqlmodel import select

from api import worker
from api.db import Competitor, Scan, Snapshot, get_session, init_db, latest_snapshots, owned_competitor
from api.diff import compare
from api.schemas import CompetitorCreate, CompetitorOut, Offer, ScanCreate, ScanOut

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from config import describe

    init_db()
    worker.start()
    log.info("API запущен: %s", describe())
    yield
    await worker.stop()


app = FastAPI(
    title="Competitor Radar",
    description="Мониторинг офферов конкурентов. Обход сайтов — через Playwright MCP.",
    version="1.0.0",
    lifespan=lifespan,
)


def _normalize(url: str) -> str:
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    return url


def _name_from(url: str) -> str:
    host = urlparse(url).netloc
    return host[4:] if host.startswith("www.") else host


def _iso(value) -> str | None:
    return value.isoformat(timespec="seconds") if value else None


# --- Конкуренты ---


@app.post("/competitors", response_model=CompetitorOut, summary="Добавить конкурента")
def add_competitor(payload: CompetitorCreate) -> CompetitorOut:
    url = _normalize(payload.url)
    if not urlparse(url).netloc:
        raise HTTPException(400, "Не похоже на URL")

    with get_session() as session:
        existing = session.exec(
            select(Competitor).where(
                Competitor.owner_tg_id == payload.owner_tg_id, Competitor.url == url
            )
        ).first()
        if existing:
            raise HTTPException(409, f"Уже добавлен под id={existing.id}")

        competitor = Competitor(
            name=payload.name or _name_from(url),
            url=url,
            owner_tg_id=payload.owner_tg_id,
        )
        session.add(competitor)
        session.commit()
        session.refresh(competitor)

        return CompetitorOut(
            id=competitor.id,
            name=competitor.name,
            url=competitor.url,
            created_at=_iso(competitor.created_at),
        )


@app.get("/competitors", response_model=list[CompetitorOut], summary="Мои конкуренты")
def list_competitors(owner_tg_id: int) -> list[CompetitorOut]:
    with get_session() as session:
        competitors = session.exec(
            select(Competitor).where(Competitor.owner_tg_id == owner_tg_id).order_by(Competitor.id)
        ).all()

        result = []
        for competitor in competitors:
            last = latest_snapshots(session, competitor.id, limit=1)
            result.append(
                CompetitorOut(
                    id=competitor.id,
                    name=competitor.name,
                    url=competitor.url,
                    created_at=_iso(competitor.created_at),
                    last_scan_at=_iso(last[0].captured_at) if last else None,
                )
            )
        return result


@app.delete("/competitors/{competitor_id}", summary="Удалить конкурента")
def remove_competitor(competitor_id: int, owner_tg_id: int) -> dict:
    with get_session() as session:
        competitor = owned_competitor(session, competitor_id, owner_tg_id)
        if competitor is None:
            raise HTTPException(404, "Не найден")

        for snapshot in session.exec(
            select(Snapshot).where(Snapshot.competitor_id == competitor_id)
        ).all():
            session.delete(snapshot)
        for scan in session.exec(select(Scan).where(Scan.competitor_id == competitor_id)).all():
            session.delete(scan)

        name = competitor.name
        session.delete(competitor)
        session.commit()
        return {"deleted": name}


# --- Сканы ---


@app.post("/scans", response_model=ScanOut, summary="Запустить обход")
def create_scan(payload: ScanCreate) -> ScanOut:
    with get_session() as session:
        competitor = owned_competitor(session, payload.competitor_id, payload.owner_tg_id)
        if competitor is None:
            raise HTTPException(404, "Конкурент не найден")

        running = session.exec(
            select(Scan).where(
                Scan.competitor_id == competitor.id, Scan.status.in_(["queued", "running"])
            )
        ).first()
        if running:
            raise HTTPException(409, f"Обход уже идёт (скан {running.id})")

        scan = Scan(competitor_id=competitor.id, chat_id=payload.chat_id)
        session.add(scan)
        session.commit()
        session.refresh(scan)
        scan_id = scan.id

    worker.enqueue(scan_id)
    return ScanOut(id=scan_id, competitor_id=payload.competitor_id, status="queued")


@app.get("/scans/{scan_id}", response_model=ScanOut, summary="Статус скана")
def get_scan(scan_id: int) -> ScanOut:
    with get_session() as session:
        scan = session.get(Scan, scan_id)
        if scan is None:
            raise HTTPException(404, "Скан не найден")
        return ScanOut(
            id=scan.id,
            competitor_id=scan.competitor_id,
            status=scan.status,
            error=scan.error,
            pages_visited=scan.pages_visited,
            tool_calls_count=scan.tool_calls_count,
            input_tokens=scan.input_tokens,
            output_tokens=scan.output_tokens,
            cost=scan.cost,
        )


# --- Результаты ---


@app.get("/competitors/{competitor_id}/snapshot", summary="Последний оффер")
def get_snapshot(competitor_id: int, owner_tg_id: int) -> dict:
    with get_session() as session:
        if owned_competitor(session, competitor_id, owner_tg_id) is None:
            raise HTTPException(404, "Конкурент не найден")

        snapshots = latest_snapshots(session, competitor_id, limit=1)
        if not snapshots:
            raise HTTPException(404, "Обход ещё не проводился")

        return {
            "captured_at": _iso(snapshots[0].captured_at),
            "screenshot_path": snapshots[0].screenshot_path,
            "offer": json.loads(snapshots[0].offer_json),
        }


@app.get("/competitors/{competitor_id}/diff", summary="Что изменилось")
def get_diff(competitor_id: int, owner_tg_id: int) -> dict:
    with get_session() as session:
        if owned_competitor(session, competitor_id, owner_tg_id) is None:
            raise HTTPException(404, "Конкурент не найден")

        snapshots = latest_snapshots(session, competitor_id, limit=2)
        if len(snapshots) < 2:
            raise HTTPException(409, "Нужно минимум два обхода — запусти /scan ещё раз")

        new, old = snapshots[0], snapshots[1]
        changes = compare(Offer.model_validate_json(old.offer_json), Offer.model_validate_json(new.offer_json))
        return {
            "changes": changes,
            "from": _iso(old.captured_at),
            "to": _iso(new.captured_at),
        }


@app.get("/compare", summary="Сводка по всем конкурентам")
def compare_all(owner_tg_id: int) -> list[dict]:
    with get_session() as session:
        competitors = session.exec(
            select(Competitor).where(Competitor.owner_tg_id == owner_tg_id).order_by(Competitor.id)
        ).all()

        rows = []
        for competitor in competitors:
            snapshots = latest_snapshots(session, competitor.id, limit=1)
            if not snapshots:
                rows.append({"id": competitor.id, "name": competitor.name, "headline": None})
                continue

            offer = Offer.model_validate_json(snapshots[0].offer_json)
            plans = ", ".join(
                f"{plan.name}: {plan.price}" for plan in offer.plans[:3] if plan.price
            )
            rows.append(
                {
                    "id": competitor.id,
                    "name": competitor.name,
                    "headline": offer.headline,
                    "plans": plans,
                    "captured_at": _iso(snapshots[0].captured_at),
                }
            )
        return rows


@app.get("/health", summary="Проверка живости")
def health() -> dict:
    return {"status": "ok"}
