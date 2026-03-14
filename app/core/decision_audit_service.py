from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class DecisionAuditEvent:
    chat_id: int
    user_id: int
    stage: str
    reason_codes: list[str] = field(default_factory=list)
    mode: str | None = None
    rewritten: bool | None = None
    message_id: int | None = None
    extra: dict[str, Any] | None = None
    ts: float = field(default_factory=time.time)


class DecisionAuditService:
    def __init__(self, *, keep_last: int = 200) -> None:
        self.keep_last = max(1, keep_last)
        self._events: list[DecisionAuditEvent] = []

    def record(self, event: DecisionAuditEvent) -> None:
        self._events.append(event)
        if len(self._events) > self.keep_last:
            self._events = self._events[-self.keep_last :]
        logger.debug('Alisa decision audit: %s', json.dumps(asdict(event), ensure_ascii=False, default=str))

    def recent(self, chat_id: int | None = None) -> list[DecisionAuditEvent]:
        if chat_id is None:
            return list(self._events)
        return [event for event in self._events if event.chat_id == chat_id]
