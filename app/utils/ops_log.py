from __future__ import annotations

import logging
from typing import Any


def log_operation(
    logger: logging.Logger,
    *,
    operation: str,
    chat_id: int | None = None,
    result: str = 'ok',
    duration_ms: float | None = None,
    error_type: str | None = None,
    extra: dict[str, Any] | None = None,
    level: int = logging.INFO,
) -> None:
    parts: list[str] = [f'operation={operation}', f'result={result}']

    if chat_id is not None:
        parts.append(f'chat_id={chat_id}')

    if duration_ms is not None:
        parts.append(f'duration_ms={duration_ms:.1f}')

    if error_type:
        parts.append(f'error_type={error_type}')

    if extra:
        for key, value in extra.items():
            parts.append(f'{key}={value}')

    logger.log(level, ' | '.join(parts))
