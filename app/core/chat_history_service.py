from __future__ import annotations

from collections import defaultdict, deque
from typing import Any, Deque


class ChatHistoryService:
    def __init__(self, max_items: int = 20) -> None:
        self.histories: dict[int, Deque[dict[str, Any]]] = defaultdict(lambda: deque(maxlen=max_items))
        self.last_reply_ts: dict[int, float] = defaultdict(lambda: 0.0)

    def remember_message(
        self,
        chat_id: int,
        role: str,
        speaker: str,
        text: str,
        *,
        author_id: int | None = None,
        addressed_to_alisa: bool = False,
        tension_marker: float = 0.0,
    ) -> None:
        value = text.strip()
        if not value:
            return
        self.histories[chat_id].append(
            {
                'role': role,
                'speaker': speaker,
                'text': value[:500],
                'author_id': author_id,
                'addressed_to_alisa': addressed_to_alisa,
                'tension_marker': float(tension_marker),
            }
        )

    def get_history(self, chat_id: int) -> list[dict[str, Any]]:
        return list(self.histories[chat_id])

    def can_reply(self, chat_id: int, now_ts: float, cooldown_sec: float) -> bool:
        return now_ts - self.last_reply_ts[chat_id] >= cooldown_sec

    def mark_reply(self, chat_id: int, now_ts: float) -> None:
        self.last_reply_ts[chat_id] = now_ts
