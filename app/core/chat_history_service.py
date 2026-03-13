from __future__ import annotations

from collections import defaultdict, deque
from typing import Deque


class ChatHistoryService:
    def __init__(self, max_items: int = 20) -> None:
        self.histories: dict[int, Deque[dict[str, str]]] = defaultdict(lambda: deque(maxlen=max_items))
        self.last_reply_ts: dict[int, float] = defaultdict(lambda: 0.0)

    def remember_message(self, chat_id: int, role: str, speaker: str, text: str) -> None:
        value = text.strip()
        if not value:
            return
        self.histories[chat_id].append({'role': role, 'speaker': speaker, 'text': value[:500]})

    def get_history(self, chat_id: int) -> list[dict[str, str]]:
        return list(self.histories[chat_id])

    def can_reply(self, chat_id: int, now_ts: float, cooldown_sec: float) -> bool:
        return now_ts - self.last_reply_ts[chat_id] >= cooldown_sec

    def mark_reply(self, chat_id: int, now_ts: float) -> None:
        self.last_reply_ts[chat_id] = now_ts
