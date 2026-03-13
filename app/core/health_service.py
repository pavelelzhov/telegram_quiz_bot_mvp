from __future__ import annotations

import time
from dataclasses import dataclass
from logging import Logger

from app.storage.db import Database
from app.utils.ops_log import log_operation


@dataclass(slots=True)
class HealthSnapshot:
    overall: str
    db_status: str
    db_ms: float
    llm_status: str
    llm_ms: float
    web_status: str
    web_ms: float


class HealthService:
    async def check(
        self,
        *,
        chat_id: int,
        db: Database,
        llm_configured: bool,
        web_search_enabled: bool,
        logger: Logger,
    ) -> HealthSnapshot:
        started = time.perf_counter()

        db_started = time.perf_counter()
        db_ok = await db.healthcheck()
        db_ms = (time.perf_counter() - db_started) * 1000

        llm_started = time.perf_counter()
        llm_status = 'OK' if llm_configured else 'DEGRADED'
        llm_ms = (time.perf_counter() - llm_started) * 1000

        web_started = time.perf_counter()
        web_status = 'OK' if web_search_enabled else 'DEGRADED'
        web_ms = (time.perf_counter() - web_started) * 1000

        db_status = 'OK' if db_ok else 'FAIL'
        overall = 'OK'
        if not db_ok:
            overall = 'FAIL'
        elif llm_status == 'DEGRADED' or web_status == 'DEGRADED':
            overall = 'DEGRADED'

        log_operation(
            logger,
            operation='health_check',
            chat_id=chat_id,
            result=overall.lower(),
            duration_ms=(time.perf_counter() - started) * 1000,
            extra={
                'db_status': db_status,
                'db_latency_ms': f'{db_ms:.1f}',
                'llm_status': llm_status,
                'llm_latency_ms': f'{llm_ms:.1f}',
                'web_status': web_status,
                'web_latency_ms': f'{web_ms:.1f}',
            },
        )

        return HealthSnapshot(
            overall=overall,
            db_status=db_status,
            db_ms=db_ms,
            llm_status=llm_status,
            llm_ms=llm_ms,
            web_status=web_status,
            web_ms=web_ms,
        )

    def format_text(self, snapshot: HealthSnapshot) -> str:
        return (
            '🩺 Health-check\n'
            f'Overall: {snapshot.overall}\n'
            f'Database: {snapshot.db_status} ({snapshot.db_ms:.1f} ms)\n'
            f'LLM config: {snapshot.llm_status} ({snapshot.llm_ms:.1f} ms)\n'
            f'Web search config: {snapshot.web_status} ({snapshot.web_ms:.1f} ms)'
        )
