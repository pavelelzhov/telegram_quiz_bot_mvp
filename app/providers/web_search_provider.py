from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx
from openai import AsyncOpenAI

from app.config import settings
from app.utils.ops_log import log_operation

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SearchSource:
    title: str
    url: str
    used: bool = False


class WebSearchProvider:
    def __init__(self) -> None:
        self.enabled = bool(settings.yandex_search_api_key and settings.yandex_search_folder_id)
        self.search_url = 'https://searchapi.api.cloud.yandex.net/v2/gen/search'
        self.llm_client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
        )
        self.llm_model = settings.openai_model

    def looks_like_web_request(self, text: str, addressed: bool = False) -> bool:
        value = text.strip().lower()

        explicit = [
            '/web', 'найди', 'поищи', 'поиск', 'погугли', 'посмотри в сети',
            'посмотри в интернете', 'найди в сети', 'проверь в сети',
            'что в сети', 'что в интернете', 'новости по', 'сводка по',
        ]
        if any(token in value for token in explicit):
            return True

        dynamic = [
            'курс доллара', 'курс валют', 'курс евро', 'курс юаня',
            'кто такой', 'что такое', 'что сейчас по', 'сколько стоит',
            'цена', 'новости', 'сегодня', 'сейчас', 'когда будет',
            'дата выхода', 'кто победил', 'погода',
        ]

        if addressed and any(token in value for token in dynamic):
            return True

        if addressed and re.search(r'\b(кто|что|когда|какой|какая|сколько)\b', value):
            if any(token in value for token in ['доллар', 'евро', 'битк', 'ton', 'новост', 'курс', 'цена']):
                return True

        return False

    def extract_query(self, text: str) -> str:
        value = text.strip()

        if value.startswith('/web'):
            return value[4:].strip()

        value = re.sub(r'^\s*(бот|квиз бот|квиз-бот|ведущий)\s*[:,\-—]?\s*', '', value, flags=re.I)

        patterns = [
            r'^\s*найди\s+',
            r'^\s*поищи\s+',
            r'^\s*поиск\s+',
            r'^\s*погугли\s+',
            r'^\s*посмотри в сети\s+',
            r'^\s*посмотри в интернете\s+',
            r'^\s*найди в сети\s+',
            r'^\s*проверь в сети\s+',
            r'^\s*что в сети по\s+',
            r'^\s*что в интернете по\s+',
            r'^\s*что сейчас по\s+',
            r'^\s*новости по\s+',
            r'^\s*сводка по\s+',
            r'^\s*что известно о\s+',
            r'^\s*что известно про\s+',
            r'^\s*найди информацию о\s+',
            r'^\s*найди информацию про\s+',
        ]

        for pattern in patterns:
            value = re.sub(pattern, '', value, flags=re.I)

        return value.strip(' ?!.,')

    async def search_and_summarize(self, chat_title: str, username: str, raw_text: str) -> str:
        if not self.enabled:
            return '🌐 Веб-поиск пока не подключён. Нужны YANDEX_SEARCH_API_KEY и YANDEX_SEARCH_FOLDER_ID в .env.'

        query = self.extract_query(raw_text)
        if not query:
            return '🌐 Дай сам запрос. Например: /web кто такой Чингисхан'

        started = time.perf_counter()
        try:
            answer, sources = await self._run_search(query)
        except Exception as exc:
            logger.exception('Web search failed: %s', exc)
            log_operation(
                logger,
                operation='web_search',
                result='error',
                duration_ms=(time.perf_counter() - started) * 1000,
                error_type=type(exc).__name__,
                extra={'query_len': len(query)},
                level=logging.WARNING,
            )
            return '🌐 С поиском сейчас вышел неловкий технический номер. Попробуй ещё раз через минуту.'

        if not answer:
            log_operation(
                logger,
                operation='web_search',
                result='empty',
                duration_ms=(time.perf_counter() - started) * 1000,
                extra={'query_len': len(query)},
            )
            return '🌐 Я сходил в сеть, но внятной сводки не собрал. Запрос слишком мутный или выдача пустая.'

        styled = await self._polish_answer(chat_title=chat_title, username=username, query=query, search_answer=answer)
        source_block = self._format_sources(sources)

        if source_block:
            log_operation(
                logger,
                operation='web_search',
                result='ok',
                duration_ms=(time.perf_counter() - started) * 1000,
                extra={'query_len': len(query), 'sources': len(sources)},
            )
            return f'🌐 По сети по запросу: {query}\n\n{styled}\n\nИсточники:\n{source_block}'
        log_operation(
            logger,
            operation='web_search',
            result='ok',
            duration_ms=(time.perf_counter() - started) * 1000,
            extra={'query_len': len(query), 'sources': len(sources)},
        )
        return f'🌐 По сети по запросу: {query}\n\n{styled}'

    async def _run_search(self, query: str) -> tuple[str, list[SearchSource]]:
        headers = {
            'Authorization': f'Api-Key {settings.yandex_search_api_key}',
            'Content-Type': 'application/json',
        }
        payload = {
            'messages': [
                {
                    'content': query,
                    'role': 'ROLE_USER'
                }
            ],
            'folderId': settings.yandex_search_folder_id,
            'searchType': 'SEARCH_TYPE_RU',
            'fixMisspell': True,
            'getPartialResults': False,
        }

        async with httpx.AsyncClient(timeout=35.0) as client:
            async def _call_search() -> httpx.Response:
                response = await client.post(self.search_url, headers=headers, json=payload)
                response.raise_for_status()
                return response

            response = await retry_async(
                _call_search,
                retries=2,
                base_delay_sec=0.7,
                should_retry=self._should_retry_http_error,
            )
            data: Any = response.json()

        if isinstance(data, list):
            data = data[0] if data else {}

        if not isinstance(data, dict):
            raise ValueError(f'Unexpected Search API response type: {type(data).__name__}')

        message = data.get('message') or {}
        if not isinstance(message, dict):
            message = {}

        answer = str(message.get('content') or '').strip()

        raw_sources = data.get('sources') or []
        if not isinstance(raw_sources, list):
            raw_sources = []

        sources: list[SearchSource] = []
        for item in raw_sources[:8]:
            if not isinstance(item, dict):
                continue
            url = str(item.get('url') or '').strip()
            title = str(item.get('title') or '').strip() or url
            used = bool(item.get('used'))
            if not url:
                continue
            sources.append(SearchSource(title=title, url=url, used=used))

        sources.sort(key=lambda x: (not x.used, x.title.lower()))
        return answer, sources[:4]

    def _should_retry_http_error(self, exc: Exception) -> bool:
        if isinstance(exc, (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError)):
            return True
        if isinstance(exc, httpx.HTTPStatusError):
            status = exc.response.status_code if exc.response is not None else None
            return bool(status in {429} or (isinstance(status, int) and status >= 500))
        return False

    async def _polish_answer(self, chat_title: str, username: str, query: str, search_answer: str) -> str:
        prompt = f"""
Ты участник Telegram-чата "{chat_title}".
Пользователь @{username} попросил найти информацию в сети.

Запрос:
{query}

Черновая сводка из поиска:
{search_answer}

Задача:
- перепиши в 2-5 коротких предложений
- факты бери только из черновой сводки
- не выдумывай ничего сверх неё
- можно добавить лёгкий юмор, но без клоунады
- если в сводке есть неопределённость, честно скажи об этом
- не используй markdown
""".strip()

        try:
            response = await self.llm_client.chat.completions.create(
                model=self.llm_model,
                temperature=0.45,
                messages=[
                    {
                        'role': 'system',
                        'content': 'Ты пишешь короткие, точные и немного ироничные сводки по результатам веб-поиска. Не выдумывай факты.'
                    },
                    {
                        'role': 'user',
                        'content': prompt
                    }
                ],
            )
            content = (response.choices[0].message.content or '').strip()
            return content or search_answer
        except Exception as exc:
            logger.exception('Search answer polish failed: %s', exc)
            return search_answer

    def _format_sources(self, sources: list[SearchSource]) -> str:
        lines: list[str] = []
        for idx, source in enumerate(sources[:3], start=1):
            host = urlparse(source.url).netloc or source.url
            title = source.title.strip()[:90]
            lines.append(f'{idx}) {title} — {host}')
        return '\n'.join(lines)
