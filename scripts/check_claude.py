"""Проверка доступа к Claude (ProxyAPI или напрямую).

Проверяет не «связь есть», а именно те три возможности, на которых держится
проект: обычный вызов, tool use и структурированный вывод. Если что-то из
этого не проксируется — узнать лучше сейчас, а не на первом скане.

Запуск:
    .\\venv\\Scripts\\python.exe -m scripts.check_claude
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from anthropic import beta_async_tool  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from api.agent.client import MAX_TOKENS, MODEL, OUTPUT_CONFIG, client  # noqa: E402
from config import ANTHROPIC_API_KEY, ANTHROPIC_BASE_URL, describe  # noqa: E402


class City(BaseModel):
    name: str
    country: str
    population_millions: float


# Клиент асинхронный, поэтому и инструмент должен быть асинхронным:
# синхронный @beta_tool в async-раннер не пролезет.
@beta_async_tool
async def get_city_population(city: str) -> str:
    """Узнать население города.

    Args:
        city: Название города.
    """
    return f"{city}: 2.1 млн человек"


def _usage(response) -> str:
    usage = response.usage
    return f"вход {usage.input_tokens}, выход {usage.output_tokens} токенов"


async def main() -> None:
    print("=" * 70)
    print("Конфигурация:", describe())
    print("Хост:", ANTHROPIC_BASE_URL or "https://api.anthropic.com (официальный)")
    print("Ключ:", "задан" if ANTHROPIC_API_KEY else "ПУСТОЙ — заполни .env")
    print("=" * 70)

    if not ANTHROPIC_API_KEY:
        raise SystemExit("Без ключа проверять нечего.")

    ok = True

    # 1. Базовый вызов: жив ли канал и та ли модель отвечает.
    print("\n[1/4] Обычный запрос...")
    try:
        response = await client.messages.create(
            model=MODEL,
            max_tokens=100,
            messages=[{"role": "user", "content": "Ответь одним словом: работает?"}],
        )
        text = next((b.text for b in response.content if b.type == "text"), "")
        print(f"  ✅ {response.model}: {text.strip()[:80]}")
        print(f"     {_usage(response)}")
    except Exception as exc:
        ok = False
        print(f"  ❌ {type(exc).__name__}: {exc}")

    # 2. Tool use: на нём держится вся фаза обхода.
    print("\n[2/4] Tool use...")
    try:
        response = await client.messages.create(
            model=MODEL,
            max_tokens=500,
            tools=[
                {
                    "name": "get_weather",
                    "description": "Узнать погоду в городе",
                    "input_schema": {
                        "type": "object",
                        "properties": {"city": {"type": "string"}},
                        "required": ["city"],
                    },
                }
            ],
            messages=[{"role": "user", "content": "Какая погода в Москве?"}],
        )
        calls = [b for b in response.content if b.type == "tool_use"]
        if calls:
            print(f"  ✅ модель вызвала инструмент: {calls[0].name}({calls[0].input})")
        else:
            ok = False
            print("  ❌ инструмент не вызван — проверь, проксируется ли tool use")
    except Exception as exc:
        ok = False
        print(f"  ❌ {type(exc).__name__}: {exc}")

    # 3. tool_runner на beta-эндпоинте — именно так работает фаза 1 обхода.
    # Обычный tool use выше может проксироваться, а beta-путь — нет,
    # поэтому проверяем его отдельно.
    print("\n[3/4] Beta tool_runner (фаза 1 обхода)...")
    try:
        runner = client.beta.messages.tool_runner(
            model=MODEL,
            max_tokens=1000,
            tools=[get_city_population],
            messages=[{"role": "user", "content": "Сколько людей живёт в Казани?"}],
            max_iterations=3,
            output_config=OUTPUT_CONFIG,
        )
        turns = 0
        last = None
        async for message in runner:
            turns += 1
            last = message
        text = next((b.text for b in last.content if b.type == "text"), "") if last else ""
        print(f"  ✅ цикл отработал за {turns} хода(ов): {text.strip()[:80]}")
    except Exception as exc:
        ok = False
        print(f"  ❌ {type(exc).__name__}: {exc}")
        print("     Без этого фаза обхода не заработает.")
        print("     TypeError на сериализации = ошибка в коде, запрос не ушёл.")
        print("     Ошибка со статусом (4xx/5xx) = beta-путь не проксируется.")

    # 4. Structured outputs: на нём держится фаза 2 (сборка карточки оффера).
    print("\n[4/4] Структурированный вывод (фаза 2)...")
    try:
        response = await client.messages.parse(
            model=MODEL,
            max_tokens=500,
            messages=[{"role": "user", "content": "Расскажи про Париж."}],
            output_format=City,
        )
        city = response.parsed_output
        print(f"  ✅ схема собрана: {city.name}, {city.country}, {city.population_millions} млн")
    except Exception as exc:
        ok = False
        print(f"  ❌ {type(exc).__name__}: {exc}")

    print("\n" + "=" * 70)
    if ok:
        print(f"Всё готово. Модель {MODEL}, effort={OUTPUT_CONFIG['effort']}, "
              f"max_tokens в обходе {MAX_TOKENS}.")
    else:
        print("Часть возможностей недоступна — смотри ошибки выше.")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
