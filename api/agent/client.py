"""Общий клиент Claude для обеих фаз агента.

Работает и через ProxyAPI, и напрямую с api.anthropic.com — разница только в
ANTHROPIC_BASE_URL. Формат запросов у ProxyAPI идентичен оригинальному, поэтому
официальный SDK совместим с ним как есть, без адаптеров.
"""

from __future__ import annotations

from anthropic import AsyncAnthropic, DefaultAsyncHttpxClient

from config import ANTHROPIC_API_KEY, ANTHROPIC_BASE_URL, ANTHROPIC_PROXY, EFFORT, MODEL

# Локальный прокси для запросов к Claude — только по явному флагу.
# С ProxyAPI он не нужен: сервис сам решает вопрос доступа, и лишний хоп
# только добавит точку отказа.
_http_client = DefaultAsyncHttpxClient(proxy=ANTHROPIC_PROXY) if ANTHROPIC_PROXY else None

client = AsyncAnthropic(
    api_key=ANTHROPIC_API_KEY or None,
    base_url=ANTHROPIC_BASE_URL,
    http_client=_http_client,
)

# max_tokens ниже плановых 32k: SDK отклоняет нестриминговые запросы, которые
# по его оценке не уложатся в таймаут. 16k хватает на ответ одного хода,
# а весь обход всё равно набирается за несколько ходов цикла.
MAX_TOKENS = 16000

# effort вынесен в .env: на этой задаче medium даёт ту же работу дешевле,
# но переключиться на high можно без правки кода.
OUTPUT_CONFIG = {"effort": EFFORT}

__all__ = ["client", "MODEL", "MAX_TOKENS", "OUTPUT_CONFIG"]
